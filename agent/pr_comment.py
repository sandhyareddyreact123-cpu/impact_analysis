"""
PR comment rendering + persistence (FR-08 / FR-09).

Two jobs:
  1. render_fallback(state, gate_status) -> deterministic markdown used whenever
     the LLM is disabled, fails, or returns an invalid comment.
  2. write_comment_file(state, body)     -> persists the final comment to disk so
     the dashboard / reviewer can open the FULL comment rather than a preview.

Kept separate from nodes.py so the UI work can read these files without importing
the agent.
"""
import json
from pathlib import Path

COMMENT_DIR = Path(__file__).resolve().parents[1] / "pr_comments"

# The six sections FR-08 mandates.
REQUIRED_SECTIONS = (
    "Affected services",
    "Owning teams",
    "Affected tests",
    "API consumers",
    "Schema impacts",
    "Severity",
)


def _bullets(items, empty="- None"):
    return items if items else [empty]


def render_fallback(state, gate_status):
    """Deterministic FR-08 comment. No LLM involved. Never raises."""
    sev = state.get("severity", "Low")
    reasons = state.get("severity_reasons") or []
    services = state.get("affected_services") or []
    consumers = state.get("api_consumers") or []
    schemas = state.get("schema_impacts") or []
    tests = state.get("affected_tests") or []
    contacts = state.get("owning_contacts") or []
    warnings = state.get("warnings") or []

    lines = [
        "## AI Impact Analysis",
        "",
        f"**Severity:** {sev}",
        "",
    ]
    if reasons:
        lines += ["**Why:**"] + [f"- {r}" for r in reasons] + [""]

    lines += ["### Affected services"]
    lines += _bullets([
        f"- `{s.get('name')}` — owner: {s.get('owner')} — criticality: {s.get('criticality')} "
        f"— depth {s.get('depth')} — path: {' -> '.join(reversed(s.get('path') or []))}"
        for s in services
    ])

    lines += ["", "### Owning teams"]
    lines += _bullets([f"- {c}" for c in contacts], "- None resolved")

    lines += ["", "### API consumers"]
    lines += _bullets([
        f"- `{c.get('consumer')}` ({c.get('type')}) — {c.get('api')}"
        + (f" v{c.get('version')}" if c.get("version") else "")
        + (" — **BREAKING**" if c.get("breaking") else "")
        for c in consumers
    ])

    lines += ["", "### Schema impacts"]
    lines += _bullets([
        f"- `{s.get('schema')}`"
        + (" — **BREAKING**" if s.get("breaking") else "")
        + f" — readers: {', '.join(s.get('readers') or []) or 'none'}"
        + f" — writers: {', '.join(s.get('writers') or []) or 'none'}"
        + f" — pipelines: {', '.join(s.get('pipelines') or []) or 'none'}"
        for s in schemas
    ])

    lines += ["", "### Affected tests"]
    lines += _bullets([f"- {t.get('type')}: `{t.get('name')}`" for t in tests])

    lines += ["", f"### CI gate: {gate_status}"]

    if sev in ("High", "Critical") and contacts:
        lines += ["", f"**Cross-team coordination required — tagging:** "
                      + ", ".join(f"@{c}" for c in contacts)]

    if warnings:
        lines += ["", "### Analysis warnings"]
        lines += [f"- `{w.get('code')}` ({w.get('source')}): {w.get('detail')}" for w in warnings]

    cov = state.get("graph_coverage") or {}
    if cov:
        lines += ["", f"_Dependency graph `{cov.get('graph_version')}` — coverage "
                      f"{cov.get('coverage_pct')}% ({cov.get('services_in_graph')}/"
                      f"{cov.get('catalog_services')} catalog services)._"]

    return "\n".join(lines)


def looks_complete(body):
    """Cheap guard: does the LLM comment actually cover the FR-08 sections?"""
    if not isinstance(body, str) or len(body.strip()) < 80:
        return False
    low = body.lower()
    hits = sum(1 for s in REQUIRED_SECTIONS if s.lower() in low)
    return hits >= 4


def write_comment_file(state, body):
    """Persist the final comment. Returns a relative path string, or '' on failure."""
    try:
        COMMENT_DIR.mkdir(parents=True, exist_ok=True)
        pr = state.get("pr_number") or state.get("event_id") or "unknown"
        sha = (state.get("commit_sha") or "nosha")[:12]
        md = COMMENT_DIR / f"pr-{pr}-{sha}.md"
        md.write_text(body, encoding="utf-8")

        meta = COMMENT_DIR / f"pr-{pr}-{sha}.json"
        meta.write_text(json.dumps({
            "pr_number": state.get("pr_number"),
            "commit_sha": state.get("commit_sha"),
            "severity": state.get("severity"),
            "rule_severity": state.get("rule_severity"),
            "severity_reasons": state.get("severity_reasons"),
            "reasoning": state.get("severity_reasoning"),
            "additional_risks": state.get("llm_additional_risks"),
            "gate_status": state.get("gate_status"),
            "notification_status": state.get("notification_status"),
            "owning_contacts": state.get("owning_contacts"),
            "llm_status": state.get("llm_status"),
            "comment_markdown": body,
        }, indent=2, default=str), encoding="utf-8")
        return str(md)
    except Exception:
        return ""
