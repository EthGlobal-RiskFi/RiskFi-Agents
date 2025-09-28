# discover.py
from typing import List, Dict, Any
from providers_ import GraphQLClient

def find_candidate_pools(subgraph_url: str, base: str, quote: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find Uniswap v3 pools for the given token pair.
    """
    g = GraphQLClient(subgraph_url)
    
    # Updated query - removed tickSpacing since it's not in all subgraphs
    QUERY_POOLS = """
    query FindPools($tokenA: String!, $tokenB: String!, $first: Int!) {
        pools(
            first: $first
            orderBy: totalValueLockedUSD
            orderDirection: desc
            where: {
                or: [
                    {token0: $tokenA, token1: $tokenB},
                    {token0: $tokenB, token1: $tokenA}
                ]
            }
        ) {
            id
            feeTier
            totalValueLockedUSD
            volumeUSD
            token0 {
                id
                symbol
                decimals
            }
            token1 {
                id
                symbol
                decimals
            }
        }
    }
    """
    
    try:
        data = g.query(QUERY_POOLS, {"tokenA": base.lower(), "tokenB": quote.lower(), "first": limit})
        pools = data.get("pools", [])
        
        # Ensure consistent structure
        for pool in pools:
            # Convert feeTier to int if it's a string
            if isinstance(pool.get('feeTier'), str):
                pool['feeTier'] = int(pool['feeTier'])
            # Ensure volumeUSD is a float
            if pool.get('volumeUSD'):
                pool['volumeUSD'] = float(pool['volumeUSD'])
            if pool.get('totalValueLockedUSD'):
                pool['totalValueLockedUSD'] = float(pool['totalValueLockedUSD'])
                
        return pools
        
    except Exception as e:
        print(f"Error with primary query: {e}")
        # Fallback to simpler query
        SIMPLE_QUERY = """
        query {
            pools(
                first: %d
                orderBy: totalValueLockedUSD
                orderDirection: desc
            ) {
                id
                feeTier
                totalValueLockedUSD
                volumeUSD
            }
        }
        """ % limit
        
        try:
            data = g.query(SIMPLE_QUERY)
            pools = data.get("pools", [])
            # Filter for our token pair
            filtered = []
            for pool in pools:
                pool_id = pool['id'].lower()
                if base.lower() in pool_id and quote.lower() in pool_id:
                    filtered.append(pool)
            return filtered[:limit]
        except Exception as e2:
            print(f"Fallback query also failed: {e2}")
            return []