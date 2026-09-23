import json
import os
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent.graph import agent
from pr_integration.git_adapter import AzureDevOpsAdapter, GitHubAdapter
from pr_integration.idempotency import InMemoryIdempotencyStore
from pr_integration.orchestration import PRAnalysisService
from pr_integration.exceptions import ProviderException
from pr_integration.webhook_listener import DuplicateEventException, WebhookError, WebhookListener

router = APIRouter(tags=["PR integration"])
idempotency_store = InMemoryIdempotencyStore()
listener = WebhookListener(secret=os.getenv("GITHUB_WEBHOOK_SECRET"),
                           token=os.getenv("AZURE_DEVOPS_WEBHOOK_TOKEN"),
                           idempotency_store=idempotency_store)


def _build_service() -> PRAnalysisService:
    adapters = {}
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        adapters["github"] = GitHubAdapter(github_token, api_url=os.getenv("GITHUB_API_URL", "https://api.github.com"))
    azure_token = os.getenv("AZURE_DEVOPS_TOKEN") or os.getenv("AZURE_DEVOPS_PAT")
    azure_org = os.getenv("AZURE_DEVOPS_ORG_URL")
    azure_project = os.getenv("AZURE_DEVOPS_PROJECT")
    if azure_token and azure_org and azure_project:
        adapters["azure_devops"] = AzureDevOpsAdapter(azure_org, azure_project, azure_token)
        adapters["azure"] = adapters["azure_devops"]
    return PRAnalysisService(listener, idempotency_store, adapters,
                             workflow=lambda payload: agent.invoke(payload))


service = _build_service()


@router.get("/integration/status")
def integration_status() -> dict[str, Any]:
    github_token_configured = bool(os.getenv("GITHUB_TOKEN"))
    github_webhook_configured = bool(github_token_configured and os.getenv("GITHUB_WEBHOOK_SECRET"))
    azure_configured = bool(
        (os.getenv("AZURE_DEVOPS_TOKEN") or os.getenv("AZURE_DEVOPS_PAT"))
        and os.getenv("AZURE_DEVOPS_WEBHOOK_TOKEN")
        and os.getenv("AZURE_DEVOPS_ORG_URL")
        and os.getenv("AZURE_DEVOPS_PROJECT")
    )
    return {
        "github": {
            "configured": github_webhook_configured,
            "manual_analysis_configured": github_token_configured,
            "webhook_path": "/webhooks/github/pull-request",
            "manual_analysis_path": "/integration/github/pull-request",
        },
        "azure_devops": {"configured": azure_configured, "webhook_path": "/webhooks/azure_devops/pull-request"},
        "last_event": None,
    }


class WebhookRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    provider: str = "github"


class ManualPRRequest(BaseModel):
    repository: str
    pr_number: int = Field(gt=0)


class HostedFileUpdateRequest(ManualPRRequest):
    path: str
    content: str
    message: str = "Update file from impact analysis assistant"


class HostedMergeRequest(ManualPRRequest):
    merge_method: str = "merge"


class HostedReviewRequest(ManualPRRequest):
    event: str
    body: str = ""


def _github_repository(value: str) -> str:
    repository = value.strip().rstrip("/")
    if repository.startswith("http://") or repository.startswith("https://"):
        parsed = urlparse(repository)
        repository = parsed.path.strip("/")
    if repository.endswith(".git"):
        repository = repository[:-4]
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("Use a GitHub repository as owner/repository or paste its GitHub URL")
    return "/".join(parts)


@router.post("/integration/github/pull-request")
def analyze_github_pull_request(request: ManualPRRequest) -> dict[str, Any]:
    """Analyze a GitHub PR directly using the token, without a webhook."""
    try:
        repository = _github_repository(request.repository)
        result = service.analyze_pr("github", repository, request.pr_number)
        analysis = result.get("workflow", {})
        comment = f"## AI Impact Analysis\n\n**Severity:** {analysis.get('severity', 'Unknown')}\n\n{analysis.get('comment_markdown', '')}"
        adapter = service.adapters["github"]
        result["comment"] = adapter.post_pull_request_comment(repository, request.pr_number, comment)
        return result
    except (ValueError, TypeError, WebhookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/integration/github/pull-requests")
def list_github_pull_requests(repository: str) -> dict[str, Any]:
    """List open GitHub PRs directly using the configured token."""
    adapter = service.adapters.get("github")
    if adapter is None:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    try:
        repository = _github_repository(repository)
        return {"repository": repository, "pull_requests": adapter.get_open_pull_requests(repository)}
    except (ValueError, TypeError, WebhookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
        


@router.post("/webhooks/{provider}/pull-request")
async def receive_pull_request_webhook(
    request: Request,
    provider: str,
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    x_event_type: str | None = Header(default=None),
    x_event_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    try:
        raw_body = await request.body()
        payload = json.loads(raw_body)
        headers = {key: value for key, value in {
            "x-github-event": x_github_event,
            "x-github-delivery": x_github_delivery,
            "x-hub-signature-256": x_hub_signature_256,
            "x-event-type": x_event_type,
            "x-event-id": x_event_id,
            "authorization": authorization,
        }.items() if value is not None}
        result = service.process(payload, headers, provider, raw_body=raw_body)
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=result)
    except DuplicateEventException as exc:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                            content={"accepted": False, "duplicate": True, "detail": str(exc)})
    except (WebhookError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/integration/github/pull-request")
def get_github_pull_request_workspace(repository: str, pr_number: int = 0) -> dict[str, Any]:
    adapter = service.adapters.get("github")
    if adapter is None:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    try:
        return adapter.get_pull_request_workspace(_github_repository(repository), pr_number)
    except (ValueError, TypeError, WebhookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integration/github/pull-request/update")
def update_github_pull_request_file(request: HostedFileUpdateRequest) -> dict[str, Any]:
    adapter = service.adapters.get("github")
    if adapter is None:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    try:
        return adapter.update_pull_request_file(_github_repository(request.repository), request.pr_number,
                                               request.path, request.content, request.message)
    except (ValueError, TypeError, WebhookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integration/github/pull-request/merge")
def merge_github_pull_request(request: HostedMergeRequest) -> dict[str, Any]:
    adapter = service.adapters.get("github")
    if adapter is None:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    try:
        repository = _github_repository(request.repository)
        merged = adapter.merge_pull_request(repository, request.pr_number, request.merge_method)
        refresh = agent.invoke({
            "event_id": f"merge-{repository}-{request.pr_number}", "event_type": "merge",
            "repository": repository, "pr_number": request.pr_number,
            "commit_sha": merged.get("sha", ""), "changed_files": []
        })
        return {**merged, "dependency_graph": refresh,
                "message": refresh.get("graph_refresh_message", "Dependency graph refreshed")}
    except (ValueError, TypeError, WebhookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integration/github/pull-request/review")
def review_github_pull_request(request: HostedReviewRequest) -> dict[str, Any]:
    adapter = service.adapters.get("github")
    if adapter is None:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    try:
        repository = _github_repository(request.repository)
        if request.event == "APPROVE":
            analysis = service.analyze_pr("github", repository, request.pr_number).get("workflow", {})
            if analysis.get("severity") == "Critical":
                raise HTTPException(status_code=409, detail="Critical severity pull requests require additional review and cannot be approved.")
        return adapter.review_pull_request(repository, request.pr_number, request.event, request.body)
    except ProviderException as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    except (ValueError, TypeError, WebhookError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc