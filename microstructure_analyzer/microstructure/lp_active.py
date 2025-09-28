from __future__ import annotations
from typing import Dict, List
from collections import defaultdict
from providers_ import GraphQLClient

# Official Uniswap v3 subgraph (The Graph)
QUERY_POSITIONS_UV3 = """
query Positions($pool: String!, $tick: Int!, $first: Int = 1000, $skip: Int = 0) {
  positions(
    where: {
      pool: $pool
      liquidity_gt: 0
      tickLower_: { tickIdx_lte: $tick }
      tickUpper_: { tickIdx_gte: $tick }
    }
    orderBy: liquidity
    orderDirection: desc
    first: $first
    skip: $skip
  ) {
    id
    owner
    liquidity
    tickLower { tickIdx }
    tickUpper { tickIdx }
  }
}
"""


# Common forked schema: poolAddress + flat ticks, BigInt as string
QUERY_POSITIONS_FLAT = """
query Positions($pool: String!, $tick: Int!, $first: Int = 1000, $skip: Int = 0) {
  positions(
    where: {
      poolAddress: $pool,
      tickLower_lte: $tick,
      tickUpper_gte: $tick,
      liquidity_gt: "0"
    }
    orderBy: liquidity
    orderDirection: desc
    first: $first
    skip: $skip
  ) {
    id
    owner
    liquidity
    tickLower
    tickUpper
  }
}
"""

# Minimal fallback (no liquidity_gt filter)
QUERY_POSITIONS_MIN = """
query Positions($pool: String!, $tick: Int!, $first: Int = 1000, $skip: Int = 0) {
  positions(
    where: {
      pool: $pool,
      tickLower_tickIdx_lte: $tick,
      tickUpper_tickIdx_gte: $tick
    }
    orderBy: liquidity
    orderDirection: desc
    first: $first
    skip: $skip
  ) {
    id
    owner
    liquidity
  }
}
"""

def _run_paged(g: GraphQLClient, query: str, vars: Dict) -> List[Dict]:
    out: List[Dict] = []
    skip = 0
    while True:
        raw = g.query(query, {**vars, "first": 1000, "skip": skip})
        data = raw.get("data", raw) if isinstance(raw, dict) else {}
        items = data.get("positions", [])
        if skip == 0 and not items:
            print("GraphQL page0 keys:", list(data.keys()))
            print("Raw sample:", str(raw)[:600])
        if not items:
            break
        out.extend(items)
        if len(items) < 1000:
            break
        skip += 1000
    return out



QUERY_POSITIONS_PROBE = """
query Positions($pool: String!, $first: Int = 5) {
  positions(where: { pool: $pool }, first: $first) {
    id
    owner
    liquidity
  }
}
"""

def _fetch_positions_any(g: GraphQLClient, pool_id_lower: str, tick: int) -> List[Dict]:
    try:
        return _run_paged(g, QUERY_POSITIONS_UV3, {"pool": pool_id_lower, "tick": int(tick)})
    except Exception as e:
        print("UV3 query error:", e)
        return []



def lp_concentration(subgraph_url: str, pool_id_lower: str, current_tick: int) -> Dict[str, float]:
    g = GraphQLClient(subgraph_url)
    pool_id_lower = pool_id_lower.lower()  # ensure lowercase for subgraph

    owners = defaultdict(int)
    total_L = 0

    positions = _fetch_positions_any(g, pool_id_lower, current_tick)

    for p in positions:
      rawL = p.get("liquidity", 0)
      try:
          L = int(rawL)
      except Exception:
          L = int(str(rawL or "0"))
      if L <= 0:
          continue
      owners[p.get("owner","0x0")] += L
      total_L += L


    if total_L == 0 or not owners:
        return {"top1Share": 0.0, "top5Share": 0.0, "hhi": 0.0, "sampledPositions": 0.0}

    values = sorted(owners.values(), reverse=True)
    shares = [v / total_L for v in values]
    top1 = shares[0] if shares else 0.0
    top5 = sum(shares[:5]) if len(shares) >= 5 else sum(shares)
    hhi = sum(s*s for s in shares)

    return {
        "top1Share": float(top1),
        "top5Share": float(top5),
        "hhi": float(hhi),
        "sampledPositions": float(len(values))
    }
