from __future__ import annotations
import time
from typing import Any, Dict, Optional
import requests
from web3 import Web3, HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware

class GraphQLClient:
    def __init__(self, url: str, timeout: float = 20.0, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.timeout = timeout
        self.headers = headers or {"Content-Type": "application/json"}

    def query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        r = requests.post(self.url, json=payload, timeout=self.timeout, headers=self.headers)
        r.raise_for_status()
        out = r.json()
        if "errors" in out:
            raise RuntimeError(f"GraphQL error: {out['errors']}")
        return out["data"]

def get_web3(rpc_url: str, chain_id: int, timeout: float = 30.0) -> Web3:
    w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
    # Inject POA middleware for chains like BSC/Polygon where needed
    if chain_id in (56, 97, 137, 80001, 1101, 8453, 84532):
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    if not w3.is_connected():
        raise RuntimeError("Web3 provider is not connected")
    return w3
