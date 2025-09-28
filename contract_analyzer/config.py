import os
from dotenv import load_dotenv

load_dotenv()

def env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)

class Settings:
    RPC_URL = env("RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/KSpsh9VuH6dNUN2fTxjbp")
    CHAIN_ID = int(env("CHAIN_ID", "1"))
    ETHERSCAN_API_KEY = env("ETHERSCAN_API_KEY", "")
    EXPLORER_API_KEYS = {
        1: env("ETHERSCAN_API_KEY", "G3MR711VSFPDS3WFCDKZ1QUE2BAREIT46Z"),
        56: env("BSCSCAN_API_KEY", ""),
        137: env("POLYGONSCAN_API_KEY", ""),
    }
    ASI_ONE_URL = env("ASI_ONE_URL", "https://api.asi1.ai/v1/chat/completions")
    ASI_ONE_API_KEY = env("ASI_ONE_API_KEY")
    ASI_ONE_MODEL = env("ASI_ONE_MODEL", "asi1-mini")   # put the exact model slug you use
    ASI_ONE_TEMPERATURE = float(env("ASI_ONE_TEMPERATURE", "0.2"))
    ASI_ONE_MAX_TOKENS = int(env("ASI_ONE_MAX_TOKENS", "8000"))
    EXPLORERS = {
        1: "https://api.etherscan.io/api",
        56: "https://api.bscscan.com/api",
        137: "https://api.polygonscan.com/api",
    }
    UNIV2_FACTORY = env("UNIV2_FACTORY", "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f")
    UNIV2_ROUTER02 = env("UNIV2_ROUTER02", "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")
    WETH = env("WETH", "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")

    UNIV3_POSITION_MANAGER = env("UNIV3_POSITION_MANAGER", "0xC36442b4a4522E871399CD717aBDD847Ab11FE88")
    UNIV3_FACTORY = env("UNIV3_FACTORY", "0x1F98431c8aD98523631AE4a59f267346ea31F984")

    KNOWN_LOCKERS = [a.strip() for a in (env("KNOWN_LOCKERS", "") or "").split(",") if a.strip()]
    DEAD_ADDRESSES = [a.strip() for a in (env("DEAD_ADDRESSES", "") or "").split(",") if a.strip()]

settings = Settings()
