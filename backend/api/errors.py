"""Error_Envelope, exception handlers, catch-all middleware, and engine error mapping.

Every non-2xx response body is ``{"error": {"code": <stable code>, "message": <1 to 500
characters>}}`` (Requirement 9.9). Messages are fixed texts per code, or the ``message``
attribute of a typed engine error whose texts are fixed (``IngestionError.message``, never
``str(IngestionError)``, which appends ``detail``). No response holds a stack trace, a
server path, SQL, provider text, a credential, or a prompt (Requirements 9.10, 23.8, 23.9).
The mapping tables follow the design's Error Handling section.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.engines.analysis_pipeline import (
    AnalysisPipelineError,
    NoAnalyzableFilesError,
    PipelineStep,
)
from backend.engines.cache_store import CacheStoreError
from backend.engines.ingestion import IngestionError, IngestionErrorKind
from backend.engines.mastery import MasteryError, MasteryErrorKind
from backend.engines.pedagogy import PedagogyError, PedagogyErrorKind

_LOGGER = logging.getLogger("backend.api")

MAX_MESSAGE_LENGTH = 500

INTERNAL_ERROR_MESSAGE = "an internal error occurred"
STORAGE_ERROR_MESSAGE = "the database operation failed"
VALIDATION_ERROR_MESSAGE = "the request is invalid"


class ApiError(Exception):
    """An HTTP error with a stable ``code`` and a safe ``message``."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = _safe_message(message)
        self.headers = dict(headers) if headers else None
        super().__init__(self.message)


def _safe_message(message: str) -> str:
    text = message.strip() if isinstance(message, str) else ""
    if not text:
        return INTERNAL_ERROR_MESSAGE
    return text[:MAX_MESSAGE_LENGTH]


def error_envelope(code: str, message: str) -> dict[str, dict[str, str]]:
    """Build the Error_Envelope body."""
    return {"error": {"code": code, "message": _safe_message(message)}}


