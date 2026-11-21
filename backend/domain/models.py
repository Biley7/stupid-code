"""Pure domain schemas for the AST and graph engine (Spec #01).

Only the standard library and Pydantic v2 are imported. Every model is frozen,
rejects unknown fields, and uses strict scalar types so values such as ``"5"``
or ``True`` are never coerced into integers.
"""

import re
import warnings
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


# --- Spec #02: provenance, topology, and pedagogy models (leaf models) ---

_SpecSource = Literal["requirements.md", "design.md", "tasks.md"]
_DriftType = Literal["UNSPECIFIED_CODE", "UNIMPLEMENTED_SPEC"]
_TopologyPattern = Literal[
    "Hexagonal / Clean Architecture",
    "Layered MVC",
    "Feature-Sliced",
    "Modular Monolith",
    "Flat / Script",
]
_DirectoryRole = Literal[
    "domain",
    "engines",
    "api",
    "ui",
    "tests",
    "config",
    "infrastructure",
    "services",
    "entry_points",
    "other",
]


def _check_stripped_length(value: str, field: str, maximum: int) -> None:
    if not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f"{field} must have 1 to {maximum} characters after stripping")


def _check_line_range(start: int, end: int, start_field: str, end_field: str) -> None:
    if start < 1:
        raise ValueError(f"{start_field} must be at least 1")
    if end < 1:
        raise ValueError(f"{end_field} must be at least 1")
    if end < start:
        raise ValueError(f"{end_field} must not be below {start_field}")


class PedagogyLens(StrEnum):
    L1_SYNTAX = "L1_SYNTAX"
    L2_FLOW = "L2_FLOW"
    L3_ARCHITECTURE = "L3_ARCHITECTURE"


class SpecLink(BaseModel):
    model_config = _CONFIG

    spec_name: StrictStr
    source_file: _SpecSource
    section_title: StrictStr
    excerpt: Annotated[StrictStr, Field(min_length=1, max_length=300)]
    confidence: UnitFloat


class SpecDriftItem(BaseModel):
    model_config = _CONFIG

    drift_type: _DriftType
    target: StrictStr
    details: StrictStr

    @model_validator(mode="after")
    def _check_drift(self) -> "SpecDriftItem":
        if not self.details.strip():
            raise ValueError("details must not be blank")
        return self


# The field name "construct" is mandated by the schema, but it shadows the
# deprecated BaseModel.construct classmethod, so Pydantic warns at class
# creation. Suppress only that one warning, only for this class definition.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "construct"', category=UserWarning)

    class SyntaxAnnotation(BaseModel):
        model_config = _CONFIG

        line_start: StrictInt
        line_end: StrictInt
        construct: StrictStr
        explanation: StrictStr
        what_if_removed: StrictStr

        @model_validator(mode="after")
        def _check_annotation(self) -> "SyntaxAnnotation":
            _check_line_range(self.line_start, self.line_end, "line_start", "line_end")
            _check_stripped_length(self.construct, "construct", 2000)
            _check_stripped_length(self.explanation, "explanation", 2000)
            _check_stripped_length(self.what_if_removed, "what_if_removed", 2000)
            return self


class FlowStep(BaseModel):
    model_config = _CONFIG

    step_number: StrictInt
    location: StrictStr
    action: StrictStr
    data_transformation: StrictStr

    @model_validator(mode="after")
    def _check_step(self) -> "FlowStep":
        if self.step_number < 1:
            raise ValueError("step_number must be at least 1")
        _check_stripped_length(self.location, "location", 1000)
        _check_stripped_length(self.action, "action", 1000)
        _check_stripped_length(self.data_transformation, "data_transformation", 1000)
        return self


class DSACard(BaseModel):
    model_config = _CONFIG

    chapter: DSAChapter
    pattern_name: StrictStr
    start_line: StrictInt
    end_line: StrictInt
    why_used_here: StrictStr
    time_complexity: StrictStr
    space_complexity: StrictStr

    @model_validator(mode="after")
    def _check_card(self) -> "DSACard":
        _check_line_range(self.start_line, self.end_line, "start_line", "end_line")
        return self


class AlternativeArchitecture(BaseModel):
    model_config = _CONFIG

    pattern_name: _TopologyPattern
    why_not_chosen: StrictStr
    when_to_switch: StrictStr

    @model_validator(mode="after")
    def _check_alternative(self) -> "AlternativeArchitecture":
        _check_stripped_length(self.why_not_chosen, "why_not_chosen", 1000)
        _check_stripped_length(self.when_to_switch, "when_to_switch", 1000)
        return self


