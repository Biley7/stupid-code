"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import os
import socket
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test with the mock LLM provider, an in-memory cache, and no Gemini key."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("STUPID_CODE_DB_PATH", ":memory:")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def _real(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.realpath(path))


def _is_within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


@pytest.fixture
def offline_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Opt-in guard that blocks network connects and pathlib reads outside allowed roots.

    Allowed roots are the repository root, the pytest temp directory, the system temp
    directory, ``sys.prefix`` and ``sys.base_prefix``. Only reads through ``Path.read_text``,
    ``Path.read_bytes`` and ``Path.open`` (in a read mode) are guarded. Everything is undone
    by ``monkeypatch`` after the test.
    """
    roots = [
        _real(root)
        for root in (
            REPO_ROOT,
            tmp_path_factory.getbasetemp(),
            tempfile.gettempdir(),
            sys.prefix,
            sys.base_prefix,
        )
    ]

    def blocked_connect(self: socket.socket, address: Any) -> None:
        raise AssertionError(f"network access attempted: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    def check(path: Path) -> None:
        if not _is_within(_real(path), roots):
            raise AssertionError(f"read outside allowed roots: {path}")

    def guard(original: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(self: Path, *args: Any, **kwargs: Any) -> Any:
            check(self)
            return original(self, *args, **kwargs)

        return wrapper

    monkeypatch.setattr(Path, "read_text", guard(Path.read_text))
    monkeypatch.setattr(Path, "read_bytes", guard(Path.read_bytes))

    original_open = Path.open

    def guarded_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if "r" in mode or "+" in mode:
            check(self)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
