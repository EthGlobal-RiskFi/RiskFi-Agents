# v3_ticks.py
from typing import List, Dict, Any
from providers_ import GraphQLClient

def fetch_initialized_ticks(subgraph_url: str, pool_id: str, tick_lower: int, tick_upper: int) -> List[Dict[str, Any]]:
    """
    Fetch initialized ticks in the given range for a Uniswap v3 pool.
    """
    g = GraphQLClient(subgraph_url)
    
    # Try different query formats based on subgraph version
    QUERY_TICKS = """
    query GetTicks($pool: String!, $tickLower: Int!, $tickUpper: Int!) {
        ticks(
            first: 1000
            where: {
                pool: $pool
                tickIdx_gte: $tickLower
                tickIdx_lte: $tickUpper
            }
            orderBy: tickIdx
        ) {
            tickIdx
            liquidityNet
            liquidityGross
        }
    }
    """
    
    try:
        data = g.query(QUERY_TICKS, {
            "pool": pool_id.lower(),
            "tickLower": tick_lower,
            "tickUpper": tick_upper
        })
        ticks = data.get("ticks", [])
        
        # Normalize field names
        for tick in ticks:
            if 'tickIdx' in tick and 'tick' not in tick:
                tick['tick'] = tick['tickIdx']
            if 'liquidityNet' in tick:
                tick['liquidityNet'] = int(tick['liquidityNet'])
                
        return ticks
        
    except Exception as e:
        print(f"Primary tick query failed: {e}")
        
        # Try alternative field name
        ALT_QUERY = """
        query GetTicks($pool: String!, $tickLower: Int!, $tickUpper: Int!) {
            ticks(
                first: 1000
                where: {
                    poolAddress: $pool
                    tick_gte: $tickLower
                    tick_lte: $tickUpper
                }
                orderBy: tick
            ) {
                tick
                liquidityNet
                liquidityGross
            }
        }
        """
        
        try:
            data = g.query(ALT_QUERY, {
                "pool": pool_id.lower(),
                "tickLower": tick_lower,
                "tickUpper": tick_upper
            })
            ticks = data.get("ticks", [])
            
            # Ensure consistent naming
            for tick in ticks:
                if 'tick' in tick and 'tickIdx' not in tick:
                    tick['tickIdx'] = tick['tick']
                if 'liquidityNet' in tick:
                    tick['liquidityNet'] = int(tick['liquidityNet'])
                    
            return ticks
            
        except Exception as e2:
            print(f"Alternative tick query also failed: {e2}")
            return []