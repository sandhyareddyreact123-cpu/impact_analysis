"""Provider-neutral pull-request access backed by GitHub and Azure DevOps REST APIs."""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from .exceptions import ProviderException


@dataclass(frozen=True)
class PRContext:
    repository: str
    pr_number: int
    author: str = ""
    title: str = ""
    source_branch: str = ""
    target_branch: str = ""
    commit_sha: str = ""


@dataclass(frozen=True)
class ProviderChangedFile:
    path: str
    change_type: str = "modified"
    old_path: str | None = None
    patch: str = ""


@dataclass(frozen=True)
class CommitDetails:
    sha: str
    message: str = ""
    author: str = ""
    timestamp: str = ""


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...
    def post(self, url: str, **kwargs: Any) -> Any: ...
    def put(self, url: str, **kwargs: Any) -> Any: ...


class GitProviderAdapter(ABC):
    @abstractmethod
    def get_pr_metadata(self, repository: str, pr_number: int) -> PRContext: ...

    @abstractmethod
    def get_changed_files(self, repository: str, pr_number: int) -> list[ProviderChangedFile]: ...

    @abstractmethod
    def get_diff(self, repository: str, pr_number: int) -> str: ...

    @abstractmethod
    def get_commit_details(self, repository: str, commit_sha: str) -> CommitDetails: ...


class _RestAdapter(GitProviderAdapter):
    provider_name = "Git provider"

    def __init__(self, client: HttpClient | None = None, timeout: float = 15.0) -> None:
        self.client = client or httpx.Client(timeout=timeout)

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = getattr(self.client, method.lower())(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                detail = response.json().get("message", response.text)
                if response.status_code == 404 and self.provider_name == "GitHub":
                    detail = "Repository not found or the token cannot access it; verify owner/repository and token repository permissions"
                if response.status_code == 403 and self.provider_name == "GitHub":
                    detail = "Token accepted but lacks write access; grant Pull requests read/write permission and approve SSO if required"
                if response.status_code == 422 and self.provider_name == "GitHub":
                    detail = f"GitHub rejected the review: {detail}. You cannot approve your own PR, and the token user must be allowed to review this repository"
                raise ProviderException(f"{self.provider_name} request failed ({response.status_code}): {detail}", response.status_code) from exc
            raise ProviderException(f"{self.provider_name} request failed: {exc}") from exc

    def _get(self, url: str, **kwargs: Any) -> Any:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs: Any) -> Any:
        return self._request("POST", url, **kwargs)

    def _put(self, url: str, **kwargs: Any) -> Any:
        return self._request("PUT", url, **kwargs)


