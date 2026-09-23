from __future__ import annotations

from abc import ABC, abstractmethod


class IdempotencyStore(ABC):
    @abstractmethod
    def is_processed(self, event_id: str, commit_sha: str, pr_number: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def mark_processed(self, event_id: str, commit_sha: str, pr_number: int) -> None:
        raise NotImplementedError


class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self) -> None:
        self._event_keys: set[tuple[str, str, int]] = set()
        self._commit_keys: set[tuple[str, int]] = set()

    def is_processed(self, event_id: str, commit_sha: str, pr_number: int) -> bool:
        return ((event_id, commit_sha, pr_number) in self._event_keys
                or (commit_sha, pr_number) in self._commit_keys)

    def mark_processed(self, event_id: str, commit_sha: str, pr_number: int) -> None:
        self._event_keys.add((event_id, commit_sha, pr_number))
        self._commit_keys.add((commit_sha, pr_number))
