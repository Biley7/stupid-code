"""Safe repository ingestion: types, GitHub URL validation, clone destination.

This module never executes or imports analyzed repository code. URL validation is a
pure function; destination construction is a separate step that runs after it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

__all__ = [
    "DiscoveryResult",
    "GitHubRepoRef",
    "GitRunner",
    "IngestionError",
    "IngestionErrorKind",
    "IngestionWarning",
    "WarningKind",
    "build_clone_destination",
    "discover_github",
    "discover_local",
    "validate_github_url",
]

# Any callable with the ``subprocess.run`` signature; tests pass a recording double.
GitRunner = Callable[..., subprocess.CompletedProcess]

MAX_URL_LENGTH = 2048
MAX_OWNER_LENGTH = 39
MAX_REPO_LENGTH = 100
DEFAULT_MAX_FILES = 500
DEFAULT_MAX_TOTAL_BYTES = 20_971_520
MAX_FILE_BYTES = 524_288
NUL_PROBE_BYTES = 8192
SUPPORTED_EXTENSIONS = frozenset({".py", ".ts", ".js", ".tsx", ".java"})
SKIPPED_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        "__pycache__",
        ".next",
        "target",
        ".pytest_cache",
    }
)
GIT_TIMEOUT_SECONDS = 60
GIT_STDERR_DETAIL_CHARS = 500
_GITHUB_HOST = "github.com"
_NAME_RE = re.compile(r"[A-Za-z0-9_.-]+")
_ENCODED_SEPARATOR_RE = re.compile(r"%(2f|5c)", re.IGNORECASE)


class IngestionErrorKind(Enum):
    EMPTY_PATH = "empty_path"
    MALFORMED_PATH = "malformed_path"
    NOT_FOUND = "not_found"
    NOT_A_DIRECTORY = "not_a_directory"
    NOT_READABLE = "not_readable"
    INVALID_LIMIT = "invalid_limit"
    ROOT_FILESYSTEM_ERROR = "root_filesystem_error"
    URL_TOO_LONG = "url_too_long"
    URL_BAD_SCHEME = "url_bad_scheme"
    URL_BAD_HOST = "url_bad_host"
    URL_FORBIDDEN_COMPONENT = "url_forbidden_component"
    URL_BAD_PATH = "url_bad_path"
    URL_BAD_OWNER = "url_bad_owner"
    URL_BAD_REPO = "url_bad_repo"
    DESTINATION_OUTSIDE_WORKSPACE = "destination_outside_workspace"
    GIT_NOT_INSTALLED = "git_not_installed"
    GIT_FAILED = "git_failed"
    GIT_TIMEOUT = "git_timeout"
    CLEANUP_FAILED = "cleanup_failed"


class IngestionError(Exception):
    """Typed ingestion failure identified by ``kind``."""

    def __init__(self, kind: IngestionErrorKind, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        return self.message if self.detail is None else f"{self.message}: {self.detail}"


class WarningKind(Enum):
    SYMLINK_ESCAPE = "symlink_escape"
    ENTRY_UNREADABLE = "entry_unreadable"


@dataclass(frozen=True)
class IngestionWarning:
    kind: WarningKind
    path: str
    detail: str


@dataclass(frozen=True)
class GitHubRepoRef:
    owner: str
    repo: str
    clone_url: str


@dataclass(frozen=True)
class DiscoveryResult:
    root: Path
    files: list[str]
    truncated: bool
    warnings: list[IngestionWarning]


def _fail(kind: IngestionErrorKind, message: str, detail: str | None = None) -> IngestionError:
    return IngestionError(kind, message, detail)


def _has_whitespace_or_control(text: str) -> bool:
    return any(ch.isspace() or unicodedata.category(ch) == "Cc" for ch in text)


def _check_name(value: str, max_length: int, kind: IngestionErrorKind, label: str) -> None:
    if not value or len(value) > max_length or _NAME_RE.fullmatch(value) is None:
        raise _fail(
            kind,
            f"Invalid GitHub {label}",
            f"{label} must match [A-Za-z0-9_.-] with length 1 to {max_length}",
        )
    if value in (".", ".."):
        raise _fail(kind, f"Invalid GitHub {label}", f"{label} must not be {value!r}")


def validate_github_url(url: str) -> GitHubRepoRef:
    """Validate a public GitHub HTTPS URL and rebuild the clone URL from owner and repo.

    Pure: never touches the filesystem or runs git. Rules apply in the design's order.
    """
    if len(url) > MAX_URL_LENGTH:
        raise _fail(
            IngestionErrorKind.URL_TOO_LONG,
            "GitHub URL is too long",
            f"maximum is {MAX_URL_LENGTH} characters",
        )
    if _has_whitespace_or_control(url):
        raise _fail(
            IngestionErrorKind.URL_FORBIDDEN_COMPONENT,
            "GitHub URL contains whitespace or control characters",
        )
    if not url.startswith("https://"):
        raise _fail(IngestionErrorKind.URL_BAD_SCHEME, "GitHub URL must use the https scheme")

    parts = urlsplit(url)
    netloc = parts.netloc
    if "@" in netloc:
        raise _fail(IngestionErrorKind.URL_FORBIDDEN_COMPONENT, "GitHub URL contains userinfo")
    host, has_port, _port = netloc.partition(":")
    if host != _GITHUB_HOST:
        raise _fail(
            IngestionErrorKind.URL_BAD_HOST, "GitHub URL host must be github.com", f"got {host!r}"
        )
    if has_port:
        raise _fail(IngestionErrorKind.URL_FORBIDDEN_COMPONENT, "GitHub URL contains a port")
    if "?" in url:
        raise _fail(IngestionErrorKind.URL_FORBIDDEN_COMPONENT, "GitHub URL contains a query")
    if "#" in url:
        raise _fail(IngestionErrorKind.URL_FORBIDDEN_COMPONENT, "GitHub URL contains a fragment")
    if _ENCODED_SEPARATOR_RE.search(url):
        raise _fail(
            IngestionErrorKind.URL_FORBIDDEN_COMPONENT,
            "GitHub URL contains an encoded path separator",
        )

    path = parts.path
    if path.endswith("/"):
        path = path[:-1]
    segments = path.split("/")
    if len(segments) != 3 or segments[0] != "":
        raise _fail(
            IngestionErrorKind.URL_BAD_PATH,
            "GitHub URL path must be /<owner>/<repo>",
            f"got {parts.path!r}",
        )
    owner, repo = segments[1], segments[2]
    repo = repo.removesuffix(".git")

    _check_name(owner, MAX_OWNER_LENGTH, IngestionErrorKind.URL_BAD_OWNER, "owner")
    _check_name(repo, MAX_REPO_LENGTH, IngestionErrorKind.URL_BAD_REPO, "repo")

    return GitHubRepoRef(
        owner=owner,
        repo=repo,
        clone_url=f"https://{_GITHUB_HOST}/{owner}/{repo}.git",
    )


def build_clone_destination(ref: GitHubRepoRef, workspace: Path) -> Path:
    """Return ``workspace/owner/repo`` as a real path verified to lie inside ``workspace``.

    Raises ``DESTINATION_OUTSIDE_WORKSPACE`` otherwise. Creates nothing and runs no git.
    """
    real_workspace = os.path.realpath(workspace)
    real_dest = os.path.realpath(Path(real_workspace) / ref.owner / ref.repo)
    inside = real_dest != real_workspace and (
        os.path.commonpath([real_workspace, real_dest]) == real_workspace
    )
    if not inside:
        raise _fail(
            IngestionErrorKind.DESTINATION_OUTSIDE_WORKSPACE,
            "Clone destination is outside the managed workspace",
            f"owner={ref.owner!r} repo={ref.repo!r}",
        )
    return Path(real_dest)


def _validate_limit(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _fail(
            IngestionErrorKind.INVALID_LIMIT,
            f"{name} must be an integer of at least 1",
            f"got {value!r}",
        )


def _is_inside(root: str, candidate: str) -> bool:
    return os.path.commonpath([root, candidate]) == root


def _walk(root: Path) -> tuple[list[tuple[str, int]], list[IngestionWarning]]:
    """Iteratively collect qualifying ``(relative_posix_path, size)`` pairs under ``root``."""
    root_str = str(root)
    qualifying: list[tuple[str, int]] = []
    warnings: list[IngestionWarning] = []
    visited_dirs: set[str] = {root_str}
    # Stack of (directory path, relative posix prefix); the root is handled first.
    stack: list[tuple[str, str]] = [(root_str, "")]

    def warn(kind: WarningKind, rel: str, detail: str) -> None:
        warnings.append(IngestionWarning(kind=kind, path=rel, detail=detail))

    while stack:
        directory, prefix = stack.pop()
        try:
            with os.scandir(directory) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            if directory == root_str:
                raise _fail(
                    IngestionErrorKind.ROOT_FILESYSTEM_ERROR,
                    "Cannot read repository root",
                    exc.strerror or type(exc).__name__,
                ) from exc
            warn(
                WarningKind.ENTRY_UNREADABLE,
                prefix.rstrip("/"),
                exc.strerror or type(exc).__name__,
            )
            continue

        child_dirs: list[tuple[str, str]] = []
        for entry in entries:
            rel = prefix + entry.name
            try:
                if entry.is_dir():
                    if entry.name in SKIPPED_DIRECTORIES:
                        continue
                    real = os.path.realpath(entry.path)
                    if not _is_inside(root_str, real):
                        warn(WarningKind.SYMLINK_ESCAPE, rel, "directory resolves outside root")
                        continue
                    if real in visited_dirs:
                        continue
                    visited_dirs.add(real)
                    child_dirs.append((entry.path, rel + "/"))
                    continue
                if os.path.splitext(entry.name)[1].lower() not in SUPPORTED_EXTENSIONS:
                    continue
                if not entry.is_file():
                    continue
                real = os.path.realpath(entry.path)
                if not _is_inside(root_str, real):
                    warn(WarningKind.SYMLINK_ESCAPE, rel, "file resolves outside root")
                    continue
                size = entry.stat().st_size
                if size > MAX_FILE_BYTES:
                    continue
                with open(entry.path, "rb") as fh:
                    if b"\x00" in fh.read(NUL_PROBE_BYTES):
                        continue
                qualifying.append((rel, size))
            except OSError as exc:
                warn(WarningKind.ENTRY_UNREADABLE, rel, exc.strerror or type(exc).__name__)
        # Reverse so that directories are popped in sorted order (deterministic pre-order).
        stack.extend(reversed(child_dirs))

    return qualifying, warnings


def _apply_limits(
    qualifying: list[tuple[str, int]], max_files: int, max_total_bytes: int
) -> tuple[list[str], bool]:
    ordered = sorted(qualifying)
    files: list[str] = []
    cumulative = 0
    for rel, size in ordered:
        if len(files) >= max_files or cumulative + size > max_total_bytes:
            return files, True
        files.append(rel)
        cumulative += size
    return files, False


def discover_from_root(root: Path, max_files: int, max_total_bytes: int) -> DiscoveryResult:
    """Walk an already validated real ``root`` and apply the file and byte limits."""
    qualifying, warnings = _walk(root)
    files, truncated = _apply_limits(qualifying, max_files, max_total_bytes)
    warnings.sort(key=lambda w: (w.path, w.kind.value))
    return DiscoveryResult(root=root, files=files, truncated=truncated, warnings=warnings)


def discover_local(
    path: str,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> DiscoveryResult:
    """Discover supported source files under a local directory without reading their code."""
    _validate_limit("max_files", max_files)
    _validate_limit("max_total_bytes", max_total_bytes)
    if not isinstance(path, str) or not path.strip():
        raise _fail(IngestionErrorKind.EMPTY_PATH, "Path is empty")
    if "\x00" in path:
        raise _fail(IngestionErrorKind.MALFORMED_PATH, "Path contains a NUL character")
    if not os.path.exists(path):
        raise _fail(IngestionErrorKind.NOT_FOUND, "Path does not exist", path)
    if not os.path.isdir(path):
        raise _fail(IngestionErrorKind.NOT_A_DIRECTORY, "Path is not a directory", path)
    if not os.access(path, os.R_OK | os.X_OK):
        raise _fail(IngestionErrorKind.NOT_READABLE, "Path is not readable", path)
    root = Path(os.path.realpath(path))
    return discover_from_root(root, max_files, max_total_bytes)


def _default_workspace() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "repos"


def _remove_inside(workspace: Path, path: Path) -> None:
    """Remove ``path`` only if its real path lies strictly inside ``workspace``."""
    real_workspace = os.path.realpath(workspace)
    real_path = os.path.realpath(path)
    if real_path == real_workspace or not _is_inside(real_workspace, real_path):
        raise _fail(
            IngestionErrorKind.CLEANUP_FAILED,
            "Refusing to remove a path outside the managed workspace",
            real_path,
        )
    try:
        if os.path.islink(path) or os.path.isfile(real_path):
            os.unlink(path)
        elif os.path.isdir(real_path):
            shutil.rmtree(real_path)
    except OSError as exc:
        raise _fail(
            IngestionErrorKind.CLEANUP_FAILED,
            "Could not remove existing clone destination",
            exc.strerror or type(exc).__name__,
        ) from exc


def discover_github(
    url: str,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    workspace: Path | None = None,
    git_runner: GitRunner = subprocess.run,
) -> DiscoveryResult:
    """Shallow-clone a public GitHub repository into the workspace and discover its files.

    ``git clone`` is the only subprocess started; no repository code is executed.
    """
    _validate_limit("max_files", max_files)
    _validate_limit("max_total_bytes", max_total_bytes)
    ref = validate_github_url(url)
    workspace_path = _default_workspace() if workspace is None else Path(workspace)
    dest = build_clone_destination(ref, workspace_path)

    if os.path.lexists(dest):
        _remove_inside(workspace_path, dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _fail(
            IngestionErrorKind.ROOT_FILESYSTEM_ERROR,
            "Cannot create clone destination directory",
            exc.strerror or type(exc).__name__,
        ) from exc

    argv = [
        "git",
        "-c",
        "core.hooksPath=" + os.devnull,
        "clone",
        "--depth",
        "30",
        "--single-branch",
        "--no-recurse-submodules",
        "--",
        ref.clone_url,
        str(dest),
    ]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    error: IngestionError | None = None
    try:
        completed = git_runner(
            argv,
            shell=False,
            timeout=GIT_TIMEOUT_SECONDS,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        error = _fail(IngestionErrorKind.GIT_NOT_INSTALLED, "git is not installed")
    except subprocess.TimeoutExpired:
        error = _fail(
            IngestionErrorKind.GIT_TIMEOUT,
            "git clone timed out",
            f"limit is {GIT_TIMEOUT_SECONDS} seconds",
        )
    else:
        if completed.returncode != 0:
            stderr = completed.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            error = _fail(
                IngestionErrorKind.GIT_FAILED,
                "git clone failed",
                (stderr or "")[:GIT_STDERR_DETAIL_CHARS],
            )

    if error is not None:
        if os.path.lexists(dest):
            _remove_inside(workspace_path, dest)
        raise error

    return discover_from_root(dest, max_files, max_total_bytes)
