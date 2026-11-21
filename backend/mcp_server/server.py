"""Stupid Code MCP server (stdio). Launched as `.venv/bin/python backend/mcp_server/server.py`.

The server exposes exactly five tools. Each one is a thin wrapper over the shared engines
(Analysis_Pipeline, Dissection_Service, Mastery_Engine), so the REST API and the MCP
server never hold a second implementation of analysis, scoring, or mastery.

Every tool returns a Tool_Result, a plain JSON object:

- success: ``{"ok": true, ...payload}``
- failure: ``{"ok": false, "error": {"code": <stable code>, "message": <fixed text>}}``

Arguments are typed ``Annotated[Any, Field(json_schema_extra={"type": ...})]`` so the SDK
publishes the right JSON schema type but passes the raw value through unchanged; this
module validates every argument itself, so a wrong type becomes a failure Tool_Result
instead of an SDK error (design research finding 2).

Nothing is written to standard output except protocol messages. Diagnostics go to
standard error through ``logging`` (the SDK binds its handler to stderr) and hold only
exception class names, never paths, prompts, provider text, or credentials.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # run as a script: put the workspace root first
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import anyio.to_thread
from mcp.server.mcpserver import MCPServer  # the only SDK import (Requirement 16.1)
from pydantic import Field, StrictInt, StrictStr, TypeAdapter, ValidationError

from backend.engines.analysis_pipeline import (
    AnalysisPipelineError,
    AnalysisResult,
    NoAnalyzableFilesError,
    PipelineStep,
    derive_local_repo_id,
    ensure_analysis,
)
from backend.engines.cache_store import CacheStore, CacheStoreError
from backend.engines.dissection import DEFAULT_MAX_DEPTH, DissectionService, InvalidLensError
from backend.engines.graph_engine import MissingTargetError
from backend.engines.ingestion import IngestionError
from backend.engines.llm_router import LLMConfigError, LLMRouter, StructuredLLM
from backend.engines.mastery import (
    Clock,
    MasteryEngine,
    MasteryError,
    MasteryErrorKind,
    system_clock,
)
from backend.engines.pedagogy import PedagogyEngine, PedagogyError, PedagogyErrorKind

__all__ = [
    "TOOL_NAMES",
    "ToolServices",
    "build_server",
    "main",
]

TOOL_NAMES = (
    "dissect_symbol",
    "trace_blast_radius",
    "analyze_folder_architecture",
    "check_spec_drift",
    "get_comprehension_vitals",
)

MAX_REPO_PATH_LENGTH = 4096
MAX_TARGET_ID_LENGTH = 500
MAX_DEPTH_LIMIT = 20
DEFAULT_LENS = "L2_FLOW"

_INSTRUCTIONS = (
    "Stupid Code dissects a local repository with five tools: dissect_symbol, "
    "trace_blast_radius, analyze_folder_architecture, check_spec_drift, and "
    "get_comprehension_vitals. Every tool returns an object with a boolean 'ok'; on "
    "failure 'error.code' names the cause. Ground every statement in tool output."
)

_logger = logging.getLogger("stupid_code.mcp_server")

# Fixed message per error code. Messages never echo inputs, paths, or provider text.
_MESSAGES: dict[str, str] = {
    "invalid_repo_path": "repo_path must be a readable local directory of 1 to 4096 characters",
    "no_supported_files": "the repository holds no readable supported source files",
    "repo_not_analyzed": "the repository has no stored analysis; run another tool on it first",
    "unknown_target": "target_id is not a symbol or scope in the stored snapshot",
    "invalid_lens": "lens must be one of L1_SYNTAX, L2_FLOW, or L3_ARCHITECTURE",
    "invalid_max_depth": "max_depth must be an integer from 0 to 20",
    "llm_unavailable": "the explanation model is unavailable or returned invalid output",
    "source_unreadable": "the target source file cannot be read",
    "storage_error": "the cache database failed",
    "analysis_failed": "repository analysis failed",
    "internal_error": "an internal error occurred",
}

_Lens = Literal["L1_SYNTAX", "L2_FLOW", "L3_ARCHITECTURE"]

_REPO_PATH = TypeAdapter(Annotated[StrictStr, Field(min_length=1, max_length=MAX_REPO_PATH_LENGTH)])
_TARGET_ID = TypeAdapter(Annotated[StrictStr, Field(min_length=1, max_length=MAX_TARGET_ID_LENGTH)])
_LENS = TypeAdapter(_Lens)
_MAX_DEPTH = TypeAdapter(Annotated[StrictInt, Field(ge=0, le=MAX_DEPTH_LIMIT)])

ToolResult = dict[str, Any]


# -- services --------------------------------------------------------------------------


@dataclass
class ToolServices:
    """The injected dependencies of the MCP server (Requirement 16.21)."""

    cache: CacheStore
    router: StructuredLLM
    clock: Clock = system_clock

    @classmethod
    def from_environment(cls) -> "ToolServices":
        """Open the Cache_Store at ``STUPID_CODE_DB_PATH`` and build the LLM_Router.

        Raises ``CacheStoreError`` or ``LLMConfigError`` on bad configuration.
        """
        cache = CacheStore()
        try:
            router = LLMRouter()
        except BaseException:
            cache.close()
            raise
        return cls(cache=cache, router=router, clock=system_clock)


@dataclass(frozen=True)
class _Engines:
    cache: CacheStore
    mastery: MasteryEngine
    dissection: DissectionService


def _engines(services: ToolServices) -> _Engines:
    mastery = MasteryEngine(services.cache, services.router, services.clock)
    pedagogy = PedagogyEngine(services.cache, services.router)
    return _Engines(
        cache=services.cache,
        mastery=mastery,
        dissection=DissectionService(services.cache, pedagogy, mastery),
    )


# -- results and errors ----------------------------------------------------------------


class _ToolFailure(Exception):
    """A failure with a stable Tool_Result code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _failure(code: str) -> ToolResult:
    return {"ok": False, "error": {"code": code, "message": _MESSAGES[code]}}


