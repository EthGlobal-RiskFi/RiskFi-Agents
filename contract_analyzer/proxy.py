from typing import Dict, Any
from web3 import Web3
from constants import EIP1967_IMPL_SLOT, EIP1967_ADMIN_SLOT
from utils import bytes32_to_address, is_zero_address

IMPL_ABI = [{"type":"function","name":"implementation","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"}]
ADMIN_ABI = [{"type":"function","name":"admin","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"}]
BEACON_ABI = [{"type":"function","name":"beacon","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"}]
BEACON_IMPL_ABI = [{"type":"function","name":"implementation","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view"}]

def _get_storage_at(w3: Web3, addr: str, slot: int) -> bytes:
    return w3.eth.get_storage_at(Web3.to_checksum_address(addr), slot)

def _try_call(w3: Web3, addr: str, abi: list, fn: str) -> str | None:
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)
        out = c.functions[fn]().call()
        if isinstance(out, str) and out != "0x0000000000000000000000000000000000000000":
            return Web3.to_checksum_address(out)
    except Exception:
        pass
    return None

def detect_proxy(w3: Web3, token: str) -> Dict[str, Any]:
    # 1) EIP-1967 slots
    impl = bytes32_to_address(_get_storage_at(w3, token, EIP1967_IMPL_SLOT))
    admin = bytes32_to_address(_get_storage_at(w3, token, EIP1967_ADMIN_SLOT))
    if not is_zero_address(impl):
        proxy_type = "EIP1967"
        # UUPS probe
        try:
            impl_c = w3.eth.contract(address=impl, abi=[{
                "type":"function","name":"proxiableUUID","stateMutability":"view",
                "inputs":[],"outputs":[{"type":"bytes32"}]}])
            _ = impl_c.functions.proxiableUUID().call()
            proxy_type = "UUPS"
        except Exception:
            if not is_zero_address(admin):
                proxy_type = "Transparent"
        return {"type": proxy_type, "implementation": impl, "admin": admin}

    # 2) Function probes (FiatTokenProxy style)
    impl2 = _try_call(w3, token, IMPL_ABI, "implementation")
    admin2 = _try_call(w3, token, ADMIN_ABI, "admin")
    if impl2:
        return {"type": "ProxyLike", "implementation": impl2, "admin": admin2}

    # 3) Beacon proxy: proxy → beacon → implementation
    beacon = _try_call(w3, token, BEACON_ABI, "beacon")
    if beacon:
        impl3 = _try_call(w3, beacon, BEACON_IMPL_ABI, "implementation")
        return {"type": "Beacon", "implementation": impl3, "admin": None}

    return {"type":"None","implementation":None,"admin":None}
