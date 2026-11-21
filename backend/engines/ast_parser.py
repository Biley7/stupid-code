"""Tree-sitter parser for the AST and graph engine (Spec #01).

This module holds the mechanics shared by every language: extension mapping,
decoding, cached parsers, line counting, parse-error collection, the
normalized AST hash, and a language-neutral symbol walk.

Language specifics live in ``LanguageExtractor`` implementations registered in
``_EXTRACTORS``. The shared walk owns scope, qualnames, collision suffixes,
``method`` versus ``function``, line ranges, hashes, and ``raw_calls``
collection. An extractor only answers four syntactic questions: which node is a
declaration (``match_declaration``), what is the callee text of a call node
(``callee_text``), and which import and export strings the file has
(``collect_imports``, ``collect_exports``). Analyzed source is only parsed,
never executed or imported.
"""

import hashlib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

import tree_sitter
from tree_sitter_language_pack import get_parser

from backend.domain.models import FileAnalysis, Language, SymbolKind, SymbolNode

__all__ = [
    "Declaration",
    "LanguageExtractor",
    "ParsedFile",
    "ParserError",
    "ParserInternalError",
    "UnsupportedLanguageError",
    "compute_normalized_ast_hash",
    "language_for_path",
    "parse_file",
    "parse_source",
]

_EXTENSION_LANGUAGES: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".js": Language.JAVASCRIPT,
    ".tsx": Language.TSX,
    ".java": Language.JAVA,
}

_COMMENT_TYPES = frozenset({"comment", "line_comment", "block_comment"})
_LINE_SPLIT = re.compile(r"\r\n|\n|\r")

_parsers: dict[Language, tree_sitter.Parser] = {}


class ParserError(Exception):
    """Base class for parser errors."""


class UnsupportedLanguageError(ParserError):
    def __init__(self, extension: str) -> None:
        super().__init__(f"unsupported file extension {extension!r}")
        self.extension = extension


class ParserInternalError(ParserError):
    """Grammar loading or Tree-sitter failed; never a syntax error in the analyzed file."""


@dataclass(frozen=True)
class ParsedFile:
    analysis: FileAnalysis
    source: bytes
    root: tree_sitter.Node
    symbol_nodes: dict[str, tree_sitter.Node] = field(default_factory=dict)


def language_for_path(file_path: str) -> Language:
    extension = os.path.splitext(file_path)[1].lower()
    language = _EXTENSION_LANGUAGES.get(extension)
    if language is None:
        raise UnsupportedLanguageError(extension)
    return language


def _get_parser(language: Language) -> tree_sitter.Parser:
    parser = _parsers.get(language)
    if parser is None:
        parser = get_parser(language.value)
        _parsers[language] = parser
    return parser


def compute_normalized_ast_hash(node: tree_sitter.Node) -> str:
    """SHA-256 of a prefix-free, comment- and whitespace-free pre-order serialization."""
    out = bytearray()
    stack: list[tree_sitter.Node | bytes] = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, bytes):
            out += item
            continue
        if item.type in _COMMENT_TYPES:
            continue
        node_type = item.type + ("!" if item.is_missing else "")
        type_bytes = node_type.encode("utf-8")
        if item.child_count == 0:
            text = item.text or b""
            out += b"(" + type_bytes + b":" + str(len(text)).encode("ascii") + b":" + text + b")"
            continue
        out += b"(" + type_bytes
        stack.append(b")")
        stack.extend(reversed(item.children))
    return hashlib.sha256(bytes(out)).hexdigest()


def _count_loc(text: str) -> int:
    return sum(1 for line in _LINE_SPLIT.split(text) if line.strip())


def _collect_parse_errors(root: tree_sitter.Node, line_count: int) -> list[str]:
    errors: list[str] = []
    stack = [root]
    while stack:
        node = stack.pop()
        is_error = node.type == "ERROR"
        if is_error or node.is_missing:
            line = min(max(node.start_point.row + 1, 1), line_count)
            if is_error:
                errors.append(f"line {line}: unexpected syntax")
            else:
                errors.append(f"line {line}: missing {node.type}")
        if is_error:
            continue
        stack.extend(reversed(node.children))
    return errors


