"""Spec discovery and parsing for the Spec_Grounder (Spec #02).

``discover_specs`` reads the Kiro spec documents under ``.kiro/specs/<name>/`` and the
steering documents directly under ``.kiro/steering/``, and splits each into Markdown
sections. It makes no LLM call, no network call, and no subprocess call, and it
only reads: nothing under the repository root is created, changed, or deleted.

Every candidate file is checked with ``lstat`` first. A symlink, a non-regular file,
or a path that resolves outside the repository root is skipped as unreadable, so a
hostile repository cannot make the grounder read files elsewhere on disk.
"""

import logging
import os
import re
import shutil
import stat
import subprocess
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal

from backend.domain.models import (
    ProvenanceReport,
    RepoGraphSnapshot,
    SpecDriftItem,
    SpecLink,
    SymbolKind,
)

__all__ = [
    "GrounderResult",
    "ParsedSection",
    "SkipReason",
    "SkippedSpecFile",
    "SpecDocument",
    "SpecGrounderError",
    "build_provenance",
    "build_spec_links",
    "detect_drift",
    "discover_specs",
]

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 524_288
_SPEC_DOCUMENTS = ("design.md", "requirements.md", "tasks.md")
_SPECS_DIR = ".kiro/specs"
_STEERING_DIR = ".kiro/steering"
_STEERING_SUFFIX = ".md"

_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})")

_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TOKEN_SPLIT_RE = re.compile(r"[\s`]+")
_HEADING_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9_.]+")
_REF_RE = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+$")
_REF_STRIP_CHARS = "()[]<>,;:\"'"
_PLACEHOLDER_MARKERS = ("<", ">", "{", "}", "*", "...")
_SUPPORTED_EXTENSIONS = (".py", ".ts", ".js", ".tsx", ".java")
_NON_CORE_DIRS = frozenset({"tests", "test", "__tests__", "docs", "examples"})

_GIT_COMMAND = ["git", "log", "-n", "20", "--pretty=format:%h|%s", "--name-only"]
_GIT_TIMEOUT_SECONDS = 10
_GIT_MAX_OUTPUT_BYTES = 1_048_576
_GIT_MAX_COMMITS = 20
_GIT_MAX_RECORDS_PER_FILE = 20
_GIT_ENV = {
    "PATH": os.environ.get("PATH", os.defpath),
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "core.quotepath",
    "GIT_CONFIG_VALUE_0": "false",
}
_COMMIT_HEADER_RE = re.compile(r"^[0-9a-f]{4,64}\|")

_CONF_PATH = 0.90
_CONF_QUALNAME = 0.75
_CONF_NAME = 0.70
_CONF_HEADING = 0.50
_EXCERPT_MAX = 300
_EXCERPT_LEAD = 60


class SpecGrounderError(Exception):
    """The spec grounder cannot run. The message names the cause."""


class SkipReason(StrEnum):
    """Why a spec or steering file was skipped."""

    UNREADABLE = "unreadable"
    INVALID_ENCODING = "invalid_encoding"
    OVERSIZE = "oversize"


@dataclass(frozen=True)
class SkippedSpecFile:
    """A spec or steering file that was skipped. ``path`` is relative to the root."""

    path: str
    reason: SkipReason


@dataclass(frozen=True)
class ParsedSection:
    """One Markdown section of a spec or steering document.

    ``source_file`` is the document file name, for example ``design.md``.
    ``text`` runs from the heading line to the next heading of the same or lower
    level number. ``own_text`` runs from the heading line to the next heading of
    any level.
    """

    origin: Literal["spec", "steering"]
    spec_name: str | None
    source_file: str
    title: str
    level: int
    text: str
    own_text: str


@dataclass(frozen=True)
class SpecDocument:
    """The full text of one parsed Kiro_Spec_Document, including text before any heading."""

    spec_name: str
    source_file: str
    text: str


@dataclass(frozen=True)
class GrounderResult:
    """Output of discovery: parsed sections, skipped files, and the spec flag.

    ``documents`` holds the full text of every Kiro_Spec_Document that was read
    (steering documents excluded), in discovery order. Drift detection uses it.
    """

    sections: tuple[ParsedSection, ...]
    skipped: tuple[SkippedSpecFile, ...]
    has_kiro_specs: bool
    documents: tuple[SpecDocument, ...] = ()


def discover_specs(repo_root: Path) -> GrounderResult:
    """Discover and parse the Kiro spec and steering documents under ``repo_root``.

    Spec directories are visited in ascending name order, documents in the order
    ``design.md``, ``requirements.md``, ``tasks.md``, then steering files in
    ascending name order. Missing sources produce no entries and no error. A file
    that cannot be read, is not UTF-8, or exceeds 524,288 bytes is recorded in
    ``skipped`` and processing continues.

    Raises ``SpecGrounderError`` if ``repo_root`` is not a readable directory.
    """
    root = Path(repo_root)
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        raise SpecGrounderError(f"repo root is not a readable directory: {str(root)!r}")
    try:
        resolved_root = root.resolve()
    except (OSError, RuntimeError) as exc:
        raise SpecGrounderError(f"repo root cannot be resolved: {str(root)!r}") from exc

    sections: list[ParsedSection] = []
    skipped: list[SkippedSpecFile] = []
    documents: list[SpecDocument] = []
    has_kiro_specs = False

    for spec_name in _list_names(root / _SPECS_DIR, want_dir=True):
        for document in _SPEC_DOCUMENTS:
            rel = f"{_SPECS_DIR}/{spec_name}/{document}"
            outcome = _read_document(root, resolved_root, rel)
            if outcome is None:
                continue
            if isinstance(outcome, SkipReason):
                skipped.append(SkippedSpecFile(path=rel, reason=outcome))
                continue
            has_kiro_specs = True
            documents.append(SpecDocument(spec_name=spec_name, source_file=document, text=outcome))
            sections.extend(_parse_sections(outcome, "spec", spec_name, document))

    for name in _list_names(root / _STEERING_DIR, want_dir=False):
        if not name.endswith(_STEERING_SUFFIX):
            continue
        rel = f"{_STEERING_DIR}/{name}"
        outcome = _read_document(root, resolved_root, rel)
        if outcome is None:
            continue
        if isinstance(outcome, SkipReason):
            skipped.append(SkippedSpecFile(path=rel, reason=outcome))
            continue
        sections.extend(_parse_sections(outcome, "steering", None, name))

    return GrounderResult(
        sections=tuple(sections),
        skipped=tuple(skipped),
        has_kiro_specs=has_kiro_specs,
        documents=tuple(documents),
    )


def _list_names(directory: Path, *, want_dir: bool) -> list[str]:
    """Return the sorted direct-child names of ``directory``, or ``[]`` if absent.

    With ``want_dir`` true only directories are returned. Otherwise every entry that
    is not a plain directory is returned, so symlinks are still reported and skipped
    later by ``_read_document``.
    """
    try:
        with os.scandir(directory) as entries:
            names: list[str] = []
            for entry in entries:
                try:
                    if want_dir:
                        if entry.is_dir():
                            names.append(entry.name)
                    elif not entry.is_dir(follow_symlinks=False):
                        names.append(entry.name)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(names)


def _read_document(root: Path, resolved_root: Path, rel: str) -> str | SkipReason | None:
    """Read one candidate file.

    Returns the decoded text, a ``SkipReason`` when the file must be skipped, or
    ``None`` when the file does not exist (a missing document is not an error).
    """
    path = root.joinpath(*rel.split("/"))
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError:
        return SkipReason.UNREADABLE
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return SkipReason.UNREADABLE
    try:
        if not path.resolve().is_relative_to(resolved_root):
            return SkipReason.UNREADABLE
    except (OSError, RuntimeError):
        return SkipReason.UNREADABLE
    if info.st_size > _MAX_FILE_BYTES:
        return SkipReason.OVERSIZE
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_FILE_BYTES + 1)
    except OSError:
        return SkipReason.UNREADABLE
    if len(data) > _MAX_FILE_BYTES:
        return SkipReason.OVERSIZE
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return SkipReason.INVALID_ENCODING


def _parse_sections(
    content: str,
    origin: Literal["spec", "steering"],
    spec_name: str | None,
    source_file: str,
) -> list[ParsedSection]:
    """Split ``content`` into sections at ATX headings outside fenced blocks."""
    lines = content.removeprefix("\ufeff").split("\n")
    headings: list[tuple[int, int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))

    sections: list[ParsedSection] = []
    for position, (start, level, title) in enumerate(headings):
        own_end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        text_end = len(lines)
        for next_start, next_level, _ in headings[position + 1 :]:
            if next_level <= level:
                text_end = next_start
                break
        sections.append(
            ParsedSection(
                origin=origin,
                spec_name=spec_name,
                source_file=source_file,
                title=title,
                level=level,
                text="\n".join(lines[start:text_end]),
                own_text="\n".join(lines[start:own_end]),
            )
        )
    return sections


