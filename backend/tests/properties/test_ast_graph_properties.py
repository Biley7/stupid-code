"""Property tests for the AST and graph engine (Spec #01).

Each property is exactly one ``@given`` test. Properties 1 to 4 follow.
"""

import socket
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass

import networkx as nx
import pytest
from hypothesis import find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import NoSuchExample

from backend.domain.models import FileAnalysis, Language, SymbolKind, SymbolNode
from backend.engines.ast_parser import parse_file
from backend.engines.graph_engine import build_graph, detect_cycles, trace_blast_radius

# ---------------------------------------------------------------------------
# Shared Hypothesis settings: derandomized, at least 100 examples, no deadline
# override and no suppressed health checks (Req 6.15).
# ---------------------------------------------------------------------------
PROPERTY_SETTINGS = settings(derandomize=True, max_examples=100)


# ---------------------------------------------------------------------------
# Offline fixture (Req 6.1, 6.4). Module scoped so Hypothesis' function-scoped
# fixture health check is not triggered; it patches by hand instead of monkeypatch.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True, scope="module")
def _offline() -> Iterator[None]:
    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network and subprocess access are forbidden in property tests")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", _blocked)
        mp.setattr(subprocess, "run", _blocked)
        mp.setattr(subprocess, "Popen", _blocked)
        mp.setenv("LLM_PROVIDER", "mock")
        yield


# ---------------------------------------------------------------------------
# Python snippet model (Properties 1 and 2)
# ---------------------------------------------------------------------------
IDENTIFIERS = ["a", "b", "c", "x", "y", "z", "count", "total", "value", "item", "result", "tmp"]
ARITH_OPS = ["+", "-", "*", "//", "%"]
COMPARE_OPS = ["<", "<=", ">", ">=", "==", "!="]

# Expressions: ("int", n) | ("name", s) | ("bin", op, left, right)
# Conditions:  ("cmp", op, left, right)
# Statements:  ("assign", name, expr) | ("return", expr)
#              | ("if", cond, body, orelse) | ("while", cond, body)


def _exprs() -> st.SearchStrategy[tuple]:
    leaf = st.one_of(
        st.integers(0, 999).map(lambda n: ("int", n)),
        st.sampled_from(IDENTIFIERS).map(lambda s: ("name", s)),
    )
    return st.recursive(
        leaf,
        lambda inner: st.tuples(st.just("bin"), st.sampled_from(ARITH_OPS), inner, inner),
        max_leaves=4,
    )


def _conds() -> st.SearchStrategy[tuple]:
    return st.tuples(st.just("cmp"), st.sampled_from(COMPARE_OPS), _exprs(), _exprs())


def _simple_stmts() -> st.SearchStrategy[tuple]:
    return st.one_of(
        st.tuples(st.just("assign"), st.sampled_from(IDENTIFIERS), _exprs()),
        st.tuples(st.just("return"), _exprs()),
    )


def _stmts() -> st.SearchStrategy[tuple]:
    def extend(inner: st.SearchStrategy[tuple]) -> st.SearchStrategy[tuple]:
        body = st.lists(inner, min_size=1, max_size=3)
        return st.one_of(
            st.tuples(st.just("if"), _conds(), body, st.one_of(st.just([]), body)),
            st.tuples(st.just("while"), _conds(), body),
        )

    return st.recursive(_simple_stmts(), extend, max_leaves=6)


@dataclass(frozen=True)
class FunctionModel:
    name: str
    params: tuple[str, ...]
    body: tuple[tuple, ...]


@st.composite
def function_models(draw: st.DrawFn) -> FunctionModel:
    name = draw(st.sampled_from(["run", "compute", "handle", "step"]))
    params = draw(st.lists(st.sampled_from(IDENTIFIERS), unique=True, max_size=3))
    body = draw(st.lists(_stmts(), min_size=1, max_size=4))
    return FunctionModel(name, tuple(params), tuple(body))


