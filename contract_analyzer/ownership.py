from typing import Optional, Dict, Any, List
from web3 import Web3
from abis import OWNABLE_ABI, ACCESS_CONTROL_ABI
from utils import is_zero_address

def read_owner(w3: Web3, addr: str) -> Optional[str]:
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=OWNABLE_ABI)
        owner = c.functions.owner().call()
        return Web3.to_checksum_address(owner)
    except Exception:
        return None

def detect_access_control(w3: Web3, addr: str) -> Dict[str, Any]:
    roles: List[str] = []
    facts: Dict[str, Any] = {}
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=ACCESS_CONTROL_ABI)
        # DEFAULT_ADMIN_ROLE = bytes32(0)
        zero32 = b"\x00"*32
        # Attempt enumerable variant; if fails, we still record presence.
        try:
            count = c.functions.getRoleMemberCount(zero32).call()
            members = []
            for i in range(int(count)):
                m = c.functions.getRoleMember(zero32, i).call()
                members.append(Web3.to_checksum_address(m))
            facts["roleMembers_DEFAULT_ADMIN_ROLE"] = members
        except Exception:
            pass
        roles.append("DEFAULT_ADMIN_ROLE")
    except Exception:
        pass
    return {"roles": roles, **facts}

def ownership_model(w3: Web3, addr: str) -> Dict[str, Any]:
    owner = read_owner(w3, addr)
    model = "Unknown"
    if owner is not None:
        model = "Ownable"
        if is_zero_address(owner):
            return {"owner": owner, "ownershipModel":"Ownable", "renounced": True}
    ac = detect_access_control(w3, addr)
    if ac.get("roles"):
        model = "AccessControl" if model == "Unknown" else f"{model}+AccessControl"
    return {"owner": owner, "ownershipModel": model, "renounced": False, **ac}