class GitHubAdapter(_RestAdapter):
    provider_name = "GitHub"
    api_url = "https://api.github.com"

    def __init__(self, token: str, client: HttpClient | None = None,
                 api_url: str = api_url, timeout: float = 15.0) -> None:
        super().__init__(client, timeout)
        self.api_url = api_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def get_pr_metadata(self, repository: str, pr_number: int) -> PRContext:
        data = self._get(f"{self.api_url}/repos/{repository}/pulls/{pr_number}", headers=self.headers).json()
        return PRContext(repository=repository, pr_number=pr_number,
                         author=str(data.get("user", {}).get("login", "")), title=str(data.get("title", "")),
                         source_branch=str(data.get("head", {}).get("ref", "")),
                         target_branch=str(data.get("base", {}).get("ref", "")),
                         commit_sha=str(data.get("head", {}).get("sha", "")))

    def get_authenticated_user(self) -> str:
        data = self._get(f"{self.api_url}/user", headers=self.headers).json()
        return str(data.get("login", ""))

    def get_open_pull_requests(self, repository: str) -> list[dict[str, Any]]:
        response = self._get(f"{self.api_url}/repos/{repository}/pulls", headers=self.headers,
                             params={"state": "open", "per_page": 100})
        return [{"number": item.get("number"), "title": item.get("title", ""),
                 "author": item.get("user", {}).get("login", ""),
                 "source_branch": item.get("head", {}).get("ref", ""),
                 "target_branch": item.get("base", {}).get("ref", "")}
                for item in response.json()]

    def get_pull_request_workspace(self, repository: str, pr_number: int) -> dict[str, Any]:
        context = self.get_pr_metadata(repository, pr_number)
        viewer = self.get_authenticated_user()
        files = []
        for changed_file in self.get_changed_files(repository, pr_number):
            content = ""
            sha = ""
            if changed_file.change_type != "deleted":
                response = self._get(
                    f"{self.api_url}/repos/{repository}/contents/{quote(changed_file.path, safe='/')}",
                    headers=self.headers, params={"ref": context.source_branch})
                data = response.json()
                sha = str(data.get("sha", ""))
                encoded = data.get("content", "").replace("\n", "")
                content = base64.b64decode(encoded).decode("utf-8") if encoded else ""
            files.append({"path": changed_file.path, "change_type": changed_file.change_type,
                          "old_path": changed_file.old_path, "patch": changed_file.patch,
                          "content": content, "sha": sha})
        return {"repository": repository, "pr_number": pr_number, "title": context.title,
                "author": context.author, "source_branch": context.source_branch,
                "target_branch": context.target_branch, "commit_sha": context.commit_sha,
            "viewer": viewer, "can_review": bool(viewer and viewer.lower() != context.author.lower()),
            "files": files}

    def update_pull_request_file(self, repository: str, pr_number: int, path: str,
                                 content: str, message: str) -> dict[str, Any]:
        context = self.get_pr_metadata(repository, pr_number)
        current = self._get(
            f"{self.api_url}/repos/{repository}/contents/{quote(path, safe='/')}",
            headers=self.headers, params={"ref": context.source_branch}).json()
        response = self._put(
            f"{self.api_url}/repos/{repository}/contents/{quote(path, safe='/')}",
            headers=self.headers,
            json={"message": message, "content": base64.b64encode(content.encode()).decode(),
                  "branch": context.source_branch, "sha": current.get("sha")})
        data = response.json()
        return {"path": path, "commit_sha": data.get("commit", {}).get("sha", ""),
                "branch": context.source_branch}

    def merge_pull_request(self, repository: str, pr_number: int,
                           merge_method: str = "merge") -> dict[str, Any]:
        response = self._put(
            f"{self.api_url}/repos/{repository}/pulls/{pr_number}/merge",
            headers=self.headers, json={"merge_method": merge_method})
        return response.json()

    def post_pull_request_comment(self, repository: str, pr_number: int, body: str) -> dict[str, Any]:
        response = self._post(
            f"{self.api_url}/repos/{repository}/issues/{pr_number}/comments",
            headers=self.headers, json={"body": body})
        data = response.json()
        return {"id": data.get("id"), "html_url": data.get("html_url"), "posted": True}

    def review_pull_request(self, repository: str, pr_number: int, event: str,
                            body: str = "") -> dict[str, Any]:
        if event not in {"APPROVE", "REQUEST_CHANGES"}:
            raise ValueError("Review event must be APPROVE or REQUEST_CHANGES")
        response = self._post(
            f"{self.api_url}/repos/{repository}/pulls/{pr_number}/reviews",
            headers=self.headers, json={"event": event, "body": body})
        data = response.json()
        return {"id": data.get("id"), "state": data.get("state"), "html_url": data.get("html_url"),
                "event": event}

    def get_changed_files(self, repository: str, pr_number: int) -> list[ProviderChangedFile]:
        files: list[ProviderChangedFile] = []
        page = 1
        while True:
            response = self._get(f"{self.api_url}/repos/{repository}/pulls/{pr_number}/files",
                                 headers=self.headers, params={"per_page": 100, "page": page})
            items = response.json()
            if not items:
                return files
            files.extend(ProviderChangedFile(path=item["filename"],
                                              change_type=item.get("status", "modified"),
                                              old_path=item.get("previous_filename"),
                                              patch=item.get("patch", "")) for item in items)
            if len(items) < 100:
                return files
            page += 1

    def get_diff(self, repository: str, pr_number: int) -> str:
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        return self._get(f"{self.api_url}/repos/{repository}/pulls/{pr_number}", headers=headers).text

    def get_commit_details(self, repository: str, commit_sha: str) -> CommitDetails:
        data = self._get(f"{self.api_url}/repos/{repository}/commits/{commit_sha}", headers=self.headers).json()
        commit = data.get("commit", {})
        return CommitDetails(sha=str(data.get("sha", commit_sha)), message=str(commit.get("message", "")),
                             author=str(commit.get("author", {}).get("name", "")),
                             timestamp=str(commit.get("author", {}).get("date", "")))