@dataclass(frozen=True)
class Style:
    indent: int  # 2, 4 or 8 spaces per level
    op_space: int  # spaces on each side of binary and comparison operators (0 to 2)
    comma_space: int  # spaces after a comma in the parameter list (0 to 2)
    trailing_spaces: int  # spaces appended to code lines (0 to 2)
    blank_lines: tuple[int, ...]  # line indexes (mod line count) followed by a blank line
    full_comments: tuple[int, ...]  # line indexes (mod line count) preceded by a comment line
    trailing_comments: tuple[int, ...]  # line indexes (mod line count) given a trailing comment


CANONICAL = Style(4, 1, 1, 0, (), (), ())

_comment_text = st.text(alphabet="abcdefg XYZ_-0189.,;:()", min_size=0, max_size=12)
_positions = st.lists(st.integers(0, 50), max_size=3).map(tuple)


def _expr_text(expr: tuple, style: Style) -> str:
    kind = expr[0]
    if kind == "int":
        return str(expr[1])
    if kind == "name":
        return expr[1]
    pad = " " * style.op_space
    left, right = (_operand(e, style) for e in expr[2:4])
    return f"{left}{pad}{expr[1]}{pad}{right}"


def _operand(expr: tuple, style: Style) -> str:
    text = _expr_text(expr, style)
    return f"({text})" if expr[0] == "bin" else text


def _cond_text(cond: tuple, style: Style) -> str:
    pad = " " * style.op_space
    return f"{_operand(cond[2], style)}{pad}{cond[1]}{pad}{_operand(cond[3], style)}"


def _lines(stmts: tuple | list, depth: int, style: Style) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for stmt in stmts:
        kind = stmt[0]
        if kind == "assign":
            pad = " " * style.op_space
            out.append((depth, f"{stmt[1]}{pad}={pad}{_expr_text(stmt[2], style)}"))
        elif kind == "return":
            out.append((depth, f"return {_expr_text(stmt[1], style)}"))
        elif kind == "if":
            out.append((depth, f"if {_cond_text(stmt[1], style)}:"))
            out.extend(_lines(stmt[2], depth + 1, style))
            if stmt[3]:
                out.append((depth, "else:"))
                out.extend(_lines(stmt[3], depth + 1, style))
        else:
            out.append((depth, f"while {_cond_text(stmt[1], style)}:"))
            out.extend(_lines(stmt[2], depth + 1, style))
    return out


def render(model: FunctionModel, style: Style, comment: str = "note") -> str:
    sep = "," + " " * style.comma_space
    header = f"def {model.name}({sep.join(model.params)}):"
    lines = [(0, header)] + _lines(model.body, 1, style)
    count = len(lines)
    full = {p % count for p in style.full_comments}
    trailing = {p % count for p in style.trailing_comments}
    blank = {p % count for p in style.blank_lines}
    out: list[str] = []
    for index, (depth, text) in enumerate(lines):
        pad = " " * (style.indent * depth)
        if index in full:
            out.append(f"{pad}# {comment}")
        code = f"{pad}{text}" + " " * style.trailing_spaces
        if index in trailing:
            code += f"  # {comment}"
        out.append(code)
        if index in blank:
            out.append("")
    return "\n".join(out) + "\n"


@st.composite
def formatting_pairs(draw: st.DrawFn) -> tuple[FunctionModel, str, str]:
    """Return (model, canonical source, transformed source) for one drawn model.

    The transformed source always carries at least one comment, so it never equals the
    canonical text (Req 6.11).
    """
    model = draw(function_models())
    comment = draw(_comment_text)
    style = Style(
        indent=draw(st.sampled_from([2, 4, 8])),
        op_space=draw(st.integers(0, 2)),
        comma_space=draw(st.integers(0, 2)),
        trailing_spaces=draw(st.integers(0, 2)),
        blank_lines=draw(_positions),
        full_comments=draw(_positions),
        trailing_comments=draw(_positions),
    )
    forced = draw(st.sampled_from(["full", "trailing"]))
    if forced == "full":
        style = Style(**{**style.__dict__, "full_comments": (*style.full_comments, 0)})
    else:
        style = Style(**{**style.__dict__, "trailing_comments": (*style.trailing_comments, 0)})
    return model, render(model, CANONICAL, comment), render(model, style, comment)


