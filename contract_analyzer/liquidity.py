from typing import Dict, Any, Optional, List
from web3 import Web3
from config import settings
from abis import UNIV2_FACTORY_ABI, UNIV2_PAIR_ABI, UNIV3_NPM_ABI
from constants import DEAD_ADDRS_DEFAULT

def find_univ2_pair(w3: Web3, token: str, weth: str | None = None, factory: str | None = None) -> Optional[str]:
    factory = factory or settings.UNIV2_FACTORY
    weth = weth or settings.WETH
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(factory), abi=UNIV2_FACTORY_ABI)
        pair = c.functions.getPair(Web3.to_checksum_address(token), Web3.to_checksum_address(weth)).call()
        if int(pair, 16) != 0:
            return Web3.to_checksum_address(pair)
        return None
    except Exception:
        return None

def lp_locked_evidence_v2(w3: Web3, pair: str, known_lockers: List[str], dead_addrs: List[str]) -> Dict[str, Any]:
    c = w3.eth.contract(address=Web3.to_checksum_address(pair), abi=UNIV2_PAIR_ABI)
    total = c.functions.totalSupply().call()
    locker_bal = 0
    dead_bal = 0
    try:
        for a in known_lockers:
            locker_bal += c.functions.balanceOf(Web3.to_checksum_address(a)).call()
        for d in dead_addrs:
            dead_bal += c.functions.balanceOf(Web3.to_checksum_address(d)).call()
    except Exception:
        pass
    locked = locker_bal + dead_bal
    pct_locked = (locked / total * 100.0) if total else 0.0
    return {
        "lpLocked": pct_locked >= 50.0,
        "lockEvidence": {
            "lockerBalance": str(locker_bal),
            "deadAddressBalance": str(dead_bal),
            "pctLocked": round(pct_locked, 4),
        }
    }

def pair_reserves(w3: Web3, pair: str) -> Dict[str, Any]:
    c = w3.eth.contract(address=Web3.to_checksum_address(pair), abi=UNIV2_PAIR_ABI)
    r0, r1, ts = c.functions.getReserves().call()
    t0 = c.functions.token0().call()
    t1 = c.functions.token1().call()
    return {"pair": Web3.to_checksum_address(pair), "token0": t0, "token1": t1, "reserves": {"r0": str(r0), "r1": str(r1)}}

def univ3_positions_sample(w3: Web3, npm_addr: str, token: str) -> List[Dict[str, Any]]:
    """
    Lightweight placeholder: in practice you'd enumerate NFT IDs via events or subgraph.
    Here we return empty (neutral) unless integrated with a subgraph.
    """
    _ = (w3, npm_addr, token)
    return []

def liquidity_overview(w3: Web3, token: str) -> Dict[str, Any]:
    facts = {"dex": None, "pair": None, "lpLocked": False, "lockEvidence": {"locker": None, "deadAddressBalance": "0"}}
    # V2 path
    pair = find_univ2_pair(w3, token)
    if pair:
        facts["dex"] = "UniswapV2Like"
        facts["pair"] = pair
        ev = lp_locked_evidence_v2(
            w3, pair,
            known_lockers=(settings.KNOWN_LOCKERS or []),
            dead_addrs=(settings.DEAD_ADDRESSES or list(DEAD_ADDRS_DEFAULT)))
        facts.update(ev)
        facts.update(pair_reserves(w3, pair))
        return facts
    # V3 path (summarized)
    positions = univ3_positions_sample(w3, settings.UNIV3_POSITION_MANAGER, token)
    if positions:
        facts.update({"dex":"UniswapV3", "positions": positions})
    return facts
