"""Structural DSA-in-the-Wild scanner (Spec #01, Requirement 5).

This module is the scanner scaffolding. It decides *which* Symbols are scanned,
builds evidence strings and confidences, de-duplicates and sorts signals, and
reports skipped files. It never decides a pattern by itself: pattern rules are
small functions registered with ``register_rule`` (one per chapter module or
function, added by later tasks). A rule receives a ``RuleContext`` and returns
``PatternMatch`` values built from observed syntax nodes.

Everything is static and deterministic. Analyzed source is only parsed, never
executed or imported, and no regular expression decides any pattern.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import get_args

import tree_sitter

from backend.domain.models import DSAChapter, DSASignal, Language, SymbolKind, SymbolNode
from backend.engines.ast_parser import (
    ParsedFile,
    UnsupportedLanguageError,
    parse_source,
)

__all__ = [
    "CHAPTERS",
    "CONFIDENCE_TABLE",
    "MAX_EVIDENCE_ITEMS",
    "MAX_EVIDENCE_LENGTH",
    "EvidenceItem",
    "PatternMatch",
    "RuleContext",
    "RuleFn",
    "ScanResult",
    "SkipReason",
    "SkippedFile",
    "callee_text",
    "collections",
    "conditional",
    "confidence_for",
    "enclosing_loop",
    "in_loop",
    "make_evidence",
    "register_rule",
    "registered_rules",
    "scan_file",
    "scan_many",
    "scan_parsed",
    "self_call",
    "short_text",
]

CHAPTERS: tuple[str, ...] = get_args(DSAChapter)
MAX_EVIDENCE_ITEMS = 10
MAX_EVIDENCE_LENGTH = 200
_MAX_IDENTIFIER_LENGTH = 40
_ELLIPSIS = "..."
_SCANNED_KINDS = frozenset({SymbolKind.FUNCTION, SymbolKind.METHOD})


class SkipReason(StrEnum):
    UNSUPPORTED_LANGUAGE = "unsupported_language"


@dataclass(frozen=True)
class SkippedFile:
    file_path: str
    reason: SkipReason


@dataclass(frozen=True)
class ScanResult:
    signals: list[DSASignal]
    skipped: list[SkippedFile]


# ---------------------------------------------------------------------------
# Confidence table (design: "Confidence table")
# ---------------------------------------------------------------------------

# Keyed by table key (the pattern name, except the two memoization rows which
# share the pattern name ``memoization``). Each row maps evidence-kind count k
# to a confidence. Rows are non-decreasing in k and use two decimals.
CONFIDENCE_TABLE: dict[str, dict[int, float]] = {
    "hash-table lookup": {2: 0.70, 3: 0.85},
    "frequency counting": {2: 0.75, 3: 0.90},
    "de-duplication": {2: 0.70, 3: 0.85},
    "queue-based traversal": {1: 0.60, 2: 0.75, 3: 0.90},
    "stack-based traversal": {2: 0.65, 3: 0.80},
    "recursive node traversal": {2: 0.70, 3: 0.85},
    "direct recursion": {1: 0.80, 2: 0.90, 3: 0.95},
    "memoization (decorator)": {1: 0.85, 2: 0.90},
    "memoization (manual)": {3: 0.90},
    "heapq operations": {1: 0.80, 2: 0.90, 3: 0.95},
    "priority queue usage": {2: 0.75, 3: 0.90},
    "bisect usage": {1: 0.85, 2: 0.90},
    "binary search": {2: 0.80, 3: 0.90},
    "custom sort key": {2: 0.65, 3: 0.80},
    "two pointers": {3: 0.75, 4: 0.90},
}


def confidence_for(table_key: str, k: int) -> float:
    """Confidence for ``k`` independent evidence kinds.

    ``k`` is clamped into the row's defined range, so the result never decreases
    as ``k`` grows. Raises ``KeyError`` for an unknown table key.
    """
    row = CONFIDENCE_TABLE[table_key]
    lowest, highest = min(row), max(row)
    clamped = min(max(k, lowest), highest)
    # Use the nearest defined entry at or below the clamped count.
    defined = max(key for key in row if key <= clamped)
    return round(row[defined], 2)


# ---------------------------------------------------------------------------
# Language profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Profile:
    loop_types: frozenset[str]
    call_type: str
    binding_type: str
    binding_name_field: str
    binding_value_field: str


_CONDITIONAL_TYPES = frozenset(
    {
        "if_statement",
        "elif_clause",
        "else_clause",
        "conditional_expression",
        "ternary_expression",
    }
)
_CALLEE_TYPES = frozenset(
    {"identifier", "attribute", "member_expression", "field_access", "this", "super"}
)

_PYTHON_PROFILE = _Profile(
    loop_types=frozenset(
        {
            "for_statement",
            "while_statement",
            "list_comprehension",
            "set_comprehension",
            "dictionary_comprehension",
            "generator_expression",
        }
    ),
    call_type="call",
    binding_type="assignment",
    binding_name_field="left",
    binding_value_field="right",
)
_ECMASCRIPT_PROFILE = _Profile(
    loop_types=frozenset({"for_statement", "for_in_statement", "while_statement", "do_statement"}),
    call_type="call_expression",
    binding_type="variable_declarator",
    binding_name_field="name",
    binding_value_field="value",
)
_JAVA_PROFILE = _Profile(
    loop_types=frozenset(
        {"for_statement", "enhanced_for_statement", "while_statement", "do_statement"}
    ),
    call_type="method_invocation",
    binding_type="variable_declarator",
    binding_name_field="name",
    binding_value_field="value",
)
_PROFILES: dict[Language, _Profile] = {
    Language.PYTHON: _PYTHON_PROFILE,
    Language.TYPESCRIPT: _ECMASCRIPT_PROFILE,
    Language.JAVASCRIPT: _ECMASCRIPT_PROFILE,
    Language.TSX: _ECMASCRIPT_PROFILE,
    Language.JAVA: _JAVA_PROFILE,
}


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """One formatted evidence string plus its source position (for ordering)."""

    start_row: int
    start_column: int
    text: str


def short_text(text: str, limit: int = _MAX_IDENTIFIER_LENGTH) -> str:
    """Cut identifier text to ``limit`` characters (the design's 40)."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: max(limit - len(_ELLIPSIS), 1)] + _ELLIPSIS


def _line_reference(start_line: int, end_line: int) -> str:
    if start_line == end_line:
        return f"at line {start_line}"
    return f"at lines {start_line}-{end_line}"


def make_evidence(symbol: SymbolNode, description: str, node: tree_sitter.Node) -> EvidenceItem:
    """Format ``"<construct> at line N"`` or ``"<construct> at lines A-B"``.

    Lines come from ``node`` and are clamped into the Symbol's line range. The
    description is shortened, never the line reference, so the item is at most
    ``MAX_EVIDENCE_LENGTH`` characters.
    """
    first = min(max(node.start_point.row + 1, symbol.start_line), symbol.end_line)
    last = min(max(node.end_point.row + 1, first), symbol.end_line)
    reference = _line_reference(first, last)
    description = " ".join(description.split()) or "construct"
    room = MAX_EVIDENCE_LENGTH - len(reference) - 1
    if len(description) > room:
        description = description[: max(room - len(_ELLIPSIS), 1)] + _ELLIPSIS
    return EvidenceItem(node.start_point.row, node.start_point.column, f"{description} {reference}")


def _ordered_evidence(items: Iterable[EvidenceItem]) -> list[str]:
    """Source order, duplicates removed, at most ``MAX_EVIDENCE_ITEMS``."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in sorted(items, key=lambda e: (e.start_row, e.start_column, e.text)):
        if item.text in seen:
            continue
        seen.add(item.text)
        ordered.append(item.text)
    return ordered[:MAX_EVIDENCE_ITEMS]


# ---------------------------------------------------------------------------
# Rule seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternMatch:
    """What a rule reports for one Symbol.

    ``k`` is the number of independent evidence kinds present. ``table_key`` is
    the confidence-table row; it defaults to ``pattern_name``.
    """

    pattern_name: str
    evidence: tuple[EvidenceItem, ...]
    k: int
    table_key: str | None = None


@dataclass(frozen=True)
class RuleContext:
    """Everything a rule may inspect for one function or method Symbol."""

    parsed: ParsedFile
    symbol: SymbolNode
    node: tree_sitter.Node  # the Symbol's declaration node
    language: Language
    source: bytes
    body_nodes: tuple[tree_sitter.Node, ...]  # pre-order, nested Symbol declarations excluded
    imports: frozenset[str]

    @property
    def profile(self) -> _Profile:
        return _PROFILES[self.language]

    def text(self, node: tree_sitter.Node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def evidence(self, description: str, node: tree_sitter.Node) -> EvidenceItem:
        return make_evidence(self.symbol, description, node)


RuleFn = Callable[[RuleContext], Iterable[PatternMatch]]


@dataclass(frozen=True)
class _Rule:
    chapter: str
    fn: RuleFn


_RULES: list[_Rule] = []


def register_rule(chapter: DSAChapter) -> Callable[[RuleFn], RuleFn]:
    """Register ``fn`` as a rule for ``chapter``. Used as a decorator."""
    if chapter not in CHAPTERS:
        raise ValueError(f"unknown DSA chapter {chapter!r}")

    def decorator(fn: RuleFn) -> RuleFn:
        _RULES.append(_Rule(chapter, fn))
        return fn

    return decorator


def registered_rules() -> list[tuple[str, RuleFn]]:
    return [(rule.chapter, rule.fn) for rule in _RULES]


# ---------------------------------------------------------------------------
# Body walk and shared predicates
# ---------------------------------------------------------------------------


def _declaration_keys(parsed: ParsedFile) -> frozenset[tuple[str, int, int]]:
    return frozenset((n.type, n.start_byte, n.end_byte) for n in parsed.symbol_nodes.values())


def _body_nodes(
    root: tree_sitter.Node, declarations: frozenset[tuple[str, int, int]]
) -> tuple[tree_sitter.Node, ...]:
    """Pre-order nodes of ``root`` without entering nested Symbol declarations."""
    nodes: list[tree_sitter.Node] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.id != root.id and (node.type, node.start_byte, node.end_byte) in declarations:
            continue
        nodes.append(node)
        stack.extend(reversed(node.children))
    return tuple(nodes)


def _ancestors(ctx: RuleContext, node: tree_sitter.Node) -> Iterator[tree_sitter.Node]:
    """Proper ancestors of ``node`` that lie inside the Symbol (root excluded)."""
    current = node.parent
    while current is not None and current.id != ctx.node.id:
        yield current
        current = current.parent


def enclosing_loop(ctx: RuleContext, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Nearest loop ancestor of ``node`` inside the Symbol, or None."""
    loops = ctx.profile.loop_types
    for ancestor in _ancestors(ctx, node):
        if ancestor.type in loops:
            return ancestor
    return None


def in_loop(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    return enclosing_loop(ctx, node) is not None


def conditional(
    ctx: RuleContext, node: tree_sitter.Node, loop: tree_sitter.Node | None = None
) -> bool:
    """``node`` lies under a conditional construct (inside ``loop`` when given)."""
    for ancestor in _ancestors(ctx, node):
        if loop is not None and ancestor.id == loop.id:
            return False
        if ancestor.type in _CONDITIONAL_TYPES:
            return True
    return False


def callee_text(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """Callee text if ``node`` is a call with an identifier or member-chain callee."""
    profile = ctx.profile
    if node.type != profile.call_type:
        return None
    if ctx.language is Language.JAVA:
        name = node.child_by_field_name("name")
        if name is None:
            return None
        target = node.child_by_field_name("object")
        if target is None:
            return ctx.text(name)
        if target.type not in _CALLEE_TYPES:
            return None
        return " ".join(f"{ctx.text(target)}.{ctx.text(name)}".split())
    function = node.child_by_field_name("function")
    if function is None or function.type not in _CALLEE_TYPES:
        return None
    return " ".join(ctx.text(function).split())


def self_call(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    """``node`` is a call to the Symbol itself (design predicate ``self_call``)."""
    callee = callee_text(ctx, node)
    if callee is None:
        return False
    name = ctx.symbol.name
    if callee == name:
        return True
    if ctx.symbol.kind is not SymbolKind.METHOD:
        return False
    receiver = "self" if ctx.language is Language.PYTHON else "this"
    return callee == f"{receiver}.{name}"


def collections(
    ctx: RuleContext, is_creation: Callable[[RuleContext, tree_sitter.Node], bool]
) -> dict[str, tree_sitter.Node]:
    """Local names bound to a creation expression accepted by ``is_creation``.

    Binding is ``assignment`` (Python) or ``variable_declarator`` (TS/JS/Java)
    with an identifier on the left. Maps name to the creation expression of its
    first binding.
    """
    profile = ctx.profile
    found: dict[str, tree_sitter.Node] = {}
    for node in ctx.body_nodes:
        if node.type != profile.binding_type:
            continue
        target = node.child_by_field_name(profile.binding_name_field)
        value = node.child_by_field_name(profile.binding_value_field)
        if target is None or value is None or target.type != "identifier":
            continue
        if is_creation(ctx, value):
            found.setdefault(ctx.text(target), value)
    return found


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def _build_context(
    parsed: ParsedFile,
    symbol: SymbolNode,
    node: tree_sitter.Node,
    declarations: frozenset[tuple[str, int, int]],
) -> RuleContext:
    return RuleContext(
        parsed=parsed,
        symbol=symbol,
        node=node,
        language=parsed.analysis.language,
        source=parsed.source,
        body_nodes=_body_nodes(node, declarations),
        imports=frozenset(parsed.analysis.imports),
    )


def _scan_symbol(ctx: RuleContext) -> list[DSASignal]:
    """Run every registered rule; merge matches sharing (chapter, pattern_name)."""
    merged: dict[tuple[str, str], tuple[float, list[EvidenceItem]]] = {}
    for rule in _RULES:
        for match in rule.fn(ctx):
            if not match.evidence:
                raise ValueError(f"rule produced pattern {match.pattern_name!r} without evidence")
            confidence = confidence_for(match.table_key or match.pattern_name, match.k)
            key = (rule.chapter, match.pattern_name)
            previous = merged.get(key)
            if previous is None:
                merged[key] = (confidence, list(match.evidence))
            else:
                merged[key] = (max(previous[0], confidence), previous[1] + list(match.evidence))
    symbol = ctx.symbol
    signals: list[DSASignal] = []
    for (chapter, pattern_name), (confidence, items) in merged.items():
        signals.append(
            DSASignal(
                symbol_id=symbol.id,
                file_path=symbol.file_path,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                chapter=chapter,  # type: ignore[arg-type]
                pattern_name=pattern_name,
                confidence=confidence,
                evidence=_ordered_evidence(items),
            )
        )
    return signals


def _sort_key(signal: DSASignal) -> tuple[str, int, str, str, int, str]:
    return (
        signal.file_path,
        signal.start_line,
        signal.chapter,
        signal.pattern_name,
        signal.end_line,
        signal.symbol_id,
    )


def _sorted_unique(signals: Iterable[DSASignal]) -> list[DSASignal]:
    unique: dict[tuple[str, str, str], DSASignal] = {}
    for signal in signals:
        unique.setdefault((signal.symbol_id, signal.chapter, signal.pattern_name), signal)
    return sorted(unique.values(), key=_sort_key)


def _signals_for(parsed: ParsedFile) -> list[DSASignal]:
    if parsed.analysis.language not in _PROFILES:
        return []
    declarations = _declaration_keys(parsed)
    signals: list[DSASignal] = []
    for symbol in parsed.analysis.symbols:
        if symbol.kind not in _SCANNED_KINDS:
            continue
        node = parsed.symbol_nodes.get(symbol.id)
        if node is None or node.has_error:
            continue
        signals.extend(_scan_symbol(_build_context(parsed, symbol, node, declarations)))
    return signals


def scan_parsed(parsed: ParsedFile) -> ScanResult:
    """Scan every function and method Symbol of one parsed file."""
    if parsed.analysis.language not in _PROFILES:
        return ScanResult(
            [], [SkippedFile(parsed.analysis.file_path, SkipReason.UNSUPPORTED_LANGUAGE)]
        )
    return ScanResult(_sorted_unique(_signals_for(parsed)), [])


def scan_file(file_path: str, source: bytes) -> ScanResult:
    """Parse and scan one file; an unsupported extension is reported as skipped."""
    try:
        parsed = parse_source(file_path, source)
    except UnsupportedLanguageError:
        return ScanResult([], [SkippedFile(file_path, SkipReason.UNSUPPORTED_LANGUAGE)])
    return scan_parsed(parsed)


def scan_many(parsed_files: Sequence[ParsedFile]) -> ScanResult:
    """Scan several parsed files; signals are sorted over the whole result."""
    signals: list[DSASignal] = []
    skipped: list[SkippedFile] = []
    for parsed in parsed_files:
        result = scan_parsed(parsed)
        signals.extend(result.signals)
        skipped.extend(result.skipped)
    skipped.sort(key=lambda s: (s.file_path, s.reason.value))
    return ScanResult(_sorted_unique(signals), skipped)


# ---------------------------------------------------------------------------
# Hash Tables rules (Req 5.6, 5.7)
# ---------------------------------------------------------------------------

_MAP, _SET, _COUNTER = "map", "set", "counter"
_LITERAL_TYPES = frozenset({"dictionary", "set", "object"})
_BINARY_TYPES = frozenset({"binary_operator", "binary_expression"})
_CONDITION_OWNERS = frozenset(
    {"if_statement", "elif_clause", "while_statement", "ternary_expression"}
)

_PY_CALLEE_KINDS: dict[str, str] = {
    "dict": _MAP,
    "defaultdict": _MAP,
    "collections.defaultdict": _MAP,
    "OrderedDict": _MAP,
    "collections.OrderedDict": _MAP,
    "set": _SET,
    "frozenset": _SET,
    "Counter": _COUNTER,
    "collections.Counter": _COUNTER,
}
_ES_CONSTRUCTOR_KINDS: dict[str, str] = {"Map": _MAP, "Set": _SET}
_JAVA_CONSTRUCTOR_KINDS: dict[str, str] = {
    "HashMap": _MAP,
    "LinkedHashMap": _MAP,
    "ConcurrentHashMap": _MAP,
    "Hashtable": _MAP,
    "HashSet": _SET,
    "LinkedHashSet": _SET,
}

# Method name -> access role, per language family.
_METHOD_ROLES: dict[str, dict[str, str]] = {
    "py": {"get": "read", "add": "add", "update": "write", "setdefault": "count"},
    "es": {"get": "read", "has": "member", "set": "write", "add": "add"},
    "java": {
        "get": "read",
        "getOrDefault": "read",
        "containsKey": "member",
        "contains": "member",
        "put": "write",
        "putIfAbsent": "write",
        "add": "add",
        "merge": "count",
    },
}
# Subscript node type and its base field, and (assignment, augmented, update) types.
_SUBSCRIPTS = {"py": ("subscript", "value"), "es": ("subscript_expression", "object")}
_ASSIGNMENTS = {
    "py": ("assignment", "augmented_assignment", None),
    "es": ("assignment_expression", "augmented_assignment_expression", "update_expression"),
}
_SEQUENCE_CALLEES = frozenset({"list", "sorted", "tuple", "Array.from", "List.copyOf"})
_JAVA_SEQUENCE_TYPES = frozenset({"ArrayList", "LinkedList"})
_COUNTING_PUTS = frozenset({"set", "put"})


@dataclass(frozen=True)
class _Access:
    """One operation on a tracked local collection. ``role`` is one of
    member, read, write, add, count."""

    role: str
    name: str
    node: tree_sitter.Node


def _family(ctx: RuleContext) -> str:
    if ctx.language is Language.PYTHON:
        return "py"
    return "java" if ctx.language is Language.JAVA else "es"


def _java_type_name(node: tree_sitter.Node, ctx: RuleContext) -> str | None:
    type_node = node.child_by_field_name("type")
    if type_node is not None and type_node.type == "generic_type" and type_node.named_children:
        type_node = type_node.named_children[0]
    return None if type_node is None else ctx.text(type_node)


def _creation_kind(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """``map``, ``set``, ``counter`` when ``node`` creates a hash collection."""
    family = _family(ctx)
    if family == "py":
        simple = {
            "dictionary": _MAP,
            "dictionary_comprehension": _MAP,
            "set": _SET,
            "set_comprehension": _SET,
        }
        if node.type in simple:
            return simple[node.type]
        callee = callee_text(ctx, node)
        return _PY_CALLEE_KINDS.get(callee) if callee else None
    if family == "es":
        if node.type == "object" and node.named_child_count == 0:
            return _MAP
        constructor = node.child_by_field_name("constructor")
        if node.type == "new_expression" and constructor is not None:
            return _ES_CONSTRUCTOR_KINDS.get(ctx.text(constructor))
        return None
    if node.type != "object_creation_expression":
        return None
    return _JAVA_CONSTRUCTOR_KINDS.get(_java_type_name(node, ctx) or "")


def _is_creation(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    return _creation_kind(ctx, node) is not None


def _tracked(ctx: RuleContext) -> dict[str, tuple[str, tree_sitter.Node]]:
    """Local name -> (kind, creation node) in order of creation."""
    found = collections(ctx, _is_creation)
    pairs = {name: (_creation_kind(ctx, node) or _MAP, node) for name, node in found.items()}
    return dict(sorted(pairs.items(), key=lambda item: item[1][1].start_byte))


def _descendants(node: tree_sitter.Node) -> Iterator[tree_sitter.Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


def _method_call(
    ctx: RuleContext, node: tree_sitter.Node
) -> tuple[str, str, tree_sitter.Node | None] | None:
    """``(receiver, method, arguments)`` for ``name.method(...)`` on an identifier."""
    if node.type != ctx.profile.call_type:
        return None
    if _family(ctx) == "java":
        receiver, method = node.child_by_field_name("object"), node.child_by_field_name("name")
    else:
        function = node.child_by_field_name("function")
        if function is None or function.type not in {"attribute", "member_expression"}:
            return None
        receiver = function.child_by_field_name("object")
        method = function.child_by_field_name("attribute" if _family(ctx) == "py" else "property")
    if receiver is None or method is None or receiver.type != "identifier":
        return None
    return ctx.text(receiver), ctx.text(method), node.child_by_field_name("arguments")


def _subscript_base(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    spec = _SUBSCRIPTS.get(_family(ctx))
    if spec is None or node.type != spec[0]:
        return None
    base = node.child_by_field_name(spec[1])
    return ctx.text(base) if base is not None and base.type == "identifier" else None


def _read_name(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """Name read by a subscript or a ``get``-style call, else None."""
    base = _subscript_base(ctx, node)
    if base is not None:
        return base
    call = _method_call(ctx, node)
    if call is not None and _METHOD_ROLES[_family(ctx)].get(call[1]) == "read":
        return call[0]
    return None


def _updates_from_own_value(ctx: RuleContext, name: str, value: tree_sitter.Node | None) -> bool:
    """``value`` is a binary expression that reads ``name`` (``d.get(k, 0) + 1``)."""
    if value is None or value.type not in _BINARY_TYPES:
        return False
    return any(_read_name(ctx, node) == name for node in _descendants(value))


def _membership(
    ctx: RuleContext, node: tree_sitter.Node, names: dict[str, tuple[str, tree_sitter.Node]]
) -> _Access | None:
    """``x in name`` (Python comparison, JS/TS ``in`` operator)."""
    family = _family(ctx)
    if family == "py" and node.type == "comparison_operator":
        operators = node.children_by_field_name("operators")
        right = node.named_children[-1] if node.named_children else None
        if len(operators) != 1 or ctx.text(operators[0]).split() not in (["in"], ["not", "in"]):
            return None
    elif family == "es" and node.type == "binary_expression":
        operator = node.child_by_field_name("operator")
        right = node.child_by_field_name("right")
        if operator is None or ctx.text(operator) != "in":
            return None
    else:
        return None
    if right is None or right.type != "identifier" or ctx.text(right) not in names:
        return None
    return _Access("member", ctx.text(right), node)


def _subscript_access(
    ctx: RuleContext, node: tree_sitter.Node, names: dict[str, tuple[str, tree_sitter.Node]]
) -> _Access | None:
    name = _subscript_base(ctx, node)
    if name is None or name not in names:
        return None
    assign, augmented, update = _ASSIGNMENTS[_family(ctx)]
    parent = node.parent
    if parent is None:
        return _Access("read", name, node)
    if parent.type == update and parent.child_by_field_name("argument") == node:
        return _Access("count", name, parent)
    if parent.type not in (assign, augmented) or parent.child_by_field_name("left") != node:
        return _Access("read", name, node)
    counting = parent.type == augmented or _updates_from_own_value(
        ctx, name, parent.child_by_field_name("right")
    )
    return _Access("count" if counting else "write", name, parent)


def _call_access(
    ctx: RuleContext, node: tree_sitter.Node, names: dict[str, tuple[str, tree_sitter.Node]]
) -> _Access | None:
    call = _method_call(ctx, node)
    if call is None or call[0] not in names:
        return None
    name, method, arguments = call
    role = _METHOD_ROLES[_family(ctx)].get(method)
    if role is None:
        return None
    if role == "write" and method == "update" and names[name][0] == _COUNTER:
        role = "count"
    if role == "write" and method in _COUNTING_PUTS and arguments is not None:
        if any(_updates_from_own_value(ctx, name, arg) for arg in arguments.named_children):
            role = "count"
    return _Access(role, name, node)


def _accesses(ctx: RuleContext, names: dict[str, tuple[str, tree_sitter.Node]]) -> list[_Access]:
    found: list[_Access] = []
    for node in ctx.body_nodes:
        access = (
            _membership(ctx, node, names)
            or _subscript_access(ctx, node, names)
            or _call_access(ctx, node, names)
        )
        if access is not None:
            found.append(access)
    return found


def _within(inner: tree_sitter.Node, outer: tree_sitter.Node) -> bool:
    return outer.start_byte <= inner.start_byte and inner.end_byte <= outer.end_byte


def _lookups_in_loop(ctx: RuleContext, accesses: list[_Access]) -> list[_Access]:
    """Membership tests and reads inside a loop, outside any counting update."""
    counting = [a.node for a in accesses if a.role == "count"]
    return [
        a
        for a in accesses
        if a.role in ("member", "read")
        and in_loop(ctx, a.node)
        and not any(_within(a.node, node) for node in counting)
    ]


def _created(ctx: RuleContext, name: str, kind: str, node: tree_sitter.Node) -> EvidenceItem:
    return ctx.evidence(f"{kind} {short_text(name)} created", node)


def _first(accesses: list[_Access], name: str, *roles: str) -> _Access | None:
    return next((a for a in accesses if a.name == name and a.role in roles), None)


def _lookup_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    names = _tracked(ctx)
    accesses = _accesses(ctx, names)
    lookups = _lookups_in_loop(ctx, accesses)
    for name, (kind, creation) in names.items():
        lookup = next((a for a in lookups if a.name == name), None)
        if lookup is None:
            continue
        evidence = [
            _created(ctx, name, kind, creation),
            ctx.evidence(f"lookup in {short_text(name)} inside loop", lookup.node),
        ]
        populate = _first(accesses, name, "write", "add")
        if populate is not None:
            evidence.append(ctx.evidence(f"insert into {short_text(name)}", populate.node))
        yield PatternMatch("hash-table lookup", tuple(evidence), len(evidence))


def _frequency_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    names = _tracked(ctx)
    accesses = _accesses(ctx, names)
    for name, (kind, creation) in names.items():
        update = _first(accesses, name, "count")
        if update is None:
            continue
        evidence = [
            _created(ctx, name, kind, creation),
            ctx.evidence(f"count update on {short_text(name)}", update.node),
        ]
        if in_loop(ctx, update.node):
            evidence.append(ctx.evidence("count update inside loop", update.node))
        yield PatternMatch("frequency counting", tuple(evidence), len(evidence))


def _in_condition(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    """``node`` lies inside the condition of an enclosing if, elif, while, or ternary."""
    for ancestor in _ancestors(ctx, node):
        if ancestor.type not in _CONDITION_OWNERS:
            continue
        condition = ancestor.child_by_field_name("condition")
        if condition is not None and _within(node, condition):
            return True
    return False


def _guarded_add(ctx: RuleContext, name: str, accesses: list[_Access]) -> _Access | None:
    """An add to ``name`` that follows a membership test in a condition, or sits in one."""
    tests = [a for a in accesses if a.name == name and a.role == "member"]
    for add in (a for a in accesses if a.name == name and a.role == "add"):
        if _in_condition(ctx, add.node):
            return add
        if any(
            t.node.start_byte < add.node.start_byte and _in_condition(ctx, t.node) for t in tests
        ):
            return add
    return None


def _sequence_conversion(ctx: RuleContext, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Argument of ``list(...)``, ``Array.from(...)``, ``[...x]``, ``new ArrayList<>(x)``."""
    if node.type == "array" and _family(ctx) == "es":
        spread = node.named_children[0] if len(node.named_children) == 1 else None
        if spread is not None and spread.type == "spread_element" and spread.named_children:
            return spread.named_children[0]
        return None
    if node.type == "object_creation_expression":
        if _java_type_name(node, ctx) not in _JAVA_SEQUENCE_TYPES:
            return None
    elif callee_text(ctx, node) not in _SEQUENCE_CALLEES:
        return None
    arguments = node.child_by_field_name("arguments")
    return arguments.named_children[0] if arguments and arguments.named_children else None


def _converted_set(
    ctx: RuleContext, argument: tree_sitter.Node, sets: dict[str, tree_sitter.Node]
) -> tree_sitter.Node | None:
    """Creation node of the set that ``argument`` is, or names (literals excluded)."""
    if argument.type == "identifier":
        creation = sets.get(ctx.text(argument))
    else:
        creation = argument if _creation_kind(ctx, argument) == _SET else None
    if creation is None or creation.type in _LITERAL_TYPES:
        return None
    return creation


def _conversion_use(
    ctx: RuleContext, sets: dict[str, tree_sitter.Node]
) -> tuple[tree_sitter.Node, tree_sitter.Node] | None:
    """``(set creation, converting node)`` for the first set turned into a sequence."""
    for node in ctx.body_nodes:
        argument = _sequence_conversion(ctx, node)
        creation = None if argument is None else _converted_set(ctx, argument, sets)
        if creation is not None:
            return creation, node
    return None


def _dedupe_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    names = _tracked(ctx)
    sets = {name: node for name, (kind, node) in names.items() if kind == _SET}
    accesses = _accesses(ctx, names)
    for name, creation in sets.items():
        add = _guarded_add(ctx, name, accesses)
        if add is None:
            continue
        evidence = [
            _created(ctx, name, _SET, creation),
            ctx.evidence(f"guarded add to {short_text(name)}", add.node),
        ]
        if in_loop(ctx, add.node):
            evidence.append(ctx.evidence("guarded add inside loop", add.node))
        yield PatternMatch("de-duplication", tuple(evidence), len(evidence))
    converted = _conversion_use(ctx, sets)
    if converted is not None:
        creation, node = converted
        evidence = [
            ctx.evidence("set created", creation),
            ctx.evidence("set converted to sequence", node),
        ]
        yield PatternMatch("de-duplication", tuple(evidence), len(evidence))


@register_rule("Hash Tables")
def hash_table_lookup_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _lookup_matches(ctx)


@register_rule("Hash Tables")
def frequency_counting_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _frequency_matches(ctx)


@register_rule("Hash Tables")
def de_duplication_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _dedupe_matches(ctx)


# ---------------------------------------------------------------------------
# Graphs & Trees rules (Req 5.8, 5.9)
# ---------------------------------------------------------------------------

_JAVA_QUEUE_TYPES = frozenset({"ArrayDeque", "LinkedList", "Queue", "Deque"})
_JAVA_QUEUE_CREATIONS = frozenset({"ArrayDeque", "LinkedList"})
_CHILD_NAMES = frozenset(
    {
        "left",
        "right",
        "children",
        "child",
        "neighbors",
        "neighbours",
        "adj",
        "adjacency",
        "successors",
    }
)
_WHILE_TYPES = frozenset({"while_statement", "do_statement"})
_ACCESS_TYPES = frozenset(
    {
        "attribute",
        "member_expression",
        "field_access",
        "subscript",
        "subscript_expression",
        "method_invocation",
        "call",
        "call_expression",
    }
)
_VISITED_TEST_METHODS = {
    "py": frozenset[str](),
    "es": frozenset({"has", "includes"}),
    "java": frozenset({"contains", "containsKey"}),
}
_VISITED_ADD_METHODS = {
    "py": frozenset({"add", "append", "update"}),
    "es": frozenset({"add", "push", "set"}),
    "java": frozenset({"add", "put"}),
}
_PUSH_METHODS = {"py": "append", "es": "push", "java": "push"}
_ATTRIBUTE_FIELDS = {
    "attribute": "attribute",
    "member_expression": "property",
    "field_access": "field",
}
_SUBSCRIPT_FIELDS = {
    "subscript": ("value", "subscript"),
    "subscript_expression": ("object", "index"),
}


def _no_arguments(arguments: tree_sitter.Node | None) -> bool:
    return arguments is None or arguments.named_child_count == 0


def _java_queue_names(ctx: RuleContext) -> frozenset[str]:
    """Java locals and parameters declared or created as a queue or deque type."""
    names: set[str] = set()
    for node in ctx.body_nodes:
        if node.type == "formal_parameter":
            name = node.child_by_field_name("name")
            if name is not None and _java_type_name(node, ctx) in _JAVA_QUEUE_TYPES:
                names.add(ctx.text(name))
        elif node.type == "local_variable_declaration":
            declared = _java_type_name(node, ctx) in _JAVA_QUEUE_TYPES
            for declarator in node.children_by_field_name("declarator"):
                name, value = (
                    declarator.child_by_field_name("name"),
                    declarator.child_by_field_name("value"),
                )
                created = (
                    value is not None
                    and value.type == "object_creation_expression"
                    and _java_type_name(value, ctx) in _JAVA_QUEUE_CREATIONS
                )
                if name is not None and (declared or created):
                    names.add(ctx.text(name))
    return frozenset(names)


def _is_queue_pop(
    ctx: RuleContext,
    method: str,
    arguments: tree_sitter.Node | None,
    receiver: str,
    queues: frozenset[str],
) -> bool:
    family = _family(ctx)
    if family == "java":
        return method in {"poll", "remove"} and _no_arguments(arguments) and receiver in queues
    if method == "popleft":
        return family == "py" and _no_arguments(arguments)
    if method == "shift":
        return family == "es" and _no_arguments(arguments)
    if method == "pop" and family == "py" and arguments is not None:
        first = arguments.named_children
        return len(first) == 1 and first[0].type == "integer" and ctx.text(first[0]) == "0"
    return False


def _queue_pops(ctx: RuleContext) -> Iterator[tuple[tree_sitter.Node, str]]:
    """``(call, receiver)`` for each queue-style removal that sits inside a loop."""
    queues = _java_queue_names(ctx) if _family(ctx) == "java" else frozenset()
    for node in ctx.body_nodes:
        call = _method_call(ctx, node)
        if call is None or not in_loop(ctx, node):
            continue
        receiver, method, arguments = call
        if _is_queue_pop(ctx, method, arguments, receiver, queues):
            yield node, receiver


def _identifiers(node: tree_sitter.Node, ctx: RuleContext) -> set[str]:
    return {ctx.text(n) for n in _descendants(node) if n.type == "identifier"}


def _popped_names(ctx: RuleContext, call: tree_sitter.Node) -> set[str]:
    """Names that receive the value of the removal ``call`` (``n = q.popleft()``)."""
    parent = call.parent
    if parent is None:
        return set()
    profile = ctx.profile
    if (
        parent.type == profile.binding_type
        and parent.child_by_field_name(profile.binding_value_field) == call
    ):
        target = parent.child_by_field_name(profile.binding_name_field)
    elif (
        parent.type in {"assignment", "assignment_expression"}
        and parent.child_by_field_name("right") == call
    ):
        target = parent.child_by_field_name("left")
    else:
        return set()
    return set() if target is None else _identifiers(target, ctx)


def _loop_iterable(loop: tree_sitter.Node) -> tree_sitter.Node | None:
    if loop.type == "enhanced_for_statement":
        return loop.child_by_field_name("value")
    if loop.type in {"for_statement", "for_in_statement"}:
        return loop.child_by_field_name("right")
    return None


def _neighbor_loop(
    ctx: RuleContext, outer: tree_sitter.Node, popped: set[str]
) -> tree_sitter.Node | None:
    """A loop inside ``outer`` over a subscript, attribute, or call using a popped name."""
    for node in ctx.body_nodes:
        if (
            node.id == outer.id
            or node.type not in ctx.profile.loop_types
            or not _within(node, outer)
        ):
            continue
        iterable = _loop_iterable(node)
        if iterable is None or iterable.type == "identifier":
            continue
        uses_popped = popped & _identifiers(iterable, ctx)
        if uses_popped and any(n.type in _ACCESS_TYPES for n in _descendants(iterable)):
            return node
    return None


def _is_in_operator(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    if _family(ctx) == "py":
        operators = [ctx.text(op).split() for op in node.children_by_field_name("operators")]
        return operators in ([["in"]], [["not", "in"]])
    operator = node.child_by_field_name("operator")
    return operator is not None and ctx.text(operator) == "in"


def _visited_test(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """Name tested for membership by ``node`` (``x in v``, ``v.has(x)``, ``v.contains(x)``)."""
    family = _family(ctx)
    if family != "java" and node.type in {"comparison_operator", "binary_expression"}:
        right = node.named_children[-1] if node.named_children else None
        if right is not None and right.type == "identifier" and _is_in_operator(ctx, node):
            return ctx.text(right)
        return None
    call = _method_call(ctx, node)
    if call is None:
        return None
    receiver, method, _ = call
    if method in _VISITED_TEST_METHODS[family]:
        return receiver
    if family == "java" and method == "add" and _in_condition(ctx, node):
        return receiver
    return None


def _visited_add(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """Name added to by ``node`` (``v.add(x)``, ``v[x] = True``)."""
    call = _method_call(ctx, node)
    if call is not None:
        return call[0] if call[1] in _VISITED_ADD_METHODS[_family(ctx)] else None
    if node.type in {"assignment", "assignment_expression"}:
        left = node.child_by_field_name("left")
        return None if left is None else _subscript_base(ctx, left)
    return None


def _visited_in(
    ctx: RuleContext, scope: tree_sitter.Node, exclude: set[str], need_add: bool
) -> tuple[tree_sitter.Node, str] | None:
    """First visited test inside ``scope``; with ``need_add`` the name must also be added to."""
    tests: list[tuple[tree_sitter.Node, str]] = []
    added: set[str] = set()
    for node in ctx.body_nodes:
        if not _within(node, scope):
            continue
        tested = _visited_test(ctx, node)
        if tested is not None and tested not in exclude:
            tests.append((node, tested))
        name = _visited_add(ctx, node)
        if name is not None:
            added.add(name)
    return next(((n, name) for n, name in tests if not need_add or name in added), None)


def _queue_traversal_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    for call, receiver in _queue_pops(ctx):
        loop = enclosing_loop(ctx, call)
        if loop is None:
            continue
        evidence = [ctx.evidence(f"queue pop on {short_text(receiver)} inside loop", call)]
        visited = _visited_in(ctx, loop, {receiver}, need_add=True)
        if visited is not None:
            evidence.append(
                ctx.evidence(f"visited {short_text(visited[1])} tested and added", visited[0])
            )
        neighbors = _neighbor_loop(ctx, loop, _popped_names(ctx, call))
        if neighbors is not None:
            evidence.append(ctx.evidence("loop over neighbors of popped value", neighbors))
        yield PatternMatch("queue-based traversal", tuple(evidence), len(evidence))
        return


def _enclosing_while(ctx: RuleContext, node: tree_sitter.Node) -> tree_sitter.Node | None:
    return next((a for a in _ancestors(ctx, node) if a.type in _WHILE_TYPES), None)


def _stack_pop_pairs(ctx: RuleContext) -> Iterator[tuple[tree_sitter.Node, str, tree_sitter.Node]]:
    """``(pop call, name, while loop)`` for ``name.pop()`` in a loop that also pushes to it."""
    push = _PUSH_METHODS[_family(ctx)]
    for node in ctx.body_nodes:
        call = _method_call(ctx, node)
        if call is None or call[1] != "pop" or not _no_arguments(call[2]):
            continue
        loop = _enclosing_while(ctx, node)
        if loop is None:
            continue
        pushes = (_method_call(ctx, n) for n in ctx.body_nodes if _within(n, loop))
        if any(p is not None and p[0] == call[0] and p[1] == push for p in pushes):
            yield node, call[0], loop


def _stack_traversal_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    for call, name, loop in _stack_pop_pairs(ctx):
        visited = _visited_in(ctx, loop, {name}, need_add=True)
        if visited is None:
            continue
        evidence = [
            ctx.evidence(f"stack pop on {short_text(name)} in while loop", call),
            ctx.evidence(f"visited {short_text(visited[1])} tested and added", visited[0]),
        ]
        neighbors = _neighbor_loop(ctx, loop, _popped_names(ctx, call))
        if neighbors is not None:
            evidence.append(ctx.evidence("loop over neighbors of popped value", neighbors))
        yield PatternMatch("stack-based traversal", tuple(evidence), len(evidence))
        return


def _accessed_names(ctx: RuleContext, node: tree_sitter.Node) -> set[str]:
    """Attribute or subscript names that ``node`` itself accesses."""
    field = _ATTRIBUTE_FIELDS.get(node.type)
    if field is not None:
        name = node.child_by_field_name(field)
        return set() if name is None else {ctx.text(name)}
    fields = _SUBSCRIPT_FIELDS.get(node.type)
    if fields is None:
        return set()
    names: set[str] = set()
    base, index = node.child_by_field_name(fields[0]), node.child_by_field_name(fields[1])
    if base is not None:
        names |= {ctx.text(base)} if base.type == "identifier" else _accessed_names(ctx, base)
    if index is not None and index.type in {"string", "string_fragment"}:
        names.add(ctx.text(index).strip("'\"`"))
    return names


def _child_access(ctx: RuleContext, call: tree_sitter.Node) -> tree_sitter.Node | None:
    """A child-named attribute or subscript in the call arguments or an enclosing loop iterable."""
    scopes = [call.child_by_field_name("arguments")]
    scopes += [_loop_iterable(a) for a in _ancestors(ctx, call) if a.type in ctx.profile.loop_types]
    for scope in scopes:
        if scope is None:
            continue
        for node in _descendants(scope):
            if _accessed_names(ctx, node) & _CHILD_NAMES:
                return node
    return None


def _recursive_traversal_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    for node in ctx.body_nodes:
        if not self_call(ctx, node):
            continue
        access = _child_access(ctx, node)
        if access is None:
            continue
        evidence = [
            ctx.evidence(f"self-call to {short_text(ctx.symbol.name)}", node),
            ctx.evidence("child access in call arguments or loop iterable", access),
        ]
        visited = _visited_in(ctx, ctx.node, set(), need_add=False)
        if visited is not None:
            evidence.append(ctx.evidence(f"visited {short_text(visited[1])} tested", visited[0]))
        yield PatternMatch("recursive node traversal", tuple(evidence), len(evidence))
        return


@register_rule("Graphs & Trees")
def queue_based_traversal_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _queue_traversal_matches(ctx)


@register_rule("Graphs & Trees")
def stack_based_traversal_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _stack_traversal_matches(ctx)


@register_rule("Graphs & Trees")
def recursive_node_traversal_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _recursive_traversal_matches(ctx)


# ---------------------------------------------------------------------------
# Recursion & Dynamic Programming rules (Req 5.10 to 5.12)
# ---------------------------------------------------------------------------
_MEMOIZATION = "memoization"
_CACHE_DECORATORS = frozenset({"lru_cache", "functools.lru_cache", "cache", "functools.cache"})
_MEMO_LOOKUP_ROLES = frozenset({"member", "read"})


def _self_calls(ctx: RuleContext) -> list[tree_sitter.Node]:
    return [node for node in ctx.body_nodes if self_call(ctx, node)]


def _base_case(ctx: RuleContext, first_call: tree_sitter.Node) -> tree_sitter.Node | None:
    """An ``if`` containing ``return`` that ends before the first self-call."""
    for node in ctx.body_nodes:
        if node.type != "if_statement" or node.end_byte > first_call.start_byte:
            continue
        if any(inner.type == "return_statement" for inner in _descendants(node)):
            return node
    return None


def _direct_recursion_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    calls = _self_calls(ctx)
    if not calls:
        return
    name = short_text(ctx.symbol.name)
    evidence = [ctx.evidence(f"self-call to {name}", calls[0])]
    base = _base_case(ctx, calls[0])
    if base is not None:
        evidence.append(ctx.evidence("base case with return before first self-call", base))
    if len(calls) >= 2:
        evidence.append(ctx.evidence(f"second self-call to {name}", calls[1]))
    yield PatternMatch("direct recursion", tuple(evidence), len(evidence))


def _decorator_name(ctx: RuleContext, decorator: tree_sitter.Node) -> str | None:
    """Decorator text without ``@`` and without call arguments."""
    expression = decorator.named_children[0] if decorator.named_children else None
    if expression is not None and expression.type == "call":
        expression = expression.child_by_field_name("function")
    if expression is None or expression.type not in {"identifier", "attribute"}:
        return None
    return " ".join(ctx.text(expression).split())


def _cache_decorator(ctx: RuleContext) -> tree_sitter.Node | None:
    if ctx.language is not Language.PYTHON:
        return None
    for child in ctx.node.children:
        if child.type == "decorator" and _decorator_name(ctx, child) in _CACHE_DECORATORS:
            return child
    return None


def _decorator_memo_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    decorator = _cache_decorator(ctx)
    if decorator is None:
        return
    evidence = [ctx.evidence(f"cache decorator {short_text(ctx.text(decorator))}", decorator)]
    calls = _self_calls(ctx)
    if calls:
        evidence.append(ctx.evidence(f"self-call to {short_text(ctx.symbol.name)}", calls[0]))
    yield PatternMatch(
        _MEMOIZATION, tuple(evidence), len(evidence), table_key="memoization (decorator)"
    )


def _manual_memo_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    calls = _self_calls(ctx)
    if not calls:
        return
    first = calls[0]
    names = {ctx.text(node): (_MAP, node) for node in ctx.body_nodes if node.type == "identifier"}
    accesses = _accesses(ctx, names)
    for name in names:
        lookup = next(
            (
                a
                for a in accesses
                if a.name == name
                and a.role in _MEMO_LOOKUP_ROLES
                and a.node.start_byte < first.start_byte
            ),
            None,
        )
        store = next(
            (
                a
                for a in accesses
                if a.name == name and a.role == "write" and a.node.end_byte >= first.end_byte
            ),
            None,
        )
        if lookup is None or store is None:
            continue
        evidence = [
            ctx.evidence(f"lookup in {short_text(name)} before self-call", lookup.node),
            ctx.evidence(f"self-call to {short_text(ctx.symbol.name)}", first),
            ctx.evidence(f"store in {short_text(name)} after self-call", store.node),
        ]
        yield PatternMatch(
            _MEMOIZATION, tuple(evidence), len(evidence), table_key="memoization (manual)"
        )
        return


@register_rule("Recursion & Dynamic Programming")
def direct_recursion_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _direct_recursion_matches(ctx)


@register_rule("Recursion & Dynamic Programming")
def decorator_memoization_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _decorator_memo_matches(ctx)


@register_rule("Recursion & Dynamic Programming")
def manual_memoization_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _manual_memo_matches(ctx)


# ---------------------------------------------------------------------------
# Heaps & Priority Queues rules (Req 5.13, 5.14)
# ---------------------------------------------------------------------------
_HEAPQ_PUSH = frozenset({"heappush"})
_HEAPQ_POP = frozenset({"heappop"})
_HEAPQ_OPERATIONS = _HEAPQ_PUSH | _HEAPQ_POP | {"heappushpop", "heapreplace"}
_HEAPQ_HEAPIFY = "heapify"
_PQ_CLASSES = frozenset(
    {"PriorityQueue", "MinHeap", "MaxHeap", "MinPriorityQueue", "MaxPriorityQueue"}
)
_PQ_PUT_METHODS = frozenset({"put", "push", "enqueue", "add", "offer", "insert"})
_PQ_GET_METHODS = frozenset({"get", "pop", "dequeue", "poll", "peek", "extractMin", "extractMax"})


def _heapq_function(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """``fn`` for ``heapq.<fn>(...)``, or a bare ``fn(...)`` when ``heapq`` is imported."""
    callee = callee_text(ctx, node)
    if callee is None:
        return None
    if callee.startswith("heapq."):
        return callee.removeprefix("heapq.")
    return callee if "heapq" in ctx.imports else None


def _heapq_calls(ctx: RuleContext) -> Iterator[tuple[str, tree_sitter.Node]]:
    if ctx.language is not Language.PYTHON:
        return
    for node in ctx.body_nodes:
        function = _heapq_function(ctx, node)
        if function is not None:
            yield function, node


def _first_call(
    calls: list[tuple[str, tree_sitter.Node]], names: Iterable[str]
) -> tree_sitter.Node | None:
    wanted = frozenset(names)
    return next((node for function, node in calls if function in wanted), None)


def _heapq_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    calls = list(_heapq_calls(ctx))
    required = _first_call(calls, _HEAPQ_OPERATIONS)
    if required is None:
        return
    push, pop = _first_call(calls, _HEAPQ_PUSH), _first_call(calls, _HEAPQ_POP)
    heapify = _first_call(calls, [_HEAPQ_HEAPIFY])
    kinds = 1 + (push is not None and pop is not None) + (heapify is not None)
    nodes = {n.id: n for n in (required, push, pop, heapify) if n is not None}
    evidence = [
        ctx.evidence(f"heapq call {short_text(ctx.text(node.children[0]))}", node)
        for node in nodes.values()
    ]
    yield PatternMatch("heapq operations", tuple(evidence), kinds)


def _pq_class(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """Class name when ``node`` creates a priority queue, else None."""
    if ctx.language is Language.PYTHON:
        callee = callee_text(ctx, node)
        if callee == "queue.PriorityQueue" or (
            callee == "PriorityQueue" and "queue" in ctx.imports
        ):
            return "PriorityQueue"
        return None
    if ctx.language is Language.JAVA:
        name = _java_type_name(node, ctx) if node.type == "object_creation_expression" else None
    else:
        constructor = node.child_by_field_name("constructor")
        is_new = node.type == "new_expression" and constructor is not None
        name = ctx.text(constructor) if is_new and constructor is not None else None
    return name if name in _PQ_CLASSES else None


def _is_pq_creation(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    return _pq_class(ctx, node) is not None


def _pq_operations(ctx: RuleContext, name: str) -> tuple[tree_sitter.Node | None, ...]:
    """First put-like and first get-like call on ``name`` (either may be None)."""
    put = get = None
    for node in ctx.body_nodes:
        call = _method_call(ctx, node)
        if call is None or call[0] != name:
            continue
        if put is None and call[1] in _PQ_PUT_METHODS:
            put = node
        elif get is None and call[1] in _PQ_GET_METHODS:
            get = node
    return put, get


def _priority_queue_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    created = collections(ctx, _is_pq_creation)
    for name, creation in sorted(created.items(), key=lambda item: item[1].start_byte):
        put, get = _pq_operations(ctx, name)
        if put is None and get is None:
            continue
        label = short_text(name)
        evidence = [ctx.evidence(f"{label} created as {_pq_class(ctx, creation)}", creation)]
        if put is not None:
            evidence.append(ctx.evidence(f"put-like call on {label}", put))
        if get is not None:
            evidence.append(ctx.evidence(f"get-like call on {label}", get))
        yield PatternMatch("priority queue usage", tuple(evidence), len(evidence))
        return


@register_rule("Heaps & Priority Queues")
def heapq_operations_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _heapq_matches(ctx)


@register_rule("Heaps & Priority Queues")
def priority_queue_usage_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _priority_queue_matches(ctx)


# ---------------------------------------------------------------------------
# Sorting & Binary Search rules (Req 5.15, 5.16, 5.19, 5.20, 5.23)
# ---------------------------------------------------------------------------
_BISECT_FUNCTIONS = frozenset(
    {"bisect", "bisect_left", "bisect_right", "insort", "insort_left", "insort_right"}
)
_COMPARISON_OPERATORS = frozenset({"<", "<=", ">", ">=", "==", "!=", "===", "!=="})
_COMPARE_METHODS = frozenset({"compareTo", "compare", "compareToIgnoreCase"})
_SHIFT_OPERATORS = frozenset({">>", ">>>"})
_FLOOR_CALLEES = frozenset({"Math.floor", "Math.trunc"})
_ES_FUNCTION_TYPES = frozenset({"arrow_function", "function_expression", "function"})
_JAVA_FUNCTION_TYPES = frozenset({"lambda_expression", "method_reference"})
_FUNCTION_DEFINITIONS = frozenset(
    {"function_definition", "function_declaration", "method_declaration"}
)


def _bisect_function(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """``fn`` for ``bisect.<fn>(...)``, or a bare ``fn(...)`` when ``bisect`` is imported."""
    callee = callee_text(ctx, node)
    if callee is None:
        return None
    function = callee.removeprefix("bisect.") if callee.startswith("bisect.") else None
    if function is None and "bisect" in ctx.imports and "." not in callee:
        function = callee
    return function if function in _BISECT_FUNCTIONS else None


def _bisect_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    if ctx.language is not Language.PYTHON:
        return
    calls = [(f, n) for n in ctx.body_nodes if (f := _bisect_function(ctx, n)) is not None]
    if not calls:
        return
    evidence = [ctx.evidence(f"bisect call {short_text(f)}", node) for f, node in calls]
    sites = {(node.start_byte, node.end_byte) for _, node in calls}
    yield PatternMatch("bisect usage", tuple(evidence), 1 + (len(sites) > 1))


def _strip_parentheses(node: tree_sitter.Node) -> tree_sitter.Node:
    while node.type == "parenthesized_expression" and node.named_children:
        node = node.named_children[0]
    return node


def _operator(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    if node.type not in _BINARY_TYPES:
        return None
    operator = node.child_by_field_name("operator")
    return ctx.text(operator) if operator is not None else None


def _operands(
    node: tree_sitter.Node,
) -> tuple[tree_sitter.Node, tree_sitter.Node] | None:
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    if left is None or right is None:
        return None
    return _strip_parentheses(left), _strip_parentheses(right)


def _unwrap_floor(ctx: RuleContext, node: tree_sitter.Node) -> tuple[tree_sitter.Node, bool]:
    """Strip parentheses and one ``Math.floor``/``Math.trunc`` call (TS/JS only)."""
    node = _strip_parentheses(node)
    if ctx.language in (Language.PYTHON, Language.JAVA) or callee_text(ctx, node) not in (
        _FLOOR_CALLEES
    ):
        return node, False
    arguments = node.child_by_field_name("arguments")
    if arguments is None or len(arguments.named_children) != 1:
        return node, False
    return _strip_parentheses(arguments.named_children[0]), True


def _halved(ctx: RuleContext, node: tree_sitter.Node, floored: bool) -> tree_sitter.Node | None:
    """The numerator when ``node`` halves it by integer division or a one-bit shift."""
    operator = _operator(ctx, node)
    operands = _operands(node) if operator is not None else None
    if operator is None or operands is None:
        return None
    numerator, divisor = operands
    if operator in _SHIFT_OPERATORS:
        return numerator if ctx.text(divisor) == "1" else None
    integer_division = {
        Language.PYTHON: operator == "//",
        Language.JAVA: operator == "/",
    }.get(ctx.language, operator == "/" and floored)
    return numerator if integer_division and ctx.text(divisor) == "2" else None


def _identifier_pair(
    ctx: RuleContext, node: tree_sitter.Node, operator: str
) -> tuple[str, str] | None:
    if _operator(ctx, node) != operator:
        return None
    operands = _operands(node)
    if operands is None or any(side.type != "identifier" for side in operands):
        return None
    return ctx.text(operands[0]), ctx.text(operands[1])


def _midpoint_bounds(ctx: RuleContext, value: tree_sitter.Node) -> tuple[str, str] | None:
    """Boundary names ``(a, b)`` when ``value`` is a midpoint of two identifiers."""
    value, floored = _unwrap_floor(ctx, value)
    half = _halved(ctx, value, floored)
    if half is not None:
        return _identifier_pair(ctx, _strip_parentheses(half), "+")
    if _operator(ctx, value) != "+":
        return None
    operands = _operands(value)
    if operands is None or operands[0].type != "identifier":
        return None
    offset, offset_floored = _unwrap_floor(ctx, operands[1])
    half = _halved(ctx, offset, floored or offset_floored)
    pair = _identifier_pair(ctx, _strip_parentheses(half), "-") if half is not None else None
    low = ctx.text(operands[0])
    return (low, pair[0]) if pair is not None and pair[1] == low else None


def _assignment_parts(
    ctx: RuleContext, node: tree_sitter.Node
) -> tuple[tree_sitter.Node, tree_sitter.Node] | None:
    """``(target, value)`` of an assignment or declarator with a value."""
    if node.type == ctx.profile.binding_type:
        target = node.child_by_field_name(ctx.profile.binding_name_field)
        value = node.child_by_field_name(ctx.profile.binding_value_field)
    elif node.type in {"assignment", "assignment_expression"}:
        target, value = node.child_by_field_name("left"), node.child_by_field_name("right")
    else:
        return None
    if target is None or value is None or target.type != "identifier":
        return None
    return target, value


def _is_comparison(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    if node.type == "comparison_operator":
        return True
    if _operator(ctx, node) in _COMPARISON_OPERATORS:
        return True
    method = node.child_by_field_name("name") if node.type == ctx.profile.call_type else None
    return method is not None and ctx.text(method) in _COMPARE_METHODS


def _has_comparison(ctx: RuleContext, node: tree_sitter.Node | None) -> bool:
    return node is not None and any(_is_comparison(ctx, n) for n in _descendants(node))


def _condition_of(ctx: RuleContext, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """The condition guarding a conditional construct, or None."""
    if node.type == "else_clause" and node.parent is not None:
        node = node.parent
    if node.type == "conditional_expression" and ctx.language is Language.PYTHON:
        return node.named_children[1] if len(node.named_children) == 3 else None
    return node.child_by_field_name("condition")


def _narrows_under_comparison(
    ctx: RuleContext, node: tree_sitter.Node, loop: tree_sitter.Node
) -> bool:
    """``node`` sits under a conditional inside ``loop`` whose condition compares."""
    for ancestor in _ancestors(ctx, node):
        if ancestor.id == loop.id:
            return False
        if ancestor.type in _CONDITIONAL_TYPES and _has_comparison(
            ctx, _condition_of(ctx, ancestor)
        ):
            return True
    return False


def _boundary_narrowing(
    ctx: RuleContext, loop: tree_sitter.Node, bounds: tuple[str, str]
) -> tree_sitter.Node | None:
    for node in ctx.body_nodes:
        parts = _assignment_parts(ctx, node)
        if parts is None or ctx.text(parts[0]) not in bounds or not _within(node, loop):
            continue
        if _narrows_under_comparison(ctx, node, loop):
            return node
    return None


def _loop_compares_bounds(
    ctx: RuleContext, loop: tree_sitter.Node, bounds: tuple[str, str]
) -> bool:
    condition = loop.child_by_field_name("condition")
    if condition is None:
        return False
    for node in _descendants(condition):
        if _is_comparison(ctx, node) and set(bounds) <= _identifiers(node, ctx):
            return True
    return False


def _binary_search_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    for node in ctx.body_nodes:
        parts = _assignment_parts(ctx, node)
        loop = enclosing_loop(ctx, node) if parts is not None else None
        bounds = _midpoint_bounds(ctx, parts[1]) if parts is not None else None
        if loop is None or bounds is None:
            continue
        narrowing = _boundary_narrowing(ctx, loop, bounds)
        if narrowing is None:
            continue
        low, high = (short_text(name) for name in bounds)
        evidence = [
            ctx.evidence(f"midpoint of {low} and {high}", node),
            ctx.evidence("boundary narrowed under comparison", narrowing),
        ]
        if _loop_compares_bounds(ctx, loop, bounds):
            evidence.append(ctx.evidence(f"loop condition compares {low} and {high}", loop))
        yield PatternMatch("binary search", tuple(evidence), len(evidence))
        return


def _sort_arguments(
    ctx: RuleContext, node: tree_sitter.Node
) -> tuple[str, tree_sitter.Node] | None:
    """``(label, arguments)`` when ``node`` is ``sorted(...)`` or a ``.sort(...)`` call."""
    if node.type != ctx.profile.call_type:
        return None
    arguments = node.child_by_field_name("arguments")
    if arguments is None:
        return None
    if ctx.language is Language.JAVA:
        name = node.child_by_field_name("name")
        return ("sort", arguments) if name is not None and ctx.text(name) == "sort" else None
    function = node.child_by_field_name("function")
    if function is None:
        return None
    if function.type == "identifier":
        is_sort = ctx.language is Language.PYTHON and ctx.text(function) == "sorted"
        return ("sorted", arguments) if is_sort else None
    member = function.child_by_field_name(
        "attribute" if ctx.language is Language.PYTHON else "property"
    )
    if function.type in {"attribute", "member_expression"} and member is not None:
        return ("sort", arguments) if ctx.text(member) == "sort" else None
    return None


def _comparator_chain(ctx: RuleContext, node: tree_sitter.Node) -> bool:
    """``Comparator.comparing...(...)``, possibly followed by chained calls."""
    while node.type == "method_invocation":
        callee = callee_text(ctx, node)
        if callee is not None:
            return callee.startswith("Comparator.comparing")
        target = node.child_by_field_name("object")
        if target is None:
            return False
        node = target
    return False


def _nested_functions(ctx: RuleContext) -> frozenset[str]:
    """Names of functions defined inside the Symbol (nested declarations included)."""
    names: set[str] = set()
    for node in _descendants(ctx.node):
        name = node.child_by_field_name("name")
        if node.id != ctx.node.id and node.type in _FUNCTION_DEFINITIONS and name is not None:
            names.add(ctx.text(name))
    return frozenset(names)


def _python_key_function(
    ctx: RuleContext, arguments: tree_sitter.Node
) -> tuple[tree_sitter.Node, bool] | None:
    """``(key value, optional-kind present)`` for a ``key=`` keyword argument."""
    for argument in arguments.named_children:
        name = argument.child_by_field_name("name")
        value = argument.child_by_field_name("value")
        if argument.type != "keyword_argument" or name is None or value is None:
            continue
        if ctx.text(name) != "key":
            continue
        if value.type == "lambda":
            return value, False
        if value.type == "identifier":
            return value, ctx.text(value) in _nested_functions(ctx)
        callee = callee_text(ctx, value)
        if callee in {"cmp_to_key", "functools.cmp_to_key"}:
            return value, True
    return None


def _other_key_function(
    ctx: RuleContext, arguments: tree_sitter.Node
) -> tuple[tree_sitter.Node, bool] | None:
    function_types = _JAVA_FUNCTION_TYPES if ctx.language is Language.JAVA else _ES_FUNCTION_TYPES
    for argument in arguments.named_children:
        if argument.type in function_types:
            return argument, False
        if ctx.language is Language.JAVA and _comparator_chain(ctx, argument):
            return argument, False
    return None


def _custom_sort_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    for node in ctx.body_nodes:
        call = _sort_arguments(ctx, node)
        if call is None:
            continue
        label, arguments = call
        finder = _python_key_function if ctx.language is Language.PYTHON else _other_key_function
        key = finder(ctx, arguments)
        if key is None:
            continue
        evidence = [
            ctx.evidence(f"{label} call", node),
            ctx.evidence(f"key function {short_text(ctx.text(key[0]))}", key[0]),
        ]
        yield PatternMatch("custom sort key", tuple(evidence), 2 + key[1])
        return


@register_rule("Sorting & Binary Search")
def bisect_usage_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _bisect_matches(ctx)


@register_rule("Sorting & Binary Search")
def binary_search_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _binary_search_matches(ctx)


@register_rule("Sorting & Binary Search")
def custom_sort_key_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _custom_sort_matches(ctx)


# ---------------------------------------------------------------------------
# Sliding Window / Two Pointers rules (Req 5.17, 5.18, 5.19, 5.20, 5.23)
# ---------------------------------------------------------------------------
_POINTER_LOOPS = frozenset({"for_statement", "while_statement", "do_statement"})
_AUGMENTED_TYPES = frozenset({"augmented_assignment", "augmented_assignment_expression"})
_ASSIGNMENT_TYPES = frozenset({"assignment", "assignment_expression"})
_STEP_OPERATORS = frozenset({"+=", "-="})
_INDEX_METHODS = frozenset({"charAt", "get"})
_INDEX_NODES = {
    "subscript": ("value", "subscript"),
    "subscript_expression": ("object", "index"),
    "array_access": ("array", "index"),
}
_LOOP_INIT_FIELDS = ("initializer", "init")


@dataclass(frozen=True)
class _Pointer:
    """A candidate pointer variable: its normalized initial value and where it is set."""

    name: str
    value: str
    node: tree_sitter.Node


def _squeeze(text: str) -> str:
    return "".join(text.split())


def _plain_assignment(node: tree_sitter.Node) -> bool:
    """A plain ``=`` assignment (not ``+=`` and friends) of an identifier."""
    if node.type in _ASSIGNMENT_TYPES and len(node.children) > 1:
        return node.children[1].type == "="
    return node.type == "variable_declarator"


def _bindings(ctx: RuleContext, node: tree_sitter.Node) -> list[tuple[str, tree_sitter.Node]]:
    """``(name, value)`` pairs bound by an assignment or declarator, tuple targets included."""
    if not _plain_assignment(node) and node.type != ctx.profile.binding_type:
        return []
    parts = _assignment_parts(ctx, node)
    if parts is not None:
        return [(ctx.text(parts[0]), parts[1])]
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    if left is None or right is None or left.type != "pattern_list":
        return []
    names, values = left.named_children, right.named_children
    if right.type != "expression_list" or len(names) != len(values):
        return []
    return [(ctx.text(n), v) for n, v in zip(names, values, strict=True) if n.type == "identifier"]


def _range_start(ctx: RuleContext, loop: tree_sitter.Node) -> _Pointer | None:
    """Python ``for i in range(...)`` counter, with its first value."""
    target, iterable = loop.child_by_field_name("left"), loop.child_by_field_name("right")
    if target is None or iterable is None or target.type != "identifier":
        return None
    if callee_text(ctx, iterable) != "range":
        return None
    arguments = iterable.child_by_field_name("arguments")
    if arguments is None or not arguments.named_children:
        return None
    start = "0" if len(arguments.named_children) == 1 else ctx.text(arguments.named_children[0])
    return _Pointer(ctx.text(target), _squeeze(start), target)


def _initializations(ctx: RuleContext, loop: tree_sitter.Node) -> list[_Pointer]:
    """Values assigned before ``loop`` or in its header, in source order (latest wins)."""
    node = loop
    header = [node.child_by_field_name(field) for field in _LOOP_INIT_FIELDS]
    regions = [h for h in header if h is not None]
    found: dict[str, _Pointer] = {}
    for candidate in ctx.body_nodes:
        before = candidate.end_byte <= node.start_byte
        if not before and not any(_within(candidate, region) for region in regions):
            continue
        for name, value in _bindings(ctx, candidate):
            found[name] = _Pointer(name, _squeeze(ctx.text(value)), candidate)
    if ctx.language is Language.PYTHON:
        counter = _range_start(ctx, node)
        if counter is not None:
            found[counter.name] = counter
    return list(found.values())


def _last_index(value: str) -> bool:
    """``len(x) - 1``, ``n - 1``, ``x.length - 1``, ``x.size() - 1`` (whitespace removed)."""
    head, _, tail = value.rpartition("-")
    return tail == "1" and bool(head)


def _related(first: _Pointer, second: _Pointer) -> str | None:
    """``"opposite ends"`` or ``"shared start"`` when the initial values qualify."""
    if first.value == second.value:
        return "shared start"
    ends = {first.value == "0", second.value == "0"}
    if ends == {True, False} and _last_index(first.value if first.value != "0" else second.value):
        return "opposite ends"
    return None


def _step_target(ctx: RuleContext, node: tree_sitter.Node) -> str | None:
    """Name stepped by exactly one unit when ``node`` is ``a++``, ``a -= 1``, ``a = a + 1``."""
    if node.type == "update_expression":
        target = node.child_by_field_name("argument") or next(iter(node.named_children), None)
        return ctx.text(target) if target is not None and target.type == "identifier" else None
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    if left is None or right is None or left.type != "identifier":
        return None
    name = ctx.text(left)
    if node.type in _AUGMENTED_TYPES or not _plain_assignment(node):
        operator = node.child_by_field_name("operator")
        text = ctx.text(operator) if operator is not None else ""
        return name if text in _STEP_OPERATORS and ctx.text(right) == "1" else None
    operands = _operands(right) if _operator(ctx, right) in {"+", "-"} else None
    if operands is None:
        return None
    pair = {ctx.text(operands[0]), ctx.text(operands[1])}
    return name if pair == {name, "1"} else None


def _moves(ctx: RuleContext, loop: tree_sitter.Node) -> dict[str, list[tree_sitter.Node]]:
    """Unit steps of a variable inside ``loop`` that happen under a conditional."""
    moves: dict[str, list[tree_sitter.Node]] = {}
    for node in ctx.body_nodes:
        if not _within(node, loop) or not conditional(ctx, node, loop):
            continue
        name = _step_target(ctx, node)
        if name is not None:
            moves.setdefault(name, []).append(node)
    return moves


def _index_use(ctx: RuleContext, node: tree_sitter.Node) -> tuple[str, set[str]] | None:
    """``(sequence, names in the index)`` for ``seq[idx]``, ``charAt(idx)`` or ``get(idx)``."""
    spec = _INDEX_NODES.get(node.type)
    if spec is not None:
        base, index = node.child_by_field_name(spec[0]), node.child_by_field_name(spec[1])
        if base is None or index is None or base.type != "identifier":
            return None
        return ctx.text(base), _identifiers(index, ctx)
    call = _method_call(ctx, node)
    if call is None or call[1] not in _INDEX_METHODS or call[2] is None:
        return None
    return call[0], _identifiers(call[2], ctx)


def _indexed_sequence(
    ctx: RuleContext, loop: tree_sitter.Node, names: tuple[str, str]
) -> tuple[str, tree_sitter.Node] | None:
    """A sequence indexed by both names inside ``loop``, with the first indexing node."""
    uses: dict[str, dict[str, tree_sitter.Node]] = {}
    for node in ctx.body_nodes:
        use = _index_use(ctx, node) if _within(node, loop) else None
        if use is None:
            continue
        for name in names:
            if name in use[1]:
                uses.setdefault(use[0], {}).setdefault(name, node)
    for sequence, by_name in uses.items():
        if set(names) <= set(by_name):
            return sequence, min(by_name.values(), key=lambda n: n.start_byte)
    return None


def _pointer_match(
    ctx: RuleContext, loop: tree_sitter.Node, pair: tuple[_Pointer, _Pointer]
) -> PatternMatch | None:
    first, second = pair
    relation = _related(first, second)
    if relation is None:
        return None
    moves = _moves(ctx, loop)
    moved = next((name for name in (first.name, second.name) if name in moves), None)
    indexed = _indexed_sequence(ctx, loop, (first.name, second.name))
    if moved is None or indexed is None:
        return None
    a, b = short_text(first.name), short_text(second.name)
    evidence = [
        ctx.evidence(f"pointers {a} and {b} at {relation}", first.node),
        ctx.evidence(f"conditional move of {short_text(moved)}", moves[moved][0]),
        ctx.evidence(f"{a} and {b} index {short_text(indexed[0])}", indexed[1]),
    ]
    if _loop_compares_bounds(ctx, loop, (first.name, second.name)):
        evidence.append(ctx.evidence(f"loop condition compares {a} and {b}", loop))
    return PatternMatch("two pointers", tuple(evidence), len(evidence))


def _two_pointer_matches(ctx: RuleContext) -> Iterator[PatternMatch]:
    best: PatternMatch | None = None
    for loop in ctx.body_nodes:
        if loop.type not in _POINTER_LOOPS:
            continue
        pointers = _initializations(ctx, loop)
        for index, first in enumerate(pointers):
            for second in pointers[index + 1 :]:
                found = _pointer_match(ctx, loop, (first, second))
                if found is not None and (best is None or found.k > best.k):
                    best = found
    if best is not None:
        yield best


@register_rule("Sliding Window / Two Pointers")
def two_pointers_rule(ctx: RuleContext) -> Iterable[PatternMatch]:
    return _two_pointer_matches(ctx)