# ---------------------------------------------------------------------------
# Property 1
# ---------------------------------------------------------------------------
# Feature: 01-ast-graph-engine, Property 1: AST hash is invariant under formatting
# and comment changes
@PROPERTY_SETTINGS
@given(formatting_pairs())
def test_property_1_ast_hash_invariant_under_formatting_and_comments(
    pair: tuple[FunctionModel, str, str],
) -> None:
    """**Validates: Requirements 3.10, 3.11, 3.12, 6.11**"""
    _, canonical, transformed = pair
    assert canonical != transformed

    original = parse_file("pkg/mod.py", canonical.encode("utf-8"))
    changed = parse_file("pkg/mod.py", transformed.encode("utf-8"))

    assert original.parse_errors == [], canonical
    assert changed.parse_errors == [], transformed
    assert changed.ast_hash == original.ast_hash
    assert len(original.symbols) >= 1
    assert [(s.qualname, s.ast_hash) for s in changed.symbols] == [
        (s.qualname, s.ast_hash) for s in original.symbols
    ]


def test_property_1_strategy_generates_differing_texts() -> None:
    """Guard (Req 6.11): the strategy yields transformed text that differs from canonical,
    and never yields an identical pair."""
    pair_settings = settings(derandomize=True, max_examples=100)
    found = find(formatting_pairs(), lambda p: p[1] != p[2], settings=pair_settings)
    assert found[1] != found[2]
    with pytest.raises(NoSuchExample):
        find(formatting_pairs(), lambda p: p[1] == p[2], settings=pair_settings)


# ---------------------------------------------------------------------------
# Property 2 strategy: extends the Python function model above. Every drawn model
# gets a guaranteed trailing statement holding one name use, one assignment target and
# one arithmetic operator, so each mutation kind always has at least one site and the
# mutation is built to apply (no assume or filter).
# ---------------------------------------------------------------------------
FRESH_IDENTIFIERS = ["alpha", "beta", "gamma", "delta", "omega", "sigma", "fresh_1", "other_name"]
_ANCHOR = ("assign", "tmp", ("bin", "+", ("name", "value"), ("int", 1)))


def _swap(current: str, pool: list[str], shift: int) -> str:
    """Return a member of ``pool`` different from ``current`` (shift in 0..len(pool)-2)."""
    others = [op for op in pool if op != current]
    return others[shift % len(others)]


class _Rewriter:
    """Counts mutation sites of one kind and rewrites the ``index``-th one (-1 rewrites none)."""

    def __init__(self, kind: str, index: int, shift: int) -> None:
        self.kind, self.index, self.shift, self.count = kind, index, shift, 0

    def _hit(self) -> bool:
        hit = self.count == self.index
        self.count += 1
        return hit

    def expr(self, expr: tuple) -> tuple:
        if expr[0] == "int":
            return expr
        if expr[0] == "name":
            if self.kind == "identifier" and self._hit():
                return ("name", FRESH_IDENTIFIERS[self.shift % len(FRESH_IDENTIFIERS)])
            return expr
        op = expr[1]
        if self.kind == "operator" and self._hit():
            op = _swap(op, ARITH_OPS, self.shift)
        return ("bin", op, self.expr(expr[2]), self.expr(expr[3]))

    def cond(self, cond: tuple) -> tuple:
        op = cond[1]
        if self.kind == "operator" and self._hit():
            op = _swap(op, COMPARE_OPS, self.shift)
        return ("cmp", op, self.expr(cond[2]), self.expr(cond[3]))

    def stmts(self, stmts: tuple | list) -> list[tuple]:
        return [self.stmt(s) for s in stmts]

    def stmt(self, stmt: tuple) -> tuple:
        kind = stmt[0]
        if kind == "assign":
            target = stmt[1]
            if self.kind == "identifier" and self._hit():
                target = FRESH_IDENTIFIERS[self.shift % len(FRESH_IDENTIFIERS)]
            return ("assign", target, self.expr(stmt[2]))
        if kind == "return":
            return ("return", self.expr(stmt[1]))
        if kind == "if":
            cond = self.cond(stmt[1])
            return ("if", cond, self.stmts(stmt[2]), self.stmts(stmt[3]))
        return ("while", self.cond(stmt[1]), self.stmts(stmt[2]))

    def model(self, model: FunctionModel) -> FunctionModel:
        return FunctionModel(model.name, model.params, tuple(self.stmts(model.body)))


