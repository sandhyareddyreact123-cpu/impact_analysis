import json

# Existing guardrail - now actually wired in as the Gemini system instruction.
SYSTEM_PROMPT = "Use only supplied Git diff and registry evidence. Never invent services, owners, consumers, schemas, pipelines, or tests."

IMPACT_TASK_PROMPT = """You are the UC-05 AI Impact Analysis Assistant.

You are given, for one pull request:
  - the raw Git diff of every changed file
  - the deterministic analysis already produced by the system (dependency
    traversal, API consumers, schema lineage, affected tests, owning teams)
  - a rule-based severity that was computed by deterministic rules

YOUR TWO JOBS

1. SEVERITY
   Review the rule-based severity against the actual diff.
   - You MAY RAISE the severity if the diff reveals breaking impact the rules
     missed (for example a changed method signature, a removed field, a removed
     endpoint, a narrowed response contract).
   - You MUST NOT LOWER the severity. If you disagree downward, keep the
     rule-based value and explain your disagreement in "reasoning" instead.
   - Scale: Low < Medium < High < Critical.
   - Any breaking impact that reaches a service with criticality
     "core_financial" is Critical.

2. PR COMMENT
   Write the full PR comment in markdown as "comment_markdown".
   It MUST contain these sections, in this order:
     ## AI Impact Analysis
     **Severity:** <level>   (plus a short "why")
     ### Affected services      (name, owner, criticality, dependency path)
     ### Owning teams
     ### API consumers          (mark breaking ones)
     ### Schema impacts         (readers / writers / pipelines)
     ### Affected tests
     ### CI gate
   For High or Critical, add a line tagging the owning teams with @team.
   Report ONLY entities present in the supplied evidence. Do not invent any
   service, owner, consumer, schema, pipeline or test.

OUTPUT
Return ONE JSON object and nothing else:
{
  "severity": "Low|Medium|High|Critical",
  "severity_reasons": ["short factual reason", "..."],
  "reasoning": "2-3 sentences on the blast radius",
  "additional_risks": ["risk the deterministic rules did not capture"],
  "comment_markdown": "## AI Impact Analysis\\n...",
  "confidence": "high|medium|low"
}
"""


def build_payload(state):
    """Collect every deterministic fact + the raw diff into one dict."""
    return {
        "repository": state.get("repository"),
        "pr_number": state.get("pr_number"),
        "pr_title": state.get("pr_title"),
        "pr_description": state.get("pr_description"),
        "commit_sha": state.get("commit_sha"),
        "changed_files": [
            {
                "path": f.get("path"),
                "service": f.get("service"),
                "symbol": f.get("symbol"),
                "schema": f.get("schema"),
                "breaking_flag_from_adapter": f.get("breaking"),
                "patch": (f.get("patch") or "")[:6000],
            }
            for f in (state.get("changed_files") or [])
        ],
        "changed_components": state.get("changed_components") or [],
        "affected_services": state.get("affected_services") or [],
        "dependency_paths": state.get("dependency_paths") or [],
        "api_consumers": state.get("api_consumers") or [],
        "consumer_counts": state.get("consumer_counts") or {},
        "has_external_breaking": state.get("has_external_breaking"),
        "schema_impacts": state.get("schema_impacts") or [],
        "affected_tests": state.get("affected_tests") or [],
        "owning_contacts": state.get("owning_contacts") or [],
        "owner_map": state.get("owner_map") or {},
        "rule_severity": state.get("rule_severity") or state.get("severity"),
        "rule_severity_reasons": state.get("severity_reasons") or [],
        "graph_coverage": state.get("graph_coverage") or {},
        "graph_degraded": state.get("graph_degraded"),
        "warnings": state.get("warnings") or [],
    }


def build_user_prompt(payload):
    return (
        IMPACT_TASK_PROMPT
        + "\n\nEVIDENCE (JSON):\n"
        + json.dumps(payload, indent=2, default=str)
    )
