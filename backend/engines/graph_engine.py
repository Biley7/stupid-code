"""Dependency and call graph engine (Spec #01).

Builds a ``networkx.DiGraph`` from ``FileAnalysis`` values. This module imports
only ``backend.domain`` and ``networkx`` plus the standard library, and it works
on already-parsed data, so analyzed code is never executed or imported.

Edge direction: ``imports`` edges run from the importing file to the imported
file, and ``calls`` edges run from the caller Symbol to the callee Symbol.
"""

import posixpath
from collections.abc import Callable, Mapping, Sequence

import networkx as nx

from backend.domain.models import (
    BlastRadius,
    DSASignal,
    EdgeType,
    FileAnalysis,
    GraphEdge,
    Language,
    RepoGraphSnapshot,
    SymbolKind,
    SymbolNode,
)

__all__ = [
    "ConvergenceError",
    "GraphEngineError",
    "InvalidArgumentError",
    "InvalidInputError",
    "MissingTargetError",
    "build_graph",
    "build_snapshot",
    "compute_vital_organs",
    "detect_cycles",
    "trace_blast_radius",
]

_EXTENSIONS = (".py", ".ts", ".js", ".tsx", ".java")


class GraphEngineError(Exception):
    """Base class for every error raised by the graph engine."""


class InvalidArgumentError(GraphEngineError):
    """A query argument (``top_k``, ``max_depth``) is out of range."""


class MissingTargetError(GraphEngineError):
    """The requested target node is not in the graph."""

    def __init__(self, target_id: str) -> None:
        super().__init__(f"target node not found: {target_id!r}")
        self.target_id = target_id


class InvalidInputError(GraphEngineError):
    """The input to graph construction is invalid, for example duplicate paths."""


class ConvergenceError(GraphEngineError):
    """An iterative computation did not converge."""


def build_graph(files: Sequence[FileAnalysis]) -> nx.DiGraph:
    """Build the dependency and call graph for ``files``.

    Raises ``InvalidInputError`` if two inputs share a ``file_path``. The result
    is identical for every permutation of ``files``.
    """
    seen: set[str] = set()
    for analysis in files:
        if analysis.file_path in seen:
            raise InvalidInputError(f"duplicate file_path: {analysis.file_path!r}")
        seen.add(analysis.file_path)

    ordered = sorted(files, key=lambda analysis: analysis.file_path)
    graph: nx.DiGraph = nx.DiGraph()

    for analysis in ordered:
        graph.add_node(
            analysis.file_path,
            node_type="file",
            language=analysis.language.value,
            loc=analysis.loc,
        )
    for analysis in ordered:
        for symbol in analysis.symbols:
            graph.add_node(
                symbol.id,
                node_type="symbol",
                kind=symbol.kind.value,
                name=symbol.name,
                qualname=symbol.qualname,
                file_path=symbol.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
            )

    resolver = _ImportResolver(seen)
    imported_files: dict[str, list[str]] = {}
    for analysis in ordered:
        targets = resolver.resolve_all(analysis)
        imported_files[analysis.file_path] = targets
        for target in targets:
            graph.add_edge(analysis.file_path, target, edge_type=EdgeType.IMPORTS.value)

    # Call resolution needs the complete import map, so it runs after all imports.
    _add_call_edges(graph, ordered, imported_files)

    return graph


_PR_ALPHA = 0.85
_PR_TOLERANCE = 1e-10
_PR_MAX_ITERATIONS = 500


def _pagerank(graph: nx.DiGraph) -> dict[str, float]:
    """Pure-Python PageRank power iteration in ``graph.nodes`` order (D1)."""
    nodes = list(graph.nodes)
    count = len(nodes)
    if count == 0:
        return {}
    successors = {node: list(graph.successors(node)) for node in nodes}
    rank = dict.fromkeys(nodes, 1.0 / count)
    teleport = (1.0 - _PR_ALPHA) / count
    for _ in range(_PR_MAX_ITERATIONS):
        dangling = sum(rank[node] for node in nodes if not successors[node])
        base = teleport + _PR_ALPHA * dangling / count
        new_rank = dict.fromkeys(nodes, base)
        for node in nodes:
            out = successors[node]
            if out:
                share = _PR_ALPHA * rank[node] / len(out)
                for target in out:
                    new_rank[target] += share
        delta = sum(abs(new_rank[node] - rank[node]) for node in nodes)
        rank = new_rank
        if delta < _PR_TOLERANCE:
            return rank
    raise ConvergenceError(f"PageRank did not converge in {_PR_MAX_ITERATIONS} iterations")


def _min_max(values: dict[str, float]) -> dict[str, float]:
    low = min(values.values())
    high = max(values.values())
    if high == low:
        return dict.fromkeys(values, 0.0)
    span = high - low
    return {node: (value - low) / span for node, value in values.items()}


