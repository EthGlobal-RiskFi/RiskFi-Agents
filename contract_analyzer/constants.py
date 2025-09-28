ZERO_ADDR = "0x0000000000000000000000000000000000000000"
DEAD_ADDRS_DEFAULT = {
    ZERO_ADDR,
    "0x000000000000000000000000000000000000dEaD",
}

# EIP-1967 slots (implementation/admin)
EIP1967_IMPL_SLOT = int.from_bytes(bytes.fromhex(
    "360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"), "big")
EIP1967_ADMIN_SLOT = int.from_bytes(bytes.fromhex(
    "b53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"), "big")

# Common function selectors for SAFE multisig (for code fingerprinting)
SAFE_FUNC_SIGS = [
    "0xa0e67e2b",  # getOwners()
    "0x694e80c3",  # getThreshold()
]

# Heuristic keywords per spec
PRIV_KEYWORDS = {
    "blacklist": ["blacklist", "isBlacklisted", "setBlacklist", "unblacklist"],
    "tax": ["transferTaxRate", "setTaxFeePercent", "_taxFee", "marketingFee", "liquidityFee"],
    "max": ["maxTxAmount","maxTransactionAmount","maxWallet","maxWalletAmount"],
    "pause": ["pause","unpause","paused"],
    "trading": ["setTradingEnabled","openTrading","setSwapEnabled","enableTrading","disableTrading"],
    "mint_burn": ["mint", "burn", "burnFrom"]
}

# Labels for exchanges (heuristic)
KNOWN_EXCHANGES = {
    "0x742d35Cc6634C0532925a3b844Bc454e4438f44e": "Bitfinex/Cold",
    # add more tagged addresses as needed or from explorer labels
}
