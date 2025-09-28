from __future__ import annotations
from typing import List, Dict
from decimal import Decimal
from math_utils import to_float

def cross_venue_spread_bps(mids: List[Decimal]) -> float:
    """Compute (max - min) / median * 1e4 in bps."""
    if not mids or len(mids) == 1:
        return 0.0
    mids_sorted = sorted(mids)
    mn = mids_sorted[0]
    mx = mids_sorted[-1]
    med = mids_sorted[len(mids)//2]
    spread = (mx - mn) / med * Decimal(10000)
    return to_float(spread)
