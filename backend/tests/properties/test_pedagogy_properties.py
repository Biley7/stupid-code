"""Property tests for topology and pedagogy (Spec #02).

The file holds exactly four Hypothesis tests, one per design property. This section holds
the shared helpers, which later properties reuse:

* ``repo_specs()`` / ``pedagogy_cases()``: Hypothesis strategies for a small repository
  (1 to 3 Python files, 1 to 4 functions each, hex ``ast_hash`` values, call edges, and
  0 to 3 ``DSASignal`` values drawn from real Phase 1 chapter and pattern names).
* ``materialize(spec, root, repo_id)``: writes the spec's source into ``root`` and returns a
  consistent ``RepoGraphSnapshot`` built with the real Phase 1 ``build_snapshot``. Every
  symbol's line range matches the written source text.
* ``build_engine(snapshot)``: an in-memory ``CacheStore`` plus a ``PedagogyEngine`` over a
  ``CountingRouter``. Returns an ``EngineBundle``; callers must ``close()`` the cache.
* ``CountingRouter``: wraps the real mock ``LLMRouter`` and counts ``generate_structured``
  calls in its ``calls`` attribute.

Each example writes its source files to its own ``tempfile.TemporaryDirectory`` and runs
without network access.
"""

import asyncio
import tempfile
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.domain.models import (
    DSASignal,
    EdgeType,
    FileAnalysis,
    GraphEdge,
    Language,
    PedagogyLens,
    ProvenanceReport,
    RepoGraphSnapshot,
    SymbolKind,
    SymbolNode,
)
from backend.engines.cache_store import CacheStore
from backend.engines.graph_engine import build_snapshot
from backend.engines.llm_router import LLMRouter, LLMSettings
from backend.engines.pedagogy import PedagogyEngine, complexity_for
from backend.engines.topology import (
    compute_boundary_metrics,
    compute_directory_roles,
    profile_topology,
)

pytestmark = pytest.mark.usefixtures("offline_guard")

# Real Phase 1 (chapter, pattern_name) pairs emitted by ``dsa_scanner``.
DSA_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Hash Tables", "hash-table lookup"),
    ("Hash Tables", "frequency counting"),
    ("Hash Tables", "de-duplication"),
    ("Graphs & Trees", "queue-based traversal"),
    ("Graphs & Trees", "stack-based traversal"),
    ("Graphs & Trees", "recursive node traversal"),
    ("Recursion & Dynamic Programming", "direct recursion"),
    ("Heaps & Priority Queues", "heapq operations"),
    ("Sorting & Binary Search", "binary search"),
    ("Sliding Window / Two Pointers", "two pointers"),
)
FILE_PATHS = ("pkg/a.py", "pkg/b.py", "core/c.py")


# ---------------------------------------------------------------------------
# Generated repository model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FunctionSpec:
    """One generated function: a global index, hex hash, and the global indexes it calls."""

    index: int
    ast_hash: str
    calls: tuple[int, ...]


@dataclass(frozen=True)
class SignalSpec:
    """One generated DSA signal on the function with global index ``function_index``."""

    function_index: int
    chapter: str
    pattern_name: str
    confidence: float


@dataclass(frozen=True)
class RepoSpec:
    """A generated repository: files (path, file hash, functions) and DSA signals."""

    files: tuple[tuple[str, str, tuple[FunctionSpec, ...]], ...]
    signals: tuple[SignalSpec, ...]

    @property
    def function_count(self) -> int:
        return sum(len(functions) for _, _, functions in self.files)


@dataclass(frozen=True)
class PedagogyCase:
    """A generated repository plus a repo id, target selector, and lens."""

    spec: RepoSpec
    repo_id: str
    target_index: int
    lens: PedagogyLens


_hex_hash = st.text(alphabet="0123456789abcdef", min_size=16, max_size=64)


@st.composite
def repo_specs(draw: st.DrawFn) -> RepoSpec:
    """Draw 1 to 3 files with 1 to 4 functions each, call edges, and 0 to 3 DSA signals."""
    paths = draw(st.lists(st.sampled_from(FILE_PATHS), min_size=1, max_size=3, unique=True))
    counts = [draw(st.integers(min_value=1, max_value=4)) for _ in paths]
    total = sum(counts)
    files = []
    index = 0
    for path, count in zip(paths, counts, strict=True):
        functions = []
        for _ in range(count):
            calls = draw(st.lists(st.integers(0, total - 1), max_size=2, unique=True))
            functions.append(FunctionSpec(index, draw(_hex_hash), tuple(calls)))
            index += 1
        files.append((path, draw(_hex_hash), tuple(functions)))
    signals = draw(st.lists(_signal_specs(total), max_size=3))
    return RepoSpec(tuple(files), tuple(signals))


