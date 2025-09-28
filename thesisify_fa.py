# thesisify_fundamental.py
# Minimal, deterministic, and safe. Mirrors token caps and fallback style
# from the tech/risk thesis generator, but targets Fundamental Analysis (FA).
#
# Usage examples:
#   python thesisify_fundamental.py --endpoint http://10.125.9.225:5000/fundamental --coin AAVE
#   ASI_ONE_API_KEY=... python thesisify_fundamental.py --base-url http://10.125.9.225:5000 --coin WBTC
#
# Programmatic use:
#   from thesisify_fundamental import fetch_fundamental_json, thesisify_fundamental
#   payload = fetch_fundamental_json("http://10.125.9.225:5000", "AAVE")
#   out = thesisify_fundamental(payload, api_key=os.getenv("ASI_ONE_API_KEY"))
#
# Notes:
# - We intentionally accept both a full endpoint (".../fundamental") and a base url.
# - We send the coin in both the query string and the JSON body for compatibility with
#   the sample snippet you provided.

from __future__ import annotations
import os
import sys
import json
import uuid
import textwrap
from typing import Any, Dict, Optional, Tuple
import requests

ASI_ONE_URL = "https://api.asi1.ai/v1/chat/completions"
DEFAULT_MODEL = "asi1-fast"

# -----------------------------
# HTTP helpers
# -----------------------------

