"""Validation and idempotency for GitHub and Azure DevOps pull-request events."""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from .exceptions import (DuplicateEventException, InvalidWebhookException,
                          UnsupportedEventException, PRIntegrationError)
from .idempotency import InMemoryIdempotencyStore

logger = logging.getLogger(__name__)

WebhookError = PRIntegrationError


@dataclass(frozen=True)
class ValidatedPREvent:
    provider: str
    repository: str
    pr_number: int
    source_branch: str
    target_branch: str
    commit_sha: str
    event_id: str = ""
    event_type: str = ""
    correlation_id: str = ""


class WebhookListener:
    SUPPORTED = {
        "github": {"pull_request.opened", "pull_request.synchronize", "pull_request.reopened"},
        "azure_devops": {"git.pullrequest.created", "git.pullrequest.updated"},
        "azure": {"git.pullrequest.created", "git.pullrequest.updated"},
    }

    def __init__(self, secret: str | None = None, token: str | None = None,
                 idempotency_store: InMemoryIdempotencyStore | None = None) -> None:
        self.secret = secret
        self.token = token
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()

    def validate(self, payload: Mapping[str, Any], headers: Mapping[str, str] | None = None,
                 provider: str = "github", raw_body: bytes | None = None,
                 reserve: bool = True) -> ValidatedPREvent:
        headers = {key.lower(): value for key, value in (headers or {}).items()}
        provider = provider.lower().replace(" ", "_").replace("-", "_")
        if self.secret and provider == "github":
            signature = headers.get("x-hub-signature-256", "")
            if raw_body is None and payload.get("raw_body") is not None:
                raw_body = str(payload["raw_body"]).encode()
            if raw_body is None or not self._valid_signature(raw_body, signature):
                raise InvalidWebhookException("Invalid GitHub webhook signature")
        if self.token and provider in {"azure", "azure_devops"}:
            supplied = headers.get("authorization", headers.get("x-webhook-token", ""))
            if not hmac.compare_digest(supplied.removeprefix("Bearer "), self.token):
                raise InvalidWebhookException("Invalid Azure DevOps webhook token")
        event_type = self._event_type(payload, headers, provider)
        if event_type not in self.SUPPORTED.get(provider, set()):
            raise UnsupportedEventException(f"Unsupported {provider} event: {event_type}")
        event = self._normalize(payload, headers, provider, event_type)
        if self.idempotency_store.is_processed(event.event_id, event.commit_sha, event.pr_number):
            raise DuplicateEventException("Pull-request event was already processed")
        if reserve:
            self.idempotency_store.mark_processed(event.event_id, event.commit_sha, event.pr_number)
        logger.info("Validated pull-request event", extra={"correlation_id": event.correlation_id})
        return event

    def is_duplicate(self, event: ValidatedPREvent) -> bool:
        return self.idempotency_store.is_processed(event.event_id, event.commit_sha, event.pr_number)

    def _valid_signature(self, body: bytes, supplied: str) -> bool:
        expected = "sha256=" + hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, supplied)

    @staticmethod
    def _event_type(payload: Mapping[str, Any], headers: Mapping[str, str], provider: str) -> str:
        if provider == "github":
            event = headers.get("x-github-event", "pull_request")
            action = str(payload.get("action", ""))
            if event == "pull_request":
                return f"pull_request.{action}"
            return event if event.startswith("pull_request.") else f"pull_request.{event}"
        return headers.get("x-event-type", headers.get("eventtype", str(payload.get("eventType", ""))))

    @staticmethod
    def _normalize(payload: Mapping[str, Any], headers: Mapping[str, str], provider: str,
                   event_type: str) -> ValidatedPREvent:
        if provider == "github":
            pr = payload.get("pull_request", {})
            repo = payload.get("repository", {})
            repository = repo.get("full_name") or repo.get("name")
            number = payload.get("number")
            source = pr.get("head", {}).get("ref")
            target = pr.get("base", {}).get("ref")
            sha = pr.get("head", {}).get("sha")
            event_id = headers.get("x-github-delivery", str(payload.get("event_id", "")))
        else:
            resource = payload.get("resource", payload)
            repository_data = resource.get("repository", {})
            repository = repository_data.get("fullName") or repository_data.get("name")
            number = resource.get("pullRequestId")
            source = resource.get("sourceRefName", "").removeprefix("refs/heads/")
            target = resource.get("targetRefName", "").removeprefix("refs/heads/")
            sha = resource.get("lastMergeSourceCommit", {}).get("commitId") or resource.get("lastMergeCommit", {}).get("commitId")
            event_id = headers.get("x-event-id", str(payload.get("id", payload.get("event_id", ""))))
        if not repository or not number or not source or not target or not sha:
            raise InvalidWebhookException("Webhook lacks repository, PR, branch, or commit information")
        return ValidatedPREvent(provider=provider, repository=str(repository), pr_number=int(number),
                                source_branch=str(source), target_branch=str(target), commit_sha=str(sha),
                                event_id=event_id, event_type=event_type,
                                correlation_id=event_id or f"{repository}:{number}:{sha}")