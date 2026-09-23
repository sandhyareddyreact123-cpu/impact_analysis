from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from .change_classifier import ChangeClassifier
from .diff_analyzer import DiffAnalyzer
from .exceptions import DuplicateEventException
from .git_adapter import GitProviderAdapter
from .idempotency import IdempotencyStore
from .models import PRAnalysisInput, PRAnalysisMetadata
from .webhook_listener import ValidatedPREvent
from agent.tools import resolve_service


class PRAnalysisService:
    def __init__(self, listener: Any, idempotency_store: IdempotencyStore,
                 adapters: Mapping[str, GitProviderAdapter],
                 analyzer: DiffAnalyzer | None = None,
                 classifier: ChangeClassifier | None = None,
                 workflow: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.listener = listener
        self.idempotency_store = idempotency_store
        self.adapters = adapters
        self.analyzer = analyzer or DiffAnalyzer()
        self.classifier = classifier or ChangeClassifier()
        self.workflow = workflow

    def process(self, payload: Mapping[str, Any], headers: Mapping[str, str],
                provider: str, raw_body: bytes | None = None) -> dict[str, Any]:
        event = self.listener.validate(payload, headers, provider, raw_body=raw_body, reserve=False)
        if self.idempotency_store.is_processed(event.event_id, event.commit_sha, event.pr_number):
            raise DuplicateEventException("Pull-request event was already processed")
        adapter = self.adapters.get(event.provider)
        if adapter is None:
            raise ValueError(f"No adapter configured for provider: {event.provider}")
        result = self.analyze_pr(event.provider, event.repository, event.pr_number,
                                 source_branch=event.source_branch,
                                 target_branch=event.target_branch,
                                 commit_sha=event.commit_sha,
                                 correlation_id=event.correlation_id)
        self.idempotency_store.mark_processed(event.event_id, event.commit_sha, event.pr_number)
        return result

    def analyze_pr(self, provider: str, repository: str, pr_number: int,
                   source_branch: str = "", target_branch: str = "", commit_sha: str = "",
                   correlation_id: str = "") -> dict[str, Any]:
        started_at = time.perf_counter()
        adapter = self.adapters.get(provider)
        if adapter is None:
            raise ValueError(f"No adapter configured for provider: {provider}")
        context = adapter.get_pr_metadata(repository, pr_number)
        changed_files = adapter.get_changed_files(repository, pr_number)
        diff = adapter.get_diff(repository, pr_number)
        analysis = self.analyzer.analyze(diff, changed_files)
        inventory = self.classifier.classify(analysis)
        metadata = PRAnalysisMetadata(
            repository=context.repository,
            pr_number=context.pr_number,
            provider=provider,
            source_branch=context.source_branch or source_branch,
            target_branch=context.target_branch or target_branch,
            commit_sha=context.commit_sha or commit_sha,
            correlation_id=correlation_id or f"{repository}:{pr_number}:{context.commit_sha or commit_sha}",
        )
        analysis_input = PRAnalysisInput(
            metadata=metadata,
            changed_files=inventory.files,
            changed_functions=inventory.functions,
            changed_classes=inventory.classes,
            changed_methods=inventory.methods,
            changed_endpoints=inventory.endpoints,
            changed_models=inventory.models,
            changed_libraries=inventory.shared_libraries,
            configuration_changes=inventory.configurations,
        )
        analysis_input_dict = analysis_input.to_dict()
        for changed_file in analysis_input_dict["changed_files"]:
            changed_file["service"] = resolve_service(changed_file.get("path", ""))
        workflow_result = (self.workflow(analysis_input_dict) or {}) if self.workflow else {}
        runtime = round(time.perf_counter() - started_at, 5)
        workflow_result["elapsed_seconds"] = runtime
        return {"accepted": True, "duplicate": False, "analysis_input": analysis_input_dict,
            "workflow": workflow_result, "elapsed_seconds": runtime}
