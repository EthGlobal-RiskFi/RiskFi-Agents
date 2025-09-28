"""
Fixed Robinhood MCP Agent for AgentVerse
========================================

This version includes proper configuration based on FetchAI documentation
to ensure the agent is active and discoverable on AgentVerse.

Key fixes:
1. Added mailbox=True for proper AgentVerse integration
2. Removed endpoint configuration (not needed with mailbox)
3. Added fund_agent_if_low for wallet funding
4. Added proper manifest publishing
5. Fixed async issues
"""

import asyncio
import json
import os
from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List, Optional, Tuple, Sequence

from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

# Import MCP components
from pydantic import BaseModel, AnyUrl
from jsonschema import Draft202012Validator, ValidationError
from openai import OpenAI
from mcp import ClientSession, types
from mcp.client.sse import sse_client
from mcp.shared.context import RequestContext
from mcp.shared.exceptions import McpError

# Configuration
AUTH = os.environ.get("AUTH_HEADER", "Bearer GATEWAY_API_KEY")
SUBGRAPH_SSE = "https://subgraphs.mcp.thegraph.com/sse"

"""
Fixed ASI Adapter - Eliminates Double Responses
===============================================

This fixes the issue where both the decision-making and final answer
were being sent to users, causing confusing double responses.
"""



