"""API settings read once at startup (Requirements 9.4 to 9.7, 10.15 to 10.17, 10.22).

``load_api_settings`` reads five environment variables. The database path is not here; it
stays with the existing ``CacheSettings`` (``STUPID_CODE_DB_PATH``). A bad value raises
``ConfigurationError``, whose message names the variable and never its value, so
``create_app`` fails and the server serves no request.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

CORS_ORIGINS_VAR = "STUPID_CODE_CORS_ORIGINS"
ALLOW_LOCAL_INGEST_VAR = "ALLOW_LOCAL_INGEST"
GITHUB_RATE_LIMIT_VAR = "STUPID_CODE_GITHUB_RATE_LIMIT"
GITHUB_RATE_WINDOW_VAR = "STUPID_CODE_GITHUB_RATE_WINDOW_SECONDS"
CREW_SECRET_VAR = "KIRO_CREW_SECRET"

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
)
DEFAULT_GITHUB_RATE_LIMIT = 5
MAX_GITHUB_RATE_LIMIT = 1000
DEFAULT_GITHUB_RATE_WINDOW_SECONDS = 60
MAX_GITHUB_RATE_WINDOW_SECONDS = 3600

_TRUE_VALUES = frozenset({"true", "1"})
_FALSE_VALUES = frozenset({"false", "0"})
# ASCII digits only (``str.isdigit`` also accepts characters such as "²"). Seven digits
# are more than any accepted value needs and keep ``int()`` cheap.
_INTEGER_PATTERN = re.compile(r"[0-9]{1,7}")


class ConfigurationError(Exception):
    """An API setting is invalid. The message names the variable, never its value."""

    variable: str

    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(f"invalid configuration: {variable}")


@dataclass(frozen=True)
class ApiSettings:
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    allow_local_ingest: bool = True
    github_rate_limit: int = DEFAULT_GITHUB_RATE_LIMIT
    github_rate_window_seconds: int = DEFAULT_GITHUB_RATE_WINDOW_SECONDS
    crew_secret: str | None = field(default=None, repr=False)


def _parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return DEFAULT_CORS_ORIGINS
    origins = tuple(entry.strip() for entry in raw.split(",") if entry.strip())
    if "*" in origins:
        raise ConfigurationError(CORS_ORIGINS_VAR)
    return origins


def _parse_allow_local_ingest(raw: str | None) -> bool:
    value = "" if raw is None else raw.strip().lower()
    if not value or value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ConfigurationError(ALLOW_LOCAL_INGEST_VAR)


def _parse_bounded_int(raw: str | None, variable: str, default: int, maximum: int) -> int:
    value = "" if raw is None else raw.strip()
    if not value:
        return default
    if _INTEGER_PATTERN.fullmatch(value) is None:
        raise ConfigurationError(variable)
    number = int(value)
    if not 1 <= number <= maximum:
        raise ConfigurationError(variable)
    return number


def load_api_settings(environ: Mapping[str, str] | None = None) -> ApiSettings:
    """Read the API settings from ``environ`` (``os.environ`` when omitted)."""
    env = os.environ if environ is None else environ
    secret = env.get(CREW_SECRET_VAR)
    return ApiSettings(
        cors_origins=_parse_cors_origins(env.get(CORS_ORIGINS_VAR)),
        allow_local_ingest=_parse_allow_local_ingest(env.get(ALLOW_LOCAL_INGEST_VAR)),
        github_rate_limit=_parse_bounded_int(
            env.get(GITHUB_RATE_LIMIT_VAR),
            GITHUB_RATE_LIMIT_VAR,
            DEFAULT_GITHUB_RATE_LIMIT,
            MAX_GITHUB_RATE_LIMIT,
        ),
        github_rate_window_seconds=_parse_bounded_int(
            env.get(GITHUB_RATE_WINDOW_VAR),
            GITHUB_RATE_WINDOW_VAR,
            DEFAULT_GITHUB_RATE_WINDOW_SECONDS,
            MAX_GITHUB_RATE_WINDOW_SECONDS,
        ),
        crew_secret=secret if secret else None,
    )


__all__ = [
    "ALLOW_LOCAL_INGEST_VAR",
    "ApiSettings",
    "CORS_ORIGINS_VAR",
    "CREW_SECRET_VAR",
    "ConfigurationError",
    "DEFAULT_CORS_ORIGINS",
    "GITHUB_RATE_LIMIT_VAR",
    "GITHUB_RATE_WINDOW_VAR",
    "load_api_settings",
]