# --- Spec #02: provenance, topology, and pedagogy models (composite models) ---

_BOUNDARY_METRIC_KEYS = frozenset(
    {"max_depth", "cross_folder_import_ratio", "domain_isolation_score", "entry_point_count"}
)
_BOUNDARY_UNIT_KEYS = ("cross_folder_import_ratio", "domain_isolation_score")

_MetricFloat = Annotated[
    float,
    BeforeValidator(_reject_bool),
    Field(strict=True, allow_inf_nan=False),
]


class ProvenanceReport(BaseModel):
    model_config = _CONFIG

    repo_id: StrictStr
    has_kiro_specs: StrictBool
    spec_links: dict[RelativePath, list[SpecLink]]
    drift_items: list[SpecDriftItem]
    recent_commits: dict[RelativePath, list[StrictStr]]


class TopologyProfile(BaseModel):
    model_config = _CONFIG

    repo_id: StrictStr
    detected_pattern: _TopologyPattern
    confidence: UnitFloat
    directory_roles: dict[RelativePath, _DirectoryRole]
    boundary_metrics: dict[StrictStr, _MetricFloat]
    evidence: list[StrictStr]

    @model_validator(mode="after")
    def _check_profile(self) -> "TopologyProfile":
        if not self.repo_id.strip():
            raise ValueError("repo_id must not be blank")
        if set(self.boundary_metrics) != _BOUNDARY_METRIC_KEYS:
            raise ValueError(
                "boundary_metrics keys must be exactly " + ", ".join(sorted(_BOUNDARY_METRIC_KEYS))
            )
        for key, value in self.boundary_metrics.items():
            if value < 0.0:
                raise ValueError(f"boundary_metrics[{key!r}] must be at least 0.0")
        for key in _BOUNDARY_UNIT_KEYS:
            if self.boundary_metrics[key] > 1.0:
                raise ValueError(f"boundary_metrics[{key!r}] must be at most 1.0")
        return self


class L1SyntaxExplanation(BaseModel):
    model_config = _CONFIG

    target_id: StrictStr
    language: Language
    summary: StrictStr
    annotations: list[SyntaxAnnotation]
    key_takeaway: StrictStr

    @model_validator(mode="after")
    def _check_l1(self) -> "L1SyntaxExplanation":
        _check_stripped_length(self.summary, "summary", 2000)
        _check_stripped_length(self.key_takeaway, "key_takeaway", 2000)
        return self


class L2FlowExplanation(BaseModel):
    model_config = _CONFIG

    target_id: StrictStr
    execution_steps: list[FlowStep]
    upstream_callers: list[StrictStr]
    downstream_callees: list[StrictStr]
    side_effects: list[StrictStr]
    dsa_cards: list[DSACard]
    llm_content_available: StrictBool = True


class L3ArchitectureExplanation(BaseModel):
    model_config = _CONFIG

    target_id: StrictStr
    topology_pattern: _TopologyPattern
    why_this_folder_structure: StrictStr
    structural_evidence: list[StrictStr]
    alternatives: list[AlternativeArchitecture]
    spec_rationale: StrictStr | None = None

    @model_validator(mode="after")
    def _check_l3(self) -> "L3ArchitectureExplanation":
        if not 1 <= len(self.structural_evidence) <= 20:
            raise ValueError("structural_evidence must have 1 to 20 entries")
        return self


class ExplanationEnvelope(BaseModel):
    model_config = _CONFIG

    repo_id: StrictStr
    target_id: StrictStr
    ast_hash: StrictStr
    lens: PedagogyLens
    cached: StrictBool
    l1: L1SyntaxExplanation | None = None
    l2: L2FlowExplanation | None = None
    l3: L3ArchitectureExplanation | None = None

    @model_validator(mode="after")
    def _check_envelope(self) -> "ExplanationEnvelope":
        tiers = {
            PedagogyLens.L1_SYNTAX: self.l1,
            PedagogyLens.L2_FLOW: self.l2,
            PedagogyLens.L3_ARCHITECTURE: self.l3,
        }
        populated = {lens for lens, tier in tiers.items() if tier is not None}
        if populated != {self.lens}:
            raise ValueError("exactly the tier matching lens must be set")
        return self


__all__ += [
    "AlternativeArchitecture",
    "DSACard",
    "ExplanationEnvelope",
    "FlowStep",
    "L1SyntaxExplanation",
    "L2FlowExplanation",
    "L3ArchitectureExplanation",
    "PedagogyLens",
    "ProvenanceReport",
    "SpecDriftItem",
    "SpecLink",
    "SyntaxAnnotation",
    "TopologyProfile",
]


