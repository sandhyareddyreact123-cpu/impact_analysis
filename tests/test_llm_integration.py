import json, sys, os, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent import llm, pr_comment
from agent.graph import Local
from agent.prompts import build_payload

FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"   <-- {detail}"))


def load(n):
    return json.loads((FIX / n).read_text())


def run(payload):
    llm._CACHE.clear()
    return Local().invoke(dict(payload))


def gemini_envelope(obj):
    """Wrap a dict the way Gemini's generateContent response nests it."""
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


def stub(response=None, exc=None, raw=None):
    def _p(system, user):
        stub.last_user = user
        if exc:
            raise exc
        if raw is not None:
            return {"candidates": [{"content": {"parts": [{"text": raw}]}}]}
        return gemini_envelope(response)
    return _p


GOOD_COMMENT = ("## AI Impact Analysis\n**Severity:** High\n### Affected services\n- x\n"
                "### Owning teams\n- y\n### API consumers\n- z\n### Schema impacts\n- s\n"
                "### Affected tests\n- t\n### CI gate: not_required")


# =====================================================================
print("\n[1] LLM DISABLED -> pure deterministic path (regression guard)")
# =====================================================================
llm.LLM_ENABLED = False
low, high, crit = run(load("low_pr.json")), run(load("high_api_break.json")), run(load("critical_financial_schema.json"))
check("low_pr -> Low", low["severity"] == "Low", low["severity"])
check("high_api_break -> High", high["severity"] == "High", high["severity"])
check("critical_financial_schema -> Critical", crit["severity"] == "Critical", crit["severity"])
check("Low gate not_required", low["gate_status"] == "not_required", low["gate_status"])
check("Critical gate pending_approval", crit["gate_status"] == "pending_approval", crit["gate_status"])
check("Critical notification sent", crit["notification_status"] == "sent", crit["notification_status"])
check("Low notification not_required", low["notification_status"] == "not_required")
check("llm_status disabled", low["llm_status"]["state"] == "disabled", low["llm_status"])
check("deterministic comment has FR-08 sections", pr_comment.looks_complete(crit["comment_markdown"]))
check("comment file written", crit["comment_file"] and pathlib.Path(crit["comment_file"]).exists())
check("Team3 warnings survive", {w["code"] for w in crit["warnings"]} >= {"malformed_edge", "unknown_node", "coverage_gap"},
      sorted({w["code"] for w in crit["warnings"]}))
check("finance-ledger reached (core_financial)",
      any(s["name"] == "finance-ledger" for s in crit["affected_services"]))
check("owner_map populated (bug fix)",
      any(v for v in (crit["owner_map"] or {}).values()), crit["owner_map"])

# =====================================================================
print("\n[2] LLM ENABLED + healthy response")
# =====================================================================
llm.LLM_ENABLED = True
llm.GEMINI_API_KEY = "test-key"
llm._post = stub({"severity": "High", "severity_reasons": ["Signature changed"],
                  "reasoning": "Order contract narrowed.", "additional_risks": ["mobile clients"],
                  "comment_markdown": GOOD_COMMENT, "confidence": "high"})
r = run(load("high_api_break.json"))
check("llm_status ok", r["llm_status"]["state"] == "ok", r["llm_status"])
check("LLM comment used", r["comment_markdown"] == GOOD_COMMENT)
check("LLM reason merged", "Signature changed" in r["severity_reasons"], r["severity_reasons"])
check("reasoning captured", r["severity_reasoning"] == "Order contract narrowed.")
check("additional_risks captured", r["llm_additional_risks"] == ["mobile clients"])
check("raw patch reached prompt", "public endpoint changed" in stub.last_user)
check("rule_severity preserved", r["rule_severity"] == "High")

# =====================================================================
print("\n[3] ESCALATION Medium -> Critical must flip the CI gate  (ordering trap)")
# =====================================================================
# order-portal has downstream dependents but NO registered api_consumers,
# so it lands on the "Medium" rung. (customer-api would be High: partner-sdk is
# an external consumer and the rule flags external regardless of breaking.)
medium_case = {"event_id": "med", "event_type": "pull_request", "repository": "demo", "pr_number": 9,
               "commit_sha": "med1",
               "changed_files": [{"path": "order-portal/Service.cs", "service": "order-portal",
                                  "patch": "internal refactor", "breaking": False}]}
llm._post = stub(None)
llm._post = lambda s, u: gemini_envelope({"severity": "Medium", "severity_reasons": [],
                                          "reasoning": "", "additional_risks": [],
                                          "comment_markdown": GOOD_COMMENT, "confidence": "low"})
base = run(medium_case)
check("baseline is Medium", base["severity"] == "Medium", base["severity"])
check("baseline gate not_required", base["gate_status"] == "not_required")

llm._post = lambda s, u: gemini_envelope({"severity": "Critical",
                                          "severity_reasons": ["Removed field used by finance-ledger"],
                                          "reasoning": "Hidden breaking change.", "additional_risks": [],
                                          "comment_markdown": GOOD_COMMENT, "confidence": "high"})
esc = run(medium_case)
check("escalated to Critical", esc["severity"] == "Critical", esc["severity"])
check("rule floor still Medium", esc["rule_severity"] == "Medium")
check("GATE FLIPPED to pending_approval", esc["gate_status"] == "pending_approval", esc["gate_status"])
check("NOTIFICATION now sent", esc["notification_status"] == "sent", esc["notification_status"])
check("escalated flag set", esc["llm_status"]["escalated"] is True)

