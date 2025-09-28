from web3 import Web3
from typing import Optional
from constants import ZERO_ADDR

def to_checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)

def is_zero_address(addr: str | None) -> bool:
    if not addr:
        return True
    try:
        return to_checksum(addr) == Web3.to_checksum_address(ZERO_ADDR)
    except Exception:
        return False

def bytes32_to_address(b: bytes) -> str:
    # Take the right-most 20 bytes
    if len(b) < 20:
        return ZERO_ADDR
    out = "0x" + b[-20:].hex()
    try:
        return to_checksum(out)
    except Exception:
        return out

def safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        return default

def label_from_pct(pct: int) -> str:
    if pct >= 70:
        return "Green"
    if pct >= 40:
        return "Yellow"
    return "Red"

def gini_from_weights(weights: list[float]) -> Optional[float]:
    if not weights:
        return None
    s = sum(weights)
    if s == 0:
        return 0.0
    x = sorted([w/s for w in weights])
    n = len(x)
    cum = 0.0
    for i, xi in enumerate(x, start=1):
        cum += i * xi
    return (2 * cum) / (n + 1) - 1
