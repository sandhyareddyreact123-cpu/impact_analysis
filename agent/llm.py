"""
Single-call LLM layer (Gemini) for UC-05 AI Impact Analysis Assistant.

DESIGN RULES (do not break these):
  1. FAIL-OPEN. This module NEVER raises. On any failure the caller keeps the
     deterministic rule-based result. NFR: "PR creation must not be blocked by
     assistant failure."
  2. SINGLE CALL. One request per PR analysis, made at the end of the node chain
     once all deterministic evidence has been gathered.
  3. ESCALATE-ONLY. This module returns a suggested severity. The CALLER applies
     max(rule_severity, llm_severity). The model can never downgrade.
  4. TEMPERATURE 0 + cache on commit_sha => repeatable demos.
"""
import logging
import os, json, hashlib, time
import httpx
from dotenv import load_dotenv
load_dotenv()
# --------------------------------------------------------------------------
# CONFIG - all overridable via environment / .env
# --------------------------------------------------------------------------
# !! CONFIRM THIS STRING against the model your API key actually supports.
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_ENABLED    = os.getenv("LLM_ENABLED", "true").strip().lower() in ("1", "true", "yes")
LLM_TIMEOUT    = float(os.getenv("LLM_TIMEOUT", "30"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
GEMINI_BASE    = os.getenv("GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")

SEVERITY_ORDER = ("Low", "Medium", "High", "Critical")

_CACHE: dict[str, dict] = {}
_LOGGER = logging.getLogger(__name__)
MAX_RETRIES = 3


def _warn(code, detail, **extra):
    """Same warning shape as tools._t3_warn so it merges into state['warnings']."""
    return {"code": code, "detail": detail, "source": "llm", **extra}


def _cache_key(payload):
    sha = payload.get("commit_sha") or ""
    body = json.dumps(payload, sort_keys=True, default=str)
    return f"{sha}:{hashlib.sha256(body.encode()).hexdigest()[:16]}"


def _extract_text(data):
    """Pull the text part out of a Gemini generateContent response."""
    for cand in (data.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            if isinstance(part.get("text"), str) and part["text"].strip():
                return part["text"]
    return ""


def _coerce(raw_text):
    """Parse model output into JSON. Tolerates ```json fences and surrounding prose."""
    txt = (raw_text or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1] if "```" in txt[3:] else txt.strip("`")
        if txt.lstrip().lower().startswith("json"):
            txt = txt.lstrip()[4:]
    txt = txt.strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    start, end = txt.find("{"), txt.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(txt[start:end + 1])
        except Exception:
            return None
    return None


def _validate(obj):
    """Shape-check + normalise. Returns (clean_dict, None) or (None, reason)."""
    if not isinstance(obj, dict):
        return None, "response was not a JSON object"

    sev = obj.get("severity")
    if sev not in SEVERITY_ORDER:
        return None, f"severity '{sev}' not in {SEVERITY_ORDER}"

    comment = obj.get("comment_markdown")
    if not isinstance(comment, str) or len(comment.strip()) < 40:
        return None, "comment_markdown missing or too short"

    def _strlist(v):
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()]

    return {
        "severity": sev,
        "severity_reasons": _strlist(obj.get("severity_reasons")),
        "reasoning": str(obj.get("reasoning") or "").strip(),
        "additional_risks": _strlist(obj.get("additional_risks")),
        "comment_markdown": comment.strip(),
        "confidence": str(obj.get("confidence") or "unknown").strip().lower(),
    }, None


def _post(system_prompt, user_prompt):
    """Raw HTTP call. Isolated so tests can monkeypatch it."""
    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": LLM_MAX_TOKENS,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=LLM_TIMEOUT) as client:
        for attempt in range(MAX_RETRIES + 1):
            resp = client.post(url, json=body, headers={"x-goog-api-key": GEMINI_API_KEY})
            if resp.status_code != 503 or attempt == MAX_RETRIES:
                resp.raise_for_status()
                return resp.json()
            delay = 2 ** attempt
            _LOGGER.warning("Gemini returned 503; retry %s/%s in %ss", attempt + 1, MAX_RETRIES, delay)
            time.sleep(delay)


def analyze(payload, system_prompt, user_prompt):
    """
    Single entry point. ALWAYS returns (result_or_None, status_dict).
    result is None whenever the deterministic fallback must be used.
    """
    if not LLM_ENABLED:
        return None, {"state": "disabled", "reason": "LLM_ENABLED is false",
                      "warning": None, "model": GEMINI_MODEL}
    if not GEMINI_API_KEY:
        return None, {"state": "fallback", "reason": "GEMINI_API_KEY not set",
                      "warning": _warn("llm_not_configured", "GEMINI_API_KEY not set"),
                      "model": GEMINI_MODEL}

    key = _cache_key(payload)
    if key in _CACHE:
        return _CACHE[key], {"state": "cached", "reason": "served from cache",
                             "warning": None, "model": GEMINI_MODEL}

    try:
        data = _post(system_prompt, user_prompt)
    except httpx.TimeoutException:
        return None, {"state": "fallback", "reason": f"timeout after {LLM_TIMEOUT}s",
                      "warning": _warn("llm_timeout", f"Gemini call timed out after {LLM_TIMEOUT}s"),
                      "model": GEMINI_MODEL}
    except Exception as exc:
        return None, {"state": "fallback", "reason": f"transport error: {exc}",
                      "warning": _warn("llm_call_failed", f"Gemini call failed: {exc}"),
                      "model": GEMINI_MODEL}

    parsed = _coerce(_extract_text(data))
    if parsed is None:
        return None, {"state": "fallback", "reason": "unparseable response",
                      "warning": _warn("llm_unparseable", "Gemini response was not valid JSON"),
                      "model": GEMINI_MODEL}

    clean, why = _validate(parsed)
    if clean is None:
        return None, {"state": "fallback", "reason": f"invalid response: {why}",
                      "warning": _warn("llm_invalid_response", f"Gemini response rejected: {why}"),
                      "model": GEMINI_MODEL}

    _CACHE[key] = clean
    return clean, {"state": "ok", "reason": "", "warning": None, "model": GEMINI_MODEL}


def escalate_only(rule_severity, llm_severity):
    """max() on the ordered scale. The model may raise severity, never lower it."""
    try:
        r = SEVERITY_ORDER.index(rule_severity)
    except ValueError:
        r = 0
    try:
        l = SEVERITY_ORDER.index(llm_severity)
    except ValueError:
        l = 0
    return SEVERITY_ORDER[max(r, l)]
