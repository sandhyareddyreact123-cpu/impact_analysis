"""Analyze unified diffs into provider-independent changed components."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Iterable

from .git_adapter import ProviderChangedFile
from .exceptions import DiffAnalysisException



@dataclass(frozen=True)
class Evidence:
    file_path: str
    line_number: int = 0
    change_type: str = "modified"


@dataclass(frozen=True)
class ChangedFile:
    path: str
    change_type: str
    old_path: str | None = None
    patch: str = ""


@dataclass(frozen=True)
class ChangedSymbol:
    name: str
    evidence: Evidence


@dataclass(frozen=True)
class ApiEndpoint:
    path: str
    method: str
    evidence: Evidence


@dataclass(frozen=True)
class DataModel:
    name: str
    evidence: Evidence


@dataclass(frozen=True)
class SharedLibrary:
    name: str
    evidence: Evidence


@dataclass(frozen=True)
class ConfigurationChange:
    file: str
    evidence: Evidence


@dataclass
class AnalysisResult:
    files: list[ChangedFile] = field(default_factory=list)
    functions: list[ChangedSymbol] = field(default_factory=list)
    classes: list[ChangedSymbol] = field(default_factory=list)
    methods: list[ChangedSymbol] = field(default_factory=list)
    endpoints: list[ApiEndpoint] = field(default_factory=list)
    models: list[DataModel] = field(default_factory=list)
    shared_libraries: list[SharedLibrary] = field(default_factory=list)
    configurations: list[ConfigurationChange] = field(default_factory=list)


class DiffAnalyzer:
    CONFIG_EXTENSIONS = {".yaml", ".yml", ".json", ".toml", ".ini", ".env", ".properties"}
    LIBRARY_PARTS = {"shared", "common", "libs", "utils", "packages", "sdk"}
    ENDPOINT_RE = re.compile(r"(?:@(?:app|router)\.(get|post|put|patch|delete|route)\s*\(\s*[\"']([^\"']+)|@(Get|Post|Put|Patch|Delete)Mapping\s*\(\s*[\"']?([^\"')]+))", re.I)

    def analyze(self, diff: str, changed_files: Iterable[ProviderChangedFile | ChangedFile] | None = None) -> AnalysisResult:
        try:
            files = self._files(diff, changed_files)
            result = AnalysisResult(files=files)
            for item in files:
                if self._is_config(item.path):
                    result.configurations.append(ConfigurationChange(item.path, Evidence(item.path, 1, item.change_type)))
                parts = set(item.path.replace("\\", "/").split("/"))
                if parts & self.LIBRARY_PARTS:
                    result.shared_libraries.append(SharedLibrary(parts & self.LIBRARY_PARTS and next(iter(parts & self.LIBRARY_PARTS)) or item.path, Evidence(item.path, 1, item.change_type)))
                self._analyze_content(item, result)
            return result
        except (SyntaxError, UnicodeError) as exc:
            raise DiffAnalysisException("Unable to analyze source diff") from exc

    def _files(self, diff: str, changed_files: Iterable[ProviderChangedFile | ChangedFile] | None) -> list[ChangedFile]:
        if changed_files is not None:
            return [ChangedFile(f.path, f.change_type, getattr(f, "old_path", None), getattr(f, "patch", "")) for f in changed_files]
        output: list[ChangedFile] = []
        current: ChangedFile | None = None
        chunks: list[str] = []
        for line in diff.splitlines():
            match = re.match(r"diff --git a/(.+) b/(.+)", line)
            if match:
                if current:
                    output.append(ChangedFile(current.path, current.change_type, current.old_path, "\n".join(chunks)))
                current, chunks = ChangedFile(match.group(2), "modified"), []
            elif current:
                chunks.append(line)
                if line.startswith("new file mode"):
                    current = ChangedFile(current.path, "added", current.old_path)
                elif line.startswith("deleted file mode"):
                    current = ChangedFile(current.path, "deleted", current.old_path)
                elif line.startswith("rename from"):
                    current = ChangedFile(current.path, "renamed", line.removeprefix("rename from "))
        if current:
            output.append(ChangedFile(current.path, current.change_type, current.old_path, "\n".join(chunks)))
        return output

    def _analyze_content(self, item: ChangedFile, result: AnalysisResult) -> None:
        lines = item.patch.splitlines()
        added = [(index, line[1:]) for index, line in enumerate(lines, 1) if line.startswith("+") and not line.startswith("+++")]
        source = "\n".join(text for _, text in added)
        if item.path.endswith(".py") and source:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                tree = None
            if tree is not None:
                evidence = Evidence(item.path, next((line for line, text in added if text.strip()), 1), item.change_type)

                class Visitor(ast.NodeVisitor):
                    class_depth = 0

                    def visit_ClassDef(self, node: ast.ClassDef) -> None:
                        result.classes.append(ChangedSymbol(node.name, evidence))
                        self.class_depth += 1
                        for child in node.body:
                            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                result.methods.append(ChangedSymbol(child.name, evidence))
                        self.generic_visit(node)
                        self.class_depth -= 1

                    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                        if self.class_depth == 0:
                            result.functions.append(ChangedSymbol(node.name, evidence))
                        self.generic_visit(node)

                    visit_AsyncFunctionDef = visit_FunctionDef

                Visitor().visit(tree)
        for index, text in added:
            for match in self.ENDPOINT_RE.finditer(text):
                method = (match.group(1) or match.group(3) or "").upper()
                path = match.group(2) or match.group(4) or ""
                if method == "ROUTE":
                    method = "ANY"
                result.endpoints.append(ApiEndpoint(path, method, Evidence(item.path, index, item.change_type)))
            model = re.search(r"\bclass\s+(\w+)(?:\([^)]*(?:Base|Model|Entity|models\.Model)[^)]*\))", text)
            if model:
                result.models.append(DataModel(model.group(1), Evidence(item.path, index, item.change_type)))

    @classmethod
    def _is_config(cls, path: str) -> bool:
        lower = path.lower()
        return lower.endswith(tuple(cls.CONFIG_EXTENSIONS)) or lower.rsplit("/", 1)[-1] in {".env", "docker-compose.yml"}