def _error_code(exc: Exception) -> str:
    """Map an engine exception to a stable code (design Error Handling, MCP mapping)."""
    if isinstance(exc, _ToolFailure):
        return exc.code
    if isinstance(exc, IngestionError):
        return "invalid_repo_path"
    if isinstance(exc, NoAnalyzableFilesError):
        return "no_supported_files"
    if isinstance(exc, AnalysisPipelineError):
        return "storage_error" if exc.step is PipelineStep.PERSIST else "analysis_failed"
    if isinstance(exc, InvalidLensError):
        return "invalid_lens"
    if isinstance(exc, PedagogyError):
        return {
            PedagogyErrorKind.UNKNOWN_TARGET: "unknown_target",
            PedagogyErrorKind.SOURCE_UNREADABLE: "source_unreadable",
            PedagogyErrorKind.LLM_FAILURE: "llm_unavailable",
            PedagogyErrorKind.INVALID_OUTPUT: "llm_unavailable",
            PedagogyErrorKind.MISSING_DATA: "repo_not_analyzed",
        }.get(exc.kind, "internal_error")
    if isinstance(exc, MasteryError):
        return {
            MasteryErrorKind.UNKNOWN_REPOSITORY: "repo_not_analyzed",
            MasteryErrorKind.UNKNOWN_TARGET: "unknown_target",
            MasteryErrorKind.SOURCE_UNREADABLE: "source_unreadable",
            MasteryErrorKind.STORAGE: "storage_error",
        }.get(exc.kind, "internal_error")
    if isinstance(exc, CacheStoreError):
        return "storage_error"
    if isinstance(exc, MissingTargetError):
        return "unknown_target"
    return "internal_error"


async def _run_tool(tool: str, body: Callable[[], ToolResult]) -> ToolResult:
    """Run ``body`` in a worker thread and turn any exception into a failure Tool_Result."""
    try:
        return await anyio.to_thread.run_sync(body)
    except Exception as exc:
        code = _error_code(exc)
        if code == "internal_error":
            _logger.error("tool %s failed with %s", tool, type(exc).__name__)
        return _failure(code)


# -- argument validation ---------------------------------------------------------------


def _validated[T](adapter: TypeAdapter[T], value: object, code: str) -> T:
    try:
        return adapter.validate_python(value, strict=True)
    except ValidationError:
        raise _ToolFailure(code) from None


def _repo_path(value: object) -> str:
    path = _validated(_REPO_PATH, value, "invalid_repo_path")
    try:
        readable = "\x00" not in path and os.path.isdir(path) and os.access(path, os.R_OK | os.X_OK)
    except (OSError, ValueError):
        readable = False
    if not readable:
        raise _ToolFailure("invalid_repo_path")
    return path


def _target_id(value: object) -> str:
    return _validated(_TARGET_ID, value, "unknown_target")


def _lens(value: object) -> str:
    return _validated(_LENS, value, "invalid_lens")


def _max_depth(value: object) -> int:
    return _validated(_MAX_DEPTH, value, "invalid_max_depth")


# -- tool parameters -------------------------------------------------------------------

RepoPathArg = Annotated[
    Any,
    Field(
        description="Path of a local repository directory to analyze.",
        json_schema_extra={"type": "string"},
    ),
]
TargetIdArg = Annotated[
    Any,
    Field(
        description=(
            "Symbol id from the Snapshot (for example 'pkg/mod.py::func'); for "
            "L3_ARCHITECTURE, the repo_id or a directory."
        ),
        json_schema_extra={"type": "string"},
    ),
]
LensArg = Annotated[
    Any,
    Field(
        description="Explanation lens: L1_SYNTAX, L2_FLOW, or L3_ARCHITECTURE.",
        json_schema_extra={"type": "string", "enum": ["L1_SYNTAX", "L2_FLOW", "L3_ARCHITECTURE"]},
    ),
]
MaxDepthArg = Annotated[
    Any,
    Field(
        description="Call-graph depth to trace, an integer from 0 to 20.",
        json_schema_extra={"type": "integer", "minimum": 0, "maximum": MAX_DEPTH_LIMIT},
    ),
]


