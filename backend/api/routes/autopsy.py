"""``POST /api/repos/{repo_id}/explain``: one explanation plus its blast radius.

Check order (Requirement 12): the Repo_Id rule and the stored repository (404
``repo_not_found``, with no store query for a malformed id), then the body (422
``validation_error``), then the Dissection_Service. The handler is thin: the mastery update
for Study Mode happens inside ``DissectionService`` (decision D10 for the thread bridge).
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from backend.api.errors import (
    ApiError,
    map_mastery_error,
    map_pedagogy_error,
    validation_api_error,
)
from backend.api.schemas import MAX_BODY_BYTES, ExplainRequest, ExplainResponse
from backend.api.services import Services, get_services
from backend.engines.dissection import InvalidLensError
from backend.engines.mastery import MasteryError, validate_repo_id
from backend.engines.pedagogy import PedagogyError

router = APIRouter()

_INVALID_BODY = "request validation failed at: body"


def _repo_not_found() -> ApiError:
    return ApiError(404, "repo_not_found", "the repository is not stored")


def _require_repository(services: Services, repo_id: str) -> None:
    try:
        validate_repo_id(repo_id)
    except MasteryError:
        raise _repo_not_found() from None
    if services.cache.get_snapshot(repo_id) is None:
        raise _repo_not_found()


async def _read_body(request: Request) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ApiError(422, "validation_error", "the request body is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_body(raw: bytes) -> ExplainRequest:
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        raise ApiError(422, "validation_error", _INVALID_BODY) from None
    try:
        return ExplainRequest.model_validate(payload)
    except ValidationError as exc:
        raise validation_api_error(exc.errors()) from None


@router.post("/api/repos/{repo_id}/explain", response_model=ExplainResponse)
async def explain(
    repo_id: str,
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> ExplainResponse:
    """Explain one Target under one lens and return its blast radius."""
    await run_in_threadpool(_require_repository, services, repo_id)
    command = _parse_body(await _read_body(request))

    def work() -> ExplainResponse:
        result = asyncio.run(
            services.dissection.dissect(repo_id, command.target_id, command.lens.value)
        )
        return ExplainResponse(envelope=result.envelope, blast_radius=result.blast_radius)

    try:
        return await run_in_threadpool(work)
    except InvalidLensError:
        raise ApiError(422, "validation_error", _INVALID_BODY) from None
    except PedagogyError as exc:
        raise map_pedagogy_error(exc) from None
    except MasteryError as exc:
        raise map_mastery_error(exc) from None


__all__ = ["router"]