# =====================================================================
print("\n[4] DOWNGRADE must be blocked")
# =====================================================================
llm._post = lambda s, u: gemini_envelope({"severity": "Low", "severity_reasons": ["looks harmless"],
                                          "reasoning": "", "additional_risks": [],
                                          "comment_markdown": GOOD_COMMENT, "confidence": "low"})
d = run(load("critical_financial_schema.json"))
check("stays Critical", d["severity"] == "Critical", d["severity"])
check("gate stays pending_approval", d["gate_status"] == "pending_approval")
check("downgrade warning emitted", any(w["code"] == "llm_downgrade_blocked" for w in d["warnings"]))

# =====================================================================
print("\n[5] FAIL-OPEN: timeout / HTTP error / bad JSON / bad severity / no key")
# =====================================================================
import httpx
for label, kw, expect_code in [
    ("timeout", {"exc": httpx.TimeoutException("t")}, "llm_timeout"),
    ("transport error", {"exc": RuntimeError("boom")}, "llm_call_failed"),
    ("unparseable", {"raw": "I think this is fine honestly"}, "llm_unparseable"),
]:
    llm._post = stub(**kw)
    r = run(load("critical_financial_schema.json"))
    check(f"{label} -> still Critical", r["severity"] == "Critical", r["severity"])
    check(f"{label} -> gate held", r["gate_status"] == "pending_approval")
    check(f"{label} -> warning {expect_code}", any(w["code"] == expect_code for w in r["warnings"]),
          [w["code"] for w in r["warnings"]])
    check(f"{label} -> deterministic comment", pr_comment.looks_complete(r["comment_markdown"]))

llm._post = lambda s, u: gemini_envelope({"severity": "Catastrophic", "comment_markdown": GOOD_COMMENT})
r = run(load("high_api_break.json"))
check("invalid severity -> fallback", r["severity"] == "High" and
      any(w["code"] == "llm_invalid_response" for w in r["warnings"]))

llm._post = lambda s, u: gemini_envelope({"severity": "Critical", "comment_markdown": "too short"})
r = run(load("high_api_break.json"))
check("short comment -> rejected, rule severity kept", r["severity"] == "High",
      r["severity"])

llm._post = lambda s, u: gemini_envelope(
    {"severity": "Critical", "severity_reasons": [], "reasoning": "", "additional_risks": [],
     "comment_markdown": "## AI Impact Analysis\n" + "x" * 200, "confidence": "high"})
r = run(load("high_api_break.json"))
check("incomplete comment -> escalate kept, fallback comment", r["severity"] == "Critical"
      and any(w["code"] == "llm_comment_incomplete" for w in r["warnings"])
      and pr_comment.looks_complete(r["comment_markdown"]))

saved = llm.GEMINI_API_KEY
llm.GEMINI_API_KEY = ""
r = run(load("low_pr.json"))
check("no API key -> fallback + warning", r["severity"] == "Low"
      and any(w["code"] == "llm_not_configured" for w in r["warnings"]))
llm.GEMINI_API_KEY = saved

# =====================================================================
print("\n[6] Parsing robustness + cache")
# =====================================================================
fenced = "```json\n" + json.dumps({"severity": "High", "severity_reasons": ["a"], "reasoning": "r",
                                   "additional_risks": [], "comment_markdown": GOOD_COMMENT,
                                   "confidence": "high"}) + "\n```"
llm._post = stub(raw=fenced)
r = run(load("high_api_break.json"))
check("```json fences parsed", r["llm_status"]["state"] == "ok", r["llm_status"])

calls = {"n": 0}
def counting(s, u):
    calls["n"] += 1
    return gemini_envelope({"severity": "High", "severity_reasons": [], "reasoning": "",
                            "additional_risks": [], "comment_markdown": GOOD_COMMENT,
                            "confidence": "high"})
llm._post = counting
llm._CACHE.clear()
p = load("high_api_break.json")
Local().invoke(dict(p)); Local().invoke(dict(p))
check("cache prevents 2nd call", calls["n"] == 1, f"calls={calls['n']}")

# =====================================================================
print("\n[7] Merge event still bypasses the LLM (FR-11 path)")
# =====================================================================
m = dict(load("low_pr.json")); m["event_type"] = "merge"
r = Local().invoke(m)
check("merge updates graph", r.get("graph_updated") is True)
check("merge made no LLM call", "llm_status" not in r)

# =====================================================================
print("\n[8] Payload completeness")
# =====================================================================
llm.LLM_ENABLED = False
st = run(load("critical_financial_schema.json"))
pl = build_payload(st)
for k in ("changed_files", "affected_services", "dependency_paths", "api_consumers",
          "schema_impacts", "affected_tests", "owning_contacts", "rule_severity",
          "graph_coverage", "warnings"):
    check(f"payload has {k}", k in pl and pl[k] is not None)
check("payload carries patch text", pl["changed_files"][0]["patch"] == "schema column removed")

print("\n" + "=" * 62)
print(f"PASSED {len(PASS)}   FAILED {len(FAIL)}")
if FAIL:
    print("FAILING:", FAIL)
print("=" * 62)
