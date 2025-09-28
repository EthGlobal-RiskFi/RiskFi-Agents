"""
Integrated Robinhood MCP Agent with Activation Trigger
======================================================

This version includes both the main agent and the interaction trigger
in a single script for easier management and activation.
"""

import asyncio
import json
import os
import sys
import time
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

class ASIAdapter:
    """ASI model adapter for MCP operations"""
    
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
        system = (
            "You select the best next action for a Model Context Protocol client. "
            "Return STRICT JSON only. "
            'Example: {"action":"call_tool","name":"search_subgraphs_by_keyword","arguments":{"keyword":"WETH"}}'
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
            f"User query:\n{user_query}\n\n"
            f"Capabilities:\n{json.dumps(menu, ensure_ascii=False)}\n\n"
            "Choose exactly one action from: call_tool, get_prompt, read_resource.\n"
            "Respond ONLY as JSON with keys action,name,uri,arguments,reason."
        )
        out = self._chat(system, user, max_tokens=400)
        decision = self._ensure_json(out)
        
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
            repair_user = (
                f"The previous JSON did not validate against the decision schema.\n"
                f"Validation error: {err}\n\n"
                f"User query: {user_query}\n\n"
                f"Available capabilities: {json.dumps(menu, ensure_ascii=False)}\n\n"
                f"Return corrected JSON with action being exactly one of: call_tool, get_prompt, read_resource"
            )
            repair_out = self._chat(system, repair_user, max_tokens=400)
            decision = self._ensure_json(repair_out)
            
        return decision

    def craft_tool_args(self, user_query: str, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "You produce JSON arguments for a tool call. "
            "Return STRICT JSON that validates against the provided JSON Schema."
        )
        schema_str = json.dumps(input_schema, ensure_ascii=False)
        user = (
            f"User query:\n{user_query}\n\n"
            f"Tool inputSchema (JSON Schema):\n{schema_str}\n\n"
            "Return ONLY the JSON arguments object."
        )
        args_raw = self._chat(system, user, max_tokens=500)
        args = self._ensure_json(args_raw)

        ok, err = self._validate_or_error(args, input_schema)
        if ok:
            return args

        repair_user = (
            "The previous JSON did not validate.\n"
            f"Validation error:\n{err}\n\n"
            f"Schema:\n{schema_str}\n\n"
            f"User query:\n{user_query}\n\n"
            "Return corrected JSON arguments only."
        )
        args2_raw = self._chat(system, repair_user, max_tokens=500)
        args2 = self._ensure_json(args2_raw)
        ok2, err2 = self._validate_or_error(args2, input_schema)
        if not ok2:
            raise RuntimeError(f"Arguments still invalid after repair: {err2}")
        return args2

    def final_answer(self, user_query: str, transcript: List[Dict[str, Any]]) -> str:
        system = (
            "You are a helpful blockchain and DeFi assistant. Provide clear, accurate answers "
            "based on the data retrieved. Be concise but informative. If the data shows errors "
            "or incomplete results, acknowledge that and suggest what the user might try instead."
        )
        user = (
            f"User query:\n{user_query}\n\n"
            f"Data retrieved:\n{json.dumps(transcript, ensure_ascii=False)}\n\n"
            "Provide a helpful response based on the retrieved data."
        )
        return self._chat(system, user, max_tokens=500)

# Global ASI adapter
asi_adapter = ASIAdapter()

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

# Create the main Robinhood MCP agent
main_agent = Agent(
    name="robinhood_mcp_agent",
    seed="robinhood_blockchain_agent_seed_12345",
    port=8000,
    mailbox=True,
)

# Fund agent wallet if needed
fund_agent_if_low(main_agent.wallet.address())

# Create protocol compatible with chat protocol spec
main_protocol = Protocol(spec=chat_protocol_spec)