def _signal_specs(total: int) -> st.SearchStrategy[SignalSpec]:
    return st.tuples(
        st.integers(0, total - 1),
        st.sampled_from(DSA_PATTERNS),
        st.sampled_from((0.6, 0.75, 0.9)),
    ).map(lambda t: SignalSpec(t[0], t[1][0], t[1][1], t[2]))


@st.composite
def pedagogy_cases(draw: st.DrawFn) -> PedagogyCase:
    """Draw a repository, a repo id, a target selector, and a lens (L1, L2, or L3)."""
    spec = draw(repo_specs())
    repo_id = draw(st.from_regex(r"[a-z][a-z0-9_-]{0,11}", fullmatch=True))
    target_index = draw(st.integers(0, spec.function_count - 1))
    lens = draw(st.sampled_from(list(PedagogyLens)))
    return PedagogyCase(spec, repo_id, target_index, lens)


def _function_source(function: FunctionSpec) -> list[str]:
    """Source lines of one function: a header, one line per call, and a return."""
    lines = [f"def f{function.index}(x):"]
    lines += [f"    f{callee}(x)" for callee in function.calls]
    lines.append("    return x")
    return lines


def materialize(spec: RepoSpec, root: Path, repo_id: str) -> RepoGraphSnapshot:
    """Write ``spec``'s source under ``root`` and build the matching Phase 1 snapshot.

    Function ``fN`` is a ``def`` line, one call line per callee, and a ``return`` line, with a
    blank line between functions, so each symbol's ``start_line`` and ``end_line`` match the
    written text. Cross-file calls stay unresolved (no imports), which is valid Phase 1 data.
    """
    analyses: list[FileAnalysis] = []
    symbols_by_index: dict[int, SymbolNode] = {}
    for path, file_hash, functions in spec.files:
        lines: list[str] = []
        symbols: list[SymbolNode] = []
        for function in functions:
            body = _function_source(function)
            start = len(lines) + 1
            lines.extend(body)
            symbol = SymbolNode(
                id=f"{path}::f{function.index}",
                name=f"f{function.index}",
                qualname=f"f{function.index}",
                kind=SymbolKind.FUNCTION,
                file_path=path,
                start_line=start,
                end_line=len(lines),
                signature=f"def f{function.index}(x)",
                ast_hash=function.ast_hash,
                decorators=[],
                is_async=False,
                raw_calls=[f"f{callee}" for callee in function.calls],
            )
            symbols.append(symbol)
            symbols_by_index[function.index] = symbol
            lines.append("")
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines), encoding="utf-8")
        analyses.append(
            FileAnalysis(
                file_path=path,
                language=Language.PYTHON,
                loc=len(lines),
                ast_hash=file_hash,
                imports=[],
                exports=[],
                symbols=symbols,
                parse_errors=[],
            )
        )
    signals = []
    for item in spec.signals:
        symbol = symbols_by_index[item.function_index]
        signals.append(
            DSASignal(
                symbol_id=symbol.id,
                file_path=symbol.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                chapter=item.chapter,  # type: ignore[arg-type]
                pattern_name=item.pattern_name,
                confidence=item.confidence,
                evidence=[f"{item.pattern_name} at lines {symbol.start_line}-{symbol.end_line}"],
            )
        )
    return build_snapshot(repo_id, str(root), analyses, signals)


def target_id_for(snapshot: RepoGraphSnapshot, case: PedagogyCase) -> str:
    """Return the Target id for ``case``: the repo id for L3, else the chosen symbol id."""
    if case.lens is PedagogyLens.L3_ARCHITECTURE:
        return snapshot.repo_id
    symbols = [symbol for analysis in snapshot.files for symbol in analysis.symbols]
    return symbols[case.target_index % len(symbols)].id


