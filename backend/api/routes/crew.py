"""Crew_Webhook: ``POST /api/apps/stupid-code/crew`` (decision D13, Requirement 15).

Check order: raw body (at most 1 MiB), signature (only when ``KIRO_CREW_SECRET`` is set,
before any parsing), request parsing, stored repository, path guard, dispatch. The handler
starts no ingestion and ignores ``ALLOW_LOCAL_INGEST``. A failure returns an
Error_Envelope with no partial result. The secret, headers, and signed text are never logged.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import TypeAdapter, ValidationError

from backend.api.crew_signature import InvalidSignature, verify_crew_signature
from backend.api.errors import (
    ApiError,
    map_mastery_error,
    map_pedagogy_error,
    validation_api_error,
)
from backend.api.schemas import (
    AutopsyFileRequest,
    CrewAutopsyResponse,
    CrewFolderResponse,
    CrewRequest,
    CrewResponse,
    CrewStudyModeResponse,
    CrewSymbolResult,
    ExplainFolderRequest,
    StudyModeAction,
)
from backend.api.services import Services, get_services
from backend.engines.mastery import MasteryError, MasteryErrorKind, read_clock, validate_repo_id
from backend.engines.pedagogy import PedagogyError

router = APIRouter()

MAX_BODY_BYTES = 1_048_576
MAX_SYMBOLS = 10

_REQUEST_ADAPTER: TypeAdapter[Any] = TypeAdapter(CrewRequest)


async def _read_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ApiError(422, "validation_error", "the request body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _path_with_query(request: Request) -> str:
    raw_path = request.scope.get("raw_path")
    path = raw_path.decode("latin-1") if isinstance(raw_path, bytes) else request.url.path
    query = request.scope.get("query_string", b"")
    if query:
        return path + "?" + query.decode("latin-1")
    return path


def _verify_signature(request: Request, services: Services, secret: str, body: bytes) -> None:
    headers = [
        (name.decode("latin-1"), value.decode("latin-1")) for name, value in request.headers.raw
    ]
    try:
        verify_crew_signature(
            secret,
            headers,
            request.method,
            _path_with_query(request),
            body,
            read_clock(services.clock),
        )
    except (InvalidSignature, MasteryError):
        raise ApiError(401, "invalid_signature", "the request signature is invalid") from None


def _unknown_target() -> ApiError:
    return ApiError(404, "unknown_target", "the target is not in the stored snapshot")


def _guard_path(path: str) -> None:
    if path.startswith("/") or "\\" in path or ".." in path.split("/"):
        raise _unknown_target()


def _repo_exists(services: Services, repo_id: str) -> None:
    try:
        validate_repo_id(repo_id)
    except MasteryError:
        raise ApiError(404, "repo_not_found", "the repository is not stored") from None
    if services.cache.get_snapshot(repo_id) is None:
        raise ApiError(404, "repo_not_found", "the repository is not stored")


def _autopsy_file(services: Services, command: AutopsyFileRequest) -> CrewResponse:
    snapshot = services.cache.get_snapshot(command.repo_id)
    if snapshot is None:
        raise ApiError(404, "repo_not_found", "the repository is not stored")
    analysis = next((f for f in snapshot.files if f.file_path == command.path), None)
    if analysis is None:
        raise _unknown_target()
    ordered = sorted(analysis.symbols, key=lambda s: (s.start_line, s.id))
    selected = ordered[:MAX_SYMBOLS]
    truncated = len(ordered) > MAX_SYMBOLS
    if not selected:
        return CrewAutopsyResponse(path=command.path, symbols=[], truncated=False)
    ids = [symbol.id for symbol in selected]
    results = asyncio.run(services.dissection.dissect_many(command.repo_id, ids, "L2_FLOW"))
    return CrewAutopsyResponse(
        path=command.path,
        symbols=[
            CrewSymbolResult(target_id=i, envelope=r.envelope, blast_radius=r.blast_radius)
            for i, r in zip(ids, results, strict=True)
        ],
        truncated=truncated,
    )


def _explain_folder(services: Services, command: ExplainFolderRequest) -> CrewResponse:
    if command.path == ".":
        target_id = command.repo_id
    else:
        topology = services.cache.get_topology(command.repo_id)
        if topology is None or command.path not in topology.directory_roles:
            raise _unknown_target()
        target_id = command.path
    result = asyncio.run(services.dissection.dissect(command.repo_id, target_id, "L3_ARCHITECTURE"))
    return CrewFolderResponse(path=command.path, envelope=result.envelope)


def _study_mode(services: Services, command: StudyModeAction) -> CrewResponse:
    services.mastery.set_study_mode(command.repo_id, command.enabled)
    vitals = services.mastery.get_vitals(command.repo_id)
    return CrewStudyModeResponse(study_mode_enabled=vitals.study_mode_enabled, vitals=vitals)


def _dispatch(services: Services, command: Any) -> CrewResponse:
    try:
        if isinstance(command, AutopsyFileRequest):
            return _autopsy_file(services, command)
        if isinstance(command, ExplainFolderRequest):
            return _explain_folder(services, command)
        return _study_mode(services, command)
    except PedagogyError as error:
        raise map_pedagogy_error(error) from None
    except MasteryError as error:
        if error.kind is MasteryErrorKind.INVALID_INPUT:
            raise ApiError(404, "repo_not_found", "the repository is not stored") from None
        raise map_mastery_error(error) from None


def _handle(services: Services, command: Any) -> CrewResponse:
    _repo_exists(services, command.repo_id)
    if not isinstance(command, StudyModeAction):
        _guard_path(command.path)
    return _dispatch(services, command)


@router.post("/api/apps/stupid-code/crew", response_model=None)
async def crew_webhook(
    request: Request, services: Annotated[Services, Depends(get_services)]
) -> CrewResponse:
    body = await _read_body(request)
    settings = getattr(request.app.state, "api_settings", None)
    secret = getattr(settings, "crew_secret", None)
    if secret:
        _verify_signature(request, services, secret, body)
    try:
        command = _REQUEST_ADAPTER.validate_json(body)
    except ValidationError as exc:
        raise validation_api_error(exc.errors(include_input=False, include_url=False)) from None
    return await run_in_threadpool(_handle, services, command)


__all__ = ["router"]