class AzureDevOpsAdapter(_RestAdapter):
    provider_name = "Azure DevOps"

    def __init__(self, organization_url: str, project: str, token: str,
                 client: HttpClient | None = None, timeout: float = 15.0) -> None:
        super().__init__(client, timeout)
        encoded = base64.b64encode(f":{token}".encode()).decode()
        self.base_url = f"{organization_url.rstrip('/')}/{project}"
        self.headers = {"Authorization": f"Basic {encoded}"}
        self.api_version = "7.1"

    def _azure_get(self, path: str, **params: Any) -> Any:
        params["api-version"] = self.api_version
        return self._get(f"{self.base_url}/_apis/git/{path.lstrip('/')}", headers=self.headers, params=params).json()

    @staticmethod
    def _repository_path(repository: str) -> str:
        return quote(repository, safe="")

    def get_pr_metadata(self, repository: str, pr_number: int) -> PRContext:
        repository_path = self._repository_path(repository)
        data = self._azure_get(f"repositories/{repository_path}/pullRequests/{pr_number}")
        return PRContext(repository=repository, pr_number=pr_number,
                         author=str(data.get("createdBy", {}).get("displayName", "")),
                         title=str(data.get("title", "")),
                         source_branch=str(data.get("sourceRefName", "")).removeprefix("refs/heads/"),
                         target_branch=str(data.get("targetRefName", "")).removeprefix("refs/heads/"),
                         commit_sha=str(data.get("lastMergeSourceCommit", {}).get("commitId", "")))

    def get_changed_files(self, repository: str, pr_number: int) -> list[ProviderChangedFile]:
        repository = self._repository_path(repository)
        iterations = self._azure_get(f"repositories/{repository}/pullRequests/{pr_number}/iterations").get("value", [])
        if not iterations:
            return []
        iteration = iterations[-1]["id"]
        data = self._azure_get(f"repositories/{repository}/pullRequests/{pr_number}/iterations/{iteration}/changes",
                       **{"$top": 2000})
        output = []
        for item in data.get("changeEntries", data.get("value", [])):
            change = item.get("change", item)
            change_type = str(item.get("changeType", change.get("changeType", "edit"))).lower()
            path = change.get("item", {}).get("path", change.get("path", ""))
            output.append(ProviderChangedFile(path=str(path).lstrip("/"),
                                              change_type={"add": "added", "edit": "modified", "delete": "deleted", "rename": "renamed"}.get(change_type, "modified")))
        return output

    def get_diff(self, repository: str, pr_number: int) -> str:
        context = self.get_pr_metadata(repository, pr_number)
        repository = self._repository_path(repository)
        data = self._azure_get(f"repositories/{repository}/diffs/commits",
                               baseVersion=context.target_branch, targetVersion=context.source_branch)
        return "\n".join(f"diff --git a/{item.get('item', {}).get('path', '').lstrip('/')} b/{item.get('item', {}).get('path', '').lstrip('/') }"
                         for item in data.get("changes", []))

    def get_commit_details(self, repository: str, commit_sha: str) -> CommitDetails:
        repository = self._repository_path(repository)
        data = self._azure_get(f"repositories/{repository}/commits/{commit_sha}")
        return CommitDetails(sha=str(data.get("commitId", commit_sha)), message=str(data.get("comment", "")),
                             author=str(data.get("author", {}).get("name", "")),
                             timestamp=str(data.get("author", {}).get("date", "")))
