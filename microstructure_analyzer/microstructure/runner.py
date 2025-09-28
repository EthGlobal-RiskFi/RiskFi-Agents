from __future__ import annotations
import argparse, json
from decimal import Decimal
from typing import Any, Dict, List, Optional
from rich import print as rprint
from web3 import Web3
import sys
from providers_ import get_web3
from discover import find_candidate_pools
from v3_state import get_v3_state
from v3_ticks import fetch_initialized_ticks
from v3_swapmath import notional_for_pct_moves, slippage_curve_for_quote_in
from cliffs import detect_liquidity_cliffs, active_liquidity_ratio
from lp_active import lp_concentration
from spreads import cross_venue_spread_bps
from mev_proxy import mev_exposure_proxy
from score import microstructure_score
from schema import MicrostructureOutput, VenueReport
from math_utils import sqrtX96_to_unscaled_sqrt
from reason_generator import generate_microstructure_reasons, generate_summary_insight

from web3.exceptions import BadFunctionCallOutput, ContractLogicError

ERC20_ABI_MIN = [
    {"constant":True,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"},
    {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"},
    {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
]

def get_token_meta(w3: Web3, addr: str) -> Dict[str, Any]:
    c = w3.eth.contract(address=addr, abi=ERC20_ABI_MIN)
    meta = {"address": addr, "name": None, "symbol": None, "decimals": None}
    try:
        meta["name"] = c.functions.name().call()
    except (BadFunctionCallOutput, ContractLogicError, ValueError):
        pass
    try:
        meta["symbol"] = c.functions.symbol().call()
    except (BadFunctionCallOutput, ContractLogicError, ValueError):
        pass
    try:
        meta["decimals"] = c.functions.decimals().call()
    except (BadFunctionCallOutput, ContractLogicError, ValueError):
        pass
    return meta



try:
    sys.stdout.reconfigure(encoding="utf-8")  # Py3.7+
except Exception:
    pass

# exportable object for reuse elsewhere
LAST_MICROSTRUCTURE_RESULT: Optional[Dict[str, Any]] = None

def get_last_microstructure_result() -> Optional[Dict[str, Any]]:
    """Returns the last augmented analyzer result dict, or None if not run yet."""
    return LAST_MICROSTRUCTURE_RESULT

__all__ = ["LAST_MICROSTRUCTURE_RESULT", "get_last_microstructure_result"]



# --- Fetch.ai / ASI:One thesis generator -------------------------------------
import os, uuid, json, textwrap, requests
from typing import Dict, Any

ASI_ONE_URL = "https://api.asi1.ai/v1/chat/completions"  # ASI:One chat completions endpoint

def _default_thesis_stub(payload: Dict[str, Any]) -> str:
    """Deterministic fallback when ASI:One is unavailable."""
    # Resolve human names
    pair = payload.get("pair", {})
    tmeta = payload.get("tokenMeta", {})
    bm = tmeta.get("base", {}) or {}
    qm = tmeta.get("quote", {}) or {}
    base_name = bm.get("name") or bm.get("symbol") or pair.get("base") or "BASE"
    quote_name = qm.get("name") or qm.get("symbol") or pair.get("quote") or "QUOTE"

    v = (payload.get("venues") or [{}])[0]
    depth = v.get("depth", {}) or {}
    up, down = depth.get("up", {}) or {}, depth.get("down", {}) or {}
    a_lr = v.get("activeLiquidityRatio")
    conc = v.get("lpConcentration", {}) or {}
    hhi = conc.get("hhi")
    top1 = conc.get("top1Share")
    reasons = payload.get("reasons", []) or []
    mev = payload.get("mevExposure", {}) or {}
    score = payload.get("microstructure_score")

    parts = []
    print("DEFAULT")
    parts.append(
        f"Microstructure thesis for {base_name} priced in {quote_name} @ block {payload.get('blockNumber')}."
    )
    parts.append(
        f"Overall microstructure score is {score}/100 with cross-venue spread near {payload.get('crossVenueSpreadBps', 0)} bps."
    )
    if a_lr is not None:
        parts.append(f"Active liquidity near touch is {a_lr:.2%}, implying sensitivity to order flow and price jumps.")
    if up.get("pct5"):
        parts.append(
            f"Depth up 5% ≈ ${up['pct5'].get('notionalQuote', 0):.0f}; "
            f"down 5% ≈ ${down.get('pct5', {}).get('notionalQuote', 0):.0f} — thin on both sides."
        )
    if hhi is not None and top1 is not None:
        parts.append(f"LP concentration is moderate (HHI {hhi:.3f}; top-1 share {top1:.1%}), reducing single-LP manipulation risk but not eliminating it.")
    if mev:
        parts.append(f"MEV exposure {mev.get('score')} with evidence {json.dumps(mev.get('evidence', {}))}.")
    if v.get("cliffs"):
        c = v["cliffs"][0]
        parts.append(f"Nearest liquidity cliff around tick {int(c['tick'])}: delta-L ratio {float(c['deltaLRatio']):.2e}.")
    if reasons:
        parts.append("Key observations: " + " ".join(reasons))
    parts.append("Actionable: use smaller clips, widen price protection, and re-quote more frequently until active liquidity thickens.")
    return " ".join(parts)


def generate_market_microstructure_thesis(payload: Dict[str, Any], model: str = "asi1-fast", temperature: float = 0.2, max_tokens: int = 8000) -> str:
    """
    Calls Fetch.ai's ASI:One chat-completions API to produce a thesis from the analyzer JSON.
    Falls back to a deterministic template if API key is missing or the request fails.
    """
    api_key = "sk_a2bfc9202dbe4f31bd7baa4c78a6aeb061a984ed8b17410d9f5a6898cca9e16c"
    if not api_key:
        return _default_thesis_stub(payload)

    # Build a crisp prompt; keep it grounded in the provided JSON only.
    system = (
        "You are a DeFi market microstructure analyst. "
        "Write a detailed, objective thesis using ONLY the provided JSON fields. "
        "Cover: depth up/down at 2%/5%/10%, liquidity cliffs, slippage curve, activeLiquidityRatio, "
        "LP concentration shares and HHI, MEV exposure, crossVenueSpreadBps, and the overall score. "
        "Avoid price predictions. No numbers not derivable from the input. "
        "Return plain paragraphs, 600-700 words."
    )
    user = textwrap.dedent(f"""
        INPUT_JSON:
        {json.dumps(payload, separators=(',', ':'))}
    """).strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-session-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    body = {
        "model": model,            # e.g., "asi1-mini", "asi1-fast", "asi1-extended"
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    try:
        resp = requests.post(ASI_ONE_URL, headers=headers, json=body, timeout=60)
        if resp.status_code == 401:
            print("[ASI:One] 401 Unauthorized. Response:", resp.text)

        resp.raise_for_status()
        data = resp.json()
        # OpenAI-style response shape
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        # Log and use a deterministic fallback to keep the pipeline unblocked
        print(f"[ASI:One] thesis generation failed: {e}")
        return _default_thesis_stub(payload)
# --- end thesis generator -----------------------------------------------------




def main():
    ap = argparse.ArgumentParser(description="Market Microstructure Analyzer (Uniswap v3 first)")
    ap.add_argument("--rpc", required=True, help="EVM RPC URL")
    ap.add_argument("--chain-id", type=int, required=True)
    ap.add_argument("--subgraph", required=True, help="Uniswap v3 subgraph URL for the chain")
    ap.add_argument("--base", required=True, help="Base token address (checksummed or lowercased)")
    ap.add_argument("--quote", required=True, help="Quote token address (prefer USDC or WETH)")
    ap.add_argument("--venues", nargs="+", default=["UniswapV3"], help="Venues to analyze (currently UniswapV3)")
    ap.add_argument("--pct-window", type=float, default=0.10, help="Percent window for ticks (e.g. 0.10 for 10%%)")
    ap.add_argument("--trade-sizes", nargs="*", type=float, default=[1000, 5000, 10000, 25000, 50000, 100000])
    args = ap.parse_args()

    w3 = get_web3(args.rpc, args.chain_id)

    base_raw  = args.base
    quote_raw = args.quote

    try:
        base_checksum  = Web3.to_checksum_address(base_raw)
        quote_checksum = Web3.to_checksum_address(quote_raw)
    except ValueError:
        raise SystemExit(f"Invalid address: base={base_raw} quote={quote_raw}")
    
    base_meta  = get_token_meta(w3, base_checksum)
    quote_meta = get_token_meta(w3, quote_checksum)


    # 1) Pool discovery
    pools = find_candidate_pools(args.subgraph, base_checksum, quote_checksum, limit=10)
    if not pools:
        raise SystemExit("No pools found for the given pair on Uniswap v3 subgraph.")
    # prefer fee tiers 500, 3000, 10000
    preferred = [500, 3000, 10000]
    pools = sorted(pools, key=lambda p: (preferred.index(p['feeTier']) if p['feeTier'] in preferred else 999, -p['volumeUSD']))
    best_pool = pools[0]
    pool_id_subgraph = best_pool["id"]                  # lowercased (for subgraph)
    pool_addr = Web3.to_checksum_address(pool_id_subgraph) 

    # 2) Core pool state (on-chain)
    state = get_v3_state(w3, pool_addr)

    # 3) Tick window (via subgraph). Use a window of +/- ~3000 ticks or +-pct-window in price terms. We choose fixed tick window here.
    window = 3000
    ticks = fetch_initialized_ticks(args.subgraph, pool_addr, state['tick'] - window, state['tick'] + window)

    ticks = [{"tick": int(t["tick"]),
          "liquidityNet": int(t.get("liquidityNet", 0)),
          "liquidityGross": int(t.get("liquidityGross", 0))} for t in ticks]

    if not ticks:
        # Fallback for ultra-sparse pools
        ticks = [{"tick": state["tick"], "liquidityNet": 0, "liquidityGross": 0}]

    # 4) Depth to 2, 5, 10 percent moves (compute in raw units first)
    depths_raw = notional_for_pct_moves(state['sqrtP'], state['tick'], state['L'], ticks, fee_bps=state['fee'])
    # Convert 'up' (token1 in) already in quote units (raw). Scale to human using token1 decimals.
    scale1 = 10 ** state['decimals1']
    scale0 = 10 ** state['decimals0']
    depths_quote = {"up": {}, "down": {}}
    for k, v in depths_raw["up"].items():
        depths_quote["up"][k] = float(v / scale1)
    for k, v in depths_raw["down"].items():
        # down move input is token0 amount; convert to quote notional using mid price approximation
        S = sqrtX96_to_unscaled_sqrt(state['sqrtP'])
        P = float((S*S)) * (10 ** (state['decimals0'] - state['decimals1']))
        token0_in = v / scale0  # in base human units
        depths_quote["down"][k] = float(token0_in * P)

    # 5) Slippage curve (quote->base)
    trade_sizes_raw = [size * (10 ** state['decimals1']) for size in args.trade_sizes]
    slippage_raw = slippage_curve_for_quote_in(state['sqrtP'], state['tick'], state['L'], ticks, trade_sizes_raw, fee_bps=state['fee'])
    slippage = [{"notionalQuote": s['notionalQuote'] / (10 ** state['decimals1']), "slippagePct": s['slippagePct']} for s in slippage_raw]

    # 6) Cliffs + Active liquidity ratio
    cliffs = detect_liquidity_cliffs(ticks, state['tick'], window_ticks=200)
    max_deltaL_ratio_near = max([c['deltaLRatio'] for c in cliffs], default=0.0)
    cliff_within_100 = any(abs(c['tick'] - state['tick']) <= 100 for c in cliffs)
    alr = active_liquidity_ratio(ticks, state['tick'], state['L'], band_ticks=600)

    # 7) LP concentration
    lpc = lp_concentration(args.subgraph, pool_id_subgraph, state['tick'])

    # 8) Cross-venue spread (only Uniswap v3 mids available here; users can extend)
    spread_bps = 0.0  # extend with more venues for a real spread

    # 9) MEV proxy
    depth_up_5 = depths_quote["up"].get("pct5", 0.0)
    mev = mev_exposure_proxy(depth_up_5, slippage)
    badge = mev["evidence"]["sandwichDensity"]

    # Score
    score = microstructure_score(
        depth_up_5=depths_quote["up"].get("pct5", 0.0),
        depth_down_5_quote=depths_quote["down"].get("pct5", 0.0),
        depth_up_10=depths_quote["up"].get("pct10", 0.0),
        depth_down_10=depths_quote["down"].get("pct10", 0.0),
        max_deltaL_ratio_near=max_deltaL_ratio_near,
        cliff_within_100=cliff_within_100,
        active_liq_ratio=alr,
        top1_share=lpc.get("top1Share", 0.0),
        top5_share=lpc.get("top5Share", 0.0),
        hhi=lpc.get("hhi", 0.0),
        cross_spread_bps=spread_bps,
        mev_badge=badge
    )

    # Generate intelligent reasons based on the analysis
    reasons = generate_microstructure_reasons(
        depth_up=depths_quote["up"],
        depth_down=depths_quote["down"],
        slippage_curve=slippage,
        cliffs=cliffs,
        active_liq_ratio=alr,
        lp_concentration=lpc,
        cross_spread_bps=spread_bps,
        mev_exposure=mev,
        score=score
    )
    
    # Optionally, add a summary insight
    summary = generate_summary_insight(
        score=score,
        depth_up_5=depths_quote["up"].get("pct5", 0.0),
        active_liq_ratio=alr,
        top1_share=lpc.get("top1Share", 0.0),
        mev_badge=badge
    )

    # Build VenueReport
    venue = VenueReport(
        name="UniswapV3",
        pool=pool_addr,
        feeBps=state["fee"],
        tick=state["tick"],
        sqrtPriceX96=str(state["sqrtP"]),
        liquidity=str(state["L"]),
        tickSpacing=state["tickSpacing"],
        depth={
            "up": {k: {"notionalQuote": v, "route": "direct"} for k, v in depths_quote["up"].items()},
            "down": {k: {"notionalQuote": v, "route": "direct"} for k, v in depths_quote["down"].items()}
        },
        slippageCurve=slippage,
        cliffs=cliffs,
        activeLiquidityRatio=alr,
        lpConcentration=lpc
    )

    output = MicrostructureOutput(
        pair={"base": base_checksum, "quote": quote_checksum, "chainId": args.chain_id},
        blockNumber=state["blockNumber"],
        venues=[venue],
        crossVenueSpreadBps=spread_bps,
        mevExposure=mev,
        microstructure_score=score,
        reasons=reasons  # Now using intelligent, dynamic reasons
    )


    def _fallback_thesis(d: Dict[str, Any]) -> str:
        v = (d.get("venues") or [{}])[0]
        depth = v.get("depth", {})
        up5 = ((depth.get("up") or {}).get("pct5") or {}).get("notionalQuote", 0)
        down5 = ((depth.get("down") or {}).get("pct5") or {}).get("notionalQuote", 0)
        alr = v.get("activeLiquidityRatio", 0)
        conc = v.get("lpConcentration", {}) or {}
        top1 = conc.get("top1Share", 0)
        hhi = conc.get("hhi", 0)
        reasons = d.get("reasons", [])
        parts = [
            f"Microstructure score {d.get('microstructure_score')}/100 with spread {d.get('crossVenueSpreadBps', 0)} bps.",
            f"Active liquidity near touch {alr:.2%}.",
            f"Depth at ±5% moves ≈ ${up5:,.0f} up and ${down5:,.0f} down.",
            f"LP concentration moderate. Top-1 {top1:.1%}, HHI {hhi:.3f}.",
        ]
        if v.get("cliffs"):
            c0 = v["cliffs"][0]
            parts.append(f"Nearest liquidity cliff tick {int(c0['tick'])} with ΔL ratio {float(c0['deltaLRatio']):.2e}.")
        if reasons:
            parts.append("Key notes: " + " ".join(reasons))
        parts.append("Trade smaller clips and use tighter protections until depth thickens.")
        return " ".join(parts)


    # Print with summary if desired
        # Print with summary if desired
    print(f"\n📊 Summary: {summary}\n")

    # Build a plain dict and inject thesis without changing Pydantic models
    out_dict = output.model_dump()
    out_dict.setdefault("tokenMeta", {"base": base_meta, "quote": quote_meta})

    # Try to call your Fetch.ai helper if you added it; otherwise use fallback
    try:
        thesis = generate_market_microstructure_thesis(out_dict)  # noqa: F821 if not defined
    except NameError:
        thesis = _fallback_thesis(out_dict)
    except Exception as e:
        print(f"[thesis] generation error: {e}")
        thesis = _fallback_thesis(out_dict)

    out_dict["market_microstructure_thesis"] = thesis

    # Save as an importable object for other modules
    global LAST_MICROSTRUCTURE_RESULT
    LAST_MICROSTRUCTURE_RESULT = out_dict

    # Pretty prints using the augmented dict
    rprint(out_dict)
    print(json.dumps(out_dict, indent=2, ensure_ascii=False))



if __name__ == "__main__":
    main()