class FixedASIAdapter:
    """Fixed ASI model adapter that only sends final responses"""
    
    def __init__(self):
        base_url = os.environ.get("ASI1_BASE_URL", "https://api.asi1.ai/v1")
        api_key = os.environ.get("ASI1_API_KEY")
        if not api_key:
            raise RuntimeError("Set ASI1_API_KEY in your environment")
        self.model = os.environ.get("ASI1_MODEL", "asi1-mini")
        self.cli = OpenAI(api_key=api_key, base_url=base_url)

    def _chat(self, system: str, user: str, max_tokens: int = 800) -> str:
        resp = self.cli.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            top_p=1.0,
            max_tokens=max_tokens,
            presence_penalty=0,
            frequency_penalty=0,
            stream=False,
            extra_body={"web_search": False},
        )
        return resp.choices[0].message.content

    @staticmethod
    def _ensure_json(text: str) -> Any:
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            if "```" in text:
                block = text.split("```")[1]
                if block.startswith("json"):
                    block = block[len("json"):].lstrip()
                return json.loads(block)
            raise

    @staticmethod
    def _validate_or_error(instance: Any, schema: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        try:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(instance)
            return True, None
        except ValidationError as e:
            path = "/".join(str(p) for p in e.path)
            return False, f"{e.message} at {path}"

    def sample_reply(self, history_messages: Sequence[Any]) -> str:
        lines = []
        for m in history_messages:
            role = getattr(m, "role", "user")
            contents = getattr(m, "content", []) or []
            for c in contents:
                if isinstance(c, types.TextContent):
                    lines.append(f"{role.upper()}: {c.text}")
                elif hasattr(c, "type") and getattr(c, "type") == "text" and hasattr(c, "text"):
                    lines.append(f"{role.upper()}: {c.text}")
        user = "\n".join(lines[-30:])
        system = "Be precise and concise."
        return self._chat(system, user, max_tokens=400)

    def select_action(self, user_query: str, prompts: List[str], resources: List[str], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        """FIXED: Only returns JSON decision, no explanatory text"""
        
        system = (
            "You are a JSON decision maker for blockchain data queries. "
            "Analyze the user query and available tools, then return ONLY a JSON object. "
            "Do NOT include any explanatory text, reasoning, or discussion. "
            "Return ONLY the JSON decision object and nothing else."
        )
        
        menu = {
            "prompts": prompts,
            "resources": resources,
            "tools": [
                {"name": t["name"], "server": t["server"], "description": t.get("description", "")[:300]}
                for t in tools
            ],
        }
        
        user = (
            f"User query: {user_query}\n\n"
            f"Available capabilities: {json.dumps(menu, ensure_ascii=False)}\n\n"
            "Return ONLY JSON with keys: action, name, uri, arguments, reason\n"
            "Action must be one of: call_tool, get_prompt, read_resource\n"
            "Example: {\"action\":\"call_tool\",\"name\":\"search_subgraphs_by_keyword\",\"arguments\":{\"keyword\":\"compound\"}}"
        )
        
        out = self._chat(system, user, max_tokens=200)
        
        # Extract only JSON, ignore any explanatory text
        try:
            decision = self._ensure_json(out)
        except:
            # If JSON parsing fails, try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', out, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group())
            else:
                # Fallback: create a default decision
                decision = {
                    "action": "call_tool",
                    "name": "search_subgraphs_by_keyword",
                    "arguments": {"keyword": ""},
                    "reason": "fallback"
                }
        
        # Validate the decision
        DECISION_SCHEMA = {
            "type": "object",
            "properties": {
                "action": {"enum": ["call_tool","get_prompt","read_resource"]},
                "name": {"type": "string"},
                "uri": {"type": "string"},
                "arguments": {"type": "object"},
                "reason": {"type": "string"}
            },
            "required": ["action"]
        }
        
        ok, err = self._validate_or_error(decision, DECISION_SCHEMA)
        if not ok:
            # If validation fails, create a simple search decision
            decision = {
                "action": "call_tool",
                "name": "search_subgraphs_by_keyword",
                "arguments": {"keyword": user_query.lower().split()[0] if user_query else ""},
                "reason": "validation_repair"
            }
            
        return decision

    def craft_tool_args(self, user_query: str, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Create tool arguments - this should also only return JSON"""
        
        system = (
            "You create JSON arguments for blockchain data tools. "
            "Return ONLY valid JSON that matches the schema. "
            "Do NOT include explanations or reasoning."
        )
        
        schema_str = json.dumps(input_schema, ensure_ascii=False)
        user = (
            f"User query: {user_query}\n"
            f"Required JSON schema: {schema_str}\n"
            "Return ONLY the JSON arguments object."
        )
        
        args_raw = self._chat(system, user, max_tokens=200)
        
        try:
            args = self._ensure_json(args_raw)
        except:
            # Extract JSON or create fallback
            import re
            json_match = re.search(r'\{.*\}', args_raw, re.DOTALL)
            if json_match:
                args = json.loads(json_match.group())
            else:
                # Create smart fallback based on query
                if "keyword" in input_schema.get("properties", {}):
                    # Extract keyword from query
                    words = user_query.lower().split()
                    keyword = ""
                    for word in words:
                        if word in ["compound", "uniswap", "aave", "weth", "usdc", "dai", "ethereum", "polygon"]:
                            keyword = word
                            break
                    args = {"keyword": keyword}
                else:
                    args = {}

        # Validate arguments
        ok, err = self._validate_or_error(args, input_schema)
        if not ok:
            # Create minimal valid arguments
            if "keyword" in input_schema.get("properties", {}):
                args = {"keyword": ""}
            else:
                args = {}
                
        return args

    def final_answer(self, user_query: str, transcript: List[Dict[str, Any]]) -> str:
        """Generate the final user-facing response"""
        
        system = (
            "You are a blockchain and DeFi data assistant. "
            "Provide a clear, helpful response based on the retrieved data. "
            "Be specific and actionable. If data is incomplete, suggest next steps. "
            "Focus on directly answering the user's question."
        )
        
        # Extract the actual data from transcript
        data_summary = ""
        for entry in transcript:
            if entry.get("result"):
                data_summary += f"Retrieved: {entry['result'][:500]}...\n"
        
        user = (
            f"User asked: {user_query}\n\n"
            f"Data retrieved:\n{data_summary}\n\n"
            "Provide a direct, helpful answer to the user's question."
        )
        
        return self._chat(system, user, max_tokens=400)

# Also fix the message handler to ensure only final response is sent
async def handle_message_fixed(ctx: Context, sender: str, msg: ChatMessage):
    """Fixed message handler that only sends the final response"""
    
    # Send acknowledgement
    try:
        await ctx.send(
            sender,
            ChatAcknowledgement(timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id),
        )
    except Exception as e:
        ctx.logger.warning(f"Failed to send acknowledgement: {e}")
    
    # Extract text from message content
    text = ''
    for item in msg.content:
        if isinstance(item, TextContent):
            text += item.text
    
    ctx.logger.info(f"Processing query: {text[:50]}...")
    
    # Process the query using MCP - this should only generate ONE response
    try:
        final_response = await process_blockchain_query(text)
        
        # Send ONLY the final response
        await ctx.send(sender, ChatMessage(
            timestamp=datetime.utcnow(),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=final_response),
                EndSessionContent(type="end-session"),
            ]
        ))
        
        ctx.logger.info("Final response sent successfully")
        
    except Exception as e:
        ctx.logger.error(f"Failed to process query: {e}")
        error_response = "I'm sorry, I encountered an error processing your request. Please try again later."
        
        await ctx.send(sender, ChatMessage(
            timestamp=datetime.utcnow(),
            msg_id=uuid4(),
            content=[
                TextContent(type="text", text=error_response),
                EndSessionContent(type="end-session"),
            ]
        ))

# Usage: Replace your existing ASIAdapter with FixedASIAdapter
# asi_adapter = FixedASIAdapter()

# Usage: Replace your existing ASIAdapter with FixedASIAdapter
# asi_adapter = FixedASIAdapter()

# Global ASI adapter
asi_adapter = FixedASIAdapter()

# Sampling callback for MCP
async def handle_sampling_message(
    context: RequestContext[ClientSession, None],
    params: types.CreateMessageRequestParams
) -> types.CreateMessageResult:
    text = asi_adapter.sample_reply(params.messages)
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text=text),
        model=os.environ.get("ASI1_MODEL", "asi1-mini"),
        stopReason="endTurn",
    )

async def process_blockchain_query(user_query: str) -> str:
    """Process a blockchain/DeFi query using the MCP connection"""
    try:
        # Create fresh MCP connection
        async with sse_client(SUBGRAPH_SSE, headers={"Authorization": AUTH}) as (read, write):
            async with ClientSession(read, write, sampling_callback=handle_sampling_message) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                
                # Get available capabilities
                try:
                    prompts_resp = await session.list_prompts()
                    available_prompts = [p.name for p in prompts_resp.prompts]
                except:
                    available_prompts = []
                
                try:
                    resources_resp = await session.list_resources()
                    available_resources = [str(r.uri) for r in resources_resp.resources]
                except:
                    available_resources = []
                
                try:
                    tools_resp = await session.list_tools()
                    available_tools = []
                    for t in tools_resp.tools:
                        schema = t.inputSchema if t.inputSchema is not None else {"type": "object", "properties": {}}
                        if hasattr(schema, "model_dump"):
                            schema = schema.model_dump()
                        available_tools.append({
                            "server": "sse",
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": schema,
                        })
                except:
                    available_tools = []
                
                if not available_tools and not available_prompts and not available_resources:
                    return "I'm sorry, but I'm currently unable to access blockchain data sources. Please try again later."
                
                # Get decision from ASI
                decision = asi_adapter.select_action(user_query, available_prompts, available_resources, available_tools)
                
                action = decision.get("action")
                name = decision.get("name")
                uri = decision.get("uri")
                args = decision.get("arguments", {}) or {}

                # Normalize action
                ALLOWED = {"call_tool", "get_prompt", "read_resource"}
                if action not in ALLOWED:
                    if any(t["name"] == action for t in available_tools):
                        name = action
                        action = "call_tool"
                    elif name and any(t["name"] == name for t in available_tools):
                        action = "call_tool"
                    elif uri and uri not in available_resources and available_resources:
                        if len(available_resources) == 1 and action == "read_resource":
                            uri = available_resources[0]

                if action == "read_resource" and (not uri or uri not in available_resources) and len(available_resources) == 1:
                    uri = available_resources[0]

                # Execute the action
                transcript = []
                result_text = ""
                
                if action == "get_prompt" and name in available_prompts:
                    prompt = await session.get_prompt(name, arguments=args)
                    if prompt.messages and len(prompt.messages) > 0:
                        message = prompt.messages[0]
                        if hasattr(message, 'content') and message.content and len(message.content) > 0:
                            block = message.content[0]
                            if isinstance(block, types.TextContent):
                                result_text = block.text
                            elif hasattr(block, 'text'):
                                result_text = block.text
                            else:
                                result_text = str(block)
                    transcript.append({"action": "get_prompt", "name": name, "arguments": args, "result": result_text})

                elif action == "read_resource" and uri in available_resources:
                    resource_content = await session.read_resource(AnyUrl(uri))
                    if resource_content.contents:
                        c0 = resource_content.contents[0]
                        if isinstance(c0, types.TextContent):
                            result_text = c0.text
                    transcript.append({"action": "read_resource", "uri": uri, "result": result_text})

                elif action == "call_tool" and any(t["name"] == name for t in available_tools):
                    chosen = next(t for t in available_tools if t["name"] == name)
                    input_schema = chosen.get("inputSchema") or {"type": "object"}
                    
                    # Validate or craft arguments
                    if args:
                        ok, err = asi_adapter._validate_or_error(args, input_schema)
                        if not ok:
                            args = asi_adapter.craft_tool_args(user_query, input_schema)
                    else:
                        args = asi_adapter.craft_tool_args(user_query, input_schema)
                    
                    call_result = await session.call_tool(name, arguments=args)
                    if call_result.structuredContent is not None:
                        result_text = json.dumps(call_result.structuredContent, indent=2)
                    elif call_result.content:
                        block = call_result.content[0]
                        if isinstance(block, types.TextContent):
                            result_text = block.text
                    transcript.append({"action": "call_tool", "name": name, "arguments": args, "result": result_text})
                
                # Generate final answer
                if transcript:
                    return asi_adapter.final_answer(user_query, transcript)
                else:
                    return "I wasn't able to retrieve the requested information. Could you please rephrase your question or try asking about specific blockchain data like token prices, DEX information, or transaction details?"
        
    except Exception as e:
        return f"I encountered an error while processing your request: {str(e)}. Please try again or rephrase your question."

# Create the uagent with proper AgentVerse configuration
agent = Agent(
    name="robinhood_mcp_agent",
    seed="robinhood_blockchain_agent_seed_12345",  # Consistent seed for same address
    port=8000,
    mailbox=True,  # KEY: This enables AgentVerse integration
)

# Fund agent wallet if needed
fund_agent_if_low(agent.wallet.address())

# Create protocol compatible with chat protocol spec
protocol = Protocol(spec=chat_protocol_spec)

@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handle incoming chat messages and respond with blockchain data"""
    
    # Send acknowledgement
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id),
    )
    
    # Extract text from message content
    text = ''
    for item in msg.content:
        if isinstance(item, TextContent):
            text += item.text
    
    ctx.logger.info(f"Processing query: {text[:50]}...")
    
    # Process the query using MCP
    response = await process_blockchain_query(text)
    
    # Send response back to user
    await ctx.send(sender, ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[
            TextContent(type="text", text=response),
            EndSessionContent(type="end-session"),
        ]
    ))