@st.composite
def mutation_cases(draw: st.DrawFn) -> tuple[str, FunctionModel, FunctionModel, Style]:
    """Return (kind, original model, mutated model, style); the models always differ."""
    base = draw(function_models())
    model = FunctionModel(base.name, base.params, (*base.body, _ANCHOR))
    kind = draw(st.sampled_from(["operator", "identifier"]))
    style = Style(
        indent=draw(st.sampled_from([2, 4, 8])),
        op_space=draw(st.integers(0, 2)),
        comma_space=draw(st.integers(0, 2)),
        trailing_spaces=0,
        blank_lines=(),
        full_comments=(),
        trailing_comments=(),
    )
    sites = _Rewriter(kind, -1, 0)
    sites.model(model)
    index = draw(st.integers(0, sites.count - 1))
    shift = draw(st.integers(0, 20))
    return kind, model, _Rewriter(kind, index, shift).model(model), style


# ---------------------------------------------------------------------------
# Property 2
# ---------------------------------------------------------------------------
# Feature: 01-ast-graph-engine, Property 2: AST hash changes when an operator or
# identifier changes
@PROPERTY_SETTINGS
@given(mutation_cases())
def test_property_2_ast_hash_changes_on_operator_or_identifier_change(
    case: tuple[str, FunctionModel, FunctionModel, Style],
) -> None:
    """**Validates: Requirements 3.13, 6.12**"""
    _, original_model, changed_model, style = case
    before = render(original_model, style)
    after = render(changed_model, style)
    assert before != after

    original = parse_file("pkg/mod.py", before.encode("utf-8"))
    changed = parse_file("pkg/mod.py", after.encode("utf-8"))

    assert original.parse_errors == [], before
    assert changed.parse_errors == [], after
    assert changed.ast_hash != original.ast_hash
    old_symbol = next(s for s in original.symbols if s.qualname == original_model.name)
    new_symbol = next(s for s in changed.symbols if s.qualname == changed_model.name)
    assert new_symbol.ast_hash != old_symbol.ast_hash


def test_property_2_strategy_covers_both_mutation_kinds() -> None:
    """Guard (Req 6.12, 6.15): the strategy yields cases for each mutation kind, and
    every case differs from its original."""
    pair_settings = settings(derandomize=True, max_examples=100)
    for kind in ("operator", "identifier"):
        found = find(mutation_cases(), lambda c, k=kind: c[0] == k, settings=pair_settings)
        assert render(found[1], found[3]) != render(found[2], found[3])
    with pytest.raises(NoSuchExample):
        find(
            mutation_cases(),
            lambda c: render(c[1], c[3]) == render(c[2], c[3]),
            settings=pair_settings,
        )


# ---------------------------------------------------------------------------
# Property 3
# ---------------------------------------------------------------------------
GraphSpec = tuple[list[str], list[tuple[str, str, str]]]


