"""Mastery routes: vitals, Study Mode, and the Socratic start and submit endpoints.

Requirements 13 and 14. Handlers stay thin: check the repository, validate the body, call one
Mastery_Engine function in a worker thread, and map the result or the typed error.

Socratic precedence: read the raw body (at most 1 MiB), then ``repo_not_found`` (also for a
malformed ``repo_id``, without a store query), ``validation_error`` (422),
``study_mode_disabled`` (409), ``unknown_target`` (404), ``invalid_answers`` (422), and
``grading_unavailable`` (503). The last four come from the Mastery_Engine in that order.

Spec conflict between Requirement 14.5 and 14.12: a failed submit for a record that is
already ``MASTERED`` returns that record's unchanged state (``MASTERED`` with its existing
``next_review_at``, with ``passed`` false), as Requirement 14.5 and the engine specify. This
module does not alter that value. For every other record, a failed or unavailable grading
never reports ``MASTERED``.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError

from backend.api.errors import ApiError, map_mastery_error, validation_api_error
from backend.api.schemas import (
    MAX_BODY_BYTES,
    SocraticStartRequest,
    SocraticSubmitRequest,
    StudyModeRequest,
    StudyModeResponse,
)
from backend.api.services import Services, get_services
from backend.domain.models import (
    ComprehensionVitals,
    SocraticCheck,
    SocraticQuestion,
    SocraticVerdict,
)
from backend.engines.mastery import MasteryError, validate_repo_id

router = APIRouter()
ServicesDep = Annotated[Services, Depends(get_services)]


def _repo_not_found() -> ApiError:
    return ApiError(404, "repo_not_found", "the repository is not stored")


async def _require_repo(services: Services, repo_id: str) -> None:
    """404 ``repo_not_found`` for a malformed or unstored ``repo_id``."""
    try:
        valid_id = validate_repo_id(repo_id)
    except MasteryError:
        raise _repo_not_found() from None
    record = await run_in_threadpool(services.cache.read, lambda tx: tx.get_repository(valid_id))
    if record is None:
        raise _repo_not_found()


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise ApiError(422, "validation_error", "the request body is too large")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ApiError(422, "validation_error", "the request body is too large")
    return raw


def _parse[M: BaseModel](model: type[M], raw: bytes) -> M:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_api_error(exc.errors(include_input=False, include_url=False)) from None


@router.get("/api/repos/{repo_id}/vitals", response_model=ComprehensionVitals)
async def get_vitals(repo_id: str, services: ServicesDep) -> ComprehensionVitals:
    await _require_repo(services, repo_id)
    try:
        return await run_in_threadpool(services.mastery.get_vitals, repo_id)
    except MasteryError as exc:
        raise map_mastery_error(exc) from None


@router.post("/api/repos/{repo_id}/study-mode", response_model=StudyModeResponse)
async def set_study_mode(
    repo_id: str, request: Request, services: ServicesDep
) -> StudyModeResponse:
    await _require_repo(services, repo_id)
    body = _parse(StudyModeRequest, await _read_body(request))
    try:
        enabled = await run_in_threadpool(services.mastery.set_study_mode, repo_id, body.enabled)
    except MasteryError as exc:
        raise map_mastery_error(exc) from None
    return StudyModeResponse(repo_id=repo_id, study_mode_enabled=enabled)


@router.post("/api/repos/{repo_id}/socratic/start", response_model=SocraticCheck)
async def socratic_start(repo_id: str, request: Request, services: ServicesDep) -> SocraticCheck:
    raw = await _read_body(request)
    await _require_repo(services, repo_id)
    body = _parse(SocraticStartRequest, raw)
    try:
        check = await run_in_threadpool(services.mastery.start_check, repo_id, body.target_id)
    except MasteryError as exc:
        raise map_mastery_error(exc) from None
    questions = [
        SocraticQuestion(
            question_id=question.question_id,
            target_id=question.target_id,
            prompt=question.prompt,
            line_reference=question.line_reference,
            expected_concepts=[],
        )
        for question in check.questions
    ]
    return SocraticCheck(repo_id=check.repo_id, target_id=check.target_id, questions=questions)


def _grade_in_worker(
    services: Services, repo_id: str, target_id: str, answers: list[tuple[str, str]]
) -> SocraticVerdict:
    # Decision D10: the async engine call runs on its own loop inside the worker thread.
    return asyncio.run(services.mastery.submit_answers(repo_id, target_id, answers))


@router.post("/api/repos/{repo_id}/socratic/submit", response_model=SocraticVerdict)
async def socratic_submit(repo_id: str, request: Request, services: ServicesDep) -> SocraticVerdict:
    raw = await _read_body(request)
    await _require_repo(services, repo_id)
    body = _parse(SocraticSubmitRequest, raw)
    answers = [(item.question_id, item.answer) for item in body.answers]
    try:
        return await run_in_threadpool(_grade_in_worker, services, repo_id, body.target_id, answers)
    except MasteryError as exc:
        raise map_mastery_error(exc) from None


__all__ = ["router"]