@dataclass(frozen=True)
class Declaration:
    """One Symbol declaration recognised by a ``LanguageExtractor``.

    ``kind`` is the language-level kind. The shared walk turns ``FUNCTION`` into
    ``METHOD`` when the nearest enclosing Symbol is a class-like scope.
    """

    node: tree_sitter.Node  # declaration node: line range and ast_hash (includes decorators)
    name: str
    kind: SymbolKind
    signature: str
    decorators: tuple[str, ...] = ()
    is_async: bool = False
    body: tree_sitter.Node | None = None  # searched for calls when ``collects_calls``
    opens_class_scope: bool = False  # functions declared directly inside become methods
    collects_calls: bool = False  # True for functions and methods
    start_node: tree_sitter.Node | None = None  # first decorator when outside ``node``


class LanguageExtractor(Protocol):
    def match_declaration(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        """Return a Declaration if ``node`` is the node to enter for a Symbol, else None."""
        ...

    def callee_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        """Return the callee text if ``node`` is a call with a simple callee, else None."""
        ...

    def collect_imports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]: ...

    def collect_exports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]: ...


def node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def signature_between(start: tree_sitter.Node, body: tree_sitter.Node | None, source: bytes) -> str:
    """Declaration text from ``start`` up to (excluding) ``body``, whitespace collapsed."""
    end = body.start_byte if body is not None else start.end_byte
    return collapse_whitespace(source[start.start_byte : end].decode("utf-8", errors="replace"))


def _has_direct_child(node: tree_sitter.Node, node_type: str) -> bool:
    return any(child.type == node_type for child in node.children)


class _PythonExtractor:
    def match_declaration(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        if node.type not in ("function_definition", "class_definition"):
            return None
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.start_byte == name_node.end_byte:
            return None
        body = node.child_by_field_name("body")
        parent = node.parent
        outer = parent if parent is not None and parent.type == "decorated_definition" else node
        decorators = tuple(
            node_text(child, source) for child in outer.children if child.type == "decorator"
        )
        signature = signature_between(node, body, source).removesuffix(":").rstrip()
        is_class = node.type == "class_definition"
        return Declaration(
            node=outer,
            name=node_text(name_node, source),
            kind=SymbolKind.CLASS if is_class else SymbolKind.FUNCTION,
            signature=signature,
            decorators=decorators,
            is_async=not is_class and _has_direct_child(node, "async"),
            body=body,
            opens_class_scope=is_class,
            collects_calls=not is_class,
        )

    def callee_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        if node.type != "call":
            return None
        function = node.child_by_field_name("function")
        current = function
        while current is not None and current.type == "attribute":
            current = current.child_by_field_name("object")
        if function is None or current is None or current.type != "identifier":
            return None
        return collapse_whitespace(node_text(function, source))

    def collect_imports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]:
        found: list[str] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == "import_statement":
                for name in node.children_by_field_name("name"):
                    target = (
                        name.child_by_field_name("name") if name.type == "aliased_import" else name
                    )
                    if target is not None:
                        found.append(collapse_whitespace(node_text(target, source)))
                continue
            if node.type == "import_from_statement":
                module = node.child_by_field_name("module_name")
                if module is not None:
                    found.append("".join(node_text(module, source).split()))
                continue
            stack.extend(reversed(node.children))
        return found

    def collect_exports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]:
        found: list[str] = []
        for statement in root.children:
            node = (
                statement.children[0]
                if statement.type == "expression_statement" and statement.children
                else statement
            )
            if node.type not in ("assignment", "augmented_assignment"):
                continue
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left is None or right is None or right.type != "list":
                continue
            if left.type != "identifier" or node_text(left, source) != "__all__":
                continue
            for item in right.children:
                value = self._plain_string(item, source)
                if value is not None:
                    found.append(value)
        return found

    @staticmethod
    def _plain_string(node: tree_sitter.Node, source: bytes) -> str | None:
        if node.type != "string" or any(c.type == "interpolation" for c in node.children):
            return None
        start = next((c for c in node.children if c.type == "string_start"), None)
        end = next((c for c in node.children if c.type == "string_end"), None)
        if start is None or end is None or start.end_byte == end.start_byte:
            return None
        return source[start.end_byte : end.start_byte].decode("utf-8", errors="replace")


_JSX_TYPES = frozenset({"jsx_element", "jsx_self_closing_element", "jsx_fragment"})
_FUNCTION_VALUE_TYPES = frozenset({"arrow_function", "function_expression"})
_CALLEE_PROPERTY_TYPES = frozenset({"property_identifier", "private_property_identifier"})
_UPPERCASE_START = re.compile(r"[A-Z]")


