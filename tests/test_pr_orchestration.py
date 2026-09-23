from pr_integration.diff_analyzer import DiffAnalyzer
from pr_integration.git_adapter import PRContext, ProviderChangedFile
from pr_integration.idempotency import InMemoryIdempotencyStore
from pr_integration.orchestration import PRAnalysisService
from pr_integration.webhook_listener import WebhookListener


class FakeAdapter:
    def get_pr_metadata(self, repository, pr_number):
        return PRContext(repository, pr_number, "developer", "Auth", "feature/auth", "main", "sha-1")

    def get_changed_files(self, repository, pr_number):
        return [ProviderChangedFile("services/auth.py", "modified", patch="+def login():\n+    return True")]

    def get_diff(self, repository, pr_number):
        return ""

    def get_commit_details(self, repository, commit_sha):
        return {"sha": commit_sha}


def test_orchestration_builds_downstream_contract():
    payload = {
        "action": "opened",
        "number": 12,
        "repository": {"full_name": "sample-api"},
        "pull_request": {"head": {"ref": "feature/auth", "sha": "sha-1"}, "base": {"ref": "main"}},
    }
    captured = []
    service = PRAnalysisService(WebhookListener(), InMemoryIdempotencyStore(), {"github": FakeAdapter()},
                                analyzer=DiffAnalyzer(), workflow=captured.append)
    result = service.process(payload, {"x-github-event": "pull_request"}, "github")
    assert result["analysis_input"]["repository"] == "sample-api"
    assert result["analysis_input"]["changed_functions"][0]["name"] == "login"
    assert result["analysis_input"]["correlation_id"]
    assert captured[0]["pr_number"] == 12