class CountingRouter:
    """The real mock ``LLMRouter`` behind a call counter (``calls``)."""

    def __init__(self) -> None:
        self.calls = 0
        self._inner = LLMRouter(LLMSettings(LLM_PROVIDER="mock"))

    async def generate_structured(
        self, system_prompt: str, user_prompt: str, response_model: Any
    ) -> Any:
        self.calls += 1
        return await self._inner.generate_structured(system_prompt, user_prompt, response_model)


@dataclass(frozen=True)
class EngineBundle:
    """A ``PedagogyEngine`` with its ``CacheStore`` and ``CountingRouter``."""

    engine: PedagogyEngine
    cache: CacheStore
    router: CountingRouter


def build_engine(snapshot: RepoGraphSnapshot) -> EngineBundle:
    """Store ``snapshot``, an empty provenance report, and its topology in a fresh cache.

    The cache is ``CacheStore(":memory:")``; the caller closes it (``bundle.cache.close()``).
    """
    cache = CacheStore(":memory:")
    try:
        cache.put_snapshot(snapshot)
        cache.put_provenance(
            ProvenanceReport(
                repo_id=snapshot.repo_id,
                has_kiro_specs=False,
                spec_links={},
                drift_items=[],
                recent_commits={},
            )
        )
        cache.put_topology(profile_topology(snapshot))
    except BaseException:
        cache.close()
        raise
    router = CountingRouter()
    return EngineBundle(PedagogyEngine(cache, router), cache, router)


# ---------------------------------------------------------------------------
# Property 1
# ---------------------------------------------------------------------------
# Feature: 02-spec-topology-pedagogy, Property 1: Explanation caching is idempotent
# Validates: Requirements 12.7, 12.8, 17.5.1
@settings(max_examples=100, deadline=timedelta(milliseconds=500))
@given(case=pedagogy_cases())
def test_explanation_caching_is_idempotent(case: PedagogyCase) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = materialize(case.spec, Path(tmp), case.repo_id)
        target_id = target_id_for(snapshot, case)
        bundle = build_engine(snapshot)
        try:

            async def run() -> tuple[Any, int, Any, int]:
                first = await bundle.engine.explain_target(case.repo_id, target_id, case.lens)
                after_first = bundle.router.calls
                second = await bundle.engine.explain_target(case.repo_id, target_id, case.lens)
                return first, after_first, second, bundle.router.calls

            first, calls_after_first, second, calls_after_second = asyncio.run(run())
        finally:
            bundle.cache.close()

    assert first.cached is False
    assert calls_after_first == 1
    assert second.cached is True
    assert calls_after_second == 1
    assert second == first.model_copy(update={"cached": True})


# ---------------------------------------------------------------------------
# Property 2
# ---------------------------------------------------------------------------
def _with_target_hash(case: PedagogyCase, target_id: str, ast_hash: str) -> RepoSpec:
    """Return ``case.spec`` with the Target's hash input set to ``ast_hash``.

    L1 and L2 read the target symbol's ``ast_hash``; L3 derives its hash from the file hashes,
    so the first file's ``ast_hash`` is replaced instead. Source text and line ranges are kept.
    ``target_id`` is ``<path>::f<index>`` for L1 and L2.
    """
    spec = case.spec
    if case.lens is PedagogyLens.L3_ARCHITECTURE:
        path, _, functions = spec.files[0]
        return replace(spec, files=((path, ast_hash, functions), *spec.files[1:]))
    position = int(target_id.rsplit("::f", 1)[1])
    files = tuple(
        (
            path,
            file_hash,
            tuple(
                replace(function, ast_hash=ast_hash) if function.index == position else function
                for function in functions
            ),
        )
        for path, file_hash, functions in spec.files
    )
    return replace(spec, files=files)