def _path_regex(path: str) -> re.Pattern[str]:
    """Return the boundary-aware regex that matches ``path`` as a whole path."""
    return re.compile(
        r"(?<![A-Za-z0-9_./-])" + re.escape(path) + r"(?![A-Za-z0-9_/-]|\.[A-Za-z0-9_])"
    )


def _excerpt(text: str, match_start: int) -> str:
    """Return ``text`` when short, else the 300-character window containing the match."""
    if len(text) <= _EXCERPT_MAX:
        return text
    start = min(max(match_start - _EXCERPT_LEAD, 0), len(text) - _EXCERPT_MAX)
    return text[start : start + _EXCERPT_MAX]


def build_spec_links(
    snapshot: RepoGraphSnapshot, sections: Sequence[ParsedSection]
) -> dict[str, list[SpecLink]]:
    """Link Snapshot files to spec sections using literal, checkable evidence.

    Evidence is attributed to the innermost section whose ``own_text`` contains it.
    Steering sections produce no links. There is one link per (file, section), at
    the highest confidence among its evidence. The result is keyed by Snapshot file
    path (ascending), lists only paths with at least one link, and sorts each list
    by ``(-confidence, spec_name, source_file, section_title)``.
    """
    spec_sections = [s for s in sections if s.origin == "spec" and s.spec_name is not None]
    if not spec_sections:
        return {}

    name_counts: dict[str, int] = {}
    stem_counts: dict[str, int] = {}
    for analysis in snapshot.files:
        stem = PurePosixPath(analysis.file_path).stem
        stem_counts[stem] = stem_counts.get(stem, 0) + 1
        for symbol in analysis.symbols:
            name_counts[symbol.name] = name_counts.get(symbol.name, 0) + 1

    section_spans: list[dict[str, int]] = []
    section_tokens: list[frozenset[str]] = []
    for section in spec_sections:
        spans: dict[str, int] = {}
        for match in _CODE_SPAN_RE.finditer(section.own_text):
            content = match.group(1).removesuffix("()")
            spans.setdefault(content, match.start())
        section_spans.append(spans)
        section_tokens.append(
            frozenset(t for t in _HEADING_TOKEN_SPLIT_RE.split(section.title) if t)
        )

    links: dict[str, list[SpecLink]] = {}
    for analysis in snapshot.files:
        path = analysis.file_path
        path_re = _path_regex(path)
        basename = PurePosixPath(path).name
        stem = PurePosixPath(path).stem
        heading_names = {basename}
        if len(stem) >= 4 and stem_counts[stem] == 1:
            heading_names.add(stem)
        qualnames = {symbol.qualname for symbol in analysis.symbols}
        unique_names = {s.name for s in analysis.symbols if name_counts[s.name] == 1}
        for symbol in analysis.symbols:
            if symbol.kind == SymbolKind.COMPONENT:
                heading_names.add(symbol.name)

        for section, spans, tokens in zip(
            spec_sections, section_spans, section_tokens, strict=True
        ):
            candidates: list[tuple[float, int]] = []
            if path in section.own_text:
                found = path_re.search(section.own_text)
                if found:
                    candidates.append((_CONF_PATH, found.start()))
            for content, position in spans.items():
                if content in qualnames:
                    candidates.append((_CONF_QUALNAME, position))
                elif content in unique_names:
                    candidates.append((_CONF_NAME, position))
            if not heading_names.isdisjoint(tokens):
                candidates.append((_CONF_HEADING, 0))
            if not candidates or section.source_file not in _SPEC_DOCUMENTS:
                continue
            confidence, position = min(candidates, key=lambda c: (-c[0], c[1]))
            links.setdefault(path, []).append(
                SpecLink(
                    spec_name=section.spec_name or "",
                    source_file=section.source_file,  # type: ignore[arg-type]
                    section_title=section.title,
                    excerpt=_excerpt(section.text, position),
                    confidence=confidence,
                )
            )

    for entries in links.values():
        entries.sort(
            key=lambda link: (
                -link.confidence,
                link.spec_name,
                link.source_file,
                link.section_title,
            )
        )
    return {path: links[path] for path in sorted(links)}