@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle acknowledgements from other agents"""
    ctx.logger.info(f"✅ Message acknowledged by {sender[:16]}...")

# Agent startup handler
@agent.on_event("startup")
async def startup_handler(ctx: Context):
    """Setup agent on startup"""
    ctx.logger.info("🚀 Robinhood MCP Agent starting...")
    ctx.logger.info(f"🤖 Agent address: {agent.address}")
    ctx.logger.info(f"💼 Wallet funded: {agent.wallet.address()}")
    ctx.logger.info(f"📫 Mailbox enabled for AgentVerse integration")
    ctx.logger.info(f"🔍 Find me on AgentVerse: https://agentverse.ai/profile/{agent.address}")
    ctx.logger.info("💬 Ready to answer blockchain and DeFi queries!")

# Attach protocol to agent with manifest publishing
agent.include(protocol, publish_manifest=True)

def main():
    """Main function to run the agent"""
    
    # Check required environment variables
    required_vars = ["ASI1_API_KEY", "AUTH_HEADER"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set the following:")
        print("  export ASI1_API_KEY='your_asi_api_key'")
        print("  export AUTH_HEADER='Bearer your_gateway_api_key'")
        return
    
    print("🚀 Starting Robinhood MCP Agent for AgentVerse...")
    print(f"🤖 Agent address: {agent.address}")
    print("📫 Mailbox configuration enabled")
    print("🔗 Agent will automatically register on AgentVerse")
    print("📊 Supported queries: token data, DEX info, subgraph data, and more")
    print("⏹️  Press Ctrl+C to stop")
    
    # Run the agent
    agent.run()

if __name__ == "__main__":
    main()