def _contains_jsx(node: tree_sitter.Node) -> bool:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in _JSX_TYPES:
            return True
        stack.extend(current.children)
    return False


def _statement_source(node: tree_sitter.Node, source: bytes) -> str | None:
    """Module specifier of an import or re-export statement, without quotes."""
    module = node.child_by_field_name("source")
    if module is None or module.type != "string":
        return None
    text = node_text(module, source)
    return text[1:-1] if len(text) > 2 else None


class _EcmaScriptExtractor:
    """TypeScript, JavaScript, and TSX share node names; flags cover the differences.

    Probed against the grammars: decorators sit on ``export_statement`` (exported
    class), on the class itself, as preceding siblings in a TypeScript
    ``class_body``, or as children of a JavaScript ``method_definition``. The
    JavaScript ``=>`` token reports a zero-width range at its end, so arrow
    signatures end at the token's ``end_byte``, which is correct for both grammars.
    """

    def __init__(self, *, interfaces: bool, components: bool) -> None:
        self._interfaces = interfaces
        self._components = components

    def match_declaration(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        node_type = node.type
        if node_type in ("function_declaration", "generator_function_declaration"):
            return self._function(node, source)
        if node_type == "variable_declarator":
            return self._declarator(node, source)
        if node_type in ("method_definition", "abstract_method_signature"):
            return self._method(node, source)
        if node_type in ("class_declaration", "abstract_class_declaration"):
            return self._class(node, source)
        if node_type == "interface_declaration" and self._interfaces:
            return self._interface(node, source)
        return None

    @staticmethod
    def _name(node: tree_sitter.Node, source: bytes) -> str | None:
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.start_byte == name_node.end_byte:
            return None
        return node_text(name_node, source)

    def _function_kind(self, name: str, node: tree_sitter.Node) -> SymbolKind:
        if self._components and _UPPERCASE_START.match(name) and _contains_jsx(node):
            return SymbolKind.COMPONENT
        return SymbolKind.FUNCTION

    def _function(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        name = self._name(node, source)
        if name is None:
            return None
        body = node.child_by_field_name("body")
        return Declaration(
            node=node,
            name=name,
            kind=self._function_kind(name, node),
            signature=signature_between(node, body, source),
            is_async=_has_direct_child(node, "async"),
            body=body,
            collects_calls=True,
        )

    def _declarator(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        name_node = node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        if (
            name_node is None
            or name_node.type != "identifier"
            or value is None
            or value.type not in _FUNCTION_VALUE_TYPES
        ):
            return None
        parent = node.parent
        declarators = (
            [c for c in parent.children if c.type == "variable_declarator"] if parent else []
        )
        declaration = parent if parent is not None and len(declarators) == 1 else node
        body = value.child_by_field_name("body")
        if value.type == "arrow_function":
            arrow = next((c for c in value.children if c.type == "=>"), None)
            end = arrow.end_byte if arrow is not None else value.end_byte
            text = source[declaration.start_byte : end]
            signature = collapse_whitespace(text.decode("utf-8", errors="replace"))
        else:
            signature = signature_between(declaration, body, source)
        name = node_text(name_node, source)
        return Declaration(
            node=declaration,
            name=name,
            kind=self._function_kind(name, node),
            signature=signature,
            is_async=_has_direct_child(value, "async"),
            body=body,
            collects_calls=True,
        )

    @staticmethod
    def _own_decorators(node: tree_sitter.Node) -> list[tree_sitter.Node]:
        return [child for child in node.children if child.type == "decorator"]

    @staticmethod
    def _signature_start(node: tree_sitter.Node) -> tree_sitter.Node:
        return next((c for c in node.children if c.type != "decorator"), node)

    def _method(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        parent = node.parent
        if parent is None or parent.type != "class_body":
            return None
        name = self._name(node, source)
        if name is None:
            return None
        decorators = self._own_decorators(node)
        previous = node.prev_sibling
        preceding: list[tree_sitter.Node] = []
        while previous is not None and previous.type in ("decorator", "comment"):
            if previous.type == "decorator":
                preceding.append(previous)
            previous = previous.prev_sibling
        decorators = [*reversed(preceding), *decorators]
        body = node.child_by_field_name("body")
        start = self._signature_start(node)
        if body is None:
            signature = (
                collapse_whitespace(
                    source[start.start_byte : node.end_byte].decode("utf-8", errors="replace")
                )
                .removesuffix(";")
                .rstrip()
            )
        else:
            signature = signature_between(start, body, source)
        return Declaration(
            node=node,
            name=name,
            kind=SymbolKind.METHOD,
            signature=signature,
            decorators=tuple(node_text(d, source) for d in decorators),
            is_async=_has_direct_child(node, "async"),
            body=body,
            collects_calls=body is not None,
            start_node=decorators[0] if decorators else None,
        )

    def _class(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        name = self._name(node, source)
        if name is None:
            return None
        decorators = self._own_decorators(node)
        parent = node.parent
        if parent is not None and parent.type == "export_statement":
            decorators = [*self._own_decorators(parent), *decorators]
        body = node.child_by_field_name("body")
        kind = SymbolKind.CLASS
        if self._components and _UPPERCASE_START.match(name) and _contains_jsx(node):
            kind = SymbolKind.COMPONENT
        return Declaration(
            node=node,
            name=name,
            kind=kind,
            signature=signature_between(self._signature_start(node), body, source),
            decorators=tuple(node_text(d, source) for d in decorators),
            body=body,
            opens_class_scope=True,
            start_node=decorators[0] if decorators else None,
        )

    def _interface(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        name = self._name(node, source)
        if name is None:
            return None
        return Declaration(
            node=node,
            name=name,
            kind=SymbolKind.INTERFACE,
            signature=signature_between(node, node.child_by_field_name("body"), source),
            body=node.child_by_field_name("body"),
        )

    def callee_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        if node.type != "call_expression":
            return None
        function = node.child_by_field_name("function")
        parts: list[str] = []
        while function is not None and function.type == "member_expression":
            prop = function.child_by_field_name("property")
            if prop is None or prop.type not in _CALLEE_PROPERTY_TYPES:
                return None
            parts.append(node_text(prop, source))
            function = function.child_by_field_name("object")
        if function is None:
            return None
        if function.type == "identifier" or (parts and function.type in ("this", "super")):
            parts.append(node_text(function, source))
            return ".".join(reversed(parts))
        return None

    def _walk_statements(self, root: tree_sitter.Node, types: tuple[str, ...]):
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type in types:
                yield node
                continue
            stack.extend(reversed(node.children))

    def collect_imports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]:
        found: list[str] = []
        for node in self._walk_statements(root, ("import_statement", "export_statement")):
            specifier = _statement_source(node, source)
            if specifier is not None:
                found.append(specifier)
        return found

    def collect_exports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]:
        found: list[str] = []
        for node in self._walk_statements(root, ("export_statement",)):
            for child in node.children:
                if child.type == "default":
                    found.append("default")
                elif child.type == "*":
                    found.append("*")
                elif child.type == "namespace_export":
                    names = [c for c in child.children if c.is_named]
                    if names:
                        found.append(node_text(names[-1], source))
                elif child.type == "export_clause":
                    for spec in child.children:
                        if spec.type != "export_specifier":
                            continue
                        target = spec.child_by_field_name("alias") or spec.child_by_field_name(
                            "name"
                        )
                        if target is not None:
                            found.append(node_text(target, source))
            declaration = node.child_by_field_name("declaration")
            if declaration is None:
                continue
            if declaration.type in ("lexical_declaration", "variable_declaration"):
                for declarator in declaration.children:
                    name_node = declarator.child_by_field_name("name")
                    if (
                        declarator.type == "variable_declarator"
                        and name_node is not None
                        and name_node.type == "identifier"
                    ):
                        found.append(node_text(name_node, source))
            else:
                name = self._name(declaration, source)
                if name is not None:
                    found.append(name)
        return found


_JAVA_CLASS_TYPES = frozenset({"class_declaration", "enum_declaration", "record_declaration"})
_JAVA_METHOD_TYPES = frozenset({"method_declaration", "constructor_declaration"})
_JAVA_ANNOTATION_TYPES = frozenset({"marker_annotation", "annotation"})
_JAVA_TYPE_TYPES = _JAVA_CLASS_TYPES | {"interface_declaration"}


class _JavaExtractor:
    """Java extraction.

    Probed against the grammar: annotations and keywords such as ``public`` are
    children of a ``modifiers`` node, which is the first child of the declaration
    (absent when there are no modifiers). ``this(...)`` and ``super(...)`` calls are
    ``explicit_constructor_invocation`` nodes and are not ``method_invocation``.
    The ``*`` of a wildcard import is an ``asterisk`` sibling, so import text is
    taken as the span between ``import`` and ``;``.
    """

    def match_declaration(self, node: tree_sitter.Node, source: bytes) -> Declaration | None:
        node_type = node.type
        if node_type in _JAVA_CLASS_TYPES:
            kind = SymbolKind.CLASS
        elif node_type == "interface_declaration":
            kind = SymbolKind.INTERFACE
        elif node_type in _JAVA_METHOD_TYPES:
            kind = SymbolKind.METHOD
        else:
            return None
        name_node = node.child_by_field_name("name")
        if name_node is None or name_node.start_byte == name_node.end_byte:
            return None
        body = node.child_by_field_name("body")
        is_method = kind is SymbolKind.METHOD
        return Declaration(
            node=node,
            name=node_text(name_node, source),
            kind=kind,
            signature=self._signature(node, body, source, is_method),
            decorators=tuple(node_text(a, source) for a in self._annotations(node)),
            body=body,
            opens_class_scope=not is_method,
            collects_calls=is_method and body is not None,
        )

    @staticmethod
    def _modifiers(node: tree_sitter.Node) -> tree_sitter.Node | None:
        return next((c for c in node.children if c.type == "modifiers"), None)

    def _annotations(self, node: tree_sitter.Node) -> list[tree_sitter.Node]:
        modifiers = self._modifiers(node)
        if modifiers is None:
            return []
        return [c for c in modifiers.children if c.type in _JAVA_ANNOTATION_TYPES]

    def _signature(
        self, node: tree_sitter.Node, body: tree_sitter.Node | None, source: bytes, is_method: bool
    ) -> str:
        """Declaration text without annotations, up to the body (or without ``;``)."""
        start = node.start_byte
        modifiers = self._modifiers(node)
        if modifiers is not None:
            first = next(
                (c for c in modifiers.children if c.type not in _JAVA_ANNOTATION_TYPES), None
            )
            if first is not None:
                start = first.start_byte
            else:
                after = modifiers.next_sibling
                start = after.start_byte if after is not None else modifiers.end_byte
        if body is not None:
            end = body.start_byte
        else:
            end = node.end_byte
        text = collapse_whitespace(source[start:end].decode("utf-8", errors="replace"))
        if body is None and is_method:
            text = text.removesuffix(";").rstrip()
        return text

    def callee_text(self, node: tree_sitter.Node, source: bytes) -> str | None:
        if node.type != "method_invocation":
            return None
        name = node.child_by_field_name("name")
        if name is None:
            return None
        obj = node.child_by_field_name("object")
        if obj is None:
            return node_text(name, source)
        parts: list[str] = [node_text(name, source)]
        while obj is not None and obj.type == "field_access":
            field = obj.child_by_field_name("field")
            if field is None:
                return None
            parts.append(node_text(field, source))
            obj = obj.child_by_field_name("object")
        if obj is None or obj.type not in ("identifier", "this", "super"):
            return None
        parts.append(node_text(obj, source))
        return ".".join(reversed(parts))

    def collect_imports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]:
        found: list[str] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == "import_declaration":
                inner = [c for c in node.children if c.type not in ("import", "static", ";")]
                if inner:
                    text = source[inner[0].start_byte : inner[-1].end_byte]
                    found.append("".join(text.decode("utf-8", errors="replace").split()))
                continue
            if node.type in ("program", "package_declaration"):
                stack.extend(reversed(node.children))
        return found

    def collect_exports(self, root: tree_sitter.Node, source: bytes) -> Iterable[str]:
        found: list[str] = []
        for node in root.children:
            if node.type not in _JAVA_TYPE_TYPES:
                continue
            modifiers = self._modifiers(node)
            name = node.child_by_field_name("name")
            if (
                modifiers is not None
                and name is not None
                and _has_direct_child(modifiers, "public")
                and name.end_byte > name.start_byte
            ):
                found.append(node_text(name, source))
        return found


_EXTRACTORS: dict[Language, LanguageExtractor] = {
    Language.PYTHON: _PythonExtractor(),
    Language.TYPESCRIPT: _EcmaScriptExtractor(interfaces=True, components=False),
    Language.JAVASCRIPT: _EcmaScriptExtractor(interfaces=False, components=True),
    Language.TSX: _EcmaScriptExtractor(interfaces=True, components=True),
    Language.JAVA: _JavaExtractor(),
}


def _collect_raw_calls(
    extractor: LanguageExtractor, body: tree_sitter.Node | None, source: bytes
) -> list[str]:
    """Callee texts in ``body`` in source order, first occurrences only.

    Nested Symbol declarations belong to their own Symbol and are not entered.
    """
    if body is None:
        return []
    calls: dict[str, None] = {}
    stack = [body]
    while stack:
        node = stack.pop()
        if node is not body and extractor.match_declaration(node, source) is not None:
            continue
        callee = extractor.callee_text(node, source)
        if callee is not None:
            calls.setdefault(callee)
        stack.extend(reversed(node.children))
    return list(calls)


@dataclass(frozen=True)
class _Scope:
    qualname: str | None = None
    in_class: bool = False


def _extract_symbols(
    file_path: str,
    root: tree_sitter.Node,
    source: bytes,
    extractor: LanguageExtractor,
) -> tuple[list[SymbolNode], dict[str, tree_sitter.Node]]:
    """Pre-order walk: parents are named before children, so suffixed parents prefix children."""
    symbols: list[SymbolNode] = []
    nodes: dict[str, tree_sitter.Node] = {}
    seen: set[str] = set()
    stack: list[tuple[tree_sitter.Node, _Scope]] = [(root, _Scope())]
    while stack:
        node, scope = stack.pop()
        declaration = extractor.match_declaration(node, source)
        child_scope = scope
        if declaration is not None:
            first = declaration.start_node or declaration.node
            start_line = first.start_point.row + 1
            qualname = (
                f"{scope.qualname}.{declaration.name}" if scope.qualname else declaration.name
            )
            # A declaration containing an error or missing node is not kept
            # (Req 3.33); it does not take part in collision handling. Valid
            # Symbols nested inside it are still emitted.
            erroneous = declaration.node.has_error
            if qualname in seen and not erroneous:
                qualname = f"{qualname}@{start_line}"
            child_scope = _Scope(qualname, declaration.opens_class_scope)
            # Two Symbols with the same name on one line cannot be told apart by
            # the "@<start_line>" rule; the later one is dropped.
            if not erroneous and qualname not in seen:
                seen.add(qualname)
                kind = declaration.kind
                if kind is SymbolKind.FUNCTION and scope.in_class:
                    kind = SymbolKind.METHOD
                symbol = SymbolNode(
                    id=f"{file_path}::{qualname}",
                    name=declaration.name,
                    qualname=qualname,
                    kind=kind,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=declaration.node.end_point.row + 1,
                    signature=declaration.signature,
                    ast_hash=compute_normalized_ast_hash(declaration.node),
                    decorators=list(declaration.decorators),
                    is_async=declaration.is_async,
                    raw_calls=(
                        _collect_raw_calls(extractor, declaration.body, source)
                        if declaration.collects_calls
                        else []
                    ),
                )
                symbols.append(symbol)
                nodes[symbol.id] = declaration.node
        stack.extend((child, child_scope) for child in reversed(node.children))
    return symbols, nodes


def parse_source(file_path: str, source: bytes) -> ParsedFile:
    language = language_for_path(file_path)
    text = source.decode("utf-8", errors="replace")
    data = text.encode("utf-8")
    try:
        tree = _get_parser(language).parse(data)
        root = tree.root_node
        line_count = max(1, len(text.split("\n")))
        parse_errors = _collect_parse_errors(root, line_count)
        ast_hash = compute_normalized_ast_hash(root)
        extractor = _EXTRACTORS[language]
        symbols, symbol_nodes = _extract_symbols(file_path, root, data, extractor)
        imports = sorted(set(extractor.collect_imports(root, data)))
        exports = sorted(set(extractor.collect_exports(root, data)))
    except Exception as exc:
        raise ParserInternalError(f"failed to parse {file_path!r}: {exc}") from exc
    analysis = FileAnalysis(
        file_path=file_path,
        language=language,
        loc=_count_loc(text),
        ast_hash=ast_hash,
        imports=imports,
        exports=exports,
        symbols=symbols,
        parse_errors=parse_errors,
    )
    return ParsedFile(analysis=analysis, source=data, root=root, symbol_nodes=symbol_nodes)


def parse_file(file_path: str, source: bytes) -> FileAnalysis:
    return parse_source(file_path, source).analysis
