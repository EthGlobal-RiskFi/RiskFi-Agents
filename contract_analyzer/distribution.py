from typing import Any, Dict, List, Tuple, Optional
from config import settings
import requests

def _etherscan_top_holders(addr: str, chain_id: int, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
    """
    Uses Etherscan-like token holder list when available.
    NOTE: Some endpoints are PRO-only; we degrade gracefully.
    """
    base = settings.EXPLORERS.get(chain_id)
    key  = settings.EXPLORER_API_KEYS.get(chain_id, "")
    if not base or not key:
        return None
    # Attempt common patterns; you can swap if your plan supports a specific endpoint.
    # Fallback: 'tokenholderlist' (if available on your plan).
    try:
        r = requests.get(base, params={
            "module":"token","action":"tokenholderlist","contractaddress":addr,"page":1,"offset":limit,"apikey":key
        }, timeout=20)
        j = r.json()
        if j.get("status") == "1":
            holders = j.get("result", [])
            out = []
            for h in holders[:limit]:
                out.append({"address": h.get("HolderAddress"), "balance": int(h.get("TokenHolderQuantity","0"))})
            return out
    except Exception:
        return None
    return None

def compute_top_holder_stats(total_supply: int, holders: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    stats: List[Dict[str, Any]] = []
    total = float(total_supply) if total_supply else 0.0
    for h in holders:
        bal = float(h.get("balance", 0))
        pct = (bal / total * 100.0) if total > 0 else 0.0
        stats.append({"address": h["address"], "pct": round(pct, 4)})
    stats_sorted = sorted(stats, key=lambda x: x["pct"], reverse=True)
    agg = {
        "top1": stats_sorted[0]["pct"] if stats_sorted else 0.0,
        "top3": sum(x["pct"] for x in stats_sorted[:3]),
        "top10": sum(x["pct"] for x in stats_sorted[:10]),
    }
    return stats_sorted, agg

def top_holders(addr: str, chain_id: int, total_supply: int) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    holders = _etherscan_top_holders(addr, chain_id, limit=20) or []
    return compute_top_holder_stats(total_supply, holders)