# Feature: 02-spec-topology-pedagogy, Property 2: A changed AST hash is a cache miss
# Validates: Requirements 12.8, 12.9, 17.5.2
@settings(max_examples=100, deadline=timedelta(milliseconds=500))
@given(
    case=pedagogy_cases(),
    hashes=st.tuples(_hex_hash, _hex_hash).filter(lambda pair: pair[0][:12] != pair[1][:12]),
)
def test_changed_ast_hash_is_a_cache_miss(case: PedagogyCase, hashes: tuple[str, str]) -> None:
    h1, h2 = hashes
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # ``build_snapshot`` sorts files by path, so resolve the Target from a real snapshot.
        target_id = target_id_for(materialize(case.spec, root, case.repo_id), case)
        snapshot_1 = materialize(_with_target_hash(case, target_id, h1), root, case.repo_id)
        snapshot_2 = materialize(_with_target_hash(case, target_id, h2), root, case.repo_id)
        bundle = build_engine(snapshot_1)
        try:

            async def run() -> tuple[Any, Any]:
                first = await bundle.engine.explain_target(case.repo_id, target_id, case.lens)
                bundle.cache.put_snapshot(snapshot_2)
                second = await bundle.engine.explain_target(case.repo_id, target_id, case.lens)
                return first, second

            first, second = asyncio.run(run())
            old_row = bundle.cache.get_explanation(
                case.repo_id, first.ast_hash, target_id, case.lens
            )
            new_row = bundle.cache.get_explanation(
                case.repo_id, second.ast_hash, target_id, case.lens
            )
            calls = bundle.router.calls
        finally:
            bundle.cache.close()

    if case.lens is not PedagogyLens.L3_ARCHITECTURE:
        assert first.ast_hash == h1
        assert second.ast_hash == h2
    assert first.ast_hash != second.ast_hash
    assert first.cached is False
    assert second.cached is False
    assert calls == 2
    tiers = ("l1", "l2", "l3")
    assert {name: getattr(second, name) for name in tiers} != {
        name: getattr(first, name) for name in tiers
    }
    # Stale rows are kept: the old hash row and the new hash row both exist (design D6).
    assert old_row is not None
    assert old_row.model_copy(update={"cached": False}) == first
    assert new_row is not None
    assert new_row.model_copy(update={"cached": False}) == second


# ---------------------------------------------------------------------------
# Property 3
# ---------------------------------------------------------------------------
def _with_target_signals(
    spec: RepoSpec,
    function_index: int,
    drop: bool,
    extra: list[tuple[str, str]],
) -> RepoSpec:
    """Return ``spec`` with the Target's signals dropped, or extended by ``extra`` patterns.

    Signals on other functions are always kept, so the zero-signal Target case still has a
    repository where other symbols carry signals.
    """
    kept = tuple(s for s in spec.signals if not (drop and s.function_index == function_index))
    added = (
        ()
        if drop
        else tuple(SignalSpec(function_index, chapter, name, 0.75) for chapter, name in extra)
    )
    return replace(spec, signals=kept + added)


# Feature: 02-spec-topology-pedagogy, Property 3: DSA cards come only from the Target's own signals
# Validates: Requirements 14.3, 14.7, 14.8, 17.5.3
@settings(max_examples=100, deadline=timedelta(milliseconds=500))
@given(
    spec=repo_specs(),
    target_selector=st.integers(min_value=0, max_value=1000),
    drop_target_signals=st.booleans(),
    extra=st.lists(st.sampled_from(DSA_PATTERNS), max_size=2),
)
def test_dsa_cards_come_only_from_the_targets_signals(
    spec: RepoSpec,
    target_selector: int,
    drop_target_signals: bool,
    extra: list[tuple[str, str]],
) -> None:
    repo_id = "repo"
    lens = PedagogyLens.L2_FLOW
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # ``build_snapshot`` sorts files by path, so resolve the Target from a real snapshot.
        case = PedagogyCase(spec, repo_id, target_selector, lens)
        target_id = target_id_for(materialize(spec, root, repo_id), case)
        function_index = int(target_id.rsplit("::f", 1)[1])
        spec = _with_target_signals(spec, function_index, drop_target_signals, extra)
        snapshot = materialize(spec, root, repo_id)
        target_keys = sorted(
            (s.chapter, s.pattern_name, s.start_line, s.end_line)
            for s in snapshot.dsa_signals
            if s.symbol_id == target_id
        )
        other_keys = {
            (s.chapter, s.pattern_name, s.start_line, s.end_line)
            for s in snapshot.dsa_signals
            if s.symbol_id != target_id
        }
        bundle = build_engine(snapshot)
        try:
            explanation = asyncio.run(bundle.engine.explain_target(repo_id, target_id, lens))
        finally:
            bundle.cache.close()

    assert explanation.l2 is not None
    cards = explanation.l2.dsa_cards
    card_keys = sorted((c.chapter, c.pattern_name, c.start_line, c.end_line) for c in cards)
    # Exactly one card per signal of the Target, and each card matches one of those signals.
    assert card_keys == target_keys
    if drop_target_signals:
        assert target_keys == []
        assert cards == []
    # No card comes only from another symbol's signal.
    assert not any(key in other_keys and key not in target_keys for key in card_keys)
    for card in cards:
        assert (card.time_complexity, card.space_complexity) == complexity_for(
            card.chapter, card.pattern_name
        )
    assert explanation.l2.llm_content_available is True