@main_protocol.on_message(ChatMessage)
async def handle_message_with_retry(ctx: Context, sender: str, msg: ChatMessage):
    """Handle incoming chat messages with retry logic"""
    
    max_retries = 3
    retry_delay = 2
    
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
    
    # Process the query using MCP
    try:
        response = await process_blockchain_query(text)
    except Exception as e:
        ctx.logger.error(f"Failed to process query: {e}")
        response = "I'm sorry, I encountered an error processing your request. Please try again later."
    
    # Send response with retry logic
    for attempt in range(max_retries):
        try:
            await ctx.send(sender, ChatMessage(
                timestamp=datetime.utcnow(),
                msg_id=uuid4(),
                content=[
                    TextContent(type="text", text=response),
                    EndSessionContent(type="end-session"),
                ]
            ))
            
            ctx.logger.info(f"Response sent successfully on attempt {attempt + 1}")
            break
            
        except Exception as e:
            ctx.logger.warning(f"Attempt {attempt + 1} failed to send response: {e}")
            
            if attempt < max_retries - 1:
                ctx.logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                ctx.logger.error(f"Failed to send response after {max_retries} attempts")
                break

@main_protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    """Handle acknowledgements from other agents"""
    ctx.logger.debug(f"Message acknowledged by {sender[:16]}...")

# Agent startup handler
@main_agent.on_event("startup")
async def startup_handler(ctx: Context):
    """Setup agent on startup"""
    ctx.logger.info("Robinhood MCP Agent starting...")
    ctx.logger.info(f"Agent address: {main_agent.address}")
    ctx.logger.info(f"Wallet: {main_agent.wallet.address()}")
    ctx.logger.info(f"Mailbox enabled for AgentVerse integration")
    ctx.logger.info(f"AgentVerse profile: https://agentverse.ai/profile/{main_agent.address}")
    ctx.logger.info("Ready to answer blockchain and DeFi queries!")

# Attach protocol to agent
main_agent.include(main_protocol, publish_manifest=True)

# Interaction Trigger Class
class InteractionTrigger:
    def __init__(self, target_agent_address):
        self.target_address = target_agent_address
        self.interactions_sent = 0
        self.responses_received = 0
        
        # Create trigger agent with different port
        self.trigger_agent = Agent(
            name="interaction_trigger",
            seed="trigger_seed_activation_12345",
            port=8001,
            mailbox=True
        )
        
        # Activation queries that trigger search and analytics
        self.activation_queries = [
            "Hello! What can you help me with?",
            "What is WETH token information?",
            "Show me Uniswap V3 data",
            "Get USDC token details",
            "What are the top DeFi protocols?",
        ]
    
    def setup_protocol(self):
        """Setup chat protocol for interaction"""
        protocol = Protocol(spec=chat_protocol_spec)
        
        @protocol.on_message(ChatMessage)
        async def handle_response(ctx: Context, sender: str, msg: ChatMessage):
            """Handle responses from target agent"""
            
            self.responses_received += 1
            
            # Extract response text
            response_text = ''
            for item in msg.content:
                if isinstance(item, TextContent):
                    response_text += item.text
            
            print(f"\nRESPONSE #{self.responses_received}:")
            print(f"{response_text[:150]}...")
            if len(response_text) > 150:
                print(f"   ... (truncated, full length: {len(response_text)} chars)")
            print("-" * 60)
            
            # Send acknowledgement
            await ctx.send(
                sender,
                ChatAcknowledgement(
                    timestamp=datetime.now(), 
                    acknowledged_msg_id=msg.msg_id
                ),
            )
        
        @protocol.on_message(ChatAcknowledgement)
        async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
            """Handle acknowledgements"""
            print(f"Acknowledgement received from {sender[:16]}...")
        
        self.trigger_agent.include(protocol)
    
    async def send_activation_interactions(self, ctx: Context):
        """Send activation interactions to trigger search and analytics"""
        
        print(f"ACTIVATING AGENT SEARCH & ANALYTICS")
        print(f"Target Agent: {self.target_address}")
        print(f"Sending {len(self.activation_queries)} activation queries...")
        print("=" * 60)
        
        for i, query in enumerate(self.activation_queries, 1):
            print(f"\nInteraction {i}/{len(self.activation_queries)}: {query}")
            
            try:
                # Send activation message
                await ctx.send(
                    self.target_address,
                    ChatMessage(
                        timestamp=datetime.utcnow(),
                        msg_id=uuid4(),
                        content=[TextContent(type="text", text=query)]
                    )
                )
                
                self.interactions_sent += 1
                print(f"Sent successfully")
                
                # Wait between interactions
                await asyncio.sleep(3)
                
            except Exception as e:
                print(f"Failed to send interaction {i}: {e}")
        
        print(f"\nACTIVATION SUMMARY:")
        print(f"   Interactions sent: {self.interactions_sent}")
        print(f"   Responses received: {self.responses_received}")
        
        # Wait for remaining responses
        print(f"\nWaiting 15 seconds for remaining responses...")
        await asyncio.sleep(15)
        
        print(f"\nFINAL RESULTS:")
        print(f"   Total sent: {self.interactions_sent}")
        print(f"   Total received: {self.responses_received}")
        print(f"   Success rate: {self.responses_received}/{self.interactions_sent}")
        
        if self.responses_received > 0:
            print(f"\nSUCCESS! Agent is now activated on AgentVerse!")
            print(f"Search and analytics have been triggered")
            print(f"Your agent should appear in AgentVerse search within 5-10 minutes")
        else:
            print(f"\nNo responses received. Check if target agent is running.")
    
    async def run_activation(self):
        """Run the activation process"""
        
        # Setup protocol
        self.setup_protocol()
        
        # Setup startup handler
        @self.trigger_agent.on_event("startup")
        async def startup_handler(ctx: Context):
            print(f"Trigger agent started: {self.trigger_agent.address}")
            print(f"Target agent: {self.target_address}")
            print(f"Mailbox enabled for AgentVerse compatibility")
            
            # Wait for connection, then start activation
            await asyncio.sleep(3)
            await self.send_activation_interactions(ctx)
        
        # Run the trigger agent
        try:
            print("Starting interaction trigger agent...")
            await self.trigger_agent.run_async()
        except KeyboardInterrupt:
            print("\nActivation stopped by user")
        except Exception as e:
            print(f"Activation error: {e}")