def _is_core_file(path: str, symbol_count: int) -> bool:
    """Return True for a Core_Implementation_File."""
    parts = path.split("/")
    if parts[-1] == "__init__.py" or symbol_count < 1:
        return False
    return _NON_CORE_DIRS.isdisjoint(parts[:-1])


def _referenced_paths(text: str) -> list[str]:
    """Collect candidate reference tokens from code spans and list items outside fences."""
    tokens: list[str] = []
    in_fence = False
    for line in text.removeprefix("\ufeff").split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _LIST_ITEM_RE.match(line):
            chunks: Iterable[str] = [line]
        else:
            chunks = [m.group(1) for m in _CODE_SPAN_RE.finditer(line)]
        for chunk in chunks:
            tokens.extend(t for t in _TOKEN_SPLIT_RE.split(chunk) if t)
    return tokens


def _clean_reference(token: str) -> str:
    """Strip surrounding punctuation and trailing dots from a candidate token."""
    previous = None
    while previous != token:
        previous = token
        token = token.strip(_REF_STRIP_CHARS).rstrip(".")
    return token


def _known_prefixes(repo_root: Path) -> frozenset[str]:
    """Return the directory names directly under ``repo_root``."""
    try:
        with os.scandir(repo_root) as entries:
            names = []
            for entry in entries:
                try:
                    if entry.is_dir():
                        names.append(entry.name)
                except OSError:
                    continue
    except OSError:
        return frozenset()
    return frozenset(names)


def _is_reference(candidate: str, prefixes: frozenset[str]) -> bool:
    """Return True when ``candidate`` is a Referenced_Task_Path."""
    if not _REF_RE.match(candidate):
        return False
    if candidate.startswith("/") or "://" in candidate:
        return False
    if any(marker in candidate for marker in _PLACEHOLDER_MARKERS):
        return False
    if "example" in candidate.lower():
        return False
    segments = candidate.split("/")
    if ".." in segments:
        return False
    return candidate.endswith(_SUPPORTED_EXTENSIONS) or segments[0] in prefixes


def detect_drift(
    snapshot: RepoGraphSnapshot,
    repo_root: Path,
    result: GrounderResult,
    spec_links: dict[str, list[SpecLink]],
) -> list[SpecDriftItem]:
    """Detect ``UNSPECIFIED_CODE`` and ``UNIMPLEMENTED_SPEC`` drift.

    Returns no items when ``result.has_kiro_specs`` is false. Items are unique per
    ``(drift_type, target)`` and sorted ascending by ``(drift_type, target)``.
    Skipped documents are absent from ``result.documents`` and yield no drift.
    """
    if not result.has_kiro_specs:
        return []
    root = Path(repo_root)
    items: dict[tuple[str, str], SpecDriftItem] = {}

    spec_texts = [doc.text for doc in result.documents]
    for analysis in snapshot.files:
        path = analysis.file_path
        if spec_links.get(path) or not _is_core_file(path, len(analysis.symbols)):
            continue
        if any(path in text and _path_regex(path).search(text) for text in spec_texts):
            continue
        items.setdefault(
            ("UNSPECIFIED_CODE", path),
            SpecDriftItem(
                drift_type="UNSPECIFIED_CODE",
                target=path,
                details=(
                    f"no spec section links or mentions this file ({len(analysis.symbols)} symbols)"
                ),
            ),
        )

    prefixes = _known_prefixes(root)
    snapshot_paths = [analysis.file_path for analysis in snapshot.files]
    for doc in result.documents:
        if doc.source_file != "tasks.md":
            continue
        for token in _referenced_paths(doc.text):
            ref = _clean_reference(token)
            key = ("UNIMPLEMENTED_SPEC", ref)
            if key in items or not _is_reference(ref, prefixes):
                continue
            try:
                if (root / ref).exists():
                    continue
            except (OSError, ValueError):
                pass
            suffix = "/" + ref
            if any(p == ref or p.endswith(suffix) for p in snapshot_paths):
                continue
            items[key] = SpecDriftItem(
                drift_type="UNIMPLEMENTED_SPEC",
                target=ref,
                details=f"referenced in {doc.spec_name}/tasks.md but not found",
            )

    return [items[key] for key in sorted(items)]


