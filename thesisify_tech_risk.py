# thesisify_tech_and_risk.py
# Minimal, deterministic, and safe. Only uses numbers present in the payloads.

from __future__ import annotations
import os
import json
import uuid
import textwrap
from typing import Any, Dict, Optional
import requests

ASI_ONE_URL = "https://api.asi1.ai/v1/chat/completions"
DEFAULT_MODEL = "asi1-fast"


# ------------ helpers ------------

def _http_get_json(url: str, params: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

# --- add near your helpers ---
import sys

def _extract_text_v1(data: dict) -> tuple[str | None, str | None]:
    """
    Returns (text, finish_reason). Text is the assistant's visible content if found.
    finish_reason is choices[0].finish_reason if present.
    """
    finish_reason = None
    try:
        ch0 = (data.get("choices") or [{}])[0]
        finish_reason = ch0.get("finish_reason")
        # Primary: OpenAI-style content
        msg = ch0.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip(), finish_reason
        # Block-style content (list of dicts with 'text'/'content')
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
        # Some providers put plain text on the choice
        for k in ("content", "text", "output_text"):
            v = ch0.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip(), finish_reason
        # Top-level fallbacks
        for k in ("output_text", "content", "text"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip(), finish_reason
    except Exception as e:
        print(f"[LLM] extractor error: {e}", file=sys.stderr)
    return None, finish_reason


# caps per model; be conservative and leave headroom
MODEL_GEN_CAP = {
    "asi1-fast": 8192,
    "asi1-mini": 4096,
    "asi1-extended": 8192,
}
HEADROOM = 128  # tokens

def _cap_tokens(requested: int, model: str) -> int:
    cap = MODEL_GEN_CAP.get(model, 8192) - HEADROOM
    cap = max(64, cap)  # floor
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

    # Attempt 1 — your requested tokens, but capped safely
    text, finish_reason, data = _post(system, user, max_tokens)
    if text:
        return text

    # Retry — ask for SHORTER output and keep tokens modest, never larger
    if finish_reason == "length" or text is None:
        short_system = system + " Keep it tight. 140–200 words. Return only the thesis text."
        # 512–1024 is plenty for a 140–200 word target
        retry_tokens = min(1024, max(512, max_tokens))
        text2, finish_reason2, data2 = _post(short_system, user, retry_tokens)
        if text2:
            return text2
        keys = list((data2 or data or {}).keys())
        print(f"[LLM] unexpected response; finish_reason={finish_reason2 or finish_reason}; keys={keys}", file=sys.stderr)

    return None




def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{float(x):.2f}%"


def _fmt(x: Optional[float], nd: int = 3) -> str:
    if x is None:
        return "n/a"
    return f"{float(x):.{nd}f}"


def _get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# ------------ deterministic fallbacks ------------

def _default_technical_thesis(payload: Dict[str, Any]) -> str:
    tkr = payload.get("ticker") or _get(payload, "metadata.ticker") or "TICKER"

    hm = payload.get("health_metrics", {}) or {}
    overall = hm.get("overall_health", {}) or {}
    momentum = hm.get("momentum_health", {}) or {}
    trend = hm.get("trend_health", {}) or {}
    vol = hm.get("volatility_health", {}) or {}
    ch = hm.get("consensus_health", {}) or {}
    ens = hm.get("ensemble_stats", {}) or {}
    rsi = ens.get("rsi", {}) or {}
    macd = ens.get("macd", {}) or {}
    bb = ens.get("bollinger_bands", {}) or {}
    ovw = hm.get("overview", {}) or {}
    ts = payload.get("time_series", {}) or {}

    latest_date = ovw.get("latest_date") or payload.get("timestamp") or "latest"
    analysis_days = ovw.get("analysis_period_days")
    recs = ovw.get("total_recreations")

    # time-series deltas for context, guarded
    ohs = ts.get("overall_health_scores") or []
    first_score = float(ohs[0]) if ohs else None
    last_score = float(ohs[-1]) if ohs else overall.get("score")

    rsi_mean_latest = momentum.get("rsi_mean") or (ts.get("rsi_mean") or [None])[-1]
    rsi_std_latest = ch.get("rsi_std") or (ts.get("rsi_std") or [None])[-1]
    macd_hist_mean = momentum.get("macd_histogram_mean") or macd.get("histogram_mean")
    macd_hist_std = ch.get("macd_std") or macd.get("histogram_std")
    bb_pos_mean = bb.get("position_mean")
    bb_pos_std = bb.get("position_std")
    bb_extremes_ratio = bb.get("extremes_ratio")

    parts = []
    parts.append(f"Technical thesis for {tkr} as of {latest_date}.")
    if analysis_days is not None and recs is not None:
        parts.append(f"The analysis covers {int(analysis_days)} days and uses {int(recs)} recreations.")

    # Overall
    grade = overall.get("grade")
    o_score = overall.get("score")
    if grade is not None and o_score is not None:
        parts.append(f"Overall health is graded {grade} with a score of {o_score:.2f}/100.")
    elif o_score is not None:
        parts.append(f"Overall health score is {o_score:.2f}/100.")

    if first_score is not None and last_score is not None:
        delta = last_score - first_score
        parts.append(f"Across the window, overall score moved from {first_score:.2f} to {last_score:.2f} ({delta:+.2f}).")

    # Momentum and trend
    bm_ratio = trend.get("bullish_momentum_ratio")
    m20 = trend.get("momentum_20_mean")
    m_score = momentum.get("score")
    parts.append(
        "Momentum and trend summary"
        f" — RSI mean { _fmt(rsi_mean_latest, 2) } with std { _fmt(rsi_std_latest, 2) }"
        f"; MACD histogram mean { _fmt(macd_hist_mean, 4) } with std { _fmt(macd_hist_std, 4) }"
        f"; bullish MACD ratio { _fmt(momentum.get('bullish_macd_ratio'), 2) }"
        f"; bullish momentum ratio { _fmt(bm_ratio, 2) }"
        f"; momentum-20 mean { _fmt(m20, 4) }"
        f"; momentum score { _fmt(m_score, 2) }."
    )
    trend_strength = trend.get("trend_strength")
    if trend_strength:
        parts.append(f"Trend strength is flagged as {trend_strength}.")

    # Bollinger and volatility
    parts.append(
        "Bollinger profile"
        f" — position mean { _fmt(bb_pos_mean, 3) }, dispersion { _fmt(bb_pos_std, 3) }, extremes ratio { _fmt(bb_extremes_ratio, 3) }."
    )
    parts.append(
        "Volatility profile"
        f" — mean { _fmt(vol.get('volatility_mean'), 3) }% with std { _fmt(vol.get('volatility_std'), 3) }%"
        f"; risk level { vol.get('risk_level') or 'n/a' }"
        f"; volatility score { _fmt(vol.get('score'), 2) }."
    )

    # Consensus
    parts.append(
        "Consensus diagnostics"
        f" — agreement { ch.get('agreement_level') or 'n/a' }, consensus score { _fmt(ch.get('score'), 2) }."
    )

    parts.append("Net view is based only on these model outputs and does not include price targets or forward predictions.")
    return " ".join(parts)


def _default_risk_thesis(payload: Dict[str, Any]) -> str:
    print("DEFAULT")
    root = payload.get("risk_assessment", {}) or {}
    tkr = payload.get("ticker") or root.get("ticker") or "TICKER"

    ra = root.get("risk_assessment", {}) or {}
    varm = root.get("var_metrics", {}) or {}
    add = root.get("additional_risk_metrics", {}) or {}
    vae = root.get("vae_specific_metrics", {}) or {}

    horizon = varm.get("time_horizon_days")
    cl = varm.get("confidence_level")
    var90 = varm.get("var_90")
    var95 = varm.get("var_95")
    var99 = varm.get("var_99")
    es95 = add.get("expected_shortfall_95")

    parts = []
    parts.append(f"Risk thesis for {tkr}.")
    if horizon is not None and cl is not None:
        parts.append(f"Horizon {int(horizon)} days at {float(cl)*100:.1f}% confidence.")

    # VaR and ES
    parts.append(
        "Distribution tails"
        f" — VaR90 {_fmt(var90, 2)}%, VaR95 {_fmt(var95, 2)}%, VaR99 {_fmt(var99, 2)}%"
        f"; Expected Shortfall 95 { _fmt(es95, 2) }%."
    )

    # Vol metrics
    parts.append(
        "Volatility context"
        f" — average daily volatility { _fmt(add.get('average_daily_volatility'), 3) }%"
        f"; annualized volatility { _fmt(add.get('portfolio_volatility_annualized'), 2) }%"
        f"; max drawdown { _fmt(add.get('max_drawdown'), 2) }%."
    )

    # VAE diagnostics
    rvr = (vae.get("recreation_volatility_range") or {}) if isinstance(vae, dict) else {}
    parts.append(
        "Monte Carlo diagnostics"
        f" — recreations { int(vae.get('number_of_recreations') or 0) } on { int(vae.get('data_points') or 0) } points"
        f"; simulated vol range min { _fmt(rvr.get('min'), 3) or _fmt(rvr.get('min_vol'), 3) }%"
        f", mean { _fmt(rvr.get('mean'), 3) }%"
        f", max { _fmt(rvr.get('max'), 3) or _fmt(rvr.get('max_vol'), 3) }%."
    )

    # Assessment
    if ra.get("risk_level") is not None and ra.get("risk_score") is not None:
        parts.append(f"Model labels risk as {ra.get('risk_level')} with score {float(ra.get('risk_score')):.2f}/100.")
    elif ra.get("risk_level") is not None:
        parts.append(f"Model labels risk as {ra.get('risk_level')}.")

    if ra.get("interpretation"):
        parts.append(f"Interpreter note — {ra.get('interpretation')}")

    parts.append("This is a statistical summary only and avoids forward predictions.")
    return " ".join(parts)


# ------------ LLM prompts ------------

def _technical_prompt(payload: Dict[str, Any]) -> Dict[str, str]:
    system = (
        "You are a technical analysis summarizer. Write a compact thesis using ONLY the numbers and fields in the JSON. "
        "Cover overall_health (grade and score), momentum and trend, RSI and MACD aggregates, Bollinger features, "
        "volatility health, consensus agreement, analysis window and latest_date, and any time-series movement present. "
        "No price predictions. No numbers that are not explicitly present. Plain paragraphs. 700-900 words."
    )
    user = textwrap.dedent(f"INPUT_JSON:\n{json.dumps(payload, separators=(',', ':'))}")
    return {"system": system, "user": user}


def _risk_prompt(payload: Dict[str, Any]) -> Dict[str, str]:
    system = (
        "You are a risk analyst. Produce a concise risk thesis using ONLY the fields in the JSON. "
        "Summarize VaR at multiple levels, Expected Shortfall, average daily volatility, annualized volatility, "
        "max drawdown, horizon and confidence, and the VAE diagnostics. "
        "No forecasts. No extraneous numbers. Plain paragraphs. 500–800 words."
    )
    user = textwrap.dedent(f"INPUT_JSON:\n{json.dumps(payload, separators=(',', ':'))}")
    return {"system": system, "user": user}


# ------------ public LLM generators ------------

def generate_technical_thesis(payload: Dict[str, Any], *, model: str = DEFAULT_MODEL, temperature: float = 0.2, max_tokens: int = 8000, api_key: Optional[str] = None) -> str:
    p = _technical_prompt(payload)
    llm = _asi_one_call(p["system"], p["user"], model=model, temperature=temperature, max_tokens=max_tokens, api_key=api_key)
    return llm or _default_technical_thesis(payload)


def generate_risk_thesis(payload: Dict[str, Any], *, model: str = DEFAULT_MODEL, temperature: float = 0.2, max_tokens: int = 8000, api_key: Optional[str] = None) -> str:
    p = _risk_prompt(payload)
    llm = _asi_one_call(p["system"], p["user"], model=model, temperature=temperature, max_tokens=max_tokens, api_key=api_key)
    return llm or _default_risk_thesis(payload)


# ------------ fetch and attach helpers ------------

def fetch_technical_json(base_url: str, ticker: str, days: int, alpha: float) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/technical"
    return _http_get_json(url, {"ticker": ticker, "days": days, "alpha": alpha})


def fetch_risk_json(base_url: str, ticker: str, days: int, alpha: float) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/risk"
    return _http_get_json(url, {"ticker": ticker, "days": days, "alpha": alpha})


def thesisify_technical(payload: Dict[str, Any], *, api_key: Optional[str] = None) -> Dict[str, Any]:
    thesis = generate_technical_thesis(payload, api_key=api_key)
    out = dict(payload)
    out["thesis"] = thesis
    return out


def thesisify_risk(payload: Dict[str, Any], *, api_key: Optional[str] = None) -> Dict[str, Any]:
    thesis = generate_risk_thesis(payload, api_key=api_key)
    out = dict(payload)
    out["thesis"] = thesis
    return out


# ------------ optional CLI for quick runs ------------

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Fetch and thesisify technical or risk JSON.")
    parser.add_argument("--base-url", default="http://10.125.9.225:5000")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", type=int, default=4)
    parser.add_argument("--alpha", type=float, default=0.95)
    parser.add_argument("--kind", choices=["technical", "risk"], required=True)
    parser.add_argument("--no-llm", action="store_true", help="Force deterministic fallback.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    api_key = "sk_a2bfc9202dbe4f31bd7baa4c78a6aeb061a984ed8b17410d9f5a6898cca9e16c"

    try:
        if args.kind == "technical":
            payload = fetch_technical_json(args.base_url, args.ticker, args.days, args.alpha)
            out = thesisify_technical(payload, api_key=api_key)
        else:
            payload = fetch_risk_json(args.base_url, args.ticker, args.days, args.alpha)
            out = thesisify_risk(payload, api_key=api_key)
        json.dump(out, sys.stdout, ensure_ascii=False, separators=(",", ":"), indent=2)
        sys.stdout.write("\n")
    except Exception as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(1)
