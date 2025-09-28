from typing import Dict, Any, List
from web3 import Web3
from abis import ERC20_MINIMAL_ABI

def _self_transfer_check(w3: Web3, token: str, from_addr: str) -> bool:
    """
    Non-invasive heuristic: staticcall transfer(from -> from, 0). If this reverts with custom error strongly,
    we note it. In practice, selling uses router; this is only a weak hint.
    """
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_MINIMAL_ABI)
        # eth_call (no state change); 'from' must be set in call params for some tokens with msg.sender guards
        data = c.functions.transfer(from_addr, 0).build_transaction({"from": from_addr})["data"]
        res = w3.eth.call({"to": token, "data": data}, "latest")
        return True if res else True
    except Exception:
        return False

def assess_honeypot(w3, token, privilege_hits):
    hints, methods = [], []

    if privilege_hits.get("blacklistPrimitives"):
        hints.append("blacklistPresent")
    if privilege_hits.get("taxPrimitives"):
        hints.append("feeOnTransferPrimitives")
        methods.append("feeOnTransferHeuristic")
    if privilege_hits.get("tradingPrimitives"):
        hints.append("tradingTogglePresent")

    ok = _self_transfer_check(w3, token, from_addr="0x0000000000000000000000000000000000000001")
    if not ok:
        # Record only as weak signal
        hints.append("transferRevertHeuristic")

    # Risk: require at least one hard primitive
    if "blacklistPresent" in hints or "feeOnTransferPrimitives" in hints or "tradingTogglePresent" in hints:
        risk = "medium"
        if ("blacklistPresent" in hints and "tradingTogglePresent" in hints):
            risk = "high"
    else:
        risk = "low"

    return {"risk": risk, "methods": methods or ["heuristics"], "notes": ", ".join(hints) if hints else "no strong red flags"}