def error_response(
    status: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a JSON response holding an Error_Envelope."""
    return JSONResponse(
        status_code=status,
        content=error_envelope(code, message),
        headers=dict(headers) if headers else None,
    )


def _format_location(location: Sequence[Any]) -> str:
    return ".".join(str(part) for part in location) or "body"


def validation_message(errors: Iterable[Mapping[str, Any]]) -> str:
    """Name the failing field locations only, never the submitted values."""
    locations: list[str] = []
    for item in errors:
        location = _format_location(tuple(item.get("loc", ())))
        if location not in locations:
            locations.append(location)
    if not locations:
        return VALIDATION_ERROR_MESSAGE
    return _safe_message("request validation failed at: " + ", ".join(locations))


def validation_api_error(errors: Iterable[Mapping[str, Any]]) -> ApiError:
    """Map Pydantic ``errors()`` output to a 422 ``validation_error``."""
    return ApiError(422, "validation_error", validation_message(errors))


# -- exception handlers -----------------------------------------------------------------


async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message, exc.headers)


async def _request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(422, "validation_error", validation_message(exc.errors()))


_HTTP_CODES: dict[int, tuple[str, str]] = {
    404: ("not_found", "the requested resource was not found"),
    405: ("method_not_allowed", "the method is not allowed for this resource"),
}


async def _http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _HTTP_CODES.get(exc.status_code, (f"http_{exc.status_code}", "request failed"))
    return error_response(exc.status_code, code, message, exc.headers)


async def _cache_store_error_handler(_request: Request, exc: CacheStoreError) -> JSONResponse:
    # ``str(CacheStoreError)`` can hold the database path, so the message is fixed.
    _LOGGER.error("storage error: %s", type(exc).__name__)
    return error_response(500, "storage_error", STORAGE_ERROR_MESSAGE)


def install_exception_handlers(app: FastAPI) -> None:
    """Register the Error_Envelope handlers on ``app``."""
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(CacheStoreError, _cache_store_error_handler)


# -- catch-all middleware -----------------------------------------------------------------


class CatchAllMiddleware:
    """Pure-ASGI middleware: any unhandled exception becomes 500 ``internal_error``.

    It logs ``type(exc).__name__`` only (no headers, body, or credentials) and does not
    re-raise, so the server keeps serving later requests (Requirement 9.11).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            _LOGGER.error("unhandled exception: %s", type(exc).__name__)
            if response_started:
                return
            response = error_response(500, "internal_error", INTERNAL_ERROR_MESSAGE)
            await response(scope, receive, send)


# -- engine error mapping -----------------------------------------------------------------

_INGESTION_400 = frozenset(
    {
        IngestionErrorKind.EMPTY_PATH,
        IngestionErrorKind.MALFORMED_PATH,
        IngestionErrorKind.URL_TOO_LONG,
        IngestionErrorKind.URL_BAD_SCHEME,
        IngestionErrorKind.URL_BAD_HOST,
        IngestionErrorKind.URL_FORBIDDEN_COMPONENT,
        IngestionErrorKind.URL_BAD_PATH,
        IngestionErrorKind.URL_BAD_OWNER,
        IngestionErrorKind.URL_BAD_REPO,
    }
)
_INGESTION_422 = frozenset(
    {
        IngestionErrorKind.NOT_FOUND,
        IngestionErrorKind.NOT_A_DIRECTORY,
        IngestionErrorKind.NOT_READABLE,
        IngestionErrorKind.INVALID_LIMIT,
        IngestionErrorKind.DESTINATION_OUTSIDE_WORKSPACE,
        IngestionErrorKind.GIT_FAILED,
    }
)
_INGESTION_500 = frozenset(
    {
        IngestionErrorKind.GIT_NOT_INSTALLED,
        IngestionErrorKind.ROOT_FILESYSTEM_ERROR,
        IngestionErrorKind.CLEANUP_FAILED,
    }
)


def map_ingestion_error(error: IngestionError) -> ApiError:
    """Map an ``IngestionError`` by kind (Requirements 10.3 to 10.5).

    The code is the lower-case kind value and the message is ``error.message``, which never
    holds the path, git stderr, or ``detail``.
    """
    kind = error.kind
    if kind in _INGESTION_400:
        status = 400
    elif kind in _INGESTION_422:
        status = 422
    elif kind is IngestionErrorKind.GIT_TIMEOUT:
        status = 504
    elif kind in _INGESTION_500:
        status = 500
    else:
        return ApiError(500, "internal_error", INTERNAL_ERROR_MESSAGE)
    return ApiError(status, kind.value, error.message or "ingestion failed")


def map_pipeline_error(error: AnalysisPipelineError) -> ApiError:
    """Map an ``AnalysisPipelineError``; ``NoAnalyzableFilesError`` is checked first."""
    if isinstance(error, NoAnalyzableFilesError):
        return ApiError(422, "no_supported_files", "the repository contains no supported files")
    try:
        step = PipelineStep(error.step)
    except ValueError:
        return ApiError(500, "analysis_failed", "analysis failed")
    if step is PipelineStep.PERSIST:
        return ApiError(500, "storage_error", STORAGE_ERROR_MESSAGE)
    return ApiError(500, "analysis_failed", f"analysis failed at step '{step.value}'")


_PEDAGOGY_MAP: dict[PedagogyErrorKind, tuple[int, str, str]] = {
    PedagogyErrorKind.UNKNOWN_TARGET: (
        404,
        "unknown_target",
        "the target is not in the stored snapshot",
    ),
    PedagogyErrorKind.MISSING_DATA: (404, "repo_not_found", "the repository is not stored"),
    PedagogyErrorKind.SOURCE_UNREADABLE: (
        409,
        "source_unreadable",
        "the target source cannot be read",
    ),
    PedagogyErrorKind.LLM_FAILURE: (503, "llm_unavailable", "the explanation is unavailable"),
    PedagogyErrorKind.INVALID_OUTPUT: (
        502,
        "invalid_llm_output",
        "the explanation output was invalid",
    ),
}


def map_pedagogy_error(error: PedagogyError) -> ApiError:
    """Map a ``PedagogyError`` by kind (Requirements 12.5 to 12.8) with fixed messages."""
    entry = _PEDAGOGY_MAP.get(error.kind)
    if entry is None:
        return ApiError(500, "internal_error", INTERNAL_ERROR_MESSAGE)
    return ApiError(*entry)


_MASTERY_MAP: dict[MasteryErrorKind, tuple[int, str, str]] = {
    MasteryErrorKind.UNKNOWN_REPOSITORY: (404, "repo_not_found", "the repository is not stored"),
    MasteryErrorKind.UNKNOWN_TARGET: (
        404,
        "unknown_target",
        "the target is not in the stored snapshot",
    ),
    MasteryErrorKind.SOURCE_UNREADABLE: (
        409,
        "source_unreadable",
        "the target source cannot be read",
    ),
    MasteryErrorKind.STUDY_MODE_DISABLED: (
        409,
        "study_mode_disabled",
        "study mode is off for this repository",
    ),
    MasteryErrorKind.GRADING_UNAVAILABLE: (503, "grading_unavailable", "grading is unavailable"),
    MasteryErrorKind.INVALID_CLOCK: (500, "internal_error", INTERNAL_ERROR_MESSAGE),
    MasteryErrorKind.REVIEW_DATE_OUT_OF_RANGE: (500, "internal_error", INTERNAL_ERROR_MESSAGE),
    MasteryErrorKind.INVALID_TRANSITION: (500, "internal_error", INTERNAL_ERROR_MESSAGE),
    MasteryErrorKind.STORAGE: (500, "storage_error", STORAGE_ERROR_MESSAGE),
}

# Kinds whose engine messages are fixed literals that describe the request shape only.
_MASTERY_OWN_MESSAGE: dict[MasteryErrorKind, tuple[int, str]] = {
    MasteryErrorKind.INVALID_ANSWERS: (422, "invalid_answers"),
    MasteryErrorKind.INVALID_INPUT: (422, "validation_error"),
}


def map_mastery_error(error: MasteryError) -> ApiError:
    """Map a ``MasteryError`` by kind (Requirements 14.6, 14.8, 14.10, 14.11)."""
    own = _MASTERY_OWN_MESSAGE.get(error.kind)
    if own is not None:
        status, code = own
        return ApiError(status, code, str(error) or VALIDATION_ERROR_MESSAGE)
    entry = _MASTERY_MAP.get(error.kind)
    if entry is None:
        return ApiError(500, "internal_error", INTERNAL_ERROR_MESSAGE)
    return ApiError(*entry)


__all__ = [
    "ApiError",
    "CatchAllMiddleware",
    "INTERNAL_ERROR_MESSAGE",
    "MAX_MESSAGE_LENGTH",
    "STORAGE_ERROR_MESSAGE",
    "error_envelope",
    "error_response",
    "install_exception_handlers",
    "map_ingestion_error",
    "map_mastery_error",
    "map_pedagogy_error",
    "map_pipeline_error",
    "validation_api_error",
    "validation_message",
]
