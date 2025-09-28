from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class DepthSide(BaseModel):
    notionalQuote: float
    route: str = "direct"

class Depth(BaseModel):
    pct2: DepthSide
    pct5: DepthSide
    pct10: DepthSide

class VenueReport(BaseModel):
    name: str
    pool: str
    feeBps: int
    tick: int
    sqrtPriceX96: str
    liquidity: str
    tickSpacing: int
    depth: Dict[str, Dict[str, DepthSide]]  # 'up' and 'down' -> DepthSide at pct2, pct5, pct10
    slippageCurve: List[Dict[str, float]]
    cliffs: List[Dict[str, float]]
    activeLiquidityRatio: float
    lpConcentration: Dict[str, float]

class MicrostructureOutput(BaseModel):
    pair: Dict[str, Any]
    blockNumber: int
    venues: List[VenueReport]
    crossVenueSpreadBps: float
    mevExposure: Dict[str, Any]
    microstructure_score: int
    reasons: List[str]

# Convenience helpers
def pretty_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)
