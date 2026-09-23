"""Convert diff analysis into the stable downstream inventory contract."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .diff_analyzer import AnalysisResult, Evidence


@dataclass(frozen=True)
class InventoryItem:
    name: str
    evidence: Evidence


@dataclass
class ChangedComponentInventory:
    files: list[Any] = field(default_factory=list)
    functions: list[Any] = field(default_factory=list)
    classes: list[Any] = field(default_factory=list)
    methods: list[Any] = field(default_factory=list)
    endpoints: list[Any] = field(default_factory=list)
    models: list[Any] = field(default_factory=list)
    shared_libraries: list[Any] = field(default_factory=list)
    configurations: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def serialize(value: Any) -> Any:
            if hasattr(value, "__dataclass_fields__"):
                return {key: serialize(item) for key, item in asdict(value).items()}
            if isinstance(value, list):
                return [serialize(item) for item in value]
            if isinstance(value, dict):
                return {key: serialize(item) for key, item in value.items()}
            return value
        return {
            "changed_files": serialize(self.files),
            "changed_functions": serialize(self.functions),
            "changed_classes": serialize(self.classes),
            "changed_methods": serialize(self.methods),
            "changed_endpoints": serialize(self.endpoints),
            "changed_models": serialize(self.models),
            "changed_libraries": serialize(self.shared_libraries),
            "configuration_changes": serialize(self.configurations),
        }


class ChangeClassifier:
    def classify(self, analysis: AnalysisResult) -> ChangedComponentInventory:
        return ChangedComponentInventory(
            files=analysis.files,
            functions=analysis.functions,
            classes=analysis.classes,
            methods=analysis.methods,
            endpoints=analysis.endpoints,
            models=analysis.models,
            shared_libraries=analysis.shared_libraries,
            configurations=analysis.configurations,
        )


def classify(analysis: AnalysisResult) -> ChangedComponentInventory:
    return ChangeClassifier().classify(analysis)


__all__ = ["ChangeClassifier", "ChangedComponentInventory", "classify", "InventoryItem"]