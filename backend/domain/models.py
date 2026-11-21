"""Pure domain schemas for the AST and graph engine (Spec #01).

Only the standard library and Pydantic v2 are imported. Every model is frozen,
rejects unknown fields, and uses strict scalar types so values such as ``"5"``
or ``True`` are never coerced into integers.
"""

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

__all__ = [
    "BlastRadius",
    "DSAChapter",
    "DSASignal",
    "EdgeType",
    "FileAnalysis",
    "GraphEdge",
    "Language",
    "RelativePath",
    "RepoGraphSnapshot",
    "SymbolKind",
    "SymbolNode",
]


class Language(StrEnum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    TSX = "tsx"
    JAVA = "java"


class SymbolKind(StrEnum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    COMPONENT = "component"


class EdgeType(StrEnum):
    IMPORTS = "imports"
    CALLS = "calls"


DSAChapter = Literal[
    "Hash Tables",
    "Graphs & Trees",
    "Recursion & Dynamic Programming",
    "Sliding Window / Two Pointers",
    "Heaps & Priority Queues",
    "Sorting & Binary Search",
]

_DRIVE_PREFIX = re.compile(r"[A-Za-z]:")
_COLLISION_SUFFIX = re.compile(r"@[0-9]+\Z")


def _check_relative_path(value: str) -> str:
    if not 1 <= len(value) <= 4096:
        raise ValueError("relative path must be 1 to 4096 characters")
    if value.startswith("/"):
        raise ValueError("relative path must not start with '/'")
    if _DRIVE_PREFIX.match(value):
        raise ValueError("relative path must not start with a drive letter")
    if "\\" in value:
        raise ValueError("relative path must not contain a backslash")
    if any(segment in (".", "..") for segment in value.split("/")):
        raise ValueError("relative path must not contain '.' or '..' segments")
    return value


RelativePath = Annotated[StrictStr, AfterValidator(_check_relative_path)]


def _reject_bool(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid number")
    return value


UnitFloat = Annotated[
    float,
    BeforeValidator(_reject_bool),
    Field(strict=True, ge=0.0, le=1.0, allow_inf_nan=False),
]

_CONFIG = ConfigDict(frozen=True, extra="forbid")


class SymbolNode(BaseModel):
    model_config = _CONFIG

    id: StrictStr
    name: StrictStr
    qualname: StrictStr
    kind: SymbolKind
    file_path: RelativePath
    start_line: StrictInt
    end_line: StrictInt
    signature: StrictStr
    ast_hash: StrictStr
    decorators: list[StrictStr]
    is_async: StrictBool
    raw_calls: list[StrictStr]

    @model_validator(mode="after")
    def _check_symbol(self) -> "SymbolNode":
        if self.id != self.file_path + "::" + self.qualname:
            raise ValueError("id must equal file_path + '::' + qualname")
        if self.start_line < 1:
            raise ValueError("start_line must be at least 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be below start_line")
        base = _COLLISION_SUFFIX.sub("", self.qualname, count=1)
        if self.name != base.rsplit(".", 1)[-1]:
            raise ValueError("name must equal the last segment of qualname")
        return self


class FileAnalysis(BaseModel):
    model_config = _CONFIG

    file_path: RelativePath
    language: Language
    loc: StrictInt
    ast_hash: StrictStr
    imports: list[StrictStr]
    exports: list[StrictStr]
    symbols: list[SymbolNode]
    parse_errors: list[StrictStr]

    @model_validator(mode="after")
    def _check_file(self) -> "FileAnalysis":
        if self.loc < 0:
            raise ValueError("loc must not be negative")
        seen: set[str] = set()
        for symbol in self.symbols:
            if symbol.file_path != self.file_path:
                raise ValueError(f"symbol {symbol.id!r} belongs to a different file_path")
            if symbol.id in seen:
                raise ValueError(f"duplicate symbol id {symbol.id!r}")
            seen.add(symbol.id)
        return self


class GraphEdge(BaseModel):
    model_config = _CONFIG

    source: StrictStr
    target: StrictStr
    edge_type: EdgeType


class BlastRadius(BaseModel):
    model_config = _CONFIG

    target_id: StrictStr
    upstream_callers: list[StrictStr]
    downstream_callees: list[StrictStr]
    impact_score: UnitFloat


class DSASignal(BaseModel):
    model_config = _CONFIG

    symbol_id: StrictStr
    file_path: RelativePath
    start_line: StrictInt
    end_line: StrictInt
    chapter: DSAChapter
    pattern_name: StrictStr
    confidence: UnitFloat
    evidence: list[StrictStr]

    @model_validator(mode="after")
    def _check_signal(self) -> "DSASignal":
        if self.start_line < 1:
            raise ValueError("start_line must be at least 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be below start_line")
        if not self.evidence:
            raise ValueError("evidence must not be empty")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("evidence items must not be blank")
        return self


class RepoGraphSnapshot(BaseModel):
    model_config = _CONFIG

    repo_id: StrictStr
    root_path: StrictStr
    files: list[FileAnalysis]
    edges: list[GraphEdge]
    vital_organs: list[StrictStr]
    cycles: list[list[StrictStr]]
    dsa_signals: list[DSASignal]
