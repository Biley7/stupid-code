"""Analysis_Pipeline: one path from a repository source to stored analysis.

REST, MCP, and Crew all reach analysis through this module, so none of them repeats
analysis logic. The pipeline only sequences existing engines:

1. Discover files with the Ingestion_Engine (``discover_local`` or ``discover_github``).
   An ``IngestionError`` propagates unchanged.
2. Derive the ``repo_id``.
3. Read the discovered files with ``O_NOFOLLOW``, a regular-file check, and the
   524,288-byte cap. A file that cannot be read becomes an ``ENTRY_UNREADABLE`` warning.
4. Raise ``NoAnalyzableFilesError`` when no file was read. Nothing is written.
5. Parse (``parse_source``), scan (``scan_many``), build the Snapshot (``build_snapshot``),
   build provenance (``build_provenance``), and profile topology (``profile_topology``).
6. Fingerprint the content: file hashes, the truncation flag, and the spec and steering
   documents found by ``discover_specs``.
7. Persist the Snapshot, provenance, topology, registry row, and mastery registration in
   one ``CacheStore.transact``, so they succeed or fail as one unit.

A failure after discovery raises ``AnalysisPipelineError`` naming the step and the
exception class only, never file content or server paths. The pipeline never executes,
imports, or installs analyzed code, and contains no parsing, graph, DSA, provenance, or
topology logic of its own.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.domain.models import ProvenanceReport, RepoGraphSnapshot, TopologyProfile
from backend.engines.ast_parser import ParsedFile, parse_source
from backend.engines.cache_store import CacheStore, CacheTransaction, RepositoryRecord
from backend.engines.dsa_scanner import scan_many
from backend.engines.graph_engine import build_snapshot
from backend.engines.ingestion import (
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_TOTAL_BYTES,
    MAX_FILE_BYTES,
    DiscoveryResult,
    GitRunner,
    IngestionWarning,
    WarningKind,
    discover_github,
    discover_local,
    validate_github_url,
)
from backend.engines.mastery import MasteryEngine
from backend.engines.spec_grounder import build_provenance, discover_specs
from backend.engines.topology import profile_topology

__all__ = [
    "AnalysisPipelineError",
    "AnalysisResult",
    "GitHubSource",
    "LocalSource",
    "NoAnalyzableFilesError",
    "PipelineStep",
    "Source",
    "analyze_repository",
    "derive_github_repo_id",
    "derive_local_repo_id",
    "ensure_analysis",
    "normalize_github_url",
]

_StoredAnalysis = tuple[
    RepositoryRecord | None,
    RepoGraphSnapshot | None,
    ProvenanceReport | None,
    TopologyProfile | None,
]

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SLUG_MAX = 60
_SCHEME_AUTHORITY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://([^/?#]*)")
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_OPEN_FLAGS = (
    os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
)

SOURCE_LOCAL = "local"
SOURCE_GITHUB = "github"


# -- sources, steps, errors, results ---------------------------------------------------


@dataclass(frozen=True)
class LocalSource:
    """A local directory to analyze."""

    path: str


@dataclass(frozen=True)
class GitHubSource:
    """A public GitHub HTTPS URL to clone and analyze."""

    url: str


Source = LocalSource | GitHubSource


class PipelineStep(StrEnum):
    READ = "read"
    PARSE = "parse"
    SCAN = "scan"
    GRAPH = "graph"
    PROVENANCE = "provenance"
    TOPOLOGY = "topology"
    PERSIST = "persist"


class AnalysisPipelineError(Exception):
    """A pipeline step after ingestion failed. The message names the step, never content."""

    def __init__(self, step: PipelineStep, message: str | None = None) -> None:
        self.step = step
        self.message = message or f"analysis failed at step '{step.value}'"
        super().__init__(self.message)


class NoAnalyzableFilesError(AnalysisPipelineError):
    """The source holds zero readable supported source files (Requirement 4.8)."""

    def __init__(self) -> None:
        super().__init__(PipelineStep.READ, "no analyzable source files were found")


@dataclass(frozen=True)
class AnalysisResult:
    repo_id: str
    snapshot: RepoGraphSnapshot
    provenance: ProvenanceReport
    topology: TopologyProfile
    truncated: bool
    warnings: tuple[IngestionWarning, ...]
    reused: bool  # True when ensure_analysis found current stored data


@dataclass(frozen=True)
class _ReadFiles:
    """Discovery output plus the bytes that were actually read."""

    discovery: DiscoveryResult
    contents: tuple[tuple[str, bytes], ...]
    warnings: tuple[IngestionWarning, ...]


# -- repo_id derivation (Requirement 4.5, 4.6) -----------------------------------------


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text).strip("-.")[:_SLUG_MAX] or "repo"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_local_repo_id(real_root: str) -> str:
    """Return ``local-<slug>-<16 hex>`` for a directory; equivalent spellings agree.

    The path is resolved with ``os.path.realpath`` first, so a trailing separator, a
    relative path, and its absolute form give one id. The digest covers the full real
    path, so two directories with the same final segment get different ids.
    """
    real = os.path.realpath(real_root)
    digest = _sha256_hex(os.fsencode(real))[:16]
    return f"local-{_slug(os.path.basename(real))}-{digest}"


def normalize_github_url(url: str) -> str:
    """Lower-case the scheme and the host of ``url`` (ASCII letters only).

    Userinfo, port, path, query, and fragment are left as they are, so
    ``validate_github_url`` still applies every other rule to the result.
    """
    match = _SCHEME_AUTHORITY_RE.match(url)
    if match is None:
        return url
    scheme, authority = match.group(1), match.group(2)
    userinfo, at, host_port = authority.rpartition("@")
    host, colon, port = host_port.partition(":")
    normalized = (
        f"{scheme.translate(_ASCII_LOWER)}://{userinfo}{at}"
        f"{host.translate(_ASCII_LOWER)}{colon}{port}"
    )
    return normalized + url[match.end() :]


def derive_github_repo_id(url: str) -> str:
    """Return ``gh-<slug>-<12 hex>`` for a GitHub URL. Raises ``IngestionError`` if invalid.

    Owner and repo are lower-cased, and ``validate_github_url`` removes a trailing ``/``
    and ``.git``, so those spellings and the host case give one id.
    """
    ref = validate_github_url(normalize_github_url(url))
    owner, repo = ref.owner.lower(), ref.repo.lower()
    digest = _sha256_hex(f"{owner}/{repo}".encode())[:12]
    return f"gh-{_slug(owner + '-' + repo)}-{digest}"


# -- steps -----------------------------------------------------------------------------


def _step[T](step: PipelineStep, operation: Callable[[], T]) -> T:
    """Run ``operation``; any exception becomes ``AnalysisPipelineError(step)``."""
    try:
        return operation()
    except AnalysisPipelineError:
        raise
    except Exception as exc:
        raise AnalysisPipelineError(
            step, f"analysis step '{step.value}' failed ({type(exc).__name__})"
        ) from exc


def _read_discovered(root: Path, rel: str) -> bytes:
    """Read one discovered file without following a final symlink. Raises ``OSError``."""
    fd = os.open(root / rel, _OPEN_FLAGS)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(0, "not a regular file")
        if info.st_size > MAX_FILE_BYTES:
            raise OSError(0, "file exceeds 524288 bytes")
        chunks: list[bytes] = []
        remaining = MAX_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_FILE_BYTES:
            raise OSError(0, "file exceeds 524288 bytes")
        return data
    finally:
        os.close(fd)


def _read_all(discovery: DiscoveryResult) -> _ReadFiles:
    """Read every discovered file; unreadable ones become ``ENTRY_UNREADABLE`` warnings."""

    def run() -> _ReadFiles:
        contents: list[tuple[str, bytes]] = []
        warnings: list[IngestionWarning] = []
        for rel in discovery.files:
            try:
                contents.append((rel, _read_discovered(discovery.root, rel)))
            except OSError as exc:
                detail = exc.strerror or type(exc).__name__
                warnings.append(IngestionWarning(WarningKind.ENTRY_UNREADABLE, rel, detail))
        return _ReadFiles(discovery, tuple(contents), tuple(warnings))

    read = _step(PipelineStep.READ, run)
    if not read.contents:
        raise NoAnalyzableFilesError()
    return read


def _fingerprint(read: _ReadFiles) -> str:
    """sha256 over file hashes, the truncation flag, and spec and steering documents."""

    def run() -> str:
        grounded = discover_specs(read.discovery.root)
        payload = {
            "files": [[rel, _sha256_hex(data)] for rel, data in read.contents],
            "truncated": read.discovery.truncated,
            "specs": [
                [doc.spec_name, doc.source_file, _sha256_hex(doc.text.encode("utf-8"))]
                for doc in grounded.documents
            ],
            "steering": [
                [section.source_file, _sha256_hex(section.own_text.encode("utf-8"))]
                for section in grounded.sections
                if section.origin == "steering"
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return _sha256_hex(canonical.encode("utf-8"))

    return _step(PipelineStep.PROVENANCE, run)


def _warnings(read: _ReadFiles) -> tuple[IngestionWarning, ...]:
    return tuple(read.discovery.warnings) + read.warnings


def _analyze_read(
    read: _ReadFiles,
    repo_id: str,
    source_kind: str,
    *,
    cache: CacheStore,
    mastery: MasteryEngine,
    content_hash: str | None = None,
) -> AnalysisResult:
    """Steps 5 to 7 on already read files."""
    root = str(read.discovery.root)
    parsed: Sequence[ParsedFile] = _step(
        PipelineStep.PARSE,
        lambda: [parse_source(rel, data) for rel, data in read.contents],
    )
    signals = _step(PipelineStep.SCAN, lambda: scan_many(parsed).signals)
    snapshot = _step(
        PipelineStep.GRAPH,
        lambda: build_snapshot(repo_id, root, [p.analysis for p in parsed], signals),
    )
    provenance = _step(PipelineStep.PROVENANCE, lambda: build_provenance(snapshot))
    topology = _step(PipelineStep.TOPOLOGY, lambda: profile_topology(snapshot))
    fingerprint = content_hash if content_hash is not None else _fingerprint(read)

    record = RepositoryRecord(
        repo_id=repo_id,
        source_kind=source_kind,
        content_hash=fingerprint,
        file_count=len(snapshot.files),
        symbol_count=sum(len(f.symbols) for f in snapshot.files),
        truncated=read.discovery.truncated,
    )

    def persist(tx: CacheTransaction) -> None:
        tx.put_snapshot(snapshot)
        tx.put_provenance(provenance)
        tx.put_topology(topology)
        tx.put_repository(record)
        mastery.register_snapshot(tx, snapshot)

    _step(PipelineStep.PERSIST, lambda: cache.transact(persist))
    return AnalysisResult(
        repo_id=repo_id,
        snapshot=snapshot,
        provenance=provenance,
        topology=topology,
        truncated=read.discovery.truncated,
        warnings=_warnings(read),
        reused=False,
    )


# -- public entry points ---------------------------------------------------------------


def analyze_repository(
    source: Source,
    *,
    cache: CacheStore,
    mastery: MasteryEngine,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    workspace: Path | None = None,
    git_runner: GitRunner = subprocess.run,
) -> AnalysisResult:
    """Analyze ``source`` with the existing engines and persist the result as one unit.

    Raises ``IngestionError`` unchanged, ``NoAnalyzableFilesError`` when nothing could be
    read, and ``AnalysisPipelineError(step)`` for any later failure. On any failure the
    previously stored data for the ``repo_id`` is unchanged.
    """
    if isinstance(source, LocalSource):
        discovery = discover_local(
            source.path, max_files=max_files, max_total_bytes=max_total_bytes
        )
        repo_id = derive_local_repo_id(str(discovery.root))
        source_kind = SOURCE_LOCAL
    elif isinstance(source, GitHubSource):
        discovery = discover_github(
            normalize_github_url(source.url),
            max_files=max_files,
            max_total_bytes=max_total_bytes,
            workspace=workspace,
            git_runner=git_runner,
        )
        repo_id = derive_github_repo_id(source.url)
        source_kind = SOURCE_GITHUB
    else:
        raise TypeError("source must be a LocalSource or a GitHubSource")
    read = _read_all(discovery)
    return _analyze_read(read, repo_id, source_kind, cache=cache, mastery=mastery)


def ensure_analysis(path: str, *, cache: CacheStore, mastery: MasteryEngine) -> AnalysisResult:
    """Return current analysis for a local directory, re-analyzing only when needed.

    Runs discovery, the reads, and the fingerprint. When the stored registry row has the
    same fingerprint and the Snapshot, provenance, and topology are all stored, returns
    them with ``reused=True`` and writes nothing. Otherwise runs the full pipeline.
    """
    discovery = discover_local(path)
    repo_id = derive_local_repo_id(str(discovery.root))
    read = _read_all(discovery)
    fingerprint = _fingerprint(read)

    def load(tx: CacheTransaction) -> _StoredAnalysis:
        return (
            tx.get_repository(repo_id),
            tx.get_snapshot(repo_id),
            tx.get_provenance(repo_id),
            tx.get_topology(repo_id),
        )

    record, snapshot, provenance, topology = cache.read(load)
    if (
        record is not None
        and record.content_hash == fingerprint
        and snapshot is not None
        and provenance is not None
        and topology is not None
    ):
        return AnalysisResult(
            repo_id=repo_id,
            snapshot=snapshot,
            provenance=provenance,
            topology=topology,
            truncated=discovery.truncated,
            warnings=_warnings(read),
            reused=True,
        )
    return _analyze_read(
        read, repo_id, SOURCE_LOCAL, cache=cache, mastery=mastery, content_hash=fingerprint
    )
