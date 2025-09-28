from typing import Dict, Any
from web3 import Web3
from constants import SAFE_FUNC_SIGS

SAFE_ABI = [
  {"type":"function","name":"getOwners","inputs":[],"outputs":[{"type":"address[]"}],"stateMutability":"view"},
  {"type":"function","name":"getThreshold","inputs":[],"outputs":[{"type":"uint256"}],"stateMutability":"view"},
]

def detect_safe(w3: Web3, addr: str) -> Dict[str, Any]:
    out = {"isSafe": False, "threshold": None, "owners": None}
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(addr)).hex()
        if all(sig[2:] in code for sig in SAFE_FUNC_SIGS):  # simple fingerprint
            c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=SAFE_ABI)
            try:
                owners = c.functions.getOwners().call()
                threshold = c.functions.getThreshold().call()
                out.update({"isSafe": True, "threshold": int(threshold), "owners": len(owners)})
            except Exception:
                out.update({"isSafe": True})
    except Exception:
        pass
    return out
