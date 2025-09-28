from typing import Dict, Any, List
from web3 import Web3
from fetcher import (
    get_w3, get_block_number, get_code, bytecode_hash,
    get_verified_abi, get_verified_source, get_contract, minimal_abi,
    erc20_total_supply_raw,   # <- make sure this import exists
)
from proxy import detect_proxy
from ownership import ownership_model
from multisig import detect_safe
from privileges import privileged_facts
from distribution import top_holders
from liquidity import liquidity_overview
from honeypot import assess_honeypot
from score import compute_score
from schema import AnalyzerOutput, Summary, Flag
from utils import to_checksum
from config import settings
from thesis import build_contract_thesis

def analyze_contract(token: str, chain_id: int, block_tag: str | None = None) -> AnalyzerOutput:
    w3 = get_w3()
    token = to_checksum(token)

    # 1. Fetch metadata
    block_num = get_block_number(w3)
    code = get_code(w3, token)
    if not code:
        raise RuntimeError("Address has no code")
    bchash = bytecode_hash(code)
    abi = get_verified_abi(token, chain_id) or minimal_abi()
    source = get_verified_source(token, chain_id)

    # 2. Proxy detection
    proxy_info = detect_proxy(w3, token)

    # 3. Ownership model  <-- move this BEFORE using it
    own = ownership_model(w3, token)

    flags: List[Flag] = []
    if proxy_info["type"] != "None":
        flags.append(Flag(code="UPGRADEABLE_PROXY", severity="high",
                          evidence={"proxyType": proxy_info["type"], "implementation": proxy_info["implementation"], "admin": proxy_info["admin"]}))

    # 4. Choose the effective control owner
    control_owner = proxy_info.get("admin") or own.get("owner")

    # 5. Multisig check on control owner
    msig = {"isSafe": False}
    if control_owner:
        msig = detect_safe(w3, control_owner)
        if not msig.get("isSafe"):
            flags.append(Flag(code="OWNER_EOA", severity="high", evidence={"owner": control_owner}))

    if own.get("renounced"):
        flags.append(Flag(code="OWNERSHIP_RENOUNCED", severity="low", evidence={"owner": own.get("owner")}))

    # 6. Privileged functions
    priv_facts = privileged_facts(w3, token, abi, source)

    # 7. Supply and distribution with robust fallback
    c = get_contract(w3, token, abi)
    try:
        total_supply = int(c.functions.totalSupply().call())
        if total_supply == 0:
            ts2 = erc20_total_supply_raw(w3, token)
            if ts2:
                total_supply = ts2
    except Exception:
        ts2 = erc20_total_supply_raw(w3, token)
        total_supply = ts2 or 0

    top_list, agg = top_holders(token, chain_id, total_supply)
    if top_list:
        if top_list[0]["pct"] >= 20:
            flags.append(Flag(code="TOP1_HOLDER_GT_20PCT", severity="med",
                              evidence={"pct": top_list[0]["pct"], "holder": top_list[0]["address"]}))
        if sum(x["pct"] for x in top_list[:10]) >= 70:
            flags.append(Flag(code="TOP10_GT_70PCT", severity="med",
                              evidence={"pct": sum(x["pct"] for x in top_list[:10])}))

    # 8. Liquidity
    liq = liquidity_overview(w3, token)
    if liq.get("pair") and not liq.get("lpLocked"):
        flags.append(Flag(code="LP_NOT_LOCKED", severity="med",
                          evidence={"pair": liq.get("pair"), "locker": (liq.get("lockEvidence") or {}).get("locker")}))

    # 9. Honeypot heuristics
    hp = assess_honeypot(w3, token, {
        "blacklistPrimitives": priv_facts.get("blacklistPrimitives", []),
        "taxPrimitives": priv_facts.get("taxPrimitives", []),
        "tradingPrimitives": priv_facts.get("tradingPrimitives", [])
    })

    # 10. Facts and score
    facts: Dict[str, Any] = {
        "owner": own.get("owner"),
        "controlOwner": control_owner,
        "ownershipModel": own.get("ownershipModel"),
        "roles": own.get("roles", []),
        "renounced": own.get("renounced", False),
        "pauseStatus": priv_facts.get("pauseStatus"),
        "blacklistPrimitives": priv_facts.get("blacklistPrimitives"),
        "taxPrimitives": priv_facts.get("taxPrimitives"),
        "maxTxPrimitives": priv_facts.get("maxTxPrimitives"),
        "tradingPrimitives": priv_facts.get("tradingPrimitives"),
        "mintBurnPrimitives": priv_facts.get("mintBurnPrimitives"),
        "proxy": proxy_info,
        "multisig": msig,
        "supply": {
            "totalSupply": str(total_supply),
            "topHolders": top_list
        },
        "liquidity": liq,
        "honeypot": hp,
        "bytecodeHash": bchash
    }

    summary_dict = compute_score(facts, [f.model_dump() for f in flags])
    summary = Summary(**summary_dict)

    out = AnalyzerOutput(
        token=token,
        chainId=chain_id,
        blockNumber=block_num,
        summary=summary,
        flags=flags,
        facts=facts
    )

    try:
        thesis = build_contract_thesis(out)
        out.contract_analysis_thesis = thesis
    except Exception as e:
        # Don’t fail the whole analysis if ASI call fails
        out.contract_analysis_thesis = None

    return out