# -- server ----------------------------------------------------------------------------


def build_server(services: ToolServices | None = None) -> MCPServer:
    """Build the MCP server with the five tools over ``services``.

    With no ``services``, they are built from the environment (``STUPID_CODE_DB_PATH``,
    ``LLM_PROVIDER``).
    """
    engines = _engines(services if services is not None else ToolServices.from_environment())
    server = MCPServer("stupid-code", instructions=_INSTRUCTIONS)

    def analyze(repo_path: str) -> AnalysisResult:
        return ensure_analysis(repo_path, cache=engines.cache, mastery=engines.mastery)

    @server.tool(
        name="dissect_symbol",
        description=(
            "Explain one symbol under a lens and return its blast radius. Records a view "
            "for mastery when Study Mode is on."
        ),
    )
    async def dissect_symbol(
        repo_path: RepoPathArg = None,
        target_id: TargetIdArg = None,
        lens: LensArg = DEFAULT_LENS,
    ) -> ToolResult:
        def body() -> ToolResult:
            path = _repo_path(repo_path)
            target = _target_id(target_id)
            chosen_lens = _lens(lens)
            analysis = analyze(path)
            result = asyncio.run(engines.dissection.dissect(analysis.repo_id, target, chosen_lens))
            return {
                "ok": True,
                "repo_id": analysis.repo_id,
                "envelope": result.envelope.model_dump(mode="json"),
                "blast_radius": result.blast_radius.model_dump(mode="json"),
            }

        return await _run_tool("dissect_symbol", body)

    @server.tool(
        name="trace_blast_radius",
        description="Return the direct and transitive callers and callees of a symbol.",
    )
    async def trace_blast_radius(
        repo_path: RepoPathArg = None,
        target_id: TargetIdArg = None,
        max_depth: MaxDepthArg = DEFAULT_MAX_DEPTH,
    ) -> ToolResult:
        def body() -> ToolResult:
            path = _repo_path(repo_path)
            target = _target_id(target_id)
            depth = _max_depth(max_depth)
            analysis = analyze(path)
            radius = engines.dissection.blast_radius(analysis.repo_id, target, depth)
            return {
                "ok": True,
                "repo_id": analysis.repo_id,
                "blast_radius": radius.model_dump(mode="json"),
            }

        return await _run_tool("trace_blast_radius", body)

    @server.tool(
        name="analyze_folder_architecture",
        description="Return the repository's topology profile. Makes no LLM call.",
    )
    async def analyze_folder_architecture(repo_path: RepoPathArg = None) -> ToolResult:
        def body() -> ToolResult:
            analysis = analyze(_repo_path(repo_path))
            return {
                "ok": True,
                "repo_id": analysis.repo_id,
                "topology": analysis.topology.model_dump(mode="json"),
            }

        return await _run_tool("analyze_folder_architecture", body)

    @server.tool(
        name="check_spec_drift",
        description="Return spec drift items and whether the repository has .kiro specs.",
    )
    async def check_spec_drift(repo_path: RepoPathArg = None) -> ToolResult:
        def body() -> ToolResult:
            analysis = analyze(_repo_path(repo_path))
            provenance = analysis.provenance
            return {
                "ok": True,
                "repo_id": analysis.repo_id,
                "has_kiro_specs": provenance.has_kiro_specs,
                "drift_items": [item.model_dump(mode="json") for item in provenance.drift_items],
            }

        return await _run_tool("check_spec_drift", body)

    @server.tool(
        name="get_comprehension_vitals",
        description=(
            "Return mastery counts, due reviews, per-file states, and study_mode_enabled. "
            "Runs no analysis and writes nothing."
        ),
    )
    async def get_comprehension_vitals(repo_path: RepoPathArg = None) -> ToolResult:
        def body() -> ToolResult:
            path = _repo_path(repo_path)
            repo_id = derive_local_repo_id(os.path.realpath(path))
            vitals = engines.mastery.get_vitals(repo_id)
            return {"ok": True, "repo_id": repo_id, "vitals": vitals.model_dump(mode="json")}

        return await _run_tool("get_comprehension_vitals", body)

    return server


def main() -> None:
    """Run the server over stdio. A configuration error exits 1 with one stderr line."""
    try:
        services = ToolServices.from_environment()
    except LLMConfigError as exc:
        sys.stderr.write(f"stupid-code MCP server: invalid LLM configuration: {exc}\n")
        raise SystemExit(1) from None
    except CacheStoreError as exc:
        sys.stderr.write(
            "stupid-code MCP server: cannot open the cache database set by "
            f"STUPID_CODE_DB_PATH ({type(exc.__cause__ or exc).__name__})\n"
        )
        raise SystemExit(1) from None
    try:
        build_server(services).run("stdio")
    finally:
        services.cache.close()


if __name__ == "__main__":
    main()
