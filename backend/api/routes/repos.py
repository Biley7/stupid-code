"""Repository routes: ingest, list, and snapshot (Requirements 10 and 11).

Routes read shared objects from the application, by this convention (tasks 9.7 and 9.8
follow it):

- ``request.app.state.api_settings``: the ``ApiSettings`` from ``load_api_settings``.
- ``request.app.state.rate_limiter``: the ``RateLimiter`` for ``url`` ingests, built from
  those settings. ``create_app`` sets both keys. When a key is missing (a bare test app)
  the route builds it once from the environment defaults and stores it under that key.
- ``Services`` come from the ``get_services`` dependency.

``POST /api/repos/ingest`` applies its checks in the order of Requirement 10.21: body
(400), limits (422), local-ingest setting for ``path`` (403, before any file-system call),
rate limit for ``url`` (429), then the Analysis_Pipeline in a worker thread. The client IP
is ``request.client.host``; ``X-Forwarded-For`` is ignored.
"""

from __future__ import annotations

import re
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from backend.api.errors import (
    ApiError,
    map_ingestion_error,
    map_mastery_error,
    map_pipeline_error,
)
from backend.api.rate_limit import RateLimiter
from backend.api.schemas import (
    IngestResponse,
    RepoSummary,
    SnapshotResponse,
    build_ingest_response,
    build_snapshot_response,
    parse_ingest_body,
)
from backend.api.services import Services, get_services
from backend.api.settings import ApiSettings, load_api_settings
from backend.engines.analysis_pipeline import (
    AnalysisPipelineError,
    GitHubSource,
    LocalSource,
    analyze_repository,
)
from backend.engines.cache_store import CacheTransaction
from backend.engines.ingestion import IngestionError
from backend.engines.mastery import MasteryError, read_clock

router = APIRouter()

ServicesDep = Annotated[Services, Depends(get_services)]

_STATE_LOCK = threading.Lock()


def _api_settings(request: Request) -> ApiSettings:
    state = request.app.state
    settings = getattr(state, "api_settings", None)
    if settings is None:
        with _STATE_LOCK:
            settings = getattr(state, "api_settings", None)
            if settings is None:
                settings = load_api_settings()
                state.api_settings = settings
    return settings


def _rate_limiter(request: Request, settings: ApiSettings) -> RateLimiter:
    state = request.app.state
    limiter = getattr(state, "rate_limiter", None)
    if limiter is None:
        with _STATE_LOCK:
            limiter = getattr(state, "rate_limiter", None)
            if limiter is None:
                limiter = RateLimiter(
                    settings.github_rate_limit, settings.github_rate_window_seconds
                )
                state.rate_limiter = limiter
    return limiter


def _repo_not_found() -> ApiError:
    return ApiError(404, "repo_not_found", "the repository is not stored")


def _valid_repo_id(repo_id: str) -> bool:
    # Same rule as mastery.validate_repo_id, without raising.
    return re.fullmatch(r"[A-Za-z0-9._-]{1,100}", repo_id) is not None


@router.post("/api/repos/ingest", response_model=IngestResponse)
async def ingest_repository(request: Request, services: ServicesDep) -> IngestResponse:
    raw = await request.body()
    command = parse_ingest_body(raw)  # checks 1 and 2
    settings = _api_settings(request)

    source: LocalSource | GitHubSource
    if command.path is not None:
        if not settings.allow_local_ingest:  # check 3, before any file-system call
            raise ApiError(
                403,
                "local_ingest_disabled",
                "local path ingestion is disabled on this server",
            )
        source = LocalSource(command.path)
    else:
        assert command.url is not None
        limiter = _rate_limiter(request, settings)
        client_ip = request.client.host if request.client else "unknown"
        try:
            now = read_clock(services.clock)
        except MasteryError as error:
            raise map_mastery_error(error) from None
        decision = limiter.check_and_count(client_ip, now)  # check 4
        if not decision.allowed:
            raise ApiError(
                429,
                "rate_limited",
                "too many GitHub clone requests, retry later",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        source = GitHubSource(command.url)

    try:
        result = await run_in_threadpool(
            analyze_repository,
            source,
            cache=services.cache,
            mastery=services.mastery,
            max_files=command.max_files,
            max_total_bytes=command.max_total_bytes,
            workspace=services.workspace,
            git_runner=services.git_runner,
        )
    except IngestionError as error:
        raise map_ingestion_error(error) from None
    except AnalysisPipelineError as error:
        raise map_pipeline_error(error) from None
    return build_ingest_response(result)


@router.get("/api/repos", response_model=list[RepoSummary])
async def list_repositories(services: ServicesDep) -> list[RepoSummary]:
    def load() -> list[RepoSummary]:
        def op(tx: CacheTransaction) -> list[RepoSummary]:
            return [
                RepoSummary(
                    repo_id=record.repo_id,
                    file_count=record.file_count,
                    symbol_count=record.symbol_count,
                    study_mode_enabled=bool(tx.get_study_mode(record.repo_id)),
                )
                for record in tx.list_repositories()
            ]

        return services.cache.read(op)

    items = await run_in_threadpool(load)
    return sorted(items, key=lambda item: item.repo_id)


@router.get("/api/repos/{repo_id}/snapshot", response_model=SnapshotResponse)
async def get_snapshot(repo_id: str, services: ServicesDep) -> SnapshotResponse:
    if not _valid_repo_id(repo_id):
        raise _repo_not_found()

    def load() -> SnapshotResponse | None:
        def op(tx: CacheTransaction) -> SnapshotResponse | None:
            if tx.get_repository(repo_id) is None:
                return None
            snapshot = tx.get_snapshot(repo_id)
            provenance = tx.get_provenance(repo_id)
            topology = tx.get_topology(repo_id)
            if snapshot is None or provenance is None or topology is None:
                raise ApiError(500, "storage_error", "the database operation failed")
            return build_snapshot_response(snapshot, provenance, topology)

        return services.cache.read(op)

    response = await run_in_threadpool(load)
    if response is None:
        raise _repo_not_found()
    return response


__all__ = ["router"]