def check_environment():
    """Check required environment variables"""
    required_vars = ["ASI1_API_KEY", "AUTH_HEADER"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set the following:")
        print("  export ASI1_API_KEY='your_asi_api_key'")
        print("  export AUTH_HEADER='Bearer your_gateway_api_key'")
        return False
    
    return True

def main():
    """Main function to run agent or trigger"""
    
    if not check_environment():
        return
    
    if len(sys.argv) > 1 and sys.argv[1] == "trigger":
        # Run activation trigger
        target_address = main_agent.address
        if len(sys.argv) > 2:
            target_address = sys.argv[2]
        
        print("AGENTVERSE INTERACTION TRIGGER")
        print("=" * 40)
        print("This will send activation interactions to trigger")
        print("search indexing and analytics on AgentVerse.")
        print("=" * 40)
        print(f"Target agent: {target_address}")
        
        trigger = InteractionTrigger(target_address)
        
        try:
            asyncio.run(trigger.run_activation())
        except Exception as e:
            print(f"Activation failed: {e}")
            return
        
        print("\nACTIVATION COMPLETE!")
        print("Your agent should now be discoverable on AgentVerse")
        print("Search and analytics have been triggered")
        print("Allow 5-10 minutes for full indexing")
        
    else:
        # Run main agent
        print("Starting Robinhood MCP Agent for AgentVerse...")
        print(f"Agent address: {main_agent.address}")
        print("Mailbox configuration enabled")
        print("Agent will automatically register on AgentVerse")
        print("Supported queries: token data, DEX info, subgraph data, and more")
        print("Press Ctrl+C to stop")
        print("")
        print("To activate search and analytics, run:")
        print(f"python {sys.argv[0]} trigger")
        
        # Run the main agent
        main_agent.run()

if __name__ == "__main__":
    main()