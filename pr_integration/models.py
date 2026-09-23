from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PRAnalysisMetadata:
    repository: str
    pr_number: int
    provider: str
    source_branch: str
    target_branch: str
    commit_sha: str
    correlation_id: str


@dataclass
class PRAnalysisInput:
    metadata: PRAnalysisMetadata
    changed_files: list[Any] = field(default_factory=list)
    changed_functions: list[Any] = field(default_factory=list)
    changed_classes: list[Any] = field(default_factory=list)
    changed_methods: list[Any] = field(default_factory=list)
    changed_endpoints: list[Any] = field(default_factory=list)
    changed_models: list[Any] = field(default_factory=list)
    changed_libraries: list[Any] = field(default_factory=list)
    configuration_changes: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def serialize(value: Any) -> Any:
            if hasattr(value, "__dataclass_fields__"):
                return {key: serialize(item) for key, item in value.__dict__.items()}
            if isinstance(value, list):
                return [serialize(item) for item in value]
            if isinstance(value, dict):
                return {key: serialize(item) for key, item in value.items()}
            return value

        output = serialize(self.metadata)
        output.update({
            "changed_files": serialize(self.changed_files),
            "changed_functions": serialize(self.changed_functions),
            "changed_classes": serialize(self.changed_classes),
            "changed_methods": serialize(self.changed_methods),
            "changed_endpoints": serialize(self.changed_endpoints),
            "changed_models": serialize(self.changed_models),
            "changed_libraries": serialize(self.changed_libraries),
            "configuration_changes": serialize(self.configuration_changes),
        })
        return output
