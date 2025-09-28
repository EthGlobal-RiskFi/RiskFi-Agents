from __future__ import annotations
from typing import Dict, Any
from web3 import Web3
from abis import IUniswapV3Pool_ABI, IERC20_MIN_ABI

def get_v3_state(w3: Web3, pool_addr: str) -> Dict[str, Any]:
    pool_addr = Web3.to_checksum_address(pool_addr)
    pool = w3.eth.contract(address=pool_addr, abi=IUniswapV3Pool_ABI)
    sqrtP, tick, *_ = pool.functions.slot0().call()
    L = pool.functions.liquidity().call()
    fee = pool.functions.fee().call()
    ts  = pool.functions.tickSpacing().call()
    t0  = pool.functions.token0().call()
    t1  = pool.functions.token1().call()

    # token metadata
    erc0 = w3.eth.contract(address=t0, abi=IERC20_MIN_ABI)
    erc1 = w3.eth.contract(address=t1, abi=IERC20_MIN_ABI)
    try:
        d0 = erc0.functions.decimals().call()
    except Exception:
        d0 = 18
    try:
        d1 = erc1.functions.decimals().call()
    except Exception:
        d1 = 18
    try:
        sym0 = erc0.functions.symbol().call()
    except Exception:
        sym0 = "T0"
    try:
        sym1 = erc1.functions.symbol().call()
    except Exception:
        sym1 = "T1"

    return {
        "sqrtP": int(sqrtP),
        "tick": int(tick),
        "L": int(L),
        "fee": int(fee),
        "tickSpacing": int(ts),
        "token0": t0,
        "token1": t1,
        "decimals0": int(d0),
        "decimals1": int(d1),
        "symbol0": sym0,
        "symbol1": sym1,
        "blockNumber": int(w3.eth.block_number)
    }