# ---------------------------------------------------------------------------
# Property 4
# ---------------------------------------------------------------------------
_DIRECTORIES = (
    "domain",
    "engines",
    "api",
    "ui",
    "tests",
    "config",
    "services",
    "features/a",
    "features/b",
    "modules/m1",
    "modules/m2",
    "",
)
_FILE_NAMES = ("a.py", "b.py", "main.py", "__init__.py")
_UNKNOWN_PATHS = ("ghost/x.py", "missing.py", "domain/ghost.py")

# One generated edge: (source index, target index, is a calls edge). Indexes are taken
# modulo the node pool (the files followed by the unknown paths).
_edge_specs = st.tuples(st.integers(0, 40), st.integers(0, 40), st.booleans())


@st.composite
def topology_layouts(
    draw: st.DrawFn,
) -> tuple[list[str], list[tuple[str, str, EdgeType]]]:
    """Draw 0 to 12 unique file paths and edges over those files plus unknown paths.

    Edges may be self-edges, duplicates, calls-type, or point at unknown paths. Files that
    appear in no edge are isolated nodes, and an empty edge list is a no-edge layout.
    """
    raw = draw(
        st.lists(
            st.tuples(st.sampled_from(_DIRECTORIES), st.sampled_from(_FILE_NAMES)),
            max_size=12,
        )
    )
    paths = list(dict.fromkeys(f"{folder}/{name}" if folder else name for folder, name in raw))
    pool = paths + list(_UNKNOWN_PATHS)
    edges = [
        (
            pool[source % len(pool)],
            pool[target % len(pool)],
            EdgeType.CALLS if is_call else EdgeType.IMPORTS,
        )
        for source, target, is_call in draw(st.lists(_edge_specs, max_size=30))
    ]
    return paths, edges


def _layout_snapshot(paths: list[str], edges: list[tuple[str, str, EdgeType]]) -> RepoGraphSnapshot:
    """Build a snapshot directly from hand-made files and edges (no parsing, no IO)."""
    files = [
        FileAnalysis(
            file_path=path,
            language=Language.PYTHON,
            loc=10,
            ast_hash=f"h-{path}",
            imports=[],
            exports=[],
            symbols=[],
            parse_errors=[],
        )
        for path in paths
    ]
    return RepoGraphSnapshot(
        repo_id="repo",
        root_path="/repo",
        files=files,
        edges=[GraphEdge(source=s, target=t, edge_type=kind) for s, t, kind in edges],
        vital_organs=[],
        cycles=[],
        dsa_signals=[],
    )


# Feature: 02-spec-topology-pedagogy, Property 4: Boundary ratios stay within 0 and 1
# Validates: Requirements 7.7, 8.7, 17.5.4
@settings(max_examples=100, deadline=timedelta(milliseconds=500))
@given(layout=topology_layouts())
def test_boundary_ratios_stay_within_unit_interval(
    layout: tuple[list[str], list[tuple[str, str, EdgeType]]],
) -> None:
    paths, edges = layout
    snapshot = _layout_snapshot(paths, edges)

    profile = profile_topology(snapshot)
    metrics = compute_boundary_metrics(snapshot, compute_directory_roles(snapshot))

    for values in (metrics, profile.boundary_metrics):
        assert 0.0 <= values["cross_folder_import_ratio"] <= 1.0
        assert 0.0 <= values["domain_isolation_score"] <= 1.0
    assert 0.0 <= profile.confidence <= 1.0
    if not paths:
        assert profile.detected_pattern == "Flat / Script"
        assert profile.confidence == 0.0

    # Determinism: the same layout with files and edges reversed gives the same profile.
    reversed_snapshot = _layout_snapshot(paths[::-1], edges[::-1])
    assert profile_topology(reversed_snapshot) == profile
