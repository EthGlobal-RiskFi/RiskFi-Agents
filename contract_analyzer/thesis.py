from __future__ import annotations
import os, uuid, sys, json, math
from typing import Optional
import requests
from config import settings
from schema import AnalyzerOutput

def _cap_tokens(req_max: int, model: str) -> int:
    # simple safety cap; adjust if your ASI model has known hard limits
    MAX_CAP = 8192
    return max(128, min(req_max, MAX_CAP))

def _extract_text_v1(data: dict) -> tuple[Optional[str], Optional[str]]:
    try:
        choices = data.get("choices") or []
        if not choices:
            return None, None
        msg = choices[0].get("message") or {}
        return msg.get("content"), choices[0].get("finish_reason")
    except Exception:
        return None, None

def _asi_one_call(system: str, user: str, *, model: str, temperature: float, max_tokens: int, api_key: Optional[str]) -> Optional[str]:
    api_key = api_key or os.getenv("ASI_ONE_API_KEY")
    if not api_key:
        print("[LLM] missing API key", file=sys.stderr)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-session-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ContractAnalyzer/1.0 (+thesis)"
    }

    # Valid slugs per docs
    CANDIDATES = []
    if model:
        CANDIDATES.append(model)
    CANDIDATES += ["asi1-mini", "asi1-fast", "asi1-extended"]  # safe fallbacks

    def _post(sys_txt: str, usr_txt: str, req_max_toks: int, mdl: str):
        body = {
            "model": mdl,
            "temperature": float(temperature),
            "max_tokens": _cap_tokens(req_max_toks, mdl),
            "messages": [
                {"role": "system", "content": sys_txt},
                {"role": "user", "content": usr_txt},
            ],
        }
        r = requests.post(settings.ASI_ONE_URL, headers=headers, json=body, timeout=60)
        if not r.ok:
            txt = r.text or ""
            if "model not found" in txt.lower() or r.status_code == 404:
                return None, "model_404", None
            if "sucuri website firewall" in txt.lower():
                print("[LLM] WAF blocked request. Check ASI_ONE_URL host or ask for allowlist.", file=sys.stderr)
            else:
                print(f"[LLM] HTTP {r.status_code} {txt[:300]}", file=sys.stderr)
            return None, "error", None
        data = r.json()
        print(data)
        text, finish_reason = _extract_text_v1(data)
        return text, finish_reason, data

    # Try requested model, then fallbacks
    for mdl in CANDIDATES:
        text, finish_reason, data = _post(system, user, max_tokens, mdl)
        if text:
            return text
        if finish_reason == "length":
            short_system = system + " Keep it tight. 140–200 words. Return only the thesis text."
            retry_tokens = min(1024, max(512, max_tokens))
            text2, finish_reason2, data2 = _post(short_system, user, retry_tokens, mdl)
            if text2:
                return text2
        if finish_reason == "model_404":
            print(f"[LLM] model '{mdl}' not found, trying fallback...", file=sys.stderr)
            continue

    return None


def _format_user_prompt(a: AnalyzerOutput) -> str:
    # Compact, lossless summary of the analyzer output, enough context for a concise thesis.
    body = {
        "token": a.token,
        "chainId": a.chainId,
        "blockNumber": a.blockNumber,
        "summary": a.summary.model_dump(),
        "flags": [f.model_dump() for f in a.flags],
        "facts": a.facts,
    }
    return (
        "You are a senior crypto auditor. Build a 700 worded thesis that explains risk posture, "
        "what’s safe, what’s not, and concrete next checks.\n\n"
        "Data:\n" + json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    )

def _system_prompt() -> str:
    return (
        "You are precise, skeptical, and concise but detailed. Avoid hype. "
        "Organize output with bullets and one-line headers. No code fences. "
        "Call out critical controls (proxy admin, multisig thresholds, blacklist/tax, LP locks), "
        "holder concentration, liquidity quality, and whether honeypot heuristics are credible."
    )

def build_contract_thesis(a: AnalyzerOutput) -> Optional[str]:
    sys_txt = _system_prompt()
    usr_txt = _format_user_prompt(a)
    return _asi_one_call(
        sys_txt, usr_txt,
        model=settings.ASI_ONE_MODEL,
        temperature=settings.ASI_ONE_TEMPERATURE,
        max_tokens=settings.ASI_ONE_MAX_TOKENS,
        api_key=settings.ASI_ONE_API_KEY
    )
