from typing import Any, Optional, Tuple
from web3 import Web3
import hashlib, requests
from config import settings
from abis import ERC20_MINIMAL_ABI

from eth_abi import decode as abi_decode

def erc20_total_supply_raw(w3: Web3, address: str) -> int | None:
    # 0x18160ddd = totalSupply()
    data = "0x18160ddd"
    try:
        res = w3.eth.call({"to": Web3.to_checksum_address(address), "data": data}, "latest")
        if res and len(res) >= 66:
            # uint256
            return int(res, 16)
    except Exception:
        return None
    return None


def get_w3(rpc_url: Optional[str] = None) -> Web3:
    url = rpc_url or settings.RPC_URL
    if not url:
        raise RuntimeError("RPC_URL not configured")
    return Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))

def get_block_number(w3: Web3) -> int:
    return w3.eth.block_number

def get_code(w3: Web3, addr: str) -> bytes:
    return w3.eth.get_code(Web3.to_checksum_address(addr))

def bytecode_hash(code: bytes) -> str:
    return hashlib.sha256(code).hexdigest()

def etherscan_get(chain_id: int, params: dict) -> Optional[dict]:
    base = settings.EXPLORERS.get(chain_id)
    key  = settings.EXPLORER_API_KEYS.get(chain_id, "")
    if not base or not key:
        return None
    p = params.copy()
    p["apikey"] = key
    try:
        r = requests.get(base, params=p, timeout=20)
        r.raise_for_status()
        j = r.json()
        return j
    except Exception:
        return None

def get_verified_abi(addr: str, chain_id: int) -> Optional[list]:
    j = etherscan_get(chain_id, {"module":"contract","action":"getabi","address":addr})
    if j and j.get("status") == "1":
        import json
        try:
            return json.loads(j["result"])
        except Exception:
            return None
    return None

def get_verified_source(addr: str, chain_id: int) -> Optional[str]:
    j = etherscan_get(chain_id, {"module":"contract","action":"getsourcecode","address":addr})
    if j and j.get("status") == "1" and j.get("result"):
        res = j["result"][0]
        # "SourceCode" may be flattened or metadata JSON; return raw for keyword scans
        return res.get("SourceCode") or None
    return None

def get_contract(w3: Web3, address: str, abi: Optional[list]) -> Any:
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi or ERC20_MINIMAL_ABI)

def minimal_abi() -> list:
    return ERC20_MINIMAL_ABI