def _http_post_json(url: str, *, coin: str, timeout: int = 60) -> Dict[str, Any]:
    """POST to the fundamental endpoint with coin in both query and body.
    Falls back to GET if POST fails.
    """
    # Make sure url ends with /fundamental
    if not url.endswith("/fundamental"):
        if url.endswith("/"):
            url = url + "fundamental"
        else:
            url = url + "/fundamental"

    # Attach query param as in the sample (even if redundant)
    q_url = f"{url}?coin={coin}"

    headers = {"Content-Type": "application/json"}
    body = json.dumps({"coin": coin})

    try:
        r = requests.request("POST", q_url, headers=headers, data=body, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        sys.stderr.write(f"[fundamental] POST failed ({e}); trying GET...\n")
        # Try GET as a compatibility fallback
        try:
            r2 = requests.get(q_url, timeout=timeout)
            r2.raise_for_status()
            return r2.json()
        except Exception as e2:
            raise RuntimeError(f"fundamental fetch failed: {e2}") from e2


def fetch_fundamental_json(base_or_endpoint: str, coin: str, timeout: int = 60) -> Dict[str, Any]:
    """Convenience wrapper that accepts a base URL or the full endpoint."""
    # If user passed the base (no trailing segment), we append /fundamental
    return _http_post_json(base_or_endpoint, coin=coin, timeout=timeout)


# -----------------------------
# LLM helpers (keeps token caps and fallback behavior)
# -----------------------------

# Same extractor logic to robustly get assistant text

def _extract_text_v1(data: dict) -> Tuple[Optional[str], Optional[str]]:
    """Returns (text, finish_reason)."""
    finish_reason = None
    try:
        ch0 = (data.get("choices") or [{}])[0]
        finish_reason = ch0.get("finish_reason")
        msg = ch0.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip(), finish_reason
        if isinstance(content, list):
            texts = []
            for b in content:
                if isinstance(b, dict):
                    if isinstance(b.get("text"), str):
                        texts.append(b["text"])
                    elif isinstance(b.get("content"), str):
                        texts.append(b["content"])
            if texts:
                return "\n".join(t.strip() for t in texts if t and t.strip()), finish_reason
        for k in ("content", "text", "output_text"):
            v = ch0.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip(), finish_reason
        for k in ("output_text", "content", "text"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip(), finish_reason
    except Exception as e:
        print(f"[LLM] extractor error: {e}", file=sys.stderr)
    return None, finish_reason


# Caps per model; conservative with a small headroom, same mapping style
MODEL_GEN_CAP = {
    "asi1-fast": 8192,
    "asi1-mini": 4096,
    "asi1-extended": 8192,
}
HEADROOM = 128  # tokens

def _cap_tokens(requested: int, model: str) -> int:
    cap = MODEL_GEN_CAP.get(model, 8192) - HEADROOM
    cap = max(64, cap)
    return min(requested, cap)


def _asi_one_call(system: str, user: str, *, model: str, temperature: float, max_tokens: int, api_key: Optional[str]) -> Optional[str]:
    api_key = api_key or os.getenv("ASI_ONE_API_KEY")
    if not api_key:
        print("[LLM] missing API key", file=sys.stderr)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "x-session-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }

    def _post(sys_txt: str, usr_txt: str, req_max_toks: int):
        body = {
            "model": model,
            "temperature": temperature,
            "max_tokens": _cap_tokens(req_max_toks, model),
            "messages": [
                {"role": "system", "content": sys_txt},
                {"role": "user", "content": usr_txt},
            ],
        }
        r = requests.post(ASI_ONE_URL, headers=headers, json=body, timeout=60)
        if not r.ok:
            print(f"[LLM] HTTP {r.status_code} {r.text}", file=sys.stderr)
            return None, None, None
        data = r.json()
        text, finish_reason = _extract_text_v1(data)
        return text, finish_reason, data

    text, finish_reason, data = _post(system, user, max_tokens)
    if text:
        return text

    # Retry with a shorter target if first try hit a length limit or failed
    if finish_reason == "length" or text is None:
        short_system = system + " Keep it tight. 140–200 words. Return only the thesis text."
        retry_tokens = min(1024, max(512, max_tokens))
        text2, finish_reason2, data2 = _post(short_system, user, retry_tokens)
        if text2:
            return text2
        keys = list((data2 or data or {}).keys())
        print(f"[LLM] unexpected response; finish_reason={finish_reason2 or finish_reason}; keys={keys}", file=sys.stderr)

    return None


# -----------------------------
# Context stub builders
# -----------------------------

def _safe_get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for k in path.split('.'):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def build_context_stubs(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create short, neutral context stubs for each top-level key in the payload.
    These are passed alongside the raw JSON to guide the LLM without injecting
    new facts.
    """
    stubs: Dict[str, Any] = {}

    coin = payload.get("coin")
    if coin:
        stubs["coin"] = f"The asset under review is {coin}."

    gh = payload.get("github_activity") or {}
    if gh:
        forks = gh.get("forks")
        stars = gh.get("stars")
        open_issues = gh.get("open_issues")
        repos = gh.get("repos") or []
        top_repo_lines = []
        for r in repos[:5]:
            rn = r.get("repo")
            rstars = r.get("stars")
            rforks = r.get("forks")
            ois = r.get("open_issues")
            if rn:
                top_repo_lines.append(
                    f"Repo {rn} has {rstars} stars, {rforks} forks, and {ois} open issues"
                )
        stubs["github_activity"] = {
            "overview": f"GitHub shows {stars} stars, {forks} forks, and {open_issues} open issues across key repos.",
            "notable_repos": top_repo_lines,
            "what_to_infer": "Use these as signals of codebase traction and maintenance pressure. Do not invent metrics."
        }

    md = payload.get("market_data") or {}
    if md:
        latest_price = md.get("latest_price")
        pchg = md.get("24h_price_change_pct")
        vchg = md.get("24h_volume_change_pct")
        dret = md.get("daily_returns") or []
        stubs["market_data"] = {
            "overview": f"Latest observed price is {latest_price}. 24h price change {pchg} percent and 24h volume change {vchg} percent.",
            "daily_returns_note": f"Daily returns array length is {len(dret)}. Discuss variability only from values present.",
            "what_to_infer": "Comment on short term behavior and dispersion without forecasting."
        }

    rs = payload.get("reddit_sentiment") or {}
    if rs:
        cats = rs.get("categories") or {}
        summary = rs.get("summary")
        cat_names = list(cats.keys())
        stubs["reddit_sentiment"] = {
            "summary_hint": "Incorporate this summary to flavor the fundamental perspective with community risk signals.",
            "categories_present": cat_names,
            "what_to_infer": "Balance positive signals with risks. Avoid numerical claims that are not in the JSON."
        }

    status = payload.get("status")
    if status:
        stubs["status"] = f"Source status reads {status}."

    # For any other keys, just add a generic note to keep us future-proof.
    for k in payload.keys():
        if k not in stubs:
            stubs[k] = "Present in payload. Use only as given."

    return stubs


# -----------------------------
# Prompt builders
# -----------------------------

def _fa_prompt(payload: Dict[str, Any]) -> Dict[str, str]:
    stubs = build_context_stubs(payload)

    system = (
        "You are a fundamental analysis writer for crypto and DeFi assets. "
        "Write an extremely detailed thesis using ONLY the facts in INPUT_JSON and CONTEXT_STUBS. "
        "We provided GitHub activity, market data, and Reddit sentiment. "
        "Tie codebase health, development traction, and repo signals to adoption and technical risk. "
        "Use the Reddit summary and categories to frame community trust, regulatory headwinds, and operational risks. "
        "Ground every numeric claim in the provided fields. Do not add any numbers that are not present. "
        "No price targets, no forecasts, no external facts. Write in clear paragraphs. Target 900–1200 words."
    )

    user = textwrap.dedent(
        """
        INPUT_JSON:
        {payload}

        CONTEXT_STUBS:
        {stubs}
        """
    ).format(payload=json.dumps(payload, separators=(",", ":")), stubs=json.dumps(stubs, ensure_ascii=False))

    return {"system": system, "user": user}


# -----------------------------
# Deterministic fallback
# -----------------------------

def _fmt(x: Optional[float], nd: int = 3) -> str:
    if x is None:
        return "n/a"
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return str(x)


def _default_fa_thesis(payload: Dict[str, Any]) -> str:
    """A safe, deterministic fallback that never invents numbers and only
    references values present in the payload. Keep neutral tone.
    """
    coin = payload.get("coin") or "ASSET"

    gh = payload.get("github_activity") or {}
    forks = gh.get("forks")
    stars = gh.get("stars")
    ois = gh.get("open_issues")
    repos = gh.get("repos") or []
    repo_lines = []
    for r in repos[:5]:
        rn = r.get("repo")
        if rn:
            repo_lines.append(
                f"{rn} with {r.get('stars')} stars, {r.get('forks')} forks, {r.get('open_issues')} open issues"
            )

    md = payload.get("market_data") or {}
    latest = md.get("latest_price")
    pchg = md.get("24h_price_change_pct")
    vchg = md.get("24h_volume_change_pct")
    dret = md.get("daily_returns") or []

    rs = payload.get("reddit_sentiment") or {}
    rs_summary = rs.get("summary")
    rs_cats = rs.get("categories") or {}

    parts = []
    parts.append(f"Fundamental thesis for {coin} based only on the provided data.")

    # GitHub
    if gh:
        parts.append(
            "Codebase signals: GitHub shows "
            f"{stars} stars, {forks} forks, and {ois} open issues across the tracked repositories."
        )
        if repo_lines:
            parts.append("Notable repositories include: " + "; ".join(repo_lines) + ".")
        parts.append(
            "Stars and forks reflect interest and reuse while open issues hint at active maintenance needs."
        )

    # Market data
    if md:
        parts.append(
            "Market context: latest observed price "
            f"{latest}. 24 hour price change {pchg} percent and 24 hour volume change {vchg} percent."
        )
        if dret:
            parts.append(
                f"Daily returns array has {len(dret)} entries. Discuss variability only from values present."
            )

    # Reddit
    if rs_summary:
        parts.append("Community sentiment summary: " + rs_summary)
    if rs_cats:
        # Include up to 5 explicit category blurbs as-is
        take = list(rs_cats.items())[:5]
        for name, text in take:
            parts.append(f"Category {name}: {text}")
        parts.append(
            "Use these views to frame risks around security, usability, market structure, and regulation without adding new claims."
        )

    status = payload.get("status")
    if status:
        parts.append(f"Source status reads {status}.")

    parts.append(
        "This fallback thesis avoids forecasts and uses only the fields present in the input JSON."
    )

    return " ".join(parts)


# -----------------------------
# Public generator and attach helper
# -----------------------------

def generate_fa_thesis(payload: Dict[str, Any], *, model: str = DEFAULT_MODEL, temperature: float = 0.2, max_tokens: int = 8000, api_key: Optional[str] = None) -> str:
    p = _fa_prompt(payload)
    llm = _asi_one_call(p["system"], p["user"], model=model, temperature=temperature, max_tokens=max_tokens, api_key=api_key)
    return llm or _default_fa_thesis(payload)


def thesisify_fundamental(payload: Dict[str, Any], *, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    thesis = generate_fa_thesis(payload, api_key=api_key, model=model)
    out = dict(payload)
    out["thesis"] = thesis
    return out


# -----------------------------
# Optional CLI
# -----------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch and thesisify Fundamental JSON.")
    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--endpoint", help="Full endpoint like http://host:5000/fundamental", default="http://10.125.9.225:5000/fundamental")
    src.add_argument("--base-url", help="Base URL like http://host:5000 (we append /fundamental)", default="http://10.125.9.225:5000")
    parser.add_argument("--coin", required=True, help="Asset symbol, e.g., AAVE or WBTC")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--no_llm", action="store_true", help="Force deterministic fallback only")
    parser.add_argument("--api-key", help="ASI One API key; if missing we use ASI_ONE_API_KEY env var")

    args = parser.parse_args()

    endpoint = args.endpoint or (args.base_url or "http://10.125.9.225:5000")

    try:
        payload = fetch_fundamental_json(endpoint, args.coin, timeout=args.timeout)
        if args.no_llm:
            thesis = _default_fa_thesis(payload)
            out = dict(payload)
            out["thesis"] = thesis
        else:
            api_key = args.api_key or os.getenv("ASI_ONE_API_KEY")
            out = thesisify_fundamental(payload, api_key=api_key, model=args.model)
        json.dump(out, sys.stdout, ensure_ascii=False, separators=(",", ":"), indent=2)
        sys.stdout.write("\n")
    except Exception as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)