@st.composite
def graph_specs(draw: st.DrawFn) -> GraphSpec:
    """Node ids plus ``(source, target, edge_type)`` triples.

    Shapes: empty, sparse, dense, complete, self-loops only, and unions that
    contain several cycles. Self-loops are added explicitly.
    """
    count = draw(st.integers(0, 12))
    nodes = [f"n{i:02d}" for i in range(count)]
    if count == 0:
        return nodes, []
    pairs = [(a, b) for a in nodes for b in nodes if a != b]
    shape = draw(st.sampled_from(["sparse", "dense", "complete", "loops", "chain"]))
    chosen: list[tuple[str, str]] = []
    if shape in ("sparse", "dense") and pairs:
        picked = draw(st.sets(st.sampled_from(pairs), max_size=len(pairs)))
        if shape == "dense":
            picked |= set(draw(st.sets(st.sampled_from(pairs), min_size=len(pairs) // 2)))
        chosen.extend(sorted(picked))
    elif shape == "complete":
        chosen.extend(pairs)
    elif shape == "chain":
        order = draw(st.permutations(nodes))
        chosen.extend(zip(order, order[1:], strict=False))
        if draw(st.booleans()):
            chosen.append((order[-1], order[0]))
    loops = draw(st.sets(st.sampled_from(nodes), max_size=count))
    if shape == "loops":
        loops = loops or {draw(st.sampled_from(nodes))}
    chosen.extend((n, n) for n in sorted(loops))
    edges = [(a, b, draw(st.sampled_from(["calls", "imports"]))) for a, b in chosen]
    return nodes, edges


def _build(nodes: list[str], edges: list[tuple[str, str, str]]) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node)
    for source, target, edge_type in edges:
        graph.add_edge(source, target, edge_type=edge_type)
    return graph


def _reach(adjacency: dict[str, set[str]], start: str) -> set[str]:
    """Nodes reachable from ``start`` by one or more edges (plain BFS)."""
    seen: set[str] = set()
    queue = list(adjacency[start])
    while queue:
        node = queue.pop(0)
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency[node] - seen)
    return seen


def _expected_cycles(nodes: list[str], edges: list[tuple[str, str, str]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target, _ in edges:
        adjacency[source].add(target)
    reach = {node: _reach(adjacency, node) for node in nodes}
    on_cycle = [node for node in nodes if node in reach[node]]
    classes: list[list[str]] = []
    for node in sorted(on_cycle):
        if not any(node in group for group in classes):
            classes.append(
                sorted(m for m in on_cycle if m == node or (m in reach[node] and node in reach[m]))
            )
    return sorted(classes)


def _small_files(nodes: list[str], links: list[tuple[str, str]]) -> list[FileAnalysis]:
    paths = {name: f"{name}.py" for name in nodes}
    files = []
    for name in nodes:
        path = paths[name]
        symbol = SymbolNode(
            id=f"{path}::f",
            name="f",
            qualname="f",
            kind=SymbolKind.FUNCTION,
            file_path=path,
            start_line=1,
            end_line=2,
            signature="def f()",
            ast_hash="h",
            decorators=[],
            is_async=False,
            raw_calls=["f", "missing"] + [f"{t}.f" for _, t in links if _ == name],
        )
        files.append(
            FileAnalysis(
                file_path=path,
                language=Language.PYTHON,
                loc=2,
                ast_hash="h",
                imports=[t for s, t in links if s == name],
                exports=[],
                symbols=[symbol],
                parse_errors=[],
            )
        )
    return files


# Feature: 01-ast-graph-engine, Property 3: Cycle detection terminates, is correct, and is
# independent of insertion order
@PROPERTY_SETTINGS
@given(graph_specs(), st.data())
def test_property_3_cycle_detection_is_correct_and_order_independent(
    spec: GraphSpec, data: st.DataObject
) -> None:
    """**Validates: Requirements 4.3, 4.21, 4.22, 4.24, 4.25, 6.13**"""
    nodes, edges = spec
    graph = _build(nodes, edges)
    node_set = set(nodes)

    # Edge integrity: every edge endpoint is a node, with a known edge type.
    for source, target, attrs in graph.edges(data=True):
        assert source in node_set and target in node_set
        assert attrs["edge_type"] in ("calls", "imports")
    assert set(graph.nodes) == node_set

    cycles = detect_cycles(graph)

    # Order independence: rebuild with permuted node and edge insertion.
    shuffled_nodes = data.draw(st.permutations(nodes))
    shuffled_edges = data.draw(st.permutations(edges))
    assert detect_cycles(_build(shuffled_nodes, shuffled_edges)) == cycles

    # Sorted output.
    assert all(cycle == sorted(cycle) for cycle in cycles)
    assert cycles == sorted(cycles)

    members = [node for cycle in cycles for node in cycle]
    assert set(members) <= node_set
    assert len(members) == len(set(members))  # each cycle node covered exactly once

    # Independent oracle: mutual reachability classes of self-reachable nodes.
    assert cycles == _expected_cycles(nodes, edges)

    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target, _ in edges:
        adjacency[source].add(target)
    for cycle in cycles:
        for node in cycle:
            reachable = _reach(adjacency, node)
            assert set(cycle) <= reachable  # strongly connected (incl. self for size 1)
    if not any(node in _reach(adjacency, node) for node in nodes):
        assert cycles == []


@st.composite
def file_link_cases(draw: st.DrawFn) -> tuple[list[str], list[tuple[str, str]]]:
    ids = draw(st.lists(st.integers(0, 5), unique=True, max_size=6))
    names = [f"m{i}" for i in ids]
    if not names:
        return names, []
    links = draw(st.lists(st.tuples(st.sampled_from(names), st.sampled_from(names)), max_size=12))
    return names, links


# Feature: 01-ast-graph-engine, Property 3 (build_graph integrity)
@PROPERTY_SETTINGS
@given(file_link_cases())
def test_property_3_build_graph_edges_reference_existing_nodes(
    case: tuple[list[str], list[tuple[str, str]]],
) -> None:
    """**Validates: Requirements 4.3, 4.21, 6.13**"""
    nodes, links = case
    graph = build_graph(_small_files(nodes, links))
    for source, target, attrs in graph.edges(data=True):
        assert source in graph.nodes and target in graph.nodes
        assert attrs["edge_type"] in ("calls", "imports")
    cycles = detect_cycles(graph)
    assert cycles == sorted(sorted(c) for c in cycles)
    assert set().union(*map(set, cycles)) <= set(graph.nodes)


def test_property_3_strategy_covers_empty_self_loop_and_multi_node_cycle() -> None:
    """Guard (Req 6.15): the generator yields an empty graph, a self-loop graph and a
    graph with a multi-node cycle."""
    pair_settings = settings(derandomize=True, max_examples=100)
    empty = find(graph_specs(), lambda s: not s[0], settings=pair_settings)
    assert detect_cycles(_build(*empty)) == []
    loop = find(graph_specs(), lambda s: any(a == b for a, b, _ in s[1]), settings=pair_settings)
    assert detect_cycles(_build(*loop)) != []
    multi = find(
        graph_specs(),
        lambda s: any(len(c) > 1 for c in detect_cycles(_build(*s))),
        settings=pair_settings,
    )
    assert any(len(c) > 1 for c in detect_cycles(_build(*multi)))


# ---------------------------------------------------------------------------
# Property 4 strategy.
# Bias (documented, Req 6.14): in at least half of the draws (``planted`` is True with
# probability 1/2) a chain of 1 to 4 distinct callers is planted into the target
# (c_k -> ... -> c_1 -> target) before random extra ``calls`` edges are added. With
# ``max_depth`` in 1..4 a planted chain always gives a non-empty upstream set, so well
# over 30% of draws have one (random edges add more). The mutation always applies by
# construction: when every other node is already upstream, a fresh extra symbol node is
# created as the new edge source.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CallerCase:
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    target: str
    max_depth: int
    source: str  # new caller; equals FRESH_NODE when no existing node qualified
    dest: str  # node inside the upstream set, or the target
    planted: bool


FRESH_NODE = "fresh_caller"


def _call_graph(nodes: tuple[str, ...], edges: tuple[tuple[str, str], ...]) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    for node in nodes:
        graph.add_node(node, node_type="symbol")
    for source, dest in edges:
        graph.add_edge(source, dest, edge_type="calls")
    return graph


@st.composite
def caller_cases(draw: st.DrawFn) -> CallerCase:
    count = draw(st.integers(2, 12))
    nodes = tuple(f"s{i:02d}" for i in range(count))
    target = draw(st.sampled_from(nodes))
    others = [n for n in nodes if n != target]
    max_depth = draw(st.integers(1, 4))
    edges: set[tuple[str, str]] = set()
    planted = draw(st.booleans())
    if planted:
        length = draw(st.integers(1, min(4, len(others))))
        chain = draw(st.permutations(others))[:length]
        edges.add((chain[0], target))
        edges.update(zip(chain[1:], chain, strict=False))
    pairs = [(a, b) for a in nodes for b in nodes if a != b]
    edges.update(draw(st.sets(st.sampled_from(pairs), max_size=2 * count)))
    ordered = tuple(sorted(edges))

    upstream = set(
        trace_blast_radius(_call_graph(nodes, ordered), target, max_depth).upstream_callers
    )
    candidates = [n for n in others if n not in upstream]
    source = draw(st.sampled_from(candidates)) if candidates else FRESH_NODE
    dest = draw(st.sampled_from(sorted(upstream | {target})))
    return CallerCase(nodes, ordered, target, max_depth, source, dest, planted)


def _apply_caller_edge(case: CallerCase) -> tuple[nx.DiGraph, nx.DiGraph]:
    before = _call_graph(case.nodes, case.edges)
    nodes = case.nodes if case.source in case.nodes else (*case.nodes, case.source)
    after = _call_graph(nodes, (*case.edges, (case.source, case.dest)))
    return before, after


# Feature: 01-ast-graph-engine, Property 4: Adding a caller edge never shrinks the
# upstream set
@PROPERTY_SETTINGS
@given(caller_cases())
def test_property_4_adding_caller_edge_never_shrinks_upstream(case: CallerCase) -> None:
    """**Validates: Requirements 4.26, 4.27, 4.28, 4.29, 6.14**"""
    before_graph, after_graph = _apply_caller_edge(case)
    before = trace_blast_radius(before_graph, case.target, case.max_depth)
    after = trace_blast_radius(after_graph, case.target, case.max_depth)

    assert set(after.upstream_callers) >= set(before.upstream_callers)
    for result in (before, after):
        assert case.target not in result.upstream_callers
        assert result.upstream_callers == sorted(set(result.upstream_callers))
        assert 0.0 <= result.impact_score <= 1.0
    assert case.dest in before.upstream_callers or case.dest == case.target
    assert case.source not in before.upstream_callers

    # Formula check where it applies: same symbol count and same downstream set.
    if case.source in case.nodes and after.downstream_callees == before.downstream_callees:
        assert len(after.upstream_callers) >= len(before.upstream_callers)
        assert after.impact_score >= before.impact_score


def test_property_4_strategy_bias_and_nontrivial_growth() -> None:
    """Guard (Req 6.14, 6.15): at least 30% of generated cases have a non-empty upstream
    set before the mutation, and at least one mutation strictly grows the upstream set."""
    stats = {"total": 0, "nonempty": 0, "grew": 0}

    @settings(derandomize=True, max_examples=200)
    @given(caller_cases())
    def sample(case: CallerCase) -> None:
        before_graph, after_graph = _apply_caller_edge(case)
        before = trace_blast_radius(before_graph, case.target, case.max_depth)
        after = trace_blast_radius(after_graph, case.target, case.max_depth)
        stats["total"] += 1
        stats["nonempty"] += bool(before.upstream_callers)
        stats["grew"] += len(after.upstream_callers) > len(before.upstream_callers)

    sample()
    assert stats["total"] >= 100
    assert stats["nonempty"] * 10 >= stats["total"] * 3
    assert stats["grew"] >= 1