# --- Spec #03: mastery, Study Mode, and Socratic models ---

_REPO_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}")
_UTC_TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _check_repo_id(value: str) -> str:
    if _REPO_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("repo_id must be 1 to 100 characters from A-Z, a-z, 0-9, '.', '_', '-'")
    return value


def _check_utc_timestamp(value: str) -> str:
    from datetime import datetime

    if _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("timestamp must be UTC ISO 8601 like 2025-01-31T12:00:00Z")
    try:
        datetime.strptime(value, _UTC_TIMESTAMP_FORMAT)
    except ValueError:
        raise ValueError("timestamp is not a valid calendar date and time") from None
    return value


def _stripped_length_check(maximum: int) -> AfterValidator:
    def check(value: str) -> str:
        if not 1 <= len(value.strip()) <= maximum:
            raise ValueError(f"must have 1 to {maximum} characters after stripping")
        return value

    return AfterValidator(check)


def _Text(maximum: int) -> object:
    """Return a strict string type of 1 to ``maximum`` characters after stripping."""
    return Annotated[StrictStr, _stripped_length_check(maximum)]


RepoId = Annotated[StrictStr, AfterValidator(_check_repo_id)]
_Id500 = Annotated[StrictStr, Field(min_length=1, max_length=500)]
_Concept = Annotated[StrictStr, _stripped_length_check(100)]
UtcTimestamp = Annotated[StrictStr, AfterValidator(_check_utc_timestamp)]
_EaseFloat = Annotated[
    float,
    BeforeValidator(_reject_bool),
    Field(strict=True, ge=1.3, allow_inf_nan=False),
]
_Percent = Annotated[
    float,
    BeforeValidator(_reject_bool),
    Field(strict=True, ge=0.0, le=100.0, allow_inf_nan=False),
]
_Count = Annotated[StrictInt, Field(ge=0)]


class MasteryState(StrEnum):
    UNAUDITED = "UNAUDITED"
    DISSECTED = "DISSECTED"
    MASTERED = "MASTERED"
    STALE = "STALE"


class ModuleMastery(BaseModel):
    model_config = _CONFIG

    repo_id: RepoId
    target_id: _Id500
    ast_hash: _Id500
    state: MasteryState
    ease_factor: _EaseFloat = 2.5
    interval_days: _Count = 0
    repetitions: _Count = 0
    next_review_at: UtcTimestamp | None = None
    last_verified_at: UtcTimestamp | None = None


class SocraticQuestion(BaseModel):
    model_config = _CONFIG

    question_id: _Id500
    target_id: _Id500
    prompt: _Text(1000)
    line_reference: _Id500
    expected_concepts: Annotated[list[_Concept], Field(max_length=10)]


class SocraticCheck(BaseModel):
    model_config = _CONFIG

    repo_id: RepoId
    target_id: _Id500
    questions: Annotated[list[SocraticQuestion], Field(min_length=1, max_length=2)]


class SocraticAnswerItem(BaseModel):
    model_config = _CONFIG

    question_id: _Id500
    answer: _Text(2000)


class SocraticVerdict(BaseModel):
    model_config = _CONFIG

    target_id: _Id500
    passed: StrictBool
    score: UnitFloat
    feedback: _Text(1000)
    new_state: MasteryState
    next_review_at: UtcTimestamp | None


class ComprehensionVitals(BaseModel):
    model_config = _CONFIG

    repo_id: RepoId
    study_mode_enabled: StrictBool
    total_modules: _Count
    unaudited_count: _Count
    dissected_count: _Count
    mastered_count: _Count
    stale_count: _Count
    mastery_percentage: _Percent
    due_for_review: list[StrictStr]
    file_states: dict[RelativePath, MasteryState]

    @model_validator(mode="after")
    def _check_vitals(self) -> "ComprehensionVitals":
        if len(self.file_states) > self.total_modules:
            raise ValueError("file_states must not have more entries than total_modules")
        return self


class SocraticGrade(BaseModel):
    model_config = _CONFIG

    score: UnitFloat
    feedback: _Text(1000)


__all__ += [
    "ComprehensionVitals",
    "MasteryState",
    "ModuleMastery",
    "SocraticAnswerItem",
    "SocraticCheck",
    "SocraticGrade",
    "SocraticQuestion",
    "SocraticVerdict",
]
