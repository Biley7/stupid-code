"""Pydantic request and response models for the REST API (Requirement 9.15).

``parse_ingest_body`` applies the body and limit checks of Requirement 10, criteria 2 and 6.
Request models use ``extra="forbid"`` and strict field types so a string never passes for a
boolean or a number.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from backend.api.errors import ApiError
from backend.domain.models import (
    BlastRadius,
    ComprehensionVitals,
    ExplanationEnvelope,
    PedagogyLens,
    ProvenanceReport,
    RepoGraphSnapshot,
    TopologyProfile,
)
from backend.engines.analysis_pipeline import AnalysisResult
from backend.engines.ingestion import DEFAULT_MAX_FILES, DEFAULT_MAX_TOTAL_BYTES

MAX_BODY_BYTES = 1_048_576
MAX_PATH_CHARS = 4_096

_REQUEST = ConfigDict(frozen=True, extra="forbid")
_RESPONSE = ConfigDict(frozen=True, extra="forbid")


class MalformedRequest(ApiError):
    """HTTP 400 ``malformed_request`` (Requirement 10.2)."""

    def __init__(self, message: str = "the request body is malformed") -> None:
        super().__init__(400, "malformed_request", message)


class InvalidLimit(ApiError):
    """HTTP 422 ``invalid_limit`` (Requirement 10.6)."""

    def __init__(self, message: str = "max_files or max_total_bytes is out of range") -> None:
        super().__init__(422, "invalid_limit", message)


# -- ingest ---------------------------------------------------------------------------


class IngestCommand(BaseModel):
    """A validated ingest request: exactly one of ``path`` and ``url``."""

    model_config = _REQUEST

    path: StrictStr | None = None
    url: StrictStr | None = None
    max_files: StrictInt = DEFAULT_MAX_FILES
    max_total_bytes: StrictInt = DEFAULT_MAX_TOTAL_BYTES


_INGEST_KEYS = frozenset({"path", "url", "max_files", "max_total_bytes"})


def _check_limit(value: Any, default_max: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidLimit()
    if value < 1 or value > default_max:
        raise InvalidLimit()
    return value


def parse_ingest_body(raw: bytes) -> IngestCommand:
    """Apply the body checks, then the limit checks, to a raw ingest body."""
    if len(raw) > MAX_BODY_BYTES:
        raise MalformedRequest()
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        raise MalformedRequest() from None
    if not isinstance(data, dict):
        raise MalformedRequest()
    if not set(data) <= _INGEST_KEYS:
        raise MalformedRequest()
    has_path, has_url = "path" in data, "url" in data
    if has_path == has_url:
        raise MalformedRequest()
    key = "path" if has_path else "url"
    value = data[key]
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_PATH_CHARS:
        raise MalformedRequest()
    max_files = (
        _check_limit(data["max_files"], DEFAULT_MAX_FILES)
        if "max_files" in data
        else DEFAULT_MAX_FILES
    )
    max_total_bytes = (
        _check_limit(data["max_total_bytes"], DEFAULT_MAX_TOTAL_BYTES)
        if "max_total_bytes" in data
        else DEFAULT_MAX_TOTAL_BYTES
    )
    return IngestCommand(**{key: value}, max_files=max_files, max_total_bytes=max_total_bytes)


class IngestSummary(BaseModel):
    model_config = _RESPONSE

    file_count: int
    symbol_count: int
    edge_count: int
    dsa_signal_count: int


class IngestWarningItem(BaseModel):
    model_config = _RESPONSE

    kind: str
    path: str
    detail: str


class IngestResponse(BaseModel):
    model_config = _RESPONSE

    repo_id: str
    summary: IngestSummary
    provenance: ProvenanceReport
    topology: TopologyProfile
    truncated: bool
    warnings: list[IngestWarningItem]


def build_ingest_response(result: AnalysisResult) -> IngestResponse:
    """Map an ``AnalysisResult`` to the ingest response (``kind.value`` per decision M5)."""
    snapshot = result.snapshot
    return IngestResponse(
        repo_id=result.repo_id,
        summary=IngestSummary(
            file_count=len(snapshot.files),
            symbol_count=sum(len(f.symbols) for f in snapshot.files),
            edge_count=len(snapshot.edges),
            dsa_signal_count=len(snapshot.dsa_signals),
        ),
        provenance=result.provenance,
        topology=result.topology,
        truncated=result.truncated,
        warnings=[
            IngestWarningItem(kind=w.kind.value, path=w.path, detail=w.detail)
            for w in result.warnings
        ],
    )


# -- repositories ---------------------------------------------------------------------


class RepoSummary(BaseModel):
    model_config = _RESPONSE

    repo_id: str
    file_count: Annotated[int, Field(ge=0)]
    symbol_count: Annotated[int, Field(ge=0)]
    study_mode_enabled: bool


class SnapshotResponse(BaseModel):
    model_config = _RESPONSE

    snapshot: RepoGraphSnapshot
    provenance: ProvenanceReport
    topology: TopologyProfile


def build_snapshot_response(
    snapshot: RepoGraphSnapshot, provenance: ProvenanceReport, topology: TopologyProfile
) -> SnapshotResponse:
    """Build the response with ``root_path`` replaced by ``"."`` (Requirement 11.4).

    The stored snapshot is not modified; a copy carries the replaced field.
    """
    return SnapshotResponse(
        snapshot=snapshot.model_copy(update={"root_path": "."}),
        provenance=provenance,
        topology=topology,
    )


# -- explain --------------------------------------------------------------------------


class ExplainRequest(BaseModel):
    model_config = _REQUEST

    target_id: Annotated[StrictStr, Field(min_length=1, max_length=500)]
    lens: PedagogyLens


class ExplainResponse(BaseModel):
    """Exactly the envelope and the blast radius (Requirement 12.1)."""

    model_config = _RESPONSE

    envelope: ExplanationEnvelope
    blast_radius: BlastRadius


# -- study mode, vitals ---------------------------------------------------------------


class StudyModeRequest(BaseModel):
    model_config = _REQUEST

    enabled: StrictBool


class StudyModeResponse(BaseModel):
    model_config = _RESPONSE

    repo_id: str
    study_mode_enabled: bool


# -- socratic -------------------------------------------------------------------------


class SocraticStartRequest(BaseModel):
    model_config = _REQUEST

    target_id: Annotated[StrictStr, Field(min_length=1)]


class SocraticAnswerPayload(BaseModel):
    """One answer as received. Length and membership rules belong to the Mastery_Engine."""

    model_config = _REQUEST

    question_id: StrictStr
    answer: StrictStr


class SocraticSubmitRequest(BaseModel):
    model_config = _REQUEST

    target_id: Annotated[StrictStr, Field(min_length=1)]
    answers: list[SocraticAnswerPayload]


# -- crew -----------------------------------------------------------------------------

_CrewPath = Annotated[StrictStr, Field(min_length=1, max_length=1_024)]
_CrewRepoId = Annotated[StrictStr, Field(min_length=1)]


class AutopsyFileRequest(BaseModel):
    model_config = _REQUEST

    action: Literal["autopsy_file"]
    repo_id: _CrewRepoId
    path: _CrewPath


class ExplainFolderRequest(BaseModel):
    model_config = _REQUEST

    action: Literal["explain_folder_architecture"]
    repo_id: _CrewRepoId
    path: _CrewPath


class StudyModeAction(BaseModel):
    model_config = _REQUEST

    action: Literal["study_mode"]
    repo_id: _CrewRepoId
    enabled: StrictBool


CrewRequest = Annotated[
    AutopsyFileRequest | ExplainFolderRequest | StudyModeAction,
    Field(discriminator="action"),
]


class CrewSymbolResult(BaseModel):
    model_config = _RESPONSE

    target_id: str
    envelope: ExplanationEnvelope
    blast_radius: BlastRadius


class CrewAutopsyResponse(BaseModel):
    model_config = _RESPONSE

    action: Literal["autopsy_file"] = "autopsy_file"
    path: str
    symbols: list[CrewSymbolResult]
    truncated: bool


class CrewFolderResponse(BaseModel):
    model_config = _RESPONSE

    action: Literal["explain_folder_architecture"] = "explain_folder_architecture"
    path: str
    envelope: ExplanationEnvelope


class CrewStudyModeResponse(BaseModel):
    model_config = _RESPONSE

    action: Literal["study_mode"] = "study_mode"
    study_mode_enabled: bool
    vitals: ComprehensionVitals


CrewResponse = CrewAutopsyResponse | CrewFolderResponse | CrewStudyModeResponse


__all__ = [
    "AutopsyFileRequest",
    "CrewAutopsyResponse",
    "CrewFolderResponse",
    "CrewRequest",
    "CrewResponse",
    "CrewStudyModeResponse",
    "CrewSymbolResult",
    "ExplainFolderRequest",
    "ExplainRequest",
    "ExplainResponse",
    "IngestCommand",
    "IngestResponse",
    "IngestSummary",
    "IngestWarningItem",
    "InvalidLimit",
    "MAX_BODY_BYTES",
    "MalformedRequest",
    "RepoSummary",
    "SnapshotResponse",
    "SocraticAnswerPayload",
    "SocraticStartRequest",
    "SocraticSubmitRequest",
    "StudyModeAction",
    "StudyModeRequest",
    "StudyModeResponse",
    "build_ingest_response",
    "build_snapshot_response",
    "parse_ingest_body",
]