def _git_log_output(repo_root: Path) -> str | None:
    """Run the read-only ``git log`` and return its decoded output, or ``None`` on failure.

    Failures (no ``.git`` directory, no git executable, timeout, oversize output,
    non-zero exit, ``OSError``) are logged by category only, never with raw output.
    """
    try:
        if not (repo_root / ".git").is_dir():
            logger.info("git history skipped: no_git_dir")
            return None
    except OSError:
        logger.info("git history skipped: no_git_dir")
        return None
    if shutil.which("git") is None:
        logger.info("git history skipped: git_unavailable")
        return None

    try:
        proc = subprocess.Popen(  # noqa: S603 - fixed argument list, shell=False
            _GIT_COMMAND,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            shell=False,
            env=_GIT_ENV,
        )
    except (OSError, ValueError):
        logger.info("git history skipped: spawn_failed")
        return None

    timer = threading.Timer(_GIT_TIMEOUT_SECONDS, proc.kill)
    timer.start()
    data = b""
    read_failed = False
    try:
        try:
            if proc.stdout is not None:
                data = proc.stdout.read(_GIT_MAX_OUTPUT_BYTES + 1)
        except OSError:
            read_failed = True
        oversize = len(data) > _GIT_MAX_OUTPUT_BYTES
        if oversize or read_failed:
            proc.kill()
    except BaseException:
        proc.kill()
        raise
    finally:
        # Always reap the process and close the pipe so no zombie or fd is left behind.
        try:
            proc.wait()
        finally:
            timer.cancel()
            if proc.stdout is not None:
                proc.stdout.close()
    if read_failed:
        logger.info("git history skipped: read_failed")
        return None
    if oversize:
        logger.info("git history skipped: oversize_output")
        return None
    if proc.returncode != 0:
        logger.info("git history skipped: nonzero_exit")
        return None
    return data.decode("utf-8", errors="replace")


def _git_history(snapshot: RepoGraphSnapshot, repo_root: Path) -> dict[str, list[str]]:
    """Return recent Commit_Records per Snapshot file, newest first.

    Returns an empty mapping when git history is unavailable. Only Commit_Records
    of Snapshot files are kept. At most 20 commits are read and at most 20 records
    are kept per file.
    """
    output = _git_log_output(repo_root)
    if not output:
        return {}
    snapshot_paths = {analysis.file_path for analysis in snapshot.files}
    if not snapshot_paths:
        return {}

    history: dict[str, list[str]] = {}
    commits = 0
    for block in output.split("\n\n"):
        record: str | None = None
        for line in block.split("\n"):
            if not line:
                continue
            if record is None:
                is_header = True
            else:
                # A commit with no changed files has no trailing blank line, so its
                # successor's header follows directly. Snapshot paths win over the pattern.
                is_header = line not in snapshot_paths and _COMMIT_HEADER_RE.match(line) is not None
            if is_header:
                commits += 1
                if commits > _GIT_MAX_COMMITS:
                    return {path: history[path] for path in sorted(history)}
                record = line
                continue
            if record is None or line not in snapshot_paths:
                continue
            records = history.setdefault(line, [])
            if len(records) < _GIT_MAX_RECORDS_PER_FILE and record not in records:
                records.append(record)
    return {path: history[path] for path in sorted(history)}


def build_provenance(
    snapshot: RepoGraphSnapshot, repo_root: Path | None = None
) -> ProvenanceReport:
    """Build the ``ProvenanceReport`` for ``snapshot``.

    ``repo_root`` defaults to ``Path(snapshot.root_path)``. The function reads files
    and runs one read-only ``git log``; it makes no LLM or network call and writes
    nothing under ``repo_root``. The same inputs produce an equal report.

    Raises ``SpecGrounderError`` when ``snapshot`` is not a ``RepoGraphSnapshot`` or
    ``repo_root`` is not a readable directory. No partial report is returned.
    """
    if not isinstance(snapshot, RepoGraphSnapshot):
        raise SpecGrounderError("snapshot must be a RepoGraphSnapshot")
    root = Path(snapshot.root_path) if repo_root is None else Path(repo_root)
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        raise SpecGrounderError(f"repo root is not a readable directory: {str(root)!r}")

    result = discover_specs(root)
    spec_links = build_spec_links(snapshot, result.sections)
    drift_items = detect_drift(snapshot, root, result, spec_links)
    recent_commits = _git_history(snapshot, root)
    return ProvenanceReport(
        repo_id=snapshot.repo_id,
        has_kiro_specs=result.has_kiro_specs,
        spec_links=spec_links,
        drift_items=drift_items,
        recent_commits=recent_commits,
    )