def compute_vital_organs(graph: nx.DiGraph, top_k: int = 10) -> list[str]:
    """Return the ``top_k`` node ids ranked by 0.5 PageRank + 0.25 in + 0.25 out degree.

    Each component is min-max normalized (0.0 when constant). Ties break by node id.
    Raises ``InvalidArgumentError`` for a non-int, bool, or negative ``top_k``.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise InvalidArgumentError(f"top_k must be a non-negative int, got {top_k!r}")
    if top_k == 0 or graph.number_of_nodes() == 0:
        return []

    pagerank = _min_max(_pagerank(graph))
    in_degree = _min_max({node: float(graph.in_degree(node)) for node in graph.nodes})
    out_degree = _min_max({node: float(graph.out_degree(node)) for node in graph.nodes})
    scores = {
        node: round(0.5 * pagerank[node] + 0.25 * in_degree[node] + 0.25 * out_degree[node], 12)
        for node in graph.nodes
    }
    ranked = sorted(scores, key=lambda node: (-scores[node], node))
    return ranked[:top_k]


def detect_cycles(graph: nx.DiGraph) -> list[list[str]]:
    """Return the cycles of ``graph`` as sorted node-id lists, themselves sorted.

    A cycle is a strongly connected component with more than one node, or a single
    node with a self-loop. The graph is not modified.
    """
    cycles = [
        sorted(component)
        for component in nx.strongly_connected_components(graph)
        if len(component) > 1 or graph.has_edge(next(iter(component)), next(iter(component)))
    ]
    return sorted(cycles)


def _bfs_calls(
    adjacency: Mapping[str, Mapping[str, dict]], target_id: str, max_depth: int
) -> list[str]:
    """Level-by-level BFS over ``calls`` edges, at most ``max_depth`` levels."""
    visited = {target_id}
    frontier = [target_id]
    found: list[str] = []
    for _ in range(max_depth):
        next_frontier: list[str] = []
        for node in frontier:
            for neighbor, data in adjacency[node].items():
                if data.get("edge_type") == EdgeType.CALLS.value and neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
        if not next_frontier:
            break
        found.extend(next_frontier)
        frontier = next_frontier
    return sorted(found)


def trace_blast_radius(graph: nx.DiGraph, target_id: str, max_depth: int = 3) -> BlastRadius:
    """Return the callers and callees of ``target_id`` within ``max_depth`` ``calls`` edges.

    ``impact_score = 0.0`` if the graph has no Symbol nodes, else
    ``min(1.0, max(0.0, (2*u + d) / (3*S)))`` with ``u`` upstream callers, ``d``
    downstream callees, and ``S`` Symbol nodes. Raises ``InvalidArgumentError`` for a
    non-int, bool, or negative ``max_depth``, then ``MissingTargetError`` for an
    unknown target.
    """
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise InvalidArgumentError(f"max_depth must be a non-negative int, got {max_depth!r}")
    if target_id not in graph:
        raise MissingTargetError(target_id)
    upstream = _bfs_calls(graph.pred, target_id, max_depth)
    downstream = _bfs_calls(graph.succ, target_id, max_depth)
    symbols = sum(1 for _, kind in graph.nodes(data="node_type") if kind == "symbol")
    if symbols == 0:
        score = 0.0
    else:
        score = min(1.0, max(0.0, (2 * len(upstream) + len(downstream)) / (3 * symbols)))
    return BlastRadius(
        target_id=target_id,
        upstream_callers=upstream,
        downstream_callees=downstream,
        impact_score=score,
    )


def _add_call_edges(
    graph: nx.DiGraph,
    ordered: Sequence[FileAnalysis],
    imported_files: dict[str, list[str]],
) -> None:
    """Add ``calls`` edges by the three ordered rules in the design (D5, D6)."""
    by_file_name: dict[str, dict[str, list[str]]] = {}
    by_file_qualname: dict[str, dict[str, str]] = {}
    for analysis in ordered:
        names = by_file_name.setdefault(analysis.file_path, {})
        qualnames = by_file_qualname.setdefault(analysis.file_path, {})
        for symbol in analysis.symbols:
            names.setdefault(symbol.name, []).append(symbol.id)
            qualnames[symbol.qualname] = symbol.id

    def lookup(file_path: str, callee: str) -> list[str]:
        if "." in callee:
            found = by_file_qualname.get(file_path, {}).get(callee)
            return [] if found is None else [found]
        return by_file_name.get(file_path, {}).get(callee, [])

    for analysis in ordered:
        file_path = analysis.file_path
        for symbol in analysis.symbols:
            for callee in symbol.raw_calls:
                target = _resolve_call(
                    symbol, callee, lookup, imported_files.get(file_path, []), by_file_qualname
                )
                if target is not None:
                    graph.add_edge(symbol.id, target, edge_type=EdgeType.CALLS.value)


def _resolve_call(
    caller: SymbolNode,
    callee: str,
    lookup: Callable[[str, str], list[str]],
    imports: list[str],
    by_file_qualname: dict[str, dict[str, str]],
) -> str | None:
    file_path = caller.file_path
    parts = callee.split(".")
    if (
        len(parts) == 2
        and parts[0] in ("self", "this")
        and parts[1] != ""
        and caller.kind is SymbolKind.METHOD
    ):
        class_qualname = caller.qualname.rpartition(".")[0]
        return by_file_qualname.get(file_path, {}).get(f"{class_qualname}.{parts[1]}")

    local = lookup(file_path, callee)
    if len(local) == 1:
        return local[0]
    if len(local) > 1:
        return None

    candidates = {found for target in imports for found in lookup(target, callee)}
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


class _ImportResolver:
    """Resolves import specifiers against the set of analyzed file paths."""

    def __init__(self, paths: set[str]) -> None:
        self._paths = paths
        # Dotted-suffix indexes: every suffix of a module path maps to its files.
        self._python_suffixes = self._suffix_index(".py", allow_init=True)
        self._java_suffixes = self._suffix_index(".java", allow_init=False)

    def _suffix_index(self, extension: str, *, allow_init: bool) -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}
        for path in self._paths:
            if allow_init and path.endswith("/__init__" + extension):
                stem = path[: -len("/__init__" + extension)]
            elif path.endswith(extension):
                stem = path[: -len(extension)]
            else:
                continue
            segments = stem.split("/")
            if not stem or segments[-1] == "":
                continue
            for start in range(len(segments)):
                index.setdefault("/".join(segments[start:]), set()).add(path)
        return index

    def resolve_all(self, analysis: FileAnalysis) -> list[str]:
        """Sorted, de-duplicated targets of all resolvable imports, excluding the file itself."""
        targets: set[str] = set()
        for specifier in analysis.imports:
            target = self._resolve(analysis.file_path, analysis.language, specifier)
            if target is not None and target != analysis.file_path:
                targets.add(target)
        return sorted(targets)

    def _resolve(self, importer: str, language: Language, specifier: str) -> str | None:
        if language is Language.PYTHON:
            if specifier.startswith("."):
                return self._python_relative(importer, specifier)
            return self._unique(self._python_suffixes, specifier.replace(".", "/"))
        if language is Language.JAVA:
            if "*" in specifier:
                return None
            return self._unique(self._java_suffixes, specifier.replace(".", "/"))
        # TypeScript, JavaScript, TSX
        if specifier.startswith(("./", "../")):
            return self._relative_path(importer, specifier)
        return None

    @staticmethod
    def _unique(index: dict[str, set[str]], key: str) -> str | None:
        candidates = index.get(key)
        if candidates is not None and len(candidates) == 1:
            return next(iter(candidates))
        return None

    def _python_relative(self, importer: str, specifier: str) -> str | None:
        stripped = specifier.lstrip(".")
        dots = len(specifier) - len(stripped)
        base = posixpath.dirname(importer)
        for _ in range(dots - 1):
            if base == "":
                return None
            base = posixpath.dirname(base)
        tail = stripped.replace(".", "/")
        prefix = f"{base}/" if base else ""
        if tail:
            candidates = (f"{prefix}{tail}.py", f"{prefix}{tail}/__init__.py")
        else:
            candidates = (f"{prefix}__init__.py",)
        return next((c for c in candidates if c in self._paths), None)

    def _relative_path(self, importer: str, specifier: str) -> str | None:
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
        if joined == ".." or joined.startswith("../"):
            return None
        base = "" if joined == "." else joined
        candidates: list[str] = []
        if base:
            candidates.append(base)
            candidates.extend(base + ext for ext in _EXTENSIONS)
        prefix = f"{base}/" if base else ""
        candidates.extend(f"{prefix}index{ext}" for ext in _EXTENSIONS)
        return next((c for c in candidates if c in self._paths), None)


def build_snapshot(
    repo_id: str,
    root_path: str,
    files: Sequence[FileAnalysis],
    dsa_signals: Sequence[DSASignal],
) -> RepoGraphSnapshot:
    """Assemble a deterministic ``RepoGraphSnapshot`` from analyses and signals."""
    graph = build_graph(files)
    vital_organs = compute_vital_organs(graph)
    cycles = detect_cycles(graph)
    edges = sorted(
        (
            GraphEdge(source=source, target=target, edge_type=EdgeType(edge_type))
            for source, target, edge_type in graph.edges(data="edge_type")
        ),
        key=lambda edge: (edge.source, edge.target, edge.edge_type.value),
    )
    signals = sorted(
        dsa_signals,
        key=lambda s: (
            s.file_path,
            s.start_line,
            s.end_line,
            s.chapter,
            s.pattern_name,
            s.symbol_id,
            s.confidence,
            tuple(s.evidence),
        ),
    )
    return RepoGraphSnapshot(
        repo_id=repo_id,
        root_path=root_path,
        files=sorted(files, key=lambda f: f.file_path),
        edges=edges,
        vital_organs=vital_organs,
        cycles=cycles,
        dsa_signals=signals,
    )
