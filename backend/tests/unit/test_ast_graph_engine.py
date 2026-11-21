"""Unit tests for the AST and graph engine (Spec #01).

Sections are grouped per area. Later tasks append their own sections below.
"""

import socket
import subprocess
from typing import Any

import pytest
from pydantic import ValidationError

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

# ---------------------------------------------------------------------------
# Offline fixture (Req 6.1, 6.4)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block network and subprocess use and force the mock LLM provider."""

    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network and subprocess access are forbidden in unit tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(subprocess, "run", _blocked)
    monkeypatch.setattr(subprocess, "Popen", _blocked)
    monkeypatch.setenv("LLM_PROVIDER", "mock")


def test_offline_fixture_blocks_external_access() -> None:
    import os

    assert os.environ["LLM_PROVIDER"] == "mock"
    with pytest.raises(AssertionError):
        subprocess.run(["true"])
    with pytest.raises(AssertionError):
        subprocess.Popen(["true"])
    with pytest.raises(AssertionError):
        socket.socket().connect(("127.0.0.1", 9))


# ---------------------------------------------------------------------------
# Domain model helpers
# ---------------------------------------------------------------------------


def make_symbol(**overrides: Any) -> SymbolNode:
    data: dict[str, Any] = {
        "id": "pkg/a.py::Outer.inner",
        "name": "inner",
        "qualname": "Outer.inner",
        "kind": SymbolKind.METHOD,
        "file_path": "pkg/a.py",
        "start_line": 1,
        "end_line": 3,
        "signature": "def inner(self)",
        "ast_hash": "abc",
        "decorators": ["staticmethod"],
        "is_async": False,
        "raw_calls": ["foo", "bar"],
    }
    data.update(overrides)
    return SymbolNode(**data)


def make_file(**overrides: Any) -> FileAnalysis:
    data: dict[str, Any] = {
        "file_path": "pkg/a.py",
        "language": Language.PYTHON,
        "loc": 10,
        "ast_hash": "h",
        "imports": ["os"],
        "exports": [],
        "symbols": [make_symbol()],
        "parse_errors": [],
    }
    data.update(overrides)
    return FileAnalysis(**data)


def make_signal(**overrides: Any) -> DSASignal:
    data: dict[str, Any] = {
        "symbol_id": "pkg/a.py::f",
        "file_path": "pkg/a.py",
        "start_line": 1,
        "end_line": 5,
        "chapter": "Hash Tables",
        "pattern_name": "dict lookup",
        "confidence": 0.5,
        "evidence": ["dict used at line 2"],
    }
    data.update(overrides)
    return DSASignal(**data)


def make_radius(**overrides: Any) -> BlastRadius:
    data: dict[str, Any] = {
        "target_id": "pkg/a.py::f",
        "upstream_callers": ["pkg/b.py::g"],
        "downstream_callees": ["pkg/c.py::h"],
        "impact_score": 0.5,
    }
    data.update(overrides)
    return BlastRadius(**data)


def make_snapshot() -> RepoGraphSnapshot:
    return RepoGraphSnapshot(
        repo_id="r",
        root_path="/tmp/r",
        files=[make_file()],
        edges=[
            GraphEdge(source="a.py", target="b.py", edge_type=EdgeType.IMPORTS),
            GraphEdge(source="x::f", target="y::g", edge_type=EdgeType.CALLS),
        ],
        vital_organs=["x::f", "y::g"],
        cycles=[["a", "b"]],
        dsa_signals=[make_signal()],
    )


def error_fields(exc: pytest.ExceptionInfo[ValidationError]) -> set[str]:
    return {str(err["loc"][0]) for err in exc.value.errors() if err["loc"]}


# ---------------------------------------------------------------------------
# Domain models: enums (Req 1.5-1.7)
# ---------------------------------------------------------------------------


class TestEnums:
    def test_language_values(self) -> None:
        assert [m.value for m in Language] == ["python", "typescript", "javascript", "tsx", "java"]

    def test_symbol_kind_values(self) -> None:
        assert [m.value for m in SymbolKind] == [
            "function",
            "method",
            "class",
            "interface",
            "component",
        ]

    def test_edge_type_values(self) -> None:
        assert [m.value for m in EdgeType] == ["imports", "calls"]


# ---------------------------------------------------------------------------
# Domain models: construction and required fields (Req 1.8-1.30)
# ---------------------------------------------------------------------------


class TestValidConstruction:
    def test_each_model_constructs(self) -> None:
        assert make_symbol().id == "pkg/a.py::Outer.inner"
        assert make_file().loc == 10
        assert make_radius().impact_score == 0.5
        assert make_signal().chapter == "Hash Tables"
        assert len(make_snapshot().files) == 1

    def test_string_values_coerce_to_enums(self) -> None:
        assert make_symbol(kind="method").kind is SymbolKind.METHOD
        assert make_file(language="python").language is Language.PYTHON

    @pytest.mark.parametrize(
        "factory",
        [make_symbol, make_file, make_signal, make_radius],
    )
    def test_models_are_frozen(self, factory: Any) -> None:
        obj = factory()
        field = next(iter(type(obj).model_fields))
        with pytest.raises(ValidationError):
            setattr(obj, field, getattr(obj, field))

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_radius(extra_field=1)


class TestRequiredAndWrongTypes:
    @pytest.mark.parametrize(
        ("model", "factory"),
        [
            (SymbolNode, make_symbol),
            (FileAnalysis, make_file),
            (DSASignal, make_signal),
            (BlastRadius, make_radius),
            (RepoGraphSnapshot, make_snapshot),
            (GraphEdge, lambda: GraphEdge(source="a", target="b", edge_type=EdgeType.CALLS)),
        ],
    )
    def test_missing_required_field_names_it(self, model: Any, factory: Any) -> None:
        full = factory().model_dump()
        for field in full:
            data = {k: v for k, v in full.items() if k != field}
            with pytest.raises(ValidationError) as exc:
                model(**data)
            assert field in error_fields(exc)

    @pytest.mark.parametrize(
        ("factory", "field", "value"),
        [
            (make_symbol, "start_line", "5"),
            (make_symbol, "start_line", True),
            (make_symbol, "start_line", 1.0),
            (make_symbol, "is_async", 1),
            (make_symbol, "decorators", "x"),
            (make_symbol, "signature", 5),
            (make_file, "loc", "10"),
            (make_file, "loc", False),
            (make_file, "imports", [1]),
            (make_radius, "impact_score", "0.5"),
            (make_radius, "impact_score", True),
            (make_signal, "confidence", "0.5"),
            (make_signal, "end_line", 2.5),
        ],
    )
    def test_wrong_type_names_field(self, factory: Any, field: str, value: Any) -> None:
        with pytest.raises(ValidationError) as exc:
            factory(**{field: value})
        assert field in error_fields(exc)

    def test_invalid_enum_value_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            make_symbol(kind="struct")
        assert "kind" in error_fields(exc)


# ---------------------------------------------------------------------------
# Domain models: SymbolNode validation (Req 1.9-1.12)
# ---------------------------------------------------------------------------


class TestSymbolNodeValidation:
    @pytest.mark.parametrize(("start", "end"), [(0, 1), (0, 0), (-1, 5), (5, 4)])
    def test_invalid_lines_rejected(self, start: int, end: int) -> None:
        with pytest.raises(ValidationError):
            make_symbol(start_line=start, end_line=end)

    @pytest.mark.parametrize(("start", "end"), [(1, 1), (1, 2), (7, 7)])
    def test_valid_lines_accepted(self, start: int, end: int) -> None:
        sym = make_symbol(start_line=start, end_line=end)
        assert (sym.start_line, sym.end_line) == (start, end)

    @pytest.mark.parametrize(
        "bad_id",
        ["pkg/a.py::outer.inner", "PKG/a.py::Outer.inner", "pkg/a.py::Outer.inner ", "x"],
    )
    def test_id_mismatch_rejected(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            make_symbol(id=bad_id)

    def test_name_must_match_last_qualname_segment(self) -> None:
        with pytest.raises(ValidationError):
            make_symbol(name="Outer")

    def test_name_with_collision_suffix(self) -> None:
        sym = make_symbol(id="pkg/a.py::f@12", qualname="f@12", name="f")
        assert sym.name == "f"

    def test_nested_name_with_collision_suffix(self) -> None:
        sym = make_symbol(id="pkg/a.py::C.f@2", qualname="C.f@2", name="f")
        assert sym.name == "f"

    def test_name_may_not_keep_suffix(self) -> None:
        with pytest.raises(ValidationError):
            make_symbol(id="pkg/a.py::f@12", qualname="f@12", name="f@12")

    @pytest.mark.parametrize(
        "path",
        ["", "/abs/a.py", "C:/a.py", "a\\b.py", "../a.py", "a/../b.py", "./a.py", "a/./b.py"],
    )
    def test_invalid_relative_path_rejected(self, path: str) -> None:
        with pytest.raises(ValidationError) as exc:
            make_symbol(file_path=path, id=path + "::Outer.inner")
        assert "file_path" in error_fields(exc)

    def test_path_length_limit(self) -> None:
        ok = "a" * 4096
        assert make_symbol(file_path=ok, id=ok + "::Outer.inner").file_path == ok
        too_long = "a" * 4097
        with pytest.raises(ValidationError):
            make_symbol(file_path=too_long, id=too_long + "::Outer.inner")

    def test_empty_lists_accepted(self) -> None:
        sym = make_symbol(decorators=[], raw_calls=[])
        assert sym.decorators == [] and sym.raw_calls == []


# ---------------------------------------------------------------------------
# Domain models: FileAnalysis validation (Req 1.14-1.16, 1.29)
# ---------------------------------------------------------------------------


class TestFileAnalysisValidation:
    def test_negative_loc_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_file(loc=-1)

    def test_zero_loc_accepted(self) -> None:
        assert make_file(loc=0).loc == 0

    def test_foreign_symbol_file_path_rejected(self) -> None:
        foreign = make_symbol(file_path="other.py", id="other.py::Outer.inner")
        with pytest.raises(ValidationError):
            make_file(symbols=[foreign])

    def test_duplicate_symbol_ids_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_file(symbols=[make_symbol(), make_symbol(signature="other")])

    def test_distinct_ids_accepted(self) -> None:
        other = make_symbol(id="pkg/a.py::f", qualname="f", name="f")
        assert len(make_file(symbols=[make_symbol(), other]).symbols) == 2

    def test_all_lists_may_be_empty(self) -> None:
        fa = make_file(imports=[], exports=[], symbols=[], parse_errors=[])
        assert fa.imports == fa.exports == fa.symbols == fa.parse_errors == []

    def test_partial_analysis_retains_both_lists_in_order(self) -> None:
        first = make_symbol(id="pkg/a.py::b", qualname="b", name="b")
        second = make_symbol(id="pkg/a.py::a", qualname="a", name="a")
        errors = ["line 9: ERROR", "line 2: MISSING ;"]
        fa = make_file(symbols=[first, second], parse_errors=errors)
        assert [s.id for s in fa.symbols] == ["pkg/a.py::b", "pkg/a.py::a"]
        assert fa.parse_errors == errors


# ---------------------------------------------------------------------------
# Domain models: BlastRadius and DSASignal (Req 1.19, 1.21-1.24)
# ---------------------------------------------------------------------------


class TestBlastRadiusBounds:
    @pytest.mark.parametrize("score", [-0.0001, 1.0001, float("nan"), float("inf")])
    def test_out_of_bounds_rejected(self, score: float) -> None:
        with pytest.raises(ValidationError) as exc:
            make_radius(impact_score=score)
        assert "impact_score" in error_fields(exc)

    @pytest.mark.parametrize("score", [0.0, 1.0, 0.5])
    def test_in_bounds_accepted(self, score: float) -> None:
        assert make_radius(impact_score=score).impact_score == score

    def test_empty_lists_accepted(self) -> None:
        br = make_radius(upstream_callers=[], downstream_callees=[])
        assert br.upstream_callers == [] and br.downstream_callees == []


class TestDSASignalValidation:
    @pytest.mark.parametrize("conf", [-0.0001, 1.0001])
    def test_confidence_out_of_bounds_rejected(self, conf: float) -> None:
        with pytest.raises(ValidationError) as exc:
            make_signal(confidence=conf)
        assert "confidence" in error_fields(exc)

    @pytest.mark.parametrize("conf", [0.0, 1.0])
    def test_confidence_bounds_accepted(self, conf: float) -> None:
        assert make_signal(confidence=conf).confidence == conf

    def test_unknown_chapter_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            make_signal(chapter="Dynamic Arrays")
        assert "chapter" in error_fields(exc)

    @pytest.mark.parametrize(
        "chapter",
        [
            "Hash Tables",
            "Graphs & Trees",
            "Recursion & Dynamic Programming",
            "Sliding Window / Two Pointers",
            "Heaps & Priority Queues",
            "Sorting & Binary Search",
        ],
    )
    def test_all_chapters_accepted(self, chapter: str) -> None:
        assert make_signal(chapter=chapter).chapter == chapter

    @pytest.mark.parametrize("evidence", [[], [""], ["   "], ["ok", "\t\n"]])
    def test_empty_or_blank_evidence_rejected(self, evidence: list[str]) -> None:
        with pytest.raises(ValidationError):
            make_signal(evidence=evidence)

    @pytest.mark.parametrize(("start", "end"), [(0, 1), (3, 2)])
    def test_invalid_lines_rejected(self, start: int, end: int) -> None:
        with pytest.raises(ValidationError):
            make_signal(start_line=start, end_line=end)

    def test_invalid_file_path_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            make_signal(file_path="../x.py")
        assert "file_path" in error_fields(exc)


# ---------------------------------------------------------------------------
# Domain models: serialization (Req 1.25-1.28)
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_snapshot_has_exact_fields(self) -> None:
        assert list(RepoGraphSnapshot.model_fields) == [
            "repo_id",
            "root_path",
            "files",
            "edges",
            "vital_organs",
            "cycles",
            "dsa_signals",
        ]

    def test_enums_serialize_as_strings(self) -> None:
        dumped = make_snapshot().model_dump(mode="json")
        file = dumped["files"][0]
        assert file["language"] == "python"
        assert file["symbols"][0]["kind"] == "method"
        assert [e["edge_type"] for e in dumped["edges"]] == ["imports", "calls"]
        assert '"language":"python"' in make_file().model_dump_json()

    @pytest.mark.parametrize(
        "factory",
        [make_symbol, make_file, make_signal, make_radius, make_snapshot],
    )
    def test_json_round_trip_equal(self, factory: Any) -> None:
        original = factory()
        restored = type(original).model_validate_json(original.model_dump_json())
        assert restored == original

    def test_round_trip_preserves_order_and_enums(self) -> None:
        original = make_snapshot()
        restored = RepoGraphSnapshot.model_validate_json(original.model_dump_json())
        assert [e.edge_type for e in restored.edges] == [EdgeType.IMPORTS, EdgeType.CALLS]
        assert restored.files[0].language is Language.PYTHON
        assert restored.vital_organs == ["x::f", "y::g"]
        assert restored.cycles == [["a", "b"]]

    def test_equal_instances_dump_byte_identical(self) -> None:
        a, b = make_snapshot(), make_snapshot()
        assert a == b
        assert a.model_dump_json() == b.model_dump_json()

    def test_snapshot_accepts_all_empty_lists(self) -> None:
        snap = RepoGraphSnapshot(
            repo_id="r",
            root_path="/r",
            files=[],
            edges=[],
            vital_organs=[],
            cycles=[],
            dsa_signals=[],
        )
        assert snap.files == [] and snap.cycles == []


# ---------------------------------------------------------------------------
# Task 2.4: GitHub URL validation and destination containment
# (Req 2.17 to 2.22, 6.2, 6.5)
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from backend.engines.ingestion import (  # noqa: E402
    GitHubRepoRef,
    IngestionError,
    IngestionErrorKind,
    build_clone_destination,
    discover_github,
    validate_github_url,
)

_K = IngestionErrorKind


class _RecordingRunner:
    """Git runner double that records calls; validation must never reach it."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"", b"")


_ACCEPT_CASES = [
    ("https://github.com/octocat/hello", "octocat", "hello"),
    ("https://github.com/octocat/hello.git", "octocat", "hello"),
    ("https://github.com/octocat/hello/", "octocat", "hello"),
    ("https://github.com/octocat/hello.git/", "octocat", "hello"),
    ("https://github.com/" + "o" * 39 + "/r", "o" * 39, "r"),
    ("https://github.com/o/" + "r" * 100, "o", "r" * 100),
    ("https://github.com/a_b-c.d/e_f-g.h", "a_b-c.d", "e_f-g.h"),
    ("https://github.com/o/a..b", "o", "a..b"),
]

_REJECT_CASES = [
    # (id, url, expected kind)
    ("scheme-http", "http://github.com/o/r", _K.URL_BAD_SCHEME),
    ("scheme-ssh", "ssh://github.com/o/r", _K.URL_BAD_SCHEME),
    ("scheme-missing", "github.com/o/r", _K.URL_BAD_SCHEME),
    ("scheme-file", "file:///etc/passwd", _K.URL_BAD_SCHEME),
    ("host-other", "https://gitlab.com/o/r", _K.URL_BAD_HOST),
    ("host-subdomain", "https://www.github.com/o/r", _K.URL_BAD_HOST),
    ("host-suffix", "https://github.com.evil.com/o/r", _K.URL_BAD_HOST),
    ("too-long", "https://github.com/o/" + "r" * 2048, _K.URL_TOO_LONG),
    ("userinfo", "https://user@github.com/o/r", _K.URL_FORBIDDEN_COMPONENT),
    ("userinfo-password", "https://user:pw@github.com/o/r", _K.URL_FORBIDDEN_COMPONENT),
    ("port", "https://github.com:443/o/r", _K.URL_FORBIDDEN_COMPONENT),
    ("query", "https://github.com/o/r?x=1", _K.URL_FORBIDDEN_COMPONENT),
    ("fragment", "https://github.com/o/r#readme", _K.URL_FORBIDDEN_COMPONENT),
    ("extra-segment", "https://github.com/o/r/tree/main", _K.URL_BAD_PATH),
    ("one-segment", "https://github.com/o", _K.URL_BAD_PATH),
    ("no-segments", "https://github.com", _K.URL_BAD_PATH),
    ("double-slash", "https://github.com/o//r", _K.URL_BAD_PATH),
    ("encoded-slash-lower", "https://github.com/o/r%2fx", _K.URL_FORBIDDEN_COMPONENT),
    ("encoded-slash-upper", "https://github.com/o%2Fr/x", _K.URL_FORBIDDEN_COMPONENT),
    ("encoded-backslash-lower", "https://github.com/o/r%5cx", _K.URL_FORBIDDEN_COMPONENT),
    ("encoded-backslash-upper", "https://github.com/o%5Cr", _K.URL_FORBIDDEN_COMPONENT),
    ("encoded-mixed-case", "https://github.com/o/r%2F%5C", _K.URL_FORBIDDEN_COMPONENT),
    ("space", "https://github.com/o/r r", _K.URL_FORBIDDEN_COMPONENT),
    ("leading-space", " https://github.com/o/r", _K.URL_FORBIDDEN_COMPONENT),
    ("tab", "https://github.com/o/r\t", _K.URL_FORBIDDEN_COMPONENT),
    ("newline", "https://github.com/o/r\n", _K.URL_FORBIDDEN_COMPONENT),
    ("nul", "https://github.com/o/r\x00", _K.URL_FORBIDDEN_COMPONENT),
    ("escape-char", "https://github.com/o/\x1br", _K.URL_FORBIDDEN_COMPONENT),
    ("owner-dot", "https://github.com/./r", _K.URL_BAD_OWNER),
    ("owner-dotdot", "https://github.com/../r", _K.URL_BAD_OWNER),
    ("repo-dot", "https://github.com/o/.", _K.URL_BAD_REPO),
    ("repo-dotdot", "https://github.com/o/..", _K.URL_BAD_REPO),
    ("owner-empty", "https://github.com//r", _K.URL_BAD_OWNER),
    ("owner-bad-char", "https://github.com/o$/r", _K.URL_BAD_OWNER),
    ("owner-too-long", "https://github.com/" + "o" * 40 + "/r", _K.URL_BAD_OWNER),
    ("repo-bad-char", "https://github.com/o/r$x", _K.URL_BAD_REPO),
    ("repo-backslash", "https://github.com/o/r\\x", _K.URL_BAD_REPO),
    ("repo-non-ascii", "https://github.com/o/r\u00e9", _K.URL_BAD_REPO),
    ("repo-too-long", "https://github.com/o/" + "r" * 101, _K.URL_BAD_REPO),
    ("repo-only-git-suffix", "https://github.com/o/.git", _K.URL_BAD_REPO),
]


class TestGitHubUrlAccept:
    @pytest.mark.parametrize(("url", "owner", "repo"), _ACCEPT_CASES)
    def test_accepts_and_rebuilds_clone_url(self, url: str, owner: str, repo: str) -> None:
        ref = validate_github_url(url)
        assert ref == GitHubRepoRef(
            owner=owner, repo=repo, clone_url=f"https://github.com/{owner}/{repo}.git"
        )

    def test_url_of_exactly_2048_chars_is_not_too_long(self) -> None:
        # Length limit boundary: 2048 passes the length rule and fails later on repo length.
        url = "https://github.com/o/" + "r" * (2048 - len("https://github.com/o/"))
        with pytest.raises(IngestionError) as info:
            validate_github_url(url)
        assert info.value.kind is _K.URL_BAD_REPO


class TestGitHubUrlReject:
    @pytest.mark.parametrize(
        ("url", "kind"),
        [pytest.param(u, k, id=i) for i, u, k in _REJECT_CASES],
    )
    def test_rejects_with_specific_kind(self, url: str, kind: IngestionErrorKind) -> None:
        with pytest.raises(IngestionError) as info:
            validate_github_url(url)
        assert info.value.kind is kind

    @pytest.mark.parametrize(
        ("url", "kind"),
        [pytest.param(u, k, id=i) for i, u, k in _REJECT_CASES],
    )
    def test_rejection_leaves_runner_and_filesystem_untouched(
        self, tmp_path: Path, url: str, kind: IngestionErrorKind
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        runner = _RecordingRunner()
        with pytest.raises(IngestionError) as info:
            discover_github(url, workspace=workspace, git_runner=runner)
        assert info.value.kind is kind
        assert runner.calls == []
        assert list(workspace.iterdir()) == []

    def test_non_existent_workspace_is_not_created_on_rejection(self, tmp_path: Path) -> None:
        workspace = tmp_path / "missing"
        runner = _RecordingRunner()
        with pytest.raises(IngestionError):
            discover_github("http://github.com/o/r", workspace=workspace, git_runner=runner)
        assert not workspace.exists()
        assert runner.calls == []


class TestDestinationContainment:
    def test_destination_is_workspace_owner_repo(self, tmp_path: Path) -> None:
        ref = validate_github_url("https://github.com/octocat/hello")
        dest = build_clone_destination(ref, tmp_path)
        assert dest == Path(tmp_path).resolve() / "octocat" / "hello"
        assert not dest.exists()  # construction creates nothing

    def test_symlinked_owner_escaping_workspace_is_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        outside = tmp_path / "outside"
        workspace.mkdir()
        outside.mkdir()
        (workspace / "octocat").symlink_to(outside, target_is_directory=True)
        ref = validate_github_url("https://github.com/octocat/hello")
        with pytest.raises(IngestionError) as info:
            build_clone_destination(ref, workspace)
        assert info.value.kind is _K.DESTINATION_OUTSIDE_WORKSPACE
        assert list(outside.iterdir()) == []

    def test_symlinked_repo_escaping_workspace_is_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        outside = tmp_path / "outside"
        (workspace / "octocat").mkdir(parents=True)
        outside.mkdir()
        (workspace / "octocat" / "hello").symlink_to(outside, target_is_directory=True)
        ref = validate_github_url("https://github.com/octocat/hello")
        with pytest.raises(IngestionError) as info:
            build_clone_destination(ref, workspace)
        assert info.value.kind is _K.DESTINATION_OUTSIDE_WORKSPACE

    def test_destination_equal_to_workspace_is_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "o").symlink_to(workspace, target_is_directory=True)
        ref = GitHubRepoRef(owner="o", repo=".", clone_url="unused")
        with pytest.raises(IngestionError) as info:
            build_clone_destination(ref, workspace)
        assert info.value.kind is _K.DESTINATION_OUTSIDE_WORKSPACE

    def test_discover_github_rejects_escaping_destination_without_runner_call(
        self, tmp_path: Path
    ) -> None:
        workspace = tmp_path / "ws"
        outside = tmp_path / "outside"
        workspace.mkdir()
        outside.mkdir()
        (workspace / "octocat").symlink_to(outside, target_is_directory=True)
        runner = _RecordingRunner()
        with pytest.raises(IngestionError) as info:
            discover_github(
                "https://github.com/octocat/hello", workspace=workspace, git_runner=runner
            )
        assert info.value.kind is _K.DESTINATION_OUTSIDE_WORKSPACE
        assert runner.calls == []
        assert list(outside.iterdir()) == []


# ---------------------------------------------------------------------------
# Task 2.5: local discovery
# (Req 2.1, 2.3 to 2.16, 2.29, 6.5)
# ---------------------------------------------------------------------------
import os  # noqa: E402
import stat  # noqa: E402

from backend.engines.ingestion import (  # noqa: E402
    SKIPPED_DIRECTORIES,
    WarningKind,
    discover_local,
)


def _write(root: Path, rel: str, content: bytes = b"x = 1\n") -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


class TestLocalDiscoveryBasics:
    def test_empty_repository_is_not_an_error(self, tmp_path: Path) -> None:
        result = discover_local(str(tmp_path))
        assert result.files == []
        assert result.truncated is False
        assert result.warnings == []

    def test_repo_without_supported_files_is_empty(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md")
        _write(tmp_path, "a.txt")
        assert discover_local(str(tmp_path)).files == []

    def test_root_is_real_path(self, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        _write(real, "a.py")
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)
        result = discover_local(str(link))
        assert result.root == Path(os.path.realpath(real))
        assert result.files == ["a.py"]

    def test_supported_extensions_case_insensitive(self, tmp_path: Path) -> None:
        for name in ["a.py", "b.TS", "c.Js", "d.TSX", "e.JAVA", "f.pyc", "g.jsx", "h.go"]:
            _write(tmp_path, name)
        assert discover_local(str(tmp_path)).files == ["a.py", "b.TS", "c.Js", "d.TSX", "e.JAVA"]

    def test_nested_paths_are_posix_relative(self, tmp_path: Path) -> None:
        _write(tmp_path, "pkg/sub/mod.py")
        assert discover_local(str(tmp_path)).files == ["pkg/sub/mod.py"]


class TestLocalDiscoverySkipping:
    @pytest.mark.parametrize("name", sorted(SKIPPED_DIRECTORIES))
    def test_skipped_directory_at_any_depth(self, tmp_path: Path, name: str) -> None:
        _write(tmp_path, f"{name}/top.py")
        _write(tmp_path, f"src/{name}/deep/inner.py")
        _write(tmp_path, "src/keep.py")
        assert discover_local(str(tmp_path)).files == ["src/keep.py"]

    def test_skipped_name_as_file_is_not_a_directory_skip(self, tmp_path: Path) -> None:
        _write(tmp_path, "build.py")
        assert discover_local(str(tmp_path)).files == ["build.py"]

    def test_binary_file_with_nul_in_first_8192_bytes_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "bin.py", b"abc\x00def")
        _write(tmp_path, "edge.py", b"a" * 8191 + b"\x00")
        _write(tmp_path, "text.py", b"print(1)\n")
        assert discover_local(str(tmp_path)).files == ["text.py"]

    def test_nul_after_first_8192_bytes_is_included(self, tmp_path: Path) -> None:
        _write(tmp_path, "late.py", b"a" * 8192 + b"\x00")
        assert discover_local(str(tmp_path)).files == ["late.py"]

    def test_file_size_boundaries(self, tmp_path: Path) -> None:
        _write(tmp_path, "under.py", b"a" * 524_287)
        _write(tmp_path, "exact.py", b"a" * 524_288)
        _write(tmp_path, "over.py", b"a" * 524_289)
        result = discover_local(str(tmp_path))
        assert result.files == ["exact.py", "under.py"]
        assert result.truncated is False


class TestLocalDiscoveryLimits:
    def test_max_files_truncates_in_sorted_order(self, tmp_path: Path) -> None:
        for name in ["c.py", "a.py", "b.py", "d.py"]:
            _write(tmp_path, name)
        result = discover_local(str(tmp_path), max_files=2)
        assert result.files == ["a.py", "b.py"]
        assert result.truncated is True

    def test_max_files_exact_count_not_truncated(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py")
        _write(tmp_path, "b.py")
        result = discover_local(str(tmp_path), max_files=2)
        assert result.files == ["a.py", "b.py"]
        assert result.truncated is False

    def test_max_total_bytes_stops_at_first_overflow(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", b"a" * 10)
        _write(tmp_path, "b.py", b"b" * 10)
        _write(tmp_path, "c.py", b"c")  # would fit, but follows the excluded b.py
        result = discover_local(str(tmp_path), max_total_bytes=15)
        assert result.files == ["a.py"]
        assert result.truncated is True

    def test_max_total_bytes_exact_fit_not_truncated(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", b"a" * 10)
        _write(tmp_path, "b.py", b"b" * 5)
        result = discover_local(str(tmp_path), max_total_bytes=15)
        assert result.files == ["a.py", "b.py"]
        assert result.truncated is False

    @pytest.mark.parametrize("bad", [0, -1, True, False, 1.5, "5", None])
    @pytest.mark.parametrize("param", ["max_files", "max_total_bytes"])
    def test_invalid_limits_raise(self, tmp_path: Path, param: str, bad: Any) -> None:
        with pytest.raises(IngestionError) as exc:
            discover_local(str(tmp_path), **{param: bad})
        assert exc.value.kind is _K.INVALID_LIMIT

    def test_minimum_limits_accepted(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", b"a")
        result = discover_local(str(tmp_path), max_files=1, max_total_bytes=1)
        assert result.files == ["a.py"]


class TestLocalDiscoveryDeterminism:
    def test_sorted_and_duplicate_free(self, tmp_path: Path) -> None:
        for rel in ["z.py", "B/x.py", "a/y.py", "a.py", "a/b/c.ts", "m.java"]:
            _write(tmp_path, rel)
        files = discover_local(str(tmp_path)).files
        assert files == sorted(files)
        assert len(files) == len(set(files)) == 6

    def test_repeat_runs_are_equal(self, tmp_path: Path) -> None:
        for rel in ["m/a.py", "m/b.js", "n/c.java", "d.tsx"]:
            _write(tmp_path, rel)
        first = discover_local(str(tmp_path))
        second = discover_local(str(tmp_path))
        assert first == second

    def test_independent_of_enumeration_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for rel in ["a.py", "b.py", "c/d.py", "c/e.py"]:
            _write(tmp_path, rel)
        expected = discover_local(str(tmp_path)).files
        real_scandir = os.scandir

        class _Reversed:
            def __init__(self, path: str) -> None:
                self._inner = real_scandir(path)

            def __enter__(self) -> list[os.DirEntry[str]]:
                return list(reversed(list(self._inner.__enter__())))

            def __exit__(self, *args: object) -> None:
                self._inner.__exit__(*args)

        monkeypatch.setattr(os, "scandir", _Reversed)
        assert discover_local(str(tmp_path)).files == expected


class TestLocalDiscoverySymlinks:
    def test_file_symlink_escape_warns_and_excludes(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        repo = tmp_path / "repo"
        _write(outside, "secret.py")
        _write(repo, "ok.py")
        (repo / "leak.py").symlink_to(outside / "secret.py")
        result = discover_local(str(repo))
        assert result.files == ["ok.py"]
        assert [(w.kind, w.path) for w in result.warnings] == [
            (WarningKind.SYMLINK_ESCAPE, "leak.py")
        ]

    def test_directory_symlink_escape_warns_and_is_not_traversed(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        repo = tmp_path / "repo"
        _write(outside, "secret.py")
        _write(repo, "ok.py")
        (repo / "linked").symlink_to(outside, target_is_directory=True)
        result = discover_local(str(repo))
        assert result.files == ["ok.py"]
        assert [(w.kind, w.path) for w in result.warnings] == [
            (WarningKind.SYMLINK_ESCAPE, "linked")
        ]

    def test_symlink_loop_terminates_without_duplicates(self, tmp_path: Path) -> None:
        _write(tmp_path, "a/mod.py")
        (tmp_path / "a" / "loop").symlink_to(tmp_path, target_is_directory=True)
        result = discover_local(str(tmp_path))
        assert result.files == ["a/mod.py"]
        assert result.warnings == []

    def test_internal_directory_symlink_traversed_once(self, tmp_path: Path) -> None:
        _write(tmp_path, "real/mod.py")
        (tmp_path / "alias").symlink_to(tmp_path / "real", target_is_directory=True)
        result = discover_local(str(tmp_path))
        # "alias" sorts before "real", so it is the first visit; the target is never repeated.
        assert len(result.files) == 1
        assert result.files[0].endswith("/mod.py")

    def test_internal_file_symlink_is_included(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py")
        (tmp_path / "b.py").symlink_to(tmp_path / "a.py")
        assert discover_local(str(tmp_path)).files == ["a.py", "b.py"]

    def test_broken_symlink_is_ignored_or_warned_not_fatal(self, tmp_path: Path) -> None:
        _write(tmp_path, "ok.py")
        (tmp_path / "dead.py").symlink_to(tmp_path / "missing.py")
        result = discover_local(str(tmp_path))
        assert "ok.py" in result.files
        assert "dead.py" not in result.files


@pytest.mark.skipif(os.geteuid() == 0, reason="permission bits are not enforced for root")
class TestLocalDiscoveryUnreadable:
    def test_unreadable_file_warns_and_continues(self, tmp_path: Path) -> None:
        _write(tmp_path, "ok.py")
        locked = _write(tmp_path, "locked.py")
        locked.chmod(0)
        try:
            result = discover_local(str(tmp_path))
        finally:
            locked.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert result.files == ["ok.py"]
        assert len(result.warnings) == 1
        warning = result.warnings[0]
        assert warning.kind is WarningKind.ENTRY_UNREADABLE
        assert warning.path == "locked.py"
        assert warning.detail

    def test_unreadable_subdirectory_warns_and_continues(self, tmp_path: Path) -> None:
        _write(tmp_path, "ok.py")
        locked = tmp_path / "private"
        _write(locked, "hidden.py")
        locked.chmod(0)
        try:
            result = discover_local(str(tmp_path))
        finally:
            locked.chmod(stat.S_IRWXU)
        assert result.files == ["ok.py"]
        assert [(w.kind, w.path) for w in result.warnings] == [
            (WarningKind.ENTRY_UNREADABLE, "private")
        ]

    def test_unreadable_root_raises_not_readable(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        _write(root, "a.py")
        root.chmod(0)
        try:
            with pytest.raises(IngestionError) as exc:
                discover_local(str(root))
        finally:
            root.chmod(stat.S_IRWXU)
        assert exc.value.kind is _K.NOT_READABLE

    def test_root_scandir_failure_raises_root_filesystem_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(path: str) -> None:
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(os, "scandir", _boom)
        with pytest.raises(IngestionError) as exc:
            discover_local(str(tmp_path))
        assert exc.value.kind is _K.ROOT_FILESYSTEM_ERROR


class TestLocalDiscoveryInvalidPaths:
    @pytest.mark.parametrize("path", ["", "   ", "\t\n"])
    def test_empty_or_whitespace(self, path: str) -> None:
        with pytest.raises(IngestionError) as exc:
            discover_local(path)
        assert exc.value.kind is _K.EMPTY_PATH

    def test_nul_character_is_malformed(self, tmp_path: Path) -> None:
        with pytest.raises(IngestionError) as exc:
            discover_local(str(tmp_path) + "\x00x")
        assert exc.value.kind is _K.MALFORMED_PATH

    def test_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(IngestionError) as exc:
            discover_local(str(tmp_path / "nope"))
        assert exc.value.kind is _K.NOT_FOUND

    def test_file_is_not_a_directory(self, tmp_path: Path) -> None:
        target = _write(tmp_path, "a.py")
        with pytest.raises(IngestionError) as exc:
            discover_local(str(target))
        assert exc.value.kind is _K.NOT_A_DIRECTORY


# ---------------------------------------------------------------------------
# Task 2.6: cloning with a recording git_runner test double
# (Req 2.22 to 2.28, 2.30, 6.2, 6.5). No real git, network, or subprocess.
# ---------------------------------------------------------------------------
import shutil  # noqa: E402
from collections.abc import Callable  # noqa: E402

_CLONE_URL = "https://github.com/octocat/hello"


class _CloneRunner:
    """Records every call; optionally populates the clone dir or raises."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stderr: bytes | str = b"",
        raises: BaseException | None = None,
        on_call: Callable[[Path], None] | None = None,
    ) -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.raises = raises
        self.on_call = on_call
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append((args, kwargs))
        dest = Path(args[0][-1])
        if self.on_call is not None:
            self.on_call(dest)
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(args[0], self.returncode, b"", self.stderr)


def _populate(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "main.py").write_text("x = 1\n")
    (dest / "sub").mkdir()
    (dest / "sub" / "util.ts").write_text("export {}\n")
    (dest / ".git").mkdir()
    (dest / ".git" / "config").write_text("[core]\n")


def _partial(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "partial.py").write_text("x = 1\n")


class TestCloneInvocation:
    def test_exact_argv_and_kwargs_single_call(self, tmp_path: Path) -> None:
        runner = _CloneRunner(on_call=_populate)
        discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)

        assert len(runner.calls) == 1
        (argv,), kwargs = runner.calls[0]
        dest = Path(os.path.realpath(tmp_path)) / "octocat" / "hello"
        assert argv == [
            "git",
            "-c",
            "core.hooksPath=" + os.devnull,
            "clone",
            "--depth",
            "30",
            "--single-branch",
            "--no-recurse-submodules",
            "--",
            "https://github.com/octocat/hello.git",
            str(dest),
        ]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 60
        assert kwargs["capture_output"] is True
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["check"] is False
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert set(kwargs) == {"shell", "timeout", "capture_output", "stdin", "check", "env"}

    def test_env_is_a_copy_of_the_process_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SOME_MARKER", "kept")
        monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
        runner = _CloneRunner(on_call=_populate)
        discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        env = runner.calls[0][1]["env"]
        assert env["SOME_MARKER"] == "kept"
        assert "GIT_TERMINAL_PROMPT" not in os.environ

    def test_invalid_url_never_calls_runner(self, tmp_path: Path) -> None:
        runner = _CloneRunner()
        with pytest.raises(IngestionError) as exc:
            discover_github("http://github.com/o/r", workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.URL_BAD_SCHEME
        assert runner.calls == []
        assert list(tmp_path.iterdir()) == []

    def test_runner_defaults_to_subprocess_run_which_is_blocked_offline(
        self, tmp_path: Path
    ) -> None:
        # The autouse fixture replaces subprocess.run; the default must not be reached
        # silently, proving no real subprocess starts in this suite.
        with pytest.raises(AssertionError):
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=subprocess.run)


class TestCloneFailures:
    def test_non_zero_exit_maps_to_git_failed_with_truncated_stderr(self, tmp_path: Path) -> None:
        runner = _CloneRunner(returncode=128, stderr=b"e" * 600, on_call=_partial)
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.GIT_FAILED
        assert exc.value.detail == "e" * 500
        assert len(runner.calls) == 1
        assert not (tmp_path / "octocat" / "hello").exists()

    def test_non_zero_exit_with_text_stderr(self, tmp_path: Path) -> None:
        runner = _CloneRunner(returncode=1, stderr="fatal: not found")
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.GIT_FAILED
        assert exc.value.detail == "fatal: not found"

    def test_missing_git(self, tmp_path: Path) -> None:
        runner = _CloneRunner(raises=FileNotFoundError("git"))
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.GIT_NOT_INSTALLED
        assert not (tmp_path / "octocat" / "hello").exists()

    def test_timeout_removes_partial_clone(self, tmp_path: Path) -> None:
        runner = _CloneRunner(raises=subprocess.TimeoutExpired("git", 60), on_call=_partial)
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.GIT_TIMEOUT
        assert not (tmp_path / "octocat" / "hello").exists()

    def test_partial_clone_removed_on_missing_git(self, tmp_path: Path) -> None:
        runner = _CloneRunner(raises=FileNotFoundError("git"), on_call=_partial)
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.GIT_NOT_INSTALLED
        assert not (tmp_path / "octocat" / "hello").exists()

    def test_workspace_itself_survives_failed_clone(self, tmp_path: Path) -> None:
        runner = _CloneRunner(returncode=1, on_call=_partial)
        with pytest.raises(IngestionError):
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert tmp_path.is_dir()


class TestCloneReplacementAndCleanup:
    def test_existing_clone_is_replaced_before_git_runs(self, tmp_path: Path) -> None:
        stale = tmp_path / "octocat" / "hello"
        stale.mkdir(parents=True)
        (stale / "stale.py").write_text("old = 1\n")
        seen: dict[str, bool] = {}

        def _check_then_populate(dest: Path) -> None:
            seen["stale_present"] = (dest / "stale.py").exists()
            _populate(dest)

        runner = _CloneRunner(on_call=_check_then_populate)
        result = discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert seen["stale_present"] is False
        assert "stale.py" not in result.files
        assert not (stale / "stale.py").exists()

    def test_existing_file_at_destination_is_replaced(self, tmp_path: Path) -> None:
        (tmp_path / "octocat").mkdir()
        (tmp_path / "octocat" / "hello").write_text("not a dir")
        runner = _CloneRunner(on_call=_populate)
        result = discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert result.files == ["main.py", "sub/util.ts"]

    def test_removal_failure_raises_cleanup_failed_without_running_git(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stale = tmp_path / "octocat" / "hello"
        stale.mkdir(parents=True)
        (stale / "stale.py").write_text("old = 1\n")

        def _deny(*args: object, **kwargs: object) -> None:
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(shutil, "rmtree", _deny)
        runner = _CloneRunner(on_call=_populate)
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.CLEANUP_FAILED
        assert runner.calls == []
        assert (stale / "stale.py").exists()

    def test_partial_clone_removal_failure_raises_cleanup_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _deny(*args: object, **kwargs: object) -> None:
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(shutil, "rmtree", _deny)
        runner = _CloneRunner(returncode=1, on_call=_partial)
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert exc.value.kind is _K.CLEANUP_FAILED

    def test_destination_symlink_escaping_workspace_is_not_followed(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        outside = tmp_path / "outside"
        workspace.mkdir()
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        (workspace / "octocat").symlink_to(outside, target_is_directory=True)
        runner = _CloneRunner(on_call=_populate)
        with pytest.raises(IngestionError) as exc:
            discover_github(_CLONE_URL, workspace=workspace, git_runner=runner)
        assert exc.value.kind is _K.DESTINATION_OUTSIDE_WORKSPACE
        assert runner.calls == []
        assert (outside / "keep.txt").read_text() == "keep"


class TestCloneThenDiscover:
    def test_successful_clone_is_discovered_on_clone_directory(self, tmp_path: Path) -> None:
        runner = _CloneRunner(on_call=_populate)
        result = discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert result.root == Path(os.path.realpath(tmp_path)) / "octocat" / "hello"
        assert result.files == ["main.py", "sub/util.ts"]
        assert result.truncated is False
        assert result.warnings == []

    def test_limits_apply_to_clone_discovery(self, tmp_path: Path) -> None:
        runner = _CloneRunner(on_call=_populate)
        result = discover_github(_CLONE_URL, max_files=1, workspace=tmp_path, git_runner=runner)
        assert result.files == ["main.py"]
        assert result.truncated is True

    def test_empty_clone_is_not_an_error(self, tmp_path: Path) -> None:
        runner = _CloneRunner(on_call=lambda dest: dest.mkdir(parents=True, exist_ok=True))
        result = discover_github(_CLONE_URL, workspace=tmp_path, git_runner=runner)
        assert result.files == []

    def test_bad_limits_rejected_before_runner(self, tmp_path: Path) -> None:
        runner = _CloneRunner()
        with pytest.raises(IngestionError):
            discover_github(_CLONE_URL, max_files=0, workspace=tmp_path, git_runner=runner)
        assert runner.calls == []


# ---------------------------------------------------------------------------
# Task 4.6: AST parser basics and normalized hashing
# Covers Requirements 3.5-3.7, 3.9-3.14, 3.35, 3.36, 6.7. Pure in-memory
# parsing with no filesystem or network access.
# ---------------------------------------------------------------------------
import re  # noqa: E402

from backend.engines import ast_parser  # noqa: E402
from backend.engines.ast_parser import (  # noqa: E402
    ParserInternalError,
    UnsupportedLanguageError,
    parse_file,
    parse_source,
)

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _hash(source: str, path: str = "m.py") -> str:
    return parse_file(path, source.encode()).ast_hash


class TestParserBasics:
    def test_unsupported_extension_carries_extension(self) -> None:
        with pytest.raises(UnsupportedLanguageError) as exc:
            parse_file("notes.RB", b"puts 1")
        assert exc.value.extension == ".rb"

    def test_missing_extension_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedLanguageError) as exc:
            parse_file("Makefile", b"all:")
        assert exc.value.extension == ""

    def test_language_from_extension_case_insensitive(self) -> None:
        assert parse_file("A.PY", b"x = 1\n").language is Language.PYTHON

    def test_empty_file(self) -> None:
        result = parse_file("empty.py", b"")
        assert result.loc == 0
        assert _HEX64.fullmatch(result.ast_hash)
        assert result.symbols == []
        assert result.parse_errors == []

    def test_non_utf8_bytes_replaced_and_repeatable(self) -> None:
        source = b"x = '\xff\xfe'\ny = 2\n"
        first = parse_file("bad.py", source)
        second = parse_file("bad.py", source)
        assert first == second
        assert first.loc == 2
        assert first.parse_errors == []
        # Decoded text equals the replacement-character source.
        assert first.ast_hash == _hash("x = '\ufffd\ufffd'\ny = 2\n")
        assert parse_source("bad.py", source).source == "x = '\ufffd\ufffd'\ny = 2\n".encode()

    def test_loc_counts_comment_only_lines_and_skips_blank(self) -> None:
        source = "# comment\n\n   \nx = 1\n\t\n# tail\n"
        assert parse_file("a.py", source.encode()).loc == 3

    @pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
    def test_loc_handles_all_line_endings(self, newline: str) -> None:
        source = newline.join(["a = 1", "", "b = 2", "# c"])
        assert parse_file("a.py", source.encode()).loc == 3

    def test_repeat_parse_equal_in_every_field(self) -> None:
        source = b"import os\n\n@d\ndef f():\n    g()\n\nclass C:\n    def m(self):\n        f()\n"
        assert parse_file("p.py", source) == parse_file("p.py", source)

    def test_syntax_error_reported_not_raised(self) -> None:
        result = parse_file("bad.py", b"def (:\n")
        assert result.parse_errors
        assert _HEX64.fullmatch(result.ast_hash)

    def test_injected_parser_failure_raises_internal_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(language: Language) -> None:
            raise RuntimeError("grammar missing")

        monkeypatch.setattr(ast_parser, "_get_parser", boom)
        with pytest.raises(ParserInternalError):
            parse_file("a.py", b"x = 1\n")


class TestNormalizedHashEqual:
    def test_identical_source(self) -> None:
        assert _hash("x = 1\n") == _hash("x = 1\n")

    def test_hash_shape(self) -> None:
        assert _HEX64.fullmatch(_hash("x = 1\n"))

    def test_whitespace_only_change(self) -> None:
        assert _hash("x=1\ny  =  f( 2,3 )\n") == _hash("x = 1\ny = f(2, 3)\n")

    def test_blank_line_only_change(self) -> None:
        assert _hash("x = 1\ny = 2\n") == _hash("\n\nx = 1\n\n\ny = 2\n\n")

    def test_comment_only_change(self) -> None:
        assert _hash("x = 1\ny = 2\n") == _hash("# top\nx = 1  # trailing\n# mid\ny = 2\n")

    def test_comment_only_change_java_block_and_line(self) -> None:
        plain = "class A { int f() { return 1; } }"
        commented = "/* b */ class A { // l\n int f() { return 1; /* x */ } }"
        assert _hash(plain, "A.java") == _hash(commented, "A.java")

    def test_reindent_not_changing_blocks(self) -> None:
        assert _hash("if a:\n    b\n    c\n") == _hash("if a:\n        b\n        c\n")

    def test_comment_and_whitespace_equal_ts(self) -> None:
        assert _hash("const a = f(1);", "a.ts") == _hash("// c\nconst  a=f( 1 ) ;\n", "a.ts")


class TestNormalizedHashDiffers:
    BASE = "def f(a, b):\n    return a + b\n"

    def test_operator_change(self) -> None:
        assert _hash(self.BASE) != _hash(self.BASE.replace("+", "-"))

    def test_identifier_change(self) -> None:
        assert _hash(self.BASE) != _hash(self.BASE.replace("f(", "g("))

    def test_literal_change(self) -> None:
        assert _hash("x = 1\n") != _hash("x = 2\n")
        assert _hash("x = 'a'\n") != _hash("x = 'b'\n")

    def test_structural_change(self) -> None:
        assert _hash("f(a, b)\n") != _hash("f(a)\nb\n")

    def test_python_indentation_changes_block_membership(self) -> None:
        inside = "if a:\n    b\n    c\n"
        outside = "if a:\n    b\nc\n"
        assert _hash(inside) != _hash(outside)

    def test_leaf_text_is_length_prefixed(self) -> None:
        # Adjacent leaves must not be able to merge into the same serialization.
        assert _hash("ab = c\n") != _hash("a = bc\n")


# ---------------------------------------------------------------------------
# Task 4.7: Python parsing
# Covers Requirements 3.15-3.17, 3.20-3.32, 6.6. Expected values are written
# out by hand from the spec, not derived from the parser.
# ---------------------------------------------------------------------------

_PY_SOURCE = '''"""Doc."""
import os, sys as system
import a.b.c
from . import sibling
from .. import up
from ..pkg.mod import thing
from pkg.sub import x
import os

__all__ = ["alpha", "Beta", 'gamma']
__all__ += ["delta"]


def top(a: int, b: str = "x") -> bool:
    helper(a)
    obj.method(b)
    helper(a)
    a.b.c()
    first()(second())

    def inner(z):
        hidden(z)
        return z

    class Local:
        def deep(self):
            deeper()

    return inner(a)


@decorator
@other.deco(1)
async def fetch(
    url,
    *,
    retries=3,
) -> None:
    await get(url)


class Outer(Base):
    """Doc."""

    @staticmethod
    def make(x):
        return build(x)

    def run(self):
        self.step()
        super().run()
        # comment
        step()

    class Nested:
        def go(self):
            pass


def dup():
    return 1


def dup():
    return 2
'''


def _py() -> FileAnalysis:
    return parse_file("pkg/m.py", _PY_SOURCE.encode())


def _py_symbol(qualname: str) -> SymbolNode:
    return next(s for s in _py().symbols if s.qualname == qualname)


class TestPythonFileLevel:
    def test_language_loc_and_hash_shape(self) -> None:
        fa = _py()
        assert fa.file_path == "pkg/m.py"
        assert fa.language is Language.PYTHON
        assert fa.loc == 48  # 65 lines minus 17 blank; the comment-only line counts
        assert fa.parse_errors == []
        assert _HEX64.fullmatch(fa.ast_hash)
        assert all(_HEX64.fullmatch(s.ast_hash) for s in fa.symbols)

    def test_symbol_order_ids_and_kinds(self) -> None:
        got = [(s.id, s.kind) for s in _py().symbols]
        assert got == [
            ("pkg/m.py::top", SymbolKind.FUNCTION),
            ("pkg/m.py::top.inner", SymbolKind.FUNCTION),
            ("pkg/m.py::top.Local", SymbolKind.CLASS),
            ("pkg/m.py::top.Local.deep", SymbolKind.METHOD),
            ("pkg/m.py::fetch", SymbolKind.FUNCTION),
            ("pkg/m.py::Outer", SymbolKind.CLASS),
            ("pkg/m.py::Outer.make", SymbolKind.METHOD),
            ("pkg/m.py::Outer.run", SymbolKind.METHOD),
            ("pkg/m.py::Outer.Nested", SymbolKind.CLASS),
            ("pkg/m.py::Outer.Nested.go", SymbolKind.METHOD),
            ("pkg/m.py::dup", SymbolKind.FUNCTION),
            ("pkg/m.py::dup@64", SymbolKind.FUNCTION),
        ]

    def test_no_component_or_interface_kinds(self) -> None:
        kinds = {s.kind for s in _py().symbols}
        assert SymbolKind.COMPONENT not in kinds
        assert SymbolKind.INTERFACE not in kinds

    def test_name_is_last_qualname_segment_without_suffix(self) -> None:
        names = {s.qualname: s.name for s in _py().symbols}
        assert names["top.Local.deep"] == "deep"
        assert names["dup@64"] == "dup"

    def test_repeat_parse_is_equal(self) -> None:
        assert _py() == _py()


class TestPythonKindsAndNesting:
    def test_function_inside_function_stays_function(self) -> None:
        sym = _py_symbol("top.inner")
        assert (sym.kind, sym.name) == (SymbolKind.FUNCTION, "inner")

    def test_function_directly_in_class_is_method(self) -> None:
        assert _py_symbol("Outer.make").kind is SymbolKind.METHOD
        assert _py_symbol("top.Local.deep").kind is SymbolKind.METHOD

    def test_class_nested_in_class_and_function(self) -> None:
        assert _py_symbol("Outer.Nested").kind is SymbolKind.CLASS
        assert _py_symbol("top.Local").kind is SymbolKind.CLASS

    def test_nested_qualnames_outermost_first(self) -> None:
        assert _py_symbol("Outer.Nested.go").id == "pkg/m.py::Outer.Nested.go"


class TestPythonSignaturesAndLines:
    def test_signatures(self) -> None:
        assert {s.qualname: s.signature for s in _py().symbols} == {
            "top": 'def top(a: int, b: str = "x") -> bool',
            "top.inner": "def inner(z)",
            "top.Local": "class Local",
            "top.Local.deep": "def deep(self)",
            "fetch": "async def fetch( url, *, retries=3, ) -> None",
            "Outer": "class Outer(Base)",
            "Outer.make": "def make(x)",
            "Outer.run": "def run(self)",
            "Outer.Nested": "class Nested",
            "Outer.Nested.go": "def go(self)",
            "dup": "def dup()",
            "dup@64": "def dup()",
        }

    def test_untyped_signature_has_no_inferred_types(self) -> None:
        sig = _py_symbol("Outer.make").signature
        assert "->" not in sig and ":" not in sig

    def test_line_ranges_include_decorators(self) -> None:
        # fetch: decorators on lines 32-33, def on 34, last body line 39.
        sym = _py_symbol("fetch")
        assert (sym.start_line, sym.end_line) == (32, 39)
        make = _py_symbol("Outer.make")
        assert (make.start_line, make.end_line) == (45, 47)

    def test_line_ranges_of_undecorated_symbols(self) -> None:
        got = {s.qualname: (s.start_line, s.end_line) for s in _py().symbols}
        assert got["top"] == (14, 29)
        assert got["top.inner"] == (21, 23)
        assert got["top.Local"] == (25, 27)
        assert got["Outer"] == (42, 57)
        assert got["Outer.Nested.go"] == (56, 57)

    def test_decorated_symbol_hash_differs_from_undecorated(self) -> None:
        plain = parse_file("m.py", b"async def f(): pass\n").symbols[0]
        decorated = parse_file("m.py", b"@d\nasync def f(): pass\n").symbols[0]
        assert plain.ast_hash != decorated.ast_hash

    def test_symbol_hash_ignores_comments_and_blank_lines(self) -> None:
        a = parse_file("m.py", b"def f(x):\n    return x\n").symbols[0]
        b = parse_file("m.py", b"def f(x):\n\n    # note\n    return x\n").symbols[0]
        assert a.ast_hash == b.ast_hash

    def test_symbol_hash_changes_with_body(self) -> None:
        a = parse_file("m.py", b"def f(x):\n    return x\n").symbols[0]
        b = parse_file("m.py", b"def f(x):\n    return x + 1\n").symbols[0]
        assert a.ast_hash != b.ast_hash


class TestPythonDecoratorsAndAsync:
    def test_decorators_are_source_text_in_order(self) -> None:
        assert _py_symbol("fetch").decorators == ["@decorator", "@other.deco(1)"]
        assert _py_symbol("Outer.make").decorators == ["@staticmethod"]

    def test_undecorated_symbols_have_none(self) -> None:
        assert _py_symbol("top").decorators == []
        assert _py_symbol("Outer").decorators == []

    def test_async_def_sets_is_async(self) -> None:
        assert _py_symbol("fetch").is_async is True

    def test_sync_symbols_are_not_async(self) -> None:
        asyncs = {s.qualname for s in _py().symbols if s.is_async}
        assert asyncs == {"fetch"}

    def test_async_method(self) -> None:
        fa = parse_file("m.py", b"class C:\n    async def m(self):\n        await x()\n")
        sym = fa.symbols[1]
        assert (sym.qualname, sym.kind, sym.is_async) == ("C.m", SymbolKind.METHOD, True)
        assert sym.signature == "async def m(self)"
        assert sym.raw_calls == ["x"]

    def test_decorated_class(self) -> None:
        fa = parse_file("m.py", b"@dataclass\nclass C:\n    x: int\n")
        sym = fa.symbols[0]
        assert (sym.kind, sym.decorators, sym.start_line, sym.end_line) == (
            SymbolKind.CLASS,
            ["@dataclass"],
            1,
            3,
        )


class TestPythonRawCalls:
    def test_order_of_first_occurrence_and_dedupe(self) -> None:
        # helper(a) appears twice; the first position is kept.
        assert _py_symbol("top").raw_calls == [
            "helper",
            "obj.method",
            "a.b.c",
            "first",
            "second",
            "inner",
        ]

    def test_nested_function_calls_belong_to_nested_symbol(self) -> None:
        assert "hidden" not in _py_symbol("top").raw_calls
        assert _py_symbol("top.inner").raw_calls == ["hidden"]

    def test_nested_class_method_calls_belong_to_nested_method(self) -> None:
        assert "deeper" not in _py_symbol("top").raw_calls
        assert _py_symbol("top.Local.deep").raw_calls == ["deeper"]

    def test_member_access_chains_and_self(self) -> None:
        assert _py_symbol("Outer.run").raw_calls == ["self.step", "super", "step"]

    def test_class_symbols_have_no_raw_calls(self) -> None:
        assert _py_symbol("Outer").raw_calls == []
        assert _py_symbol("Outer.Nested").raw_calls == []

    def test_calls_in_comments_and_strings_are_ignored(self) -> None:
        src = b'def f():\n    # nope()\n    s = "nope()"\n    real()\n'
        assert parse_file("m.py", src).symbols[0].raw_calls == ["real"]

    def test_function_without_calls(self) -> None:
        assert _py_symbol("Outer.Nested.go").raw_calls == []


class TestPythonImportsAndExports:
    def test_imports_sorted_deduplicated_with_leading_dots(self) -> None:
        assert _py().imports == [".", "..", "..pkg.mod", "a.b.c", "os", "pkg.sub", "sys"]

    def test_aliased_import_records_module_not_alias(self) -> None:
        fa = parse_file("m.py", b"import numpy as np\nfrom os import path as p\n")
        assert fa.imports == ["numpy", "os"]

    def test_single_dot_relative_module(self) -> None:
        assert parse_file("m.py", b"from .mod import x\n").imports == [".mod"]

    def test_imports_inside_functions_are_recorded(self) -> None:
        fa = parse_file("m.py", b"def f():\n    import json\n")
        assert fa.imports == ["json"]

    def test_exports_from_all_string_literals_sorted(self) -> None:
        assert _py().exports == ["Beta", "alpha", "delta", "gamma"]

    def test_no_exports_without_all(self) -> None:
        fa = parse_file("m.py", b"def public():\n    pass\n\nclass C:\n    pass\n")
        assert fa.exports == []

    def test_non_literal_all_entries_are_skipped(self) -> None:
        src = b'name = "x"\n__all__ = ["a", name, f"{name}b", "a"]\n'
        assert parse_file("m.py", src).exports == ["a"]

    def test_all_tuple_is_not_an_explicit_export(self) -> None:
        assert parse_file("m.py", b'__all__ = ("a", "b")\n').exports == []


class TestPythonCollisionSuffix:
    def test_first_unchanged_later_gets_start_line_suffix(self) -> None:
        src = b"def f():\n    pass\n\n\ndef f():\n    pass\n\n\ndef f():\n    pass\n"
        ids = [s.id for s in parse_file("m.py", src).symbols]
        assert ids == ["m.py::f", "m.py::f@5", "m.py::f@9"]

    def test_suffix_uses_decorator_start_line(self) -> None:
        src = b"def f():\n    pass\n\n@d\ndef f():\n    pass\n"
        assert [s.qualname for s in parse_file("m.py", src).symbols] == ["f", "f@4"]

    def test_suffixed_class_prefixes_its_methods(self) -> None:
        method = b"    def m(self):\n        pass\n"
        src = b"class C:\n" + method + b"\nclass C:\n" + method
        fa = parse_file("m.py", src)
        assert [s.qualname for s in fa.symbols] == ["C", "C.m", "C@5", "C@5.m"]
        assert len({s.id for s in fa.symbols}) == 4

    def test_duplicate_methods_in_one_class(self) -> None:
        src = b"class C:\n    def m(self):\n        pass\n    def m(self):\n        pass\n"
        fa = parse_file("m.py", src)
        assert [s.qualname for s in fa.symbols] == ["C", "C.m", "C.m@4"]
        assert fa.symbols[2].name == "m"


# ---------------------------------------------------------------------------
# Task 4.8: TypeScript, JavaScript, and TSX parsing
# Covers Requirements 3.15-3.19, 3.22-3.24, 3.26-3.28, 3.30, 3.31, 6.6.
# Expected values are written out by hand from the spec, not derived from the
# parser. Line numbers in the comments refer to the fixture sources below.
# ---------------------------------------------------------------------------

_TS_SOURCE = """\
import { a, b } from "./mod";
import def from '../up/thing';
import * as ns from "pkg";
import "./side";
export { x as y, z } from "./re";
export * from "./all";
export default top;

export interface Shape {
  area(): number;
}

export function top(a: number, b?: string): boolean {
  helper(a);
  obj.method(b);
  helper(a);
  this.x.y();
  return false;
}

export const arrow = async (x: number): Promise<void> => {
  await load(x);
};

// comment
@Injectable()
export class Service extends Base {
  @Log
  @Cache("x")
  async run(id: number): Promise<void> {
    this.step();
    super.run();
    fetchIt(id);
  }

  private step(): void {}

}

export @Sealed class Late {
  go() {
    function inner() { deep(); }
    return inner();
  }
}
"""

_JS_SOURCE = """\
import React from "react";
import { helper } from './util.js';
export { default as Foo } from "./foo";
export * as utils from "./utils";

export function Card(props) {
  return <div>{props.title}</div>;
}

export const Frag = () => <>{render()}</>;

function lower() { return <b/>; }

const Btn = async function () { await go(); };

@Component
class Widget extends Base {
  render() {
    return <span/>;
  }
  @bound
  async load() {
    this.fetch();
  }
}

export default Card;
export { Btn, lower as low };
"""

_TSX_SOURCE = """\
import type { Props } from "./types";
import { useState } from "react";

export interface ButtonProps {
  label: string;
}

export const Button = ({ label }: ButtonProps): JSX.Element => {
  const [n, setN] = useState(0);
  return <button onClick={() => setN(n + 1)}>{label}</button>;
};

export default function App(): JSX.Element {
  return <><Button label="x" /></>;
}

function helper(x: number): number {
  return x * 2;
}

export class Panel extends React.Component<Props> {
  @observable
  async render() {
    return <div />;
  }
}
"""


def _ecma(path: str, source: str) -> FileAnalysis:
    return parse_file(path, source.encode())


def _by_qualname(fa: FileAnalysis) -> dict[str, SymbolNode]:
    return {s.qualname: s for s in fa.symbols}


class TestTypeScriptFile:
    def test_file_level(self) -> None:
        fa = _ecma("src/a.ts", _TS_SOURCE)
        assert fa.language is Language.TYPESCRIPT
        assert fa.loc == 38  # 45 lines minus 7 blank; the comment-only line counts
        assert fa.parse_errors == []
        assert _HEX64.fullmatch(fa.ast_hash)
        assert all(_HEX64.fullmatch(s.ast_hash) for s in fa.symbols)
        assert fa == _ecma("src/a.ts", _TS_SOURCE)

    def test_symbol_ids_and_kinds_in_source_order(self) -> None:
        got = [(s.id, s.kind) for s in _ecma("src/a.ts", _TS_SOURCE).symbols]
        assert got == [
            ("src/a.ts::Shape", SymbolKind.INTERFACE),
            ("src/a.ts::top", SymbolKind.FUNCTION),
            ("src/a.ts::arrow", SymbolKind.FUNCTION),
            ("src/a.ts::Service", SymbolKind.CLASS),
            ("src/a.ts::Service.run", SymbolKind.METHOD),
            ("src/a.ts::Service.step", SymbolKind.METHOD),
            ("src/a.ts::Late", SymbolKind.CLASS),
            ("src/a.ts::Late.go", SymbolKind.METHOD),
            ("src/a.ts::Late.go.inner", SymbolKind.FUNCTION),
        ]

    def test_no_component_kind_in_typescript(self) -> None:
        kinds = {s.kind for s in _ecma("a.ts", _TS_SOURCE).symbols}
        assert SymbolKind.COMPONENT not in kinds

    def test_signatures(self) -> None:
        sigs = {s.qualname: s.signature for s in _ecma("a.ts", _TS_SOURCE).symbols}
        assert sigs == {
            "Shape": "interface Shape",
            "top": "function top(a: number, b?: string): boolean",
            "arrow": "const arrow = async (x: number): Promise<void> =>",
            "Service": "class Service extends Base",
            "Service.run": "async run(id: number): Promise<void>",
            "Service.step": "private step(): void",
            "Late": "class Late",
            "Late.go": "go()",
            "Late.go.inner": "function inner()",
        }

    def test_untyped_signature_has_no_inferred_types(self) -> None:
        assert _by_qualname(_ecma("a.ts", _TS_SOURCE))["Late.go"].signature == "go()"

    def test_line_ranges_include_decorators(self) -> None:
        got = {s.qualname: (s.start_line, s.end_line) for s in _ecma("a.ts", _TS_SOURCE).symbols}
        assert got == {
            "Shape": (9, 11),
            "top": (13, 19),
            "arrow": (21, 23),
            "Service": (26, 38),  # starts at the @Injectable() before `export`
            "Service.run": (28, 34),  # starts at @Log
            "Service.step": (36, 36),
            "Late": (40, 45),  # starts at the decorator on the same line
            "Late.go": (41, 44),
            "Late.go.inner": (42, 42),
        }

    def test_decorators_in_all_three_placements(self) -> None:
        symbols = _by_qualname(_ecma("a.ts", _TS_SOURCE))
        assert symbols["Service"].decorators == ["@Injectable()"]  # on export_statement
        assert symbols["Late"].decorators == ["@Sealed"]  # on the class itself
        assert symbols["Service.run"].decorators == ["@Log", '@Cache("x")']  # preceding siblings
        assert symbols["Service.step"].decorators == []
        assert symbols["top"].decorators == []

    def test_async_flags(self) -> None:
        got = {s.qualname: s.is_async for s in _ecma("a.ts", _TS_SOURCE).symbols}
        assert [q for q, is_async in got.items() if is_async] == ["arrow", "Service.run"]

    def test_raw_calls(self) -> None:
        calls = {s.qualname: s.raw_calls for s in _ecma("a.ts", _TS_SOURCE).symbols}
        assert calls == {
            "Shape": [],
            "top": ["helper", "obj.method", "this.x.y"],  # duplicate helper dropped
            "arrow": ["load"],
            "Service": [],
            "Service.run": ["this.step", "super.run", "fetchIt"],
            "Service.step": [],
            "Late": [],
            "Late.go": ["inner"],  # the call inside inner() belongs to inner
            "Late.go.inner": ["deep"],
        }

    def test_imports_and_reexports_sorted_without_quotes(self) -> None:
        assert _ecma("a.ts", _TS_SOURCE).imports == [
            "../up/thing",
            "./all",
            "./mod",
            "./re",
            "./side",
            "pkg",
        ]

    def test_exports_named_default_and_star(self) -> None:
        assert _ecma("a.ts", _TS_SOURCE).exports == [
            "*",
            "Late",
            "Service",
            "Shape",
            "arrow",
            "default",
            "top",
            "y",
            "z",
        ]

    def test_dynamic_import_require_and_new_are_not_recorded(self) -> None:
        src = "const m = require('r');\nasync function f() { await import('d'); new K(); }\n"
        fa = _ecma("a.ts", src)
        assert fa.imports == []
        assert fa.symbols[0].raw_calls == []

    def test_non_exported_constructs_record_no_exports(self) -> None:
        assert _ecma("a.ts", "const a = 1;\nfunction f() {}\nclass C {}\n").exports == []


class TestJavaScriptFile:
    def test_file_level(self) -> None:
        fa = _ecma("web/a.js", _JS_SOURCE)
        assert fa.language is Language.JAVASCRIPT
        assert fa.loc == 22  # 28 lines minus 6 blank
        assert fa.parse_errors == []
        assert _HEX64.fullmatch(fa.ast_hash)
        assert fa == _ecma("web/a.js", _JS_SOURCE)

    def test_symbol_ids_and_kinds_in_source_order(self) -> None:
        got = [(s.id, s.kind) for s in _ecma("web/a.js", _JS_SOURCE).symbols]
        assert got == [
            ("web/a.js::Card", SymbolKind.COMPONENT),
            ("web/a.js::Frag", SymbolKind.COMPONENT),
            ("web/a.js::lower", SymbolKind.FUNCTION),  # JSX but lowercase name
            ("web/a.js::Btn", SymbolKind.FUNCTION),  # uppercase but no JSX
            ("web/a.js::Widget", SymbolKind.COMPONENT),  # class with JSX
            ("web/a.js::Widget.render", SymbolKind.METHOD),  # methods are never components
            ("web/a.js::Widget.load", SymbolKind.METHOD),
        ]

    def test_signatures(self) -> None:
        sigs = {s.qualname: s.signature for s in _ecma("a.js", _JS_SOURCE).symbols}
        assert sigs == {
            "Card": "function Card(props)",
            "Frag": "const Frag = () =>",
            "lower": "function lower()",
            "Btn": "const Btn = async function ()",
            "Widget": "class Widget extends Base",
            "Widget.render": "render()",
            "Widget.load": "async load()",
        }

    def test_line_ranges_include_decorators(self) -> None:
        got = {s.qualname: (s.start_line, s.end_line) for s in _ecma("a.js", _JS_SOURCE).symbols}
        assert got == {
            "Card": (6, 8),
            "Frag": (10, 10),
            "lower": (12, 12),
            "Btn": (14, 14),
            "Widget": (16, 25),  # starts at @Component
            "Widget.render": (18, 20),
            "Widget.load": (21, 24),  # starts at @bound
        }

    def test_decorators(self) -> None:
        symbols = _by_qualname(_ecma("a.js", _JS_SOURCE))
        assert symbols["Widget"].decorators == ["@Component"]
        assert symbols["Widget.load"].decorators == ["@bound"]
        assert symbols["Widget.render"].decorators == []

    def test_async_flags(self) -> None:
        got = {s.qualname: s.is_async for s in _ecma("a.js", _JS_SOURCE).symbols}
        assert [q for q, is_async in got.items() if is_async] == ["Btn", "Widget.load"]

    def test_raw_calls(self) -> None:
        calls = {s.qualname: s.raw_calls for s in _ecma("a.js", _JS_SOURCE).symbols}
        assert calls == {
            "Card": [],
            "Frag": ["render"],
            "lower": [],
            "Btn": ["go"],
            "Widget": [],
            "Widget.render": [],
            "Widget.load": ["this.fetch"],
        }

    def test_imports_and_reexports(self) -> None:
        assert _ecma("a.js", _JS_SOURCE).imports == ["./foo", "./util.js", "./utils", "react"]

    def test_exports(self) -> None:
        assert _ecma("a.js", _JS_SOURCE).exports == [
            "Btn",
            "Card",
            "Foo",
            "Frag",
            "default",
            "low",
            "utils",
        ]

    def test_no_interface_symbols_in_javascript(self) -> None:
        assert SymbolKind.INTERFACE not in {s.kind for s in _ecma("a.js", _JS_SOURCE).symbols}
        fa = _ecma("a.js", "interface Foo { x: number }\nfunction ok() {}\n")
        assert SymbolKind.INTERFACE not in {s.kind for s in fa.symbols}
        assert "Foo" not in {s.name for s in fa.symbols}


class TestTsxFile:
    def test_file_level(self) -> None:
        fa = _ecma("ui/b.tsx", _TSX_SOURCE)
        assert fa.language is Language.TSX
        assert fa.loc == 21  # 26 lines minus 5 blank
        assert fa.parse_errors == []
        assert _HEX64.fullmatch(fa.ast_hash)
        assert fa == _ecma("ui/b.tsx", _TSX_SOURCE)

    def test_symbol_ids_and_kinds_in_source_order(self) -> None:
        got = [(s.id, s.kind) for s in _ecma("ui/b.tsx", _TSX_SOURCE).symbols]
        assert got == [
            ("ui/b.tsx::ButtonProps", SymbolKind.INTERFACE),
            ("ui/b.tsx::Button", SymbolKind.COMPONENT),
            ("ui/b.tsx::App", SymbolKind.COMPONENT),  # fragment with self-closing element
            ("ui/b.tsx::helper", SymbolKind.FUNCTION),  # no JSX
            ("ui/b.tsx::Panel", SymbolKind.COMPONENT),
            ("ui/b.tsx::Panel.render", SymbolKind.METHOD),  # JSX in a method, still a method
        ]

    def test_signatures(self) -> None:
        sigs = {s.qualname: s.signature for s in _ecma("b.tsx", _TSX_SOURCE).symbols}
        assert sigs == {
            "ButtonProps": "interface ButtonProps",
            "Button": "const Button = ({ label }: ButtonProps): JSX.Element =>",
            "App": "function App(): JSX.Element",
            "helper": "function helper(x: number): number",
            "Panel": "class Panel extends React.Component<Props>",
            "Panel.render": "async render()",
        }

    def test_line_ranges_include_decorators(self) -> None:
        got = {s.qualname: (s.start_line, s.end_line) for s in _ecma("b.tsx", _TSX_SOURCE).symbols}
        assert got == {
            "ButtonProps": (4, 6),
            "Button": (8, 11),
            "App": (13, 15),
            "helper": (17, 19),
            "Panel": (21, 26),
            "Panel.render": (22, 25),  # starts at @observable
        }

    def test_decorators_and_async(self) -> None:
        render = _by_qualname(_ecma("b.tsx", _TSX_SOURCE))["Panel.render"]
        assert render.decorators == ["@observable"]
        assert render.is_async is True
        assert [s.qualname for s in _ecma("b.tsx", _TSX_SOURCE).symbols if s.is_async] == [
            "Panel.render"
        ]

    def test_raw_calls(self) -> None:
        calls = {s.qualname: s.raw_calls for s in _ecma("b.tsx", _TSX_SOURCE).symbols}
        assert calls == {
            "ButtonProps": [],
            "Button": ["useState", "setN"],
            "App": [],
            "helper": [],
            "Panel": [],
            "Panel.render": [],
        }

    def test_imports_and_exports(self) -> None:
        fa = _ecma("b.tsx", _TSX_SOURCE)
        assert fa.imports == ["./types", "react"]
        assert fa.exports == ["App", "Button", "ButtonProps", "Panel", "default"]


class TestEcmaScriptHashAndRecovery:
    def test_hash_ignores_comments_and_whitespace(self) -> None:
        a = _ecma("a.ts", "function f(x: number) { return x + 1; }\n").symbols[0]
        b = _ecma("a.ts", "// c\nfunction f( x: number ) {\n\n  /* m */ return x+1;\n}\n").symbols[
            0
        ]
        assert a.ast_hash == b.ast_hash

    def test_hash_changes_with_operator_or_identifier(self) -> None:
        base = _ecma("a.js", "function f(x) { return x + 1; }\n")
        op = _ecma("a.js", "function f(x) { return x - 1; }\n")
        ident = _ecma("a.js", "function g(x) { return x + 1; }\n")
        assert base.symbols[0].ast_hash != op.symbols[0].ast_hash
        assert base.symbols[0].ast_hash != ident.symbols[0].ast_hash
        assert base.ast_hash != op.ast_hash

    @pytest.mark.parametrize(
        ("path", "source"),
        [
            (
                "a.ts",
                "function ok(): number {\n  return 1;\n}\n\nfunction broken( {\n  return ;\n}\n",
            ),
            ("a.js", "function ok() {\n  return 1;\n}\n\nfunction broken( {\n  return ;\n}\n"),
            ("a.tsx", "function ok() {\n  return <b/>;\n}\n\nfunction broken( {\n  return ;\n}\n"),
        ],
    )
    def test_syntax_error_keeps_valid_symbols_and_drops_broken(
        self, path: str, source: str
    ) -> None:
        fa = _ecma(path, source)
        line_count = len(source.split("\n"))
        assert fa.parse_errors
        for entry in fa.parse_errors:
            line = int(entry.split(":")[0].removeprefix("line "))
            assert 1 <= line <= line_count
        assert _HEX64.fullmatch(fa.ast_hash)
        names = {s.name for s in fa.symbols}
        assert "ok" in names
        assert "broken" not in names
        assert fa == _ecma(path, source)


# ---------------------------------------------------------------------------
# Task 4.9: Java parsing
# Covers Requirements 3.15-3.18, 3.22, 3.23, 3.26-3.28, 3.30, 3.31, 6.6.
# Expected values are written out by hand from the spec, not derived from the
# parser. Line numbers in the comments refer to the fixture source below.
# ---------------------------------------------------------------------------
_JAVA_SOURCE = """\
package com.acme;

import java.util.List;
import java.util.*;
import static java.lang.Math.max;
import static java.lang.Math.*;
import java.util.List;

// a comment-only line
public abstract class Box<T> extends Base implements Shape {
    private int n;

    public Box(int n) {
        this.n = n;
        init();
    }

    @Override
    @SuppressWarnings("unchecked")
    public String name() {
        helper.run();
        this.a.b.go();
        helper.run();
        Runnable r = () -> log();
        return String.valueOf(n) + make().toString();
    }

    protected abstract int todo(int x, String s);

    public enum Color { RED, GREEN; int code() { return 1; } }
    record Pt(int x, int y) {}
    interface Inner { void m(); }
}

interface Shape { double area(); }
enum Mode { ON }
public interface Api { }

@FunctionalInterface
public record Rec(int a) { }
"""
# Line map: 1 package, 3-7 imports, 9 comment, 10-33 Box, 13-16 ctor, 18-26 name(),
# 28 todo, 30 Color, 31 Pt, 32 Inner, 35 Shape, 36 Mode, 37 Api, 39-40 Rec.


def _java() -> FileAnalysis:
    return _ecma("src/Box.java", _JAVA_SOURCE)


class TestJavaFile:
    def test_file_level(self) -> None:
        fa = _java()
        assert fa.language is Language.JAVA
        assert fa.loc == 32  # 40 lines minus 8 blank; the comment-only line counts
        assert fa.parse_errors == []
        assert _HEX64.fullmatch(fa.ast_hash)
        assert all(_HEX64.fullmatch(s.ast_hash) for s in fa.symbols)
        assert fa == _java()

    def test_symbol_ids_kinds_and_lines_in_source_order(self) -> None:
        got = [(s.id, s.kind, s.start_line, s.end_line) for s in _java().symbols]
        assert got == [
            ("src/Box.java::Box", SymbolKind.CLASS, 10, 33),
            ("src/Box.java::Box.Box", SymbolKind.METHOD, 13, 16),
            ("src/Box.java::Box.name", SymbolKind.METHOD, 18, 26),
            ("src/Box.java::Box.todo", SymbolKind.METHOD, 28, 28),
            ("src/Box.java::Box.Color", SymbolKind.CLASS, 30, 30),
            ("src/Box.java::Box.Color.code", SymbolKind.METHOD, 30, 30),
            ("src/Box.java::Box.Pt", SymbolKind.CLASS, 31, 31),
            ("src/Box.java::Box.Inner", SymbolKind.INTERFACE, 32, 32),
            ("src/Box.java::Box.Inner.m", SymbolKind.METHOD, 32, 32),
            ("src/Box.java::Shape", SymbolKind.INTERFACE, 35, 35),
            ("src/Box.java::Shape.area", SymbolKind.METHOD, 35, 35),
            ("src/Box.java::Mode", SymbolKind.CLASS, 36, 36),
            ("src/Box.java::Api", SymbolKind.INTERFACE, 37, 37),
            ("src/Box.java::Rec", SymbolKind.CLASS, 39, 40),
        ]

    def test_no_component_kind_and_no_async(self) -> None:
        symbols = _java().symbols
        assert all(s.kind is not SymbolKind.COMPONENT for s in symbols)
        assert all(s.kind is not SymbolKind.FUNCTION for s in symbols)
        assert all(s.is_async is False for s in symbols)

    def test_signatures(self) -> None:
        sym = _by_qualname(_java())
        assert sym["Box"].signature == "public abstract class Box<T> extends Base implements Shape"
        assert sym["Box.Box"].signature == "public Box(int n)"
        assert sym["Box.todo"].signature == "protected abstract int todo(int x, String s)"
        assert sym["Box.Color"].signature == "public enum Color"
        assert sym["Box.Color.code"].signature == "int code()"
        assert sym["Box.Pt"].signature == "record Pt(int x, int y)"
        assert sym["Box.Inner.m"].signature == "void m()"
        assert sym["Shape"].signature == "interface Shape"

    def test_annotations_are_the_only_decorators(self) -> None:
        sym = _by_qualname(_java())
        assert sym["Box.name"].decorators == ["@Override", '@SuppressWarnings("unchecked")']
        assert sym["Rec"].decorators == ["@FunctionalInterface"]
        for qualname, s in sym.items():
            if qualname not in ("Box.name", "Rec"):
                assert s.decorators == [], qualname

    def test_annotation_lines_are_included_in_symbol_range(self) -> None:
        sym = _by_qualname(_java())
        assert sym["Box.name"].start_line == 18  # first annotation line, not `public String`
        assert sym["Rec"].start_line == 39  # the @FunctionalInterface line

    def test_raw_calls_for_methods_and_constructors(self) -> None:
        sym = _by_qualname(_java())
        assert sym["Box.Box"].raw_calls == ["init"]
        # Duplicates removed, lambda body belongs to the method, chained receiver skipped.
        assert sym["Box.name"].raw_calls == [
            "helper.run",
            "this.a.b.go",
            "log",
            "String.valueOf",
            "make",
        ]
        assert sym["Box.todo"].raw_calls == []  # bodiless
        assert sym["Box.Color.code"].raw_calls == []
        assert sym["Box"].raw_calls == []
        assert sym["Shape"].raw_calls == []

    def test_imports_plain_wildcard_static_sorted_and_deduplicated(self) -> None:
        assert _java().imports == [
            "java.lang.Math.*",
            "java.lang.Math.max",
            "java.util.*",
            "java.util.List",
        ]

    def test_exports_are_public_top_level_types_only(self) -> None:
        # Box, Api, Rec are public top-level. Shape and Mode are package-private,
        # and nested Color is public but not top-level.
        assert _java().exports == ["Api", "Box", "Rec"]

    def test_no_exports_without_public(self) -> None:
        fa = _ecma("A.java", "class A { public void f() {} }\n")
        assert fa.exports == []
        assert fa.imports == []

    def test_other_languages_cannot_produce_java_shapes(self) -> None:
        # Java declares no top-level functions: every Symbol is class, interface, or method.
        kinds = {s.kind for s in _java().symbols}
        assert kinds == {SymbolKind.CLASS, SymbolKind.INTERFACE, SymbolKind.METHOD}


class TestJavaHashAndRecovery:
    def test_hash_ignores_comments_and_whitespace(self) -> None:
        a = _ecma("A.java", "class A { int f(int x) { return x + 1; } }\n").symbols[1]
        b = _ecma(
            "A.java",
            "class A {\n  // c\n  int f( int x ) {\n\n    /* m */ return x+1;\n  }\n}\n",
        ).symbols[1]
        assert a.qualname == b.qualname == "A.f"
        assert a.ast_hash == b.ast_hash

    def test_hash_changes_with_operator_or_identifier(self) -> None:
        base = _ecma("A.java", "class A { int f(int x) { return x + 1; } }\n")
        op = _ecma("A.java", "class A { int f(int x) { return x - 1; } }\n")
        ident = _ecma("A.java", "class A { int g(int x) { return x + 1; } }\n")
        assert base.symbols[1].ast_hash != op.symbols[1].ast_hash
        assert base.symbols[1].ast_hash != ident.symbols[1].ast_hash
        assert base.ast_hash != op.ast_hash

    def test_syntax_error_keeps_valid_symbols_and_drops_broken(self) -> None:
        source = "class Ok {\n  void a() {}\n}\n\nclass Bad {\n  void b( {\n}\n"
        fa = _ecma("A.java", source)
        line_count = len(source.split("\n"))
        assert fa.parse_errors
        for entry in fa.parse_errors:
            line = int(entry.split(":")[0].removeprefix("line "))
            assert 1 <= line <= line_count
        assert _HEX64.fullmatch(fa.ast_hash)
        qualnames = {s.qualname for s in fa.symbols}
        assert {"Ok", "Ok.a"} <= qualnames
        assert "Bad" not in qualnames
        assert "Bad.b" not in qualnames
        assert fa == _ecma("A.java", source)


# ---------------------------------------------------------------------------
# Task 4.10: Syntax-error recovery across all five languages
# Covers Requirements 3.33, 3.34, 6.6. Each source has one erroneous function
# between two valid sibling functions. "unexpected" cases produce an ERROR
# node, "missing" cases produce an is_missing node. A syntax error is reported
# in parse_errors and never raised; ParserInternalError is a separate failure.
# ---------------------------------------------------------------------------
_RECOVERY_UNEXPECTED = {
    "python": (
        "a.py",
        "def ok():\n    return 1\n\ndef broken():\n    x = = 3\n\ndef ok2():\n    return 2\n",
        ["ok", "ok2"],
    ),
    "javascript": (
        "a.js",
        "function ok() { return 1; }\nfunction broken() { let = = 3; }\n"
        "function ok2() { return 2; }\n",
        ["ok", "ok2"],
    ),
    "typescript": (
        "a.ts",
        "function ok(): number { return 1; }\nfunction broken() { let = = 3; }\n"
        "function ok2(): number { return 2; }\n",
        ["ok", "ok2"],
    ),
    "tsx": (
        "a.tsx",
        "function ok() { return <b/>; }\nfunction broken() { let = = 3; }\n"
        "function ok2() { return <i/>; }\n",
        ["ok", "ok2"],
    ),
    "java": (
        "A.java",
        "class A {\n void ok() {}\n void broken() { int = = 3; }\n void ok2() {}\n}\n",
        ["A.ok", "A.ok2"],
    ),
}
_RECOVERY_MISSING = {
    "python": (
        "a.py",
        "def ok():\n    return 1\n\ndef broken(:\n    return\n\ndef ok2():\n    return 2\n",
        ["ok", "ok2"],
    ),
    "javascript": (
        "a.js",
        "function ok() { return 1; }\nfunction broken() { return foo(1, 2; }\n"
        "function ok2() { return 2; }\n",
        ["ok", "ok2"],
    ),
    "typescript": (
        "a.ts",
        "function ok(): number { return 1; }\nfunction broken() { return foo(1, 2; }\n"
        "function ok2(): number { return 2; }\n",
        ["ok", "ok2"],
    ),
    "tsx": (
        "a.tsx",
        "function ok() { return <b/>; }\nfunction broken() { return foo(1, 2; }\n"
        "function ok2() { return <i/>; }\n",
        ["ok", "ok2"],
    ),
    "java": (
        "A.java",
        "class A {\n void ok() {}\n void broken( {}\n void ok2() {}\n}\n",
        ["A.ok", "A.ok2"],
    ),
}


def _error_lines(fa: FileAnalysis) -> list[int]:
    return [int(e.split(":")[0].removeprefix("line ")) for e in fa.parse_errors]


def _assert_recovered(path: str, source: str, expected: list[str]) -> FileAnalysis:
    fa = parse_file(path, source.encode())
    line_count = len(source.split("\n"))
    assert fa.parse_errors
    assert all(1 <= n <= line_count for n in _error_lines(fa))
    assert _HEX64.fullmatch(fa.ast_hash)
    qualnames = [s.qualname for s in fa.symbols]
    assert qualnames == expected
    assert not any("broken" in q for q in qualnames)
    assert all(_HEX64.fullmatch(s.ast_hash) for s in fa.symbols)
    assert fa == parse_file(path, source.encode())
    return fa


class TestSyntaxErrorRecovery:
    @pytest.mark.parametrize("name", sorted(_RECOVERY_UNEXPECTED))
    def test_unexpected_syntax_keeps_siblings_and_drops_broken(self, name: str) -> None:
        path, source, expected = _RECOVERY_UNEXPECTED[name]
        fa = _assert_recovered(path, source, expected)
        assert any(e.endswith("unexpected syntax") for e in fa.parse_errors)
        # The error sits on the line of the broken function.
        assert 2 <= min(_error_lines(fa)) <= 5

    @pytest.mark.parametrize("name", sorted(_RECOVERY_MISSING))
    def test_missing_node_reported_and_symbol_dropped(self, name: str) -> None:
        path, source, expected = _RECOVERY_MISSING[name]
        fa = _assert_recovered(path, source, expected)
        assert any(": missing " in e for e in fa.parse_errors)
        parsed = parse_source(path, source.encode())
        stack = [parsed.root]
        found_missing = False
        while stack:
            node = stack.pop()
            found_missing = found_missing or node.is_missing
            stack.extend(node.children)
        assert found_missing

    def test_syntax_error_does_not_raise_internal_error(self) -> None:
        for path, source, _ in _RECOVERY_UNEXPECTED.values():
            parse_file(path, source.encode())

    def test_internal_error_is_distinct_from_parse_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path, source, _ = _RECOVERY_UNEXPECTED["python"]
        assert parse_file(path, source.encode()).parse_errors

        def boom(language: Language) -> None:
            raise RuntimeError("grammar missing")

        monkeypatch.setattr(ast_parser, "_get_parser", boom)
        # Valid and invalid sources alike raise ParserInternalError, never a
        # FileAnalysis carrying parse_errors.
        for text in (source, "x = 1\n"):
            with pytest.raises(ParserInternalError):
                parse_file(path, text.encode())


# ---------------------------------------------------------------------------
# Graph construction and import edges (Task 6.7; Req 4.1, 4.3-4.9, 4.15, 4.35,
# 4.37, 6.8). Inputs are FileAnalysis values built directly.
# ---------------------------------------------------------------------------
import itertools  # noqa: E402

from backend.engines.graph_engine import InvalidInputError, build_graph  # noqa: E402

_EXT_LANGUAGE = {
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".js": Language.JAVASCRIPT,
    ".java": Language.JAVA,
}


def gfile(path: str, imports: list[str] | None = None, **overrides: Any) -> FileAnalysis:
    """A FileAnalysis with no symbols; the language follows the file extension."""
    suffix = "." + path.rsplit(".", 1)[-1]
    data: dict[str, Any] = {
        "file_path": path,
        # Extensionless paths (exact-match fixtures) get an arbitrary language.
        "language": _EXT_LANGUAGE.get(suffix, Language.PYTHON),
        "imports": imports or [],
        "symbols": [],
    }
    data.update(overrides)
    return make_file(**data)


def gsymbol(path: str, qualname: str, **overrides: Any) -> SymbolNode:
    data: dict[str, Any] = {
        "id": f"{path}::{qualname}",
        "name": qualname.rsplit(".", 1)[-1],
        "qualname": qualname,
        "file_path": path,
        "kind": SymbolKind.FUNCTION,
        "raw_calls": [],
    }
    data.update(overrides)
    return make_symbol(**data)


def import_edges(files: list[FileAnalysis]) -> set[tuple[str, str]]:
    graph = build_graph(files)
    return {(u, v) for u, v, d in graph.edges(data=True) if d["edge_type"] == "imports"}


def resolve(importer: str, specifier: str, others: list[str]) -> set[tuple[str, str]]:
    files = [gfile(importer, [specifier])] + [gfile(p) for p in others]
    return import_edges(files)


class TestGraphNodes:
    def test_empty_input_gives_empty_graph(self) -> None:
        graph = build_graph([])
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0

    def test_file_node_attributes(self) -> None:
        graph = build_graph([gfile("src/a.ts", loc=42)])
        assert graph.nodes["src/a.ts"] == {
            "node_type": "file",
            "language": "typescript",
            "loc": 42,
        }

    def test_symbol_node_attributes_and_id(self) -> None:
        sym = gsymbol("a.py", "C.m", kind=SymbolKind.METHOD, start_line=4, end_line=9)
        graph = build_graph([gfile("a.py", symbols=[sym])])
        assert graph.nodes["a.py::C.m"] == {
            "node_type": "symbol",
            "kind": "method",
            "name": "m",
            "qualname": "C.m",
            "file_path": "a.py",
            "start_line": 4,
            "end_line": 9,
        }
        assert set(graph.nodes) == {"a.py", "a.py::C.m"}

    def test_one_node_per_file_and_symbol(self) -> None:
        files = [
            gfile("a.py", symbols=[gsymbol("a.py", "f"), gsymbol("a.py", "g")]),
            gfile("b.py", symbols=[gsymbol("b.py", "f")]),
        ]
        graph = build_graph(files)
        assert graph.number_of_nodes() == 5

    def test_every_edge_has_valid_edge_type(self) -> None:
        files = [
            gfile("a.py", ["b"], symbols=[gsymbol("a.py", "f", raw_calls=["f"])]),
            gfile("b.py"),
        ]
        graph = build_graph(files)
        assert graph.number_of_edges() == 2
        assert {d["edge_type"] for _, _, d in graph.edges(data=True)} == {"imports", "calls"}

    def test_duplicate_file_path_raises(self) -> None:
        with pytest.raises(InvalidInputError, match="a.py"):
            build_graph([gfile("a.py"), gfile("b.py"), gfile("a.py")])


class TestPythonRelativeImports:
    def test_single_dot_sibling_module(self) -> None:
        assert resolve("pkg/a.py", ".b", ["pkg/b.py"]) == {("pkg/a.py", "pkg/b.py")}

    def test_single_dot_package_init_when_no_module(self) -> None:
        assert resolve("pkg/a.py", ".sub", ["pkg/sub/__init__.py"]) == {
            ("pkg/a.py", "pkg/sub/__init__.py")
        }

    def test_module_file_wins_over_package_init(self) -> None:
        got = resolve("pkg/a.py", ".sub", ["pkg/sub.py", "pkg/sub/__init__.py"])
        assert got == {("pkg/a.py", "pkg/sub.py")}

    def test_bare_dot_resolves_to_own_package_init(self) -> None:
        assert resolve("pkg/a.py", ".", ["pkg/__init__.py"]) == {("pkg/a.py", "pkg/__init__.py")}

    def test_bare_dot_without_init_gives_no_edge(self) -> None:
        assert resolve("pkg/a.py", ".", ["pkg/b.py"]) == set()

    def test_two_dots_move_up_one_directory(self) -> None:
        assert resolve("pkg/sub/a.py", "..x", ["pkg/x.py", "pkg/sub/x.py"]) == {
            ("pkg/sub/a.py", "pkg/x.py")
        }

    def test_dotted_tail_converts_to_slashes(self) -> None:
        assert resolve("pkg/sub/a.py", "..p.q", ["pkg/p/q.py"]) == {("pkg/sub/a.py", "pkg/p/q.py")}

    def test_three_dots_move_up_two_directories(self) -> None:
        assert resolve("a/b/c.py", "...x", ["x.py", "a/x.py"]) == {("a/b/c.py", "x.py")}

    def test_root_level_file_single_dot(self) -> None:
        assert resolve("a.py", ".b", ["b.py"]) == {("a.py", "b.py")}

    def test_root_level_file_double_dot_goes_above_root(self) -> None:
        assert resolve("a.py", "..b", ["b.py"]) == set()

    def test_going_above_root_from_nested_file(self) -> None:
        assert resolve("pkg/a.py", "...b", ["b.py", "pkg/b.py"]) == set()

    def test_bare_double_dot_at_root_gives_no_edge(self) -> None:
        assert resolve("a.py", "..", ["__init__.py"]) == set()

    def test_exactly_reaching_root_is_allowed(self) -> None:
        assert resolve("pkg/a.py", "..b", ["b.py"]) == {("pkg/a.py", "b.py")}

    def test_unresolved_relative_gives_no_edge(self) -> None:
        assert resolve("pkg/a.py", ".missing", ["pkg/b.py"]) == set()


class TestPythonAbsoluteImports:
    def test_exact_root_module(self) -> None:
        assert resolve("main.py", "util", ["util.py"]) == {("main.py", "util.py")}

    def test_dotted_path_exact(self) -> None:
        assert resolve("main.py", "a.b.c", ["a/b/c.py"]) == {("main.py", "a/b/c.py")}

    def test_dotted_suffix_match_under_repository_prefix(self) -> None:
        got = resolve("backend/main.py", "engines.x", ["backend/engines/x.py"])
        assert got == {("backend/main.py", "backend/engines/x.py")}

    def test_package_init_matches_dotted_name(self) -> None:
        assert resolve("main.py", "pkg", ["pkg/__init__.py"]) == {("main.py", "pkg/__init__.py")}

    def test_ambiguous_suffix_gives_no_edge(self) -> None:
        assert resolve("main.py", "x.y", ["one/x/y.py", "two/x/y.py"]) == set()

    def test_ambiguous_between_module_and_package_init(self) -> None:
        assert resolve("main.py", "x", ["x.py", "sub/x/__init__.py"]) == set()

    def test_suffix_must_align_to_path_segments(self) -> None:
        assert resolve("main.py", "util", ["myutil.py", "pkg/myutil.py"]) == set()

    def test_external_package_gives_no_edge(self) -> None:
        assert resolve("main.py", "os.path", ["util.py"]) == set()

    def test_other_language_files_are_not_python_candidates(self) -> None:
        assert resolve("main.py", "util", ["util.ts", "util.java"]) == set()


class TestJavaImports:
    def test_fully_qualified_import(self) -> None:
        got = resolve("src/Main.java", "com.acme.Util", ["src/com/acme/Util.java"])
        assert got == {("src/Main.java", "src/com/acme/Util.java")}

    def test_ambiguous_java_import_gives_no_edge(self) -> None:
        got = resolve(
            "Main.java", "com.acme.Util", ["a/com/acme/Util.java", "b/com/acme/Util.java"]
        )
        assert got == set()

    def test_wildcard_import_gives_no_edge(self) -> None:
        assert resolve("Main.java", "com.acme.*", ["com/acme/Util.java"]) == set()

    def test_static_member_import_gives_no_edge(self) -> None:
        assert resolve("Main.java", "com.acme.Util.helper", ["com/acme/Util.java"]) == set()

    def test_external_java_import_gives_no_edge(self) -> None:
        assert resolve("Main.java", "java.util.List", ["com/acme/Util.java"]) == set()

    def test_java_does_not_use_init_files(self) -> None:
        assert resolve("Main.java", "pkg", ["pkg/__init__.py"]) == set()


class TestScriptRelativeImports:
    @pytest.mark.parametrize("importer", ["src/a.ts", "src/a.js", "src/a.tsx"])
    def test_applies_to_ts_js_tsx(self, importer: str) -> None:
        assert resolve(importer, "./b", ["src/b.ts"]) == {(importer, "src/b.ts")}

    def test_exact_path_wins_over_extensions(self) -> None:
        got = resolve("src/a.ts", "./b", ["src/b", "src/b.ts"])
        assert got == {("src/a.ts", "src/b")}

    def test_explicit_extension_is_an_exact_match(self) -> None:
        assert resolve("src/a.ts", "./b.js", ["src/b.js"]) == {("src/a.ts", "src/b.js")}

    def test_esm_js_specifier_does_not_map_to_ts(self) -> None:
        assert resolve("src/a.ts", "./b.js", ["src/b.ts"]) == set()

    @pytest.mark.parametrize(
        ("present", "expected"),
        [
            ([".py", ".ts", ".js", ".tsx", ".java"], ".py"),
            ([".ts", ".js", ".tsx", ".java"], ".ts"),
            ([".js", ".tsx", ".java"], ".js"),
            ([".tsx", ".java"], ".tsx"),
            ([".java"], ".java"),
        ],
    )
    def test_extension_order(self, present: list[str], expected: str) -> None:
        others = ["src/b" + ext for ext in present]
        assert resolve("src/a.ts", "./b", others) == {("src/a.ts", "src/b" + expected)}

    def test_file_with_extension_wins_over_directory_index(self) -> None:
        got = resolve("src/a.ts", "./b", ["src/b/index.ts", "src/b.js"])
        assert got == {("src/a.ts", "src/b.js")}

    def test_directory_index(self) -> None:
        got = resolve("src/a.ts", "./lib", ["src/lib/index.ts"])
        assert got == {("src/a.ts", "src/lib/index.ts")}

    @pytest.mark.parametrize(
        ("present", "expected"),
        [
            ([".py", ".ts", ".js", ".tsx", ".java"], ".py"),
            ([".ts", ".js", ".tsx", ".java"], ".ts"),
            ([".js", ".tsx", ".java"], ".js"),
            ([".tsx", ".java"], ".tsx"),
            ([".java"], ".java"),
        ],
    )
    def test_index_extension_order(self, present: list[str], expected: str) -> None:
        others = ["src/lib/index" + ext for ext in present]
        assert resolve("src/a.ts", "./lib", others) == {("src/a.ts", "src/lib/index" + expected)}

    def test_parent_directory_specifier(self) -> None:
        assert resolve("src/deep/a.ts", "../b", ["src/b.ts"]) == {("src/deep/a.ts", "src/b.ts")}

    def test_dot_slash_normalization(self) -> None:
        got = resolve("src/a.ts", "./x/../b", ["src/b.ts"])
        assert got == {("src/a.ts", "src/b.ts")}

    def test_reaching_root_via_parent(self) -> None:
        assert resolve("src/a.ts", "../b", ["b.ts"]) == {("src/a.ts", "b.ts")}

    def test_above_root_gives_no_edge(self) -> None:
        assert resolve("a.ts", "../b", ["b.ts"]) == set()

    def test_above_root_from_nested_file_gives_no_edge(self) -> None:
        assert resolve("src/a.ts", "../../b", ["b.ts"]) == set()

    def test_dot_slash_only_resolves_to_directory_index(self) -> None:
        assert resolve("src/a.ts", "./", ["src/index.ts"]) == {("src/a.ts", "src/index.ts")}

    def test_bare_specifier_gives_no_edge(self) -> None:
        assert resolve("src/a.ts", "react", ["react.ts", "src/react.ts"]) == set()
        assert resolve("src/a.ts", "@x/y", ["@x/y.ts", "src/@x/y.ts"]) == set()

    def test_unresolved_relative_gives_no_edge(self) -> None:
        assert resolve("src/a.ts", "./nope", ["src/b.ts"]) == set()


class TestImportEdgeProperties:
    def test_edge_direction_is_importer_to_imported(self) -> None:
        graph = build_graph([gfile("a.py", ["b"]), gfile("b.py")])
        assert graph.has_edge("a.py", "b.py")
        assert not graph.has_edge("b.py", "a.py")
        assert graph.edges["a.py", "b.py"] == {"edge_type": "imports"}

    def test_mutual_imports_make_two_directed_edges(self) -> None:
        got = import_edges([gfile("a.py", ["b"]), gfile("b.py", ["a"])])
        assert got == {("a.py", "b.py"), ("b.py", "a.py")}

    def test_no_self_import_via_relative(self) -> None:
        assert import_edges([gfile("pkg/a.py", [".a"])]) == set()

    def test_no_self_import_via_absolute(self) -> None:
        assert import_edges([gfile("a.py", ["a"])]) == set()

    def test_no_self_import_via_script_index(self) -> None:
        assert import_edges([gfile("src/index.ts", ["./"])]) == set()

    def test_self_import_ignored_but_other_imports_kept(self) -> None:
        got = import_edges([gfile("pkg/a.py", [".a", ".b"]), gfile("pkg/b.py")])
        assert got == {("pkg/a.py", "pkg/b.py")}

    def test_duplicate_imports_make_one_edge(self) -> None:
        graph = build_graph([gfile("a.py", ["b", "b", ".b"]), gfile("b.py")])
        assert graph.number_of_edges() == 1

    def test_unresolved_imports_do_not_stop_building(self) -> None:
        got = import_edges([gfile("a.py", ["os", "nope", "..x", "b"]), gfile("b.py")])
        assert got == {("a.py", "b.py")}

    def test_imports_are_resolved_per_importer_language(self) -> None:
        files = [
            gfile("src/a.ts", ["./b"]),
            gfile("src/b.ts"),
            gfile("src/c.py", ["./b"]),
        ]
        assert import_edges(files) == {("src/a.ts", "src/b.ts")}


class TestPermutationInvariance:
    @staticmethod
    def _snapshot(graph: Any) -> tuple[list[Any], list[Any]]:
        return list(graph.nodes(data=True)), list(graph.edges(data=True))

    def test_every_permutation_gives_identical_graph(self) -> None:
        files = [
            gfile("src/a.ts", ["./b", "./lib"], symbols=[gsymbol("src/a.ts", "f")]),
            gfile("src/b.ts", ["./lib"]),
            gfile("src/lib/index.ts"),
            gfile("main.py", ["util"], symbols=[gsymbol("main.py", "g", raw_calls=["g"])]),
            gfile("util.py", ["main"]),
        ]
        reference = self._snapshot(build_graph(files))
        for perm in itertools.permutations(files):
            assert self._snapshot(build_graph(list(perm))) == reference

    def test_nodes_and_edges_inserted_in_sorted_order(self) -> None:
        files = [gfile("z.py", ["a", "m"]), gfile("m.py"), gfile("a.py", ["m"])]
        graph = build_graph(files)
        assert list(graph.nodes) == ["a.py", "m.py", "z.py"]
        assert list(graph.edges) == [("a.py", "m.py"), ("z.py", "a.py"), ("z.py", "m.py")]

    def test_files_precede_symbols_in_node_order(self) -> None:
        files = [
            gfile("b.py", symbols=[gsymbol("b.py", "f")]),
            gfile("a.py", symbols=[gsymbol("a.py", "f")]),
        ]
        assert list(build_graph(files).nodes) == ["a.py", "b.py", "a.py::f", "b.py::f"]

    def test_input_list_is_not_mutated(self) -> None:
        files = [gfile("b.py"), gfile("a.py", ["b"])]
        build_graph(files)
        assert [f.file_path for f in files] == ["b.py", "a.py"]


# ---------------------------------------------------------------------------
# Call edges (Task 6.8; Req 4.4, 4.10-4.14, 6.8). Inputs are FileAnalysis
# values built directly. Expected edges are written out by hand from the
# three ordered resolution rules in the design ("Call resolution").
# ---------------------------------------------------------------------------
def call_edges(files: list[FileAnalysis]) -> set[tuple[str, str]]:
    graph = build_graph(files)
    return {(u, v) for u, v, d in graph.edges(data=True) if d["edge_type"] == "calls"}


class TestCallEdges:
    def test_same_file_call_by_name(self) -> None:
        files = [
            gfile(
                "a.py",
                symbols=[
                    gsymbol("a.py", "caller", raw_calls=["helper"]),
                    gsymbol("a.py", "helper"),
                ],
            )
        ]
        assert call_edges(files) == {("a.py::caller", "a.py::helper")}

    def test_same_file_call_by_dotted_qualname(self) -> None:
        files = [
            gfile(
                "a.py",
                symbols=[
                    gsymbol("a.py", "caller", raw_calls=["Util.run"]),
                    gsymbol("a.py", "Util.run", kind=SymbolKind.METHOD),
                ],
            )
        ]
        assert call_edges(files) == {("a.py::caller", "a.py::Util.run")}

    def test_edge_direction_is_caller_to_callee(self) -> None:
        files = [
            gfile(
                "a.py",
                symbols=[
                    gsymbol("a.py", "caller", raw_calls=["callee"]),
                    gsymbol("a.py", "callee"),
                ],
            )
        ]
        graph = build_graph(files)
        assert graph.has_edge("a.py::caller", "a.py::callee")
        assert not graph.has_edge("a.py::callee", "a.py::caller")
        assert graph.edges["a.py::caller", "a.py::callee"]["edge_type"] == "calls"

    def test_imported_file_call(self) -> None:
        files = [
            gfile("pkg/a.py", [".b"], symbols=[gsymbol("pkg/a.py", "f", raw_calls=["g"])]),
            gfile("pkg/b.py", symbols=[gsymbol("pkg/b.py", "g")]),
        ]
        assert call_edges(files) == {("pkg/a.py::f", "pkg/b.py::g")}

    def test_call_into_file_that_is_not_imported_is_unresolved(self) -> None:
        files = [
            gfile("a.py", symbols=[gsymbol("a.py", "f", raw_calls=["g"])]),
            gfile("b.py", symbols=[gsymbol("b.py", "g")]),
        ]
        assert call_edges(files) == set()

    def test_same_file_match_wins_over_imported_file(self) -> None:
        files = [
            gfile(
                "pkg/a.py",
                [".b"],
                symbols=[gsymbol("pkg/a.py", "f", raw_calls=["g"]), gsymbol("pkg/a.py", "g")],
            ),
            gfile("pkg/b.py", symbols=[gsymbol("pkg/b.py", "g")]),
        ]
        assert call_edges(files) == {("pkg/a.py::f", "pkg/a.py::g")}

    def test_self_call_resolves_to_same_class_method(self) -> None:
        files = [
            gfile(
                "a.py",
                symbols=[
                    gsymbol("a.py", "C.m", kind=SymbolKind.METHOD, raw_calls=["self.n"]),
                    gsymbol("a.py", "C.n", kind=SymbolKind.METHOD),
                    gsymbol("a.py", "D.n", kind=SymbolKind.METHOD),
                ],
            )
        ]
        assert call_edges(files) == {("a.py::C.m", "a.py::C.n")}

    def test_this_call_resolves_to_same_class_method(self) -> None:
        files = [
            gfile(
                "a.ts",
                symbols=[
                    gsymbol("a.ts", "C.m", kind=SymbolKind.METHOD, raw_calls=["this.n"]),
                    gsymbol("a.ts", "C.n", kind=SymbolKind.METHOD),
                ],
            )
        ]
        assert call_edges(files) == {("a.ts::C.m", "a.ts::C.n")}

    def test_self_call_has_no_fallback_when_class_lacks_method(self) -> None:
        # A same-file function and an imported-file function both named "n"
        # exist, but the self. rule never falls through to them.
        files = [
            gfile(
                "pkg/a.py",
                [".b"],
                symbols=[
                    gsymbol("pkg/a.py", "C.m", kind=SymbolKind.METHOD, raw_calls=["self.n"]),
                    gsymbol("pkg/a.py", "n"),
                ],
            ),
            gfile("pkg/b.py", symbols=[gsymbol("pkg/b.py", "n")]),
        ]
        assert call_edges(files) == set()

    def test_ambiguous_same_file_call_creates_no_edge(self) -> None:
        files = [
            gfile(
                "a.py",
                symbols=[
                    gsymbol("a.py", "caller", raw_calls=["dup"]),
                    gsymbol("a.py", "A.dup", kind=SymbolKind.METHOD),
                    gsymbol("a.py", "B.dup", kind=SymbolKind.METHOD),
                ],
            )
        ]
        assert call_edges(files) == set()

    def test_ambiguous_same_file_call_does_not_fall_to_imports(self) -> None:
        files = [
            gfile(
                "pkg/a.py",
                [".b"],
                symbols=[
                    gsymbol("pkg/a.py", "caller", raw_calls=["dup"]),
                    gsymbol("pkg/a.py", "A.dup", kind=SymbolKind.METHOD),
                    gsymbol("pkg/a.py", "B.dup", kind=SymbolKind.METHOD),
                ],
            ),
            gfile("pkg/b.py", symbols=[gsymbol("pkg/b.py", "dup")]),
        ]
        assert call_edges(files) == set()

    def test_ambiguous_imported_candidates_create_no_edge(self) -> None:
        files = [
            gfile("pkg/a.py", [".b", ".c"], symbols=[gsymbol("pkg/a.py", "f", raw_calls=["g"])]),
            gfile("pkg/b.py", symbols=[gsymbol("pkg/b.py", "g")]),
            gfile("pkg/c.py", symbols=[gsymbol("pkg/c.py", "g")]),
        ]
        assert call_edges(files) == set()

    def test_unresolved_call_creates_no_edge(self) -> None:
        files = [gfile("a.py", symbols=[gsymbol("a.py", "f", raw_calls=["print", "os.path.join"])])]
        assert call_edges(files) == set()

    def test_self_recursion_creates_self_loop(self) -> None:
        files = [gfile("a.py", symbols=[gsymbol("a.py", "fact", raw_calls=["fact"])])]
        graph = build_graph(files)
        assert call_edges(files) == {("a.py::fact", "a.py::fact")}
        assert graph.edges["a.py::fact", "a.py::fact"]["edge_type"] == "calls"

    def test_duplicate_calls_collapse_to_one_edge(self) -> None:
        files = [
            gfile(
                "a.py",
                symbols=[gsymbol("a.py", "f", raw_calls=["g", "g"]), gsymbol("a.py", "g")],
            )
        ]
        assert build_graph(files).number_of_edges() == 1


# ---------------------------------------------------------------------------
# Vital organs: PageRank plus degree scoring (Req 4.16 to 4.20, 6.8).
# Graphs are built directly with networkx. Expected values are derived by hand.
# ---------------------------------------------------------------------------
import networkx as nx  # noqa: E402

from backend.engines.graph_engine import (  # noqa: E402
    InvalidArgumentError,
    compute_vital_organs,
)


def _digraph(nodes: list[str], edges: list[tuple[str, str]]) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from(edges)
    return graph


def _chain() -> nx.DiGraph:
    return _digraph(["a", "b", "c"], [("a", "b"), ("b", "c")])


class TestVitalOrganArithmetic:
    def test_hand_computed_chain_scores_and_order(self) -> None:
        # Chain a -> b -> c, N = 3, damping d = 0.85, c is dangling.
        # Let k = (1 - d) / 3 + d * r_c / 3. Then r_a = k, r_b = k (1 + d),
        # r_c = k (1 + d + d^2), and the ranks sum to 1.
        # Min-max PageRank: a = 0, c = 1, b = d / (d + d^2) = 1 / 1.85.
        # In-degrees (0, 1, 1) and out-degrees (1, 1, 0) normalize to themselves.
        d = 0.85
        k = 1 / (3 + 2 * d + d**2)
        r = {"a": k, "b": k * (1 + d), "c": k * (1 + d + d**2)}
        assert sum(r.values()) == pytest.approx(1.0)
        pr_n_b = (r["b"] - r["a"]) / (r["c"] - r["a"])
        assert pr_n_b == pytest.approx(1 / 1.85)

        expected = {
            "a": 0.5 * 0.0 + 0.25 * 0.0 + 0.25 * 1.0,  # 0.25
            "b": 0.5 * pr_n_b + 0.25 * 1.0 + 0.25 * 1.0,  # about 0.77027
            "c": 0.5 * 1.0 + 0.25 * 1.0 + 0.25 * 0.0,  # 0.75
        }
        assert expected["b"] == pytest.approx(0.5 / 1.85 + 0.5)
        hand_order = sorted(expected, key=lambda n: (-expected[n], n))
        assert hand_order == ["b", "c", "a"]
        assert compute_vital_organs(_chain(), top_k=10) == hand_order

    def test_top_k_is_a_prefix_of_the_ranking(self) -> None:
        assert compute_vital_organs(_chain(), top_k=1) == ["b"]
        assert compute_vital_organs(_chain(), top_k=2) == ["b", "c"]

    def test_default_top_k_is_ten(self) -> None:
        nodes = [f"n{i:02d}" for i in range(12)]
        assert compute_vital_organs(_digraph(nodes, [])) == nodes[:10]

    def test_self_loop_counts_once_in_each_degree(self) -> None:
        # x -> x and x -> y, N = 2. In-degrees x=1, y=1 (constant, so 0.0);
        # out-degrees x=2, y=0 (x = 1, y = 0). x also has more PageRank.
        graph = _digraph(["x", "y"], [("x", "x"), ("x", "y")])
        assert compute_vital_organs(graph) == ["x", "y"]


class TestVitalOrganTieBreakAndNormalization:
    def test_equal_scores_break_by_node_id(self) -> None:
        graph = _digraph(["m", "z", "a", "k"], [])
        assert compute_vital_organs(graph) == ["a", "k", "m", "z"]

    def test_symmetric_pair_breaks_by_node_id(self) -> None:
        graph = _digraph(["b", "a"], [("b", "a"), ("a", "b")])
        assert compute_vital_organs(graph, top_k=2) == ["a", "b"]

    def test_constant_components_normalize_to_zero_without_error(self) -> None:
        # A directed ring has constant PageRank, in-degree, and out-degree.
        # Every score is 0.0 and the result is the sorted node ids.
        ring = _digraph(["c", "a", "b"], [("c", "a"), ("a", "b"), ("b", "c")])
        assert compute_vital_organs(ring) == ["a", "b", "c"]


class TestVitalOrganBounds:
    def test_empty_graph_returns_empty_list(self) -> None:
        assert compute_vital_organs(nx.DiGraph()) == []
        assert compute_vital_organs(nx.DiGraph(), top_k=0) == []

    def test_top_k_zero_returns_empty_list(self) -> None:
        assert compute_vital_organs(_chain(), top_k=0) == []

    @pytest.mark.parametrize("top_k", [4, 100])
    def test_top_k_larger_than_node_count_returns_all_nodes(self, top_k: int) -> None:
        assert compute_vital_organs(_chain(), top_k=top_k) == ["b", "c", "a"]

    @pytest.mark.parametrize("bad", [-1, -100, True, 1.5, "3", None])
    def test_invalid_top_k_raises_and_leaves_graph_unmodified(self, bad: Any) -> None:
        graph = _chain()
        graph.nodes["a"]["tag"] = "keep"
        graph.edges["a", "b"]["edge_type"] = "calls"
        before = (list(graph.nodes(data=True)), list(graph.edges(data=True)))
        with pytest.raises(InvalidArgumentError):
            compute_vital_organs(graph, top_k=bad)
        assert (list(graph.nodes(data=True)), list(graph.edges(data=True))) == before

    def test_invalid_top_k_raises_even_for_empty_graph(self) -> None:
        with pytest.raises(InvalidArgumentError):
            compute_vital_organs(nx.DiGraph(), top_k=-1)

    def test_valid_call_does_not_modify_graph(self) -> None:
        graph = _chain()
        before = (list(graph.nodes(data=True)), list(graph.edges(data=True)))
        compute_vital_organs(graph)
        assert (list(graph.nodes(data=True)), list(graph.edges(data=True))) == before


class TestVitalOrganOrderIndependence:
    def test_insertion_order_does_not_change_result(self) -> None:
        nodes = ["a", "b", "c", "d", "e"]
        edges = [("a", "b"), ("b", "c"), ("c", "a"), ("d", "c"), ("e", "c"), ("c", "d")]
        baseline = compute_vital_organs(_digraph(nodes, edges), top_k=5)
        assert baseline[0] == "c"
        for node_order in itertools.islice(itertools.permutations(nodes), 0, 120, 7):
            for edge_order in (edges, edges[::-1], edges[2:] + edges[:2]):
                graph = _digraph(list(node_order), list(edge_order))
                assert compute_vital_organs(graph, top_k=5) == baseline

    def test_repeat_calls_are_equal(self) -> None:
        assert compute_vital_organs(_chain()) == compute_vital_organs(_chain())


# ---------------------------------------------------------------------------
# Task 6.10: cycle detection (Req 4.21 to 4.25, 6.8).
# Graphs are built directly with networkx. Expected values are written by hand.
# ---------------------------------------------------------------------------
import random  # noqa: E402
import time  # noqa: E402

from backend.engines.graph_engine import detect_cycles  # noqa: E402


def _snapshot_graph(graph: nx.DiGraph) -> tuple[list[Any], list[Any]]:
    return list(graph.nodes(data=True)), list(graph.edges(data=True))


class TestDetectCycles:
    def test_simple_cycle(self) -> None:
        graph = _digraph(["c", "a", "b"], [("a", "b"), ("b", "c"), ("c", "a")])
        assert detect_cycles(graph) == [["a", "b", "c"]]

    def test_self_loop_is_a_cycle(self) -> None:
        graph = _digraph(["a", "b"], [("a", "a"), ("a", "b")])
        assert detect_cycles(graph) == [["a"]]

    def test_multiple_components(self) -> None:
        graph = _digraph(
            ["a", "b", "c", "d", "e", "f", "g"],
            [("a", "b"), ("b", "a"), ("c", "d"), ("d", "e"), ("e", "c"), ("f", "f"), ("a", "g")],
        )
        assert detect_cycles(graph) == [["a", "b"], ["c", "d", "e"], ["f"]]

    def test_acyclic_graph_returns_empty_list(self) -> None:
        graph = _digraph(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
        assert detect_cycles(graph) == []

    def test_empty_graph_returns_empty_list(self) -> None:
        assert detect_cycles(nx.DiGraph()) == []

    def test_result_is_sorted_lexicographically(self) -> None:
        # Components are added in reverse order; "a10" sorts before "a2" as strings.
        graph = _digraph(
            ["z1", "z2", "m", "a2", "a10", "b"],
            [("z1", "z2"), ("z2", "z1"), ("m", "m"), ("a2", "a10"), ("a10", "a2"), ("b", "b")],
        )
        result = detect_cycles(graph)
        assert result == [["a10", "a2"], ["b"], ["m"], ["z1", "z2"]]
        assert all(cycle == sorted(cycle) for cycle in result)

    def test_insertion_order_does_not_change_result(self) -> None:
        nodes = ["a", "b", "c", "d", "e", "f"]
        edges = [("a", "b"), ("b", "c"), ("c", "a"), ("d", "e"), ("e", "d"), ("f", "f"), ("c", "d")]
        baseline = detect_cycles(_digraph(nodes, edges))
        assert baseline == [["a", "b", "c"], ["d", "e"], ["f"]]
        for node_order in itertools.islice(itertools.permutations(nodes), 0, 720, 37):
            for edge_order in (edges, edges[::-1], edges[3:] + edges[:3]):
                graph = _digraph(list(node_order), list(edge_order))
                assert detect_cycles(graph) == baseline

    def test_graph_is_not_modified(self) -> None:
        graph = _digraph(["a", "b", "c"], [("a", "b"), ("b", "a"), ("c", "c")])
        graph.edges["a", "b"]["edge_type"] = "calls"
        before = _snapshot_graph(graph)
        detect_cycles(graph)
        assert _snapshot_graph(graph) == before

    def test_large_seeded_graph_finishes_within_five_seconds(self) -> None:
        rng = random.Random(20240601)
        node_count, edge_count = 10_000, 50_000
        nodes = [f"n{i:05d}" for i in range(node_count)]
        edges: set[tuple[str, str]] = set()
        while len(edges) < edge_count:
            edges.add((rng.choice(nodes), rng.choice(nodes)))
        graph = _digraph(nodes, sorted(edges))
        assert graph.number_of_nodes() == node_count
        assert graph.number_of_edges() == edge_count

        start = time.perf_counter()
        result = detect_cycles(graph)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0
        assert result == sorted(result)
        assert all(cycle == sorted(cycle) for cycle in result)
        # Average out-degree 5 gives one giant strongly connected component.
        assert len(result) >= 1
        assert max(len(cycle) for cycle in result) > node_count // 2


# ---------------------------------------------------------------------------
# Task 6.11: blast radius (Req 4.26 to 4.34, 6.8).
# Graphs are built directly with networkx. Expected values are written by hand.
# ---------------------------------------------------------------------------
from backend.engines.graph_engine import MissingTargetError, trace_blast_radius  # noqa: E402


def _calls_graph(
    symbols: list[str],
    calls: list[tuple[str, str]],
    imports: list[tuple[str, str]] | None = None,
    files: list[str] | None = None,
) -> nx.DiGraph:
    graph = nx.DiGraph()
    for name in files or []:
        graph.add_node(name, node_type="file")
    for name in symbols:
        graph.add_node(name, node_type="symbol")
    for source, target in calls:
        graph.add_edge(source, target, edge_type="calls")
    for source, target in imports or []:
        graph.add_edge(source, target, edge_type="imports")
    return graph


def _blast_chain() -> nx.DiGraph:
    # s1 -> s2 -> s3 -> s4 -> s5 -> s6 -> s7 over calls. The imports edges x -> s4 and
    # s4 -> y must be ignored. The file node f.py is not a Symbol. S = 9 symbols.
    names = [f"s{i}" for i in range(1, 8)]
    return _calls_graph(
        [*names, "x", "y"],
        list(zip(names, names[1:], strict=False)),
        imports=[("x", "s4"), ("s4", "y")],
        files=["f.py"],
    )


class TestTraceBlastRadius:
    @pytest.mark.parametrize(
        ("depth", "upstream", "downstream"),
        [
            (1, ["s3"], ["s5"]),
            (2, ["s2", "s3"], ["s5", "s6"]),
            (3, ["s1", "s2", "s3"], ["s5", "s6", "s7"]),
            (10, ["s1", "s2", "s3"], ["s5", "s6", "s7"]),
        ],
    )
    def test_exact_lists_per_depth(
        self, depth: int, upstream: list[str], downstream: list[str]
    ) -> None:
        result = trace_blast_radius(_blast_chain(), "s4", depth)
        assert isinstance(result, BlastRadius)
        assert result.target_id == "s4"
        assert result.upstream_callers == upstream
        assert result.downstream_callees == downstream

    def test_default_depth_is_three(self) -> None:
        graph = _calls_graph(
            [f"n{i}" for i in range(9)], [(f"n{i}", f"n{i + 1}") for i in range(8)]
        )
        result = trace_blast_radius(graph, "n4")
        assert result.upstream_callers == ["n1", "n2", "n3"]
        assert result.downstream_callees == ["n5", "n6", "n7"]

    def test_depth_zero_is_empty_with_zero_score(self) -> None:
        result = trace_blast_radius(_blast_chain(), "s4", 0)
        assert result.upstream_callers == []
        assert result.downstream_callees == []
        assert result.impact_score == 0.0

    def test_cycle_through_target_excludes_target(self) -> None:
        # a -> b -> c -> a, target b. Upstream follows c then a, downstream follows c then a.
        graph = _calls_graph(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
        result = trace_blast_radius(graph, "b", 5)
        assert result.upstream_callers == ["a", "c"]
        assert result.downstream_callees == ["a", "c"]
        assert "b" not in result.upstream_callers + result.downstream_callees

    def test_self_loop_does_not_include_target(self) -> None:
        graph = _calls_graph(["a", "b"], [("a", "a"), ("a", "b")])
        result = trace_blast_radius(graph, "a", 3)
        assert result.upstream_callers == []
        assert result.downstream_callees == ["b"]

    def test_diamond_has_no_duplicates_and_is_sorted(self) -> None:
        # top calls m2 and m1, both call bottom. Target bottom reaches top by two paths.
        graph = _calls_graph(
            ["top", "m2", "m1", "bottom"],
            [("top", "m2"), ("top", "m1"), ("m2", "bottom"), ("m1", "bottom")],
        )
        result = trace_blast_radius(graph, "bottom", 3)
        assert result.upstream_callers == ["m1", "m2", "top"]
        assert result.downstream_callees == []
        down = trace_blast_radius(graph, "top", 3).downstream_callees
        assert down == ["bottom", "m1", "m2"]
        assert len(set(down)) == len(down)

    def test_only_calls_edges_are_followed(self) -> None:
        graph = _calls_graph(["a", "b", "c"], [], imports=[("a", "b"), ("b", "c")])
        result = trace_blast_radius(graph, "b", 3)
        assert result.upstream_callers == []
        assert result.downstream_callees == []
        assert result.impact_score == 0.0

    def test_file_target_has_empty_lists(self) -> None:
        result = trace_blast_radius(_blast_chain(), "f.py", 3)
        assert result.upstream_callers == []
        assert result.downstream_callees == []
        assert result.impact_score == 0.0

    def test_missing_target_carries_target_id(self) -> None:
        with pytest.raises(MissingTargetError) as info:
            trace_blast_radius(_blast_chain(), "nope", 3)
        assert info.value.target_id == "nope"

    @pytest.mark.parametrize("bad", [-1, True, False, 1.0, "2", None])
    def test_invalid_depth_raises(self, bad: Any) -> None:
        with pytest.raises(InvalidArgumentError):
            trace_blast_radius(_blast_chain(), "s4", bad)

    def test_invalid_depth_is_checked_before_missing_target(self) -> None:
        with pytest.raises(InvalidArgumentError):
            trace_blast_radius(_blast_chain(), "nope", -1)

    def test_graph_is_not_modified(self) -> None:
        graph = _blast_chain()
        before = _snapshot_graph(graph)
        trace_blast_radius(graph, "s4", 3)
        assert _snapshot_graph(graph) == before

    def test_repeat_queries_are_equal(self) -> None:
        graph = _blast_chain()
        first = trace_blast_radius(graph, "s4", 3)
        assert trace_blast_radius(graph, "s4", 3) == first
        assert trace_blast_radius(_blast_chain(), "s4", 3) == first


class TestImpactScore:
    @pytest.mark.parametrize(
        ("depth", "expected"),
        [
            # S = 9 symbols. (2u + d) / 27 with u = d = depth.
            (1, 3 / 27),
            (2, 6 / 27),
            (3, 9 / 27),
        ],
    )
    def test_hand_computed_chain_scores(self, depth: int, expected: float) -> None:
        assert trace_blast_radius(_blast_chain(), "s4", depth).impact_score == pytest.approx(
            expected
        )

    def test_upstream_counts_double(self) -> None:
        # a -> b -> c, S = 3. Target c: u = 2, d = 0 gives 4/9. Target a: u = 0, d = 2 gives 2/9.
        graph = _calls_graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
        assert trace_blast_radius(graph, "c", 3).impact_score == pytest.approx(4 / 9)
        assert trace_blast_radius(graph, "a", 3).impact_score == pytest.approx(2 / 9)
        assert trace_blast_radius(graph, "b", 3).impact_score == pytest.approx(3 / 9)

    def test_zero_symbol_graph_scores_zero(self) -> None:
        graph = nx.DiGraph()
        graph.add_node("f.py", node_type="file")
        result = trace_blast_radius(graph, "f.py", 3)
        assert result.impact_score == 0.0
        assert result.upstream_callers == [] and result.downstream_callees == []

    def test_single_symbol_scores_zero(self) -> None:
        graph = _calls_graph(["a"], [])
        assert trace_blast_radius(graph, "a", 3).impact_score == 0.0

    def test_scores_stay_within_unit_interval_and_below_one(self) -> None:
        # Complete call graph on n symbols: u = d = n - 1, so score = (n - 1) / n.
        for n in (2, 3, 5, 8):
            names = [f"v{i}" for i in range(n)]
            graph = _calls_graph(names, [(a, b) for a in names for b in names if a != b])
            for name in names:
                score = trace_blast_radius(graph, name, 3).impact_score
                assert score == pytest.approx((n - 1) / n)
                assert 0.0 <= score < 1.0

    def test_monotonic_in_upstream_count(self) -> None:
        # Fixed downstream d = 1 and S = 8: one callee and k extra callers of the target.
        table = [(k, (2 * k + 1) / 24) for k in range(0, 6)]
        scores = []
        for k, expected in table:
            callers = [f"c{i}" for i in range(k)]
            graph = _calls_graph(
                ["t", "callee", *callers, *[f"pad{i}" for i in range(6 - k)]],
                [("t", "callee"), *[(c, "t") for c in callers]],
            )
            assert graph.number_of_nodes() == 8
            result = trace_blast_radius(graph, "t", 3)
            assert len(result.upstream_callers) == k
            assert result.impact_score == pytest.approx(expected)
            scores.append(result.impact_score)
        assert scores == sorted(scores)
        assert len(set(scores)) == len(scores)


# ---------------------------------------------------------------------------
# Snapshot assembly (task 6.12; Req 4.36, 4.37, 1.25, 1.27)
# Inputs are built directly; expected orderings are written out by hand.
# ---------------------------------------------------------------------------
import json  # noqa: E402

from backend.engines.graph_engine import build_snapshot  # noqa: E402


def _snap_files() -> list[FileAnalysis]:
    """Three files: a.py and b.py import each other, a.py::f calls a.py::g."""
    return [
        gfile(
            "a.py",
            ["b"],
            symbols=[
                gsymbol("a.py", "f", raw_calls=["g"]),
                gsymbol("a.py", "g"),
            ],
        ),
        gfile("b.py", ["a"]),
        gfile("c.py", ["a"]),
    ]


def _sig(**overrides: Any) -> DSASignal:
    return make_signal(**overrides)


class TestSnapshotAssembly:
    def test_identity_fields_are_passed_through(self) -> None:
        snap = build_snapshot("repo-1", "/tmp/root", [], [])
        assert snap.repo_id == "repo-1"
        assert snap.root_path == "/tmp/root"

    def test_files_sorted_by_file_path(self) -> None:
        files = [gfile("z.py"), gfile("a.py"), gfile("m/x.py"), gfile("b.py")]
        snap = build_snapshot("r", "/r", files, [])
        assert [f.file_path for f in snap.files] == ["a.py", "b.py", "m/x.py", "z.py"]

    def test_edges_sorted_by_source_target_type(self) -> None:
        snap = build_snapshot("r", "/r", _snap_files(), [])
        assert [(e.source, e.target, e.edge_type.value) for e in snap.edges] == [
            ("a.py", "b.py", "imports"),
            ("a.py::f", "a.py::g", "calls"),
            ("b.py", "a.py", "imports"),
            ("c.py", "a.py", "imports"),
        ]

    def test_dsa_signals_sorted_by_file_then_start_line(self) -> None:
        signals = [
            _sig(file_path="b.py", start_line=1, end_line=2, symbol_id="b.py::f"),
            _sig(file_path="a.py", start_line=9, end_line=12, symbol_id="a.py::h"),
            _sig(file_path="a.py", start_line=2, end_line=3, symbol_id="a.py::g"),
        ]
        snap = build_snapshot("r", "/r", [], signals)
        assert [(s.file_path, s.start_line) for s in snap.dsa_signals] == [
            ("a.py", 2),
            ("a.py", 9),
            ("b.py", 1),
        ]

    def test_signal_tie_on_file_and_start_line_broken_by_remaining_fields(self) -> None:
        # Every signal shares file_path and start_line; each differs from the previous
        # one only in the next field of the sort key, so the expected order is the list.
        base: dict[str, Any] = {
            "file_path": "a.py",
            "start_line": 3,
            "end_line": 5,
            "chapter": "Graphs & Trees",
            "pattern_name": "bfs",
            "symbol_id": "a.py::f",
            "confidence": 0.5,
            "evidence": ["queue at line 3"],
        }
        ordered = [
            _sig(**base),
            _sig(**{**base, "evidence": ["queue at line 3", "z at line 4"]}),
            _sig(**{**base, "confidence": 0.75}),
            _sig(**{**base, "symbol_id": "a.py::g"}),
            _sig(**{**base, "pattern_name": "dfs"}),
            _sig(**{**base, "chapter": "Hash Tables"}),
            _sig(**{**base, "end_line": 9}),
        ]
        # Sort key after (file_path, start_line) is end_line, chapter, pattern_name,
        # symbol_id, confidence, evidence.
        expected = sorted(
            ordered,
            key=lambda s: (
                s.end_line,
                s.chapter,
                s.pattern_name,
                s.symbol_id,
                s.confidence,
                tuple(s.evidence),
            ),
        )
        # Hand-written order: the end_line 5 group first, then end_line 9.
        assert [(s.end_line, s.chapter, s.pattern_name) for s in expected] == [
            (5, "Graphs & Trees", "bfs"),
            (5, "Graphs & Trees", "bfs"),
            (5, "Graphs & Trees", "bfs"),
            (5, "Graphs & Trees", "bfs"),
            (5, "Graphs & Trees", "dfs"),
            (5, "Hash Tables", "bfs"),
            (9, "Graphs & Trees", "bfs"),
        ]
        for permuted in (ordered, ordered[::-1], ordered[3:] + ordered[:3]):
            snap = build_snapshot("r", "/r", [], permuted)
            assert snap.dsa_signals == expected

    def test_equal_position_signals_ordered_by_chapter_then_pattern(self) -> None:
        a = _sig(chapter="Sorting & Binary Search", pattern_name="a-pattern")
        b = _sig(chapter="Hash Tables", pattern_name="z-pattern")
        c = _sig(chapter="Hash Tables", pattern_name="b-pattern")
        snap = build_snapshot("r", "/r", [], [a, b, c])
        assert [(s.chapter, s.pattern_name) for s in snap.dsa_signals] == [
            ("Hash Tables", "b-pattern"),
            ("Hash Tables", "z-pattern"),
            ("Sorting & Binary Search", "a-pattern"),
        ]

    def test_chapter_breaks_tie_before_symbol_id(self) -> None:
        first = _sig(chapter="Graphs & Trees", symbol_id="a.py::z")
        second = _sig(chapter="Hash Tables", symbol_id="a.py::a")
        snap = build_snapshot("r", "/r", [], [second, first])
        assert snap.dsa_signals == [first, second]

    def test_vital_organs_and_cycles_content(self) -> None:
        files = _snap_files()
        snap = build_snapshot("r", "/r", files, [])
        graph = build_graph(files)
        assert snap.vital_organs == compute_vital_organs(graph)
        assert set(snap.vital_organs) <= set(graph.nodes)
        assert snap.vital_organs[0] == "a.py"  # the most imported node ranks first
        assert snap.cycles == [["a.py", "b.py"]]

    def test_acyclic_input_has_no_cycles(self) -> None:
        files = [gfile("a.py", ["b"]), gfile("b.py")]
        assert build_snapshot("r", "/r", files, []).cycles == []

    def test_empty_input(self) -> None:
        snap = build_snapshot("r", "/r", [], [])
        assert snap.files == []
        assert snap.edges == []
        assert snap.vital_organs == []
        assert snap.cycles == []
        assert snap.dsa_signals == []

    def test_input_permutation_invariance(self) -> None:
        files = _snap_files()
        signals = [
            _sig(file_path="a.py", start_line=4, end_line=6),
            _sig(file_path="a.py", start_line=4, end_line=5, pattern_name="other"),
            _sig(file_path="c.py", start_line=1, end_line=2, symbol_id="c.py::q"),
        ]
        reference = build_snapshot("r", "/r", files, signals)
        for perm_files in itertools.permutations(files):
            for perm_signals in (signals, signals[::-1], signals[1:] + signals[:1]):
                assert build_snapshot("r", "/r", list(perm_files), list(perm_signals)) == reference

    def test_inputs_are_not_mutated(self) -> None:
        files = [gfile("b.py"), gfile("a.py")]
        signals = [_sig(file_path="b.py"), _sig(file_path="a.py")]
        build_snapshot("r", "/r", files, signals)
        assert [f.file_path for f in files] == ["b.py", "a.py"]
        assert [s.file_path for s in signals] == ["b.py", "a.py"]

    def test_json_round_trip_and_byte_identical_dump(self) -> None:
        signals = [
            _sig(file_path="b.py", start_line=2, end_line=4, symbol_id="b.py::f"),
            _sig(file_path="a.py", start_line=1, end_line=2, symbol_id="a.py::f"),
        ]
        snap = build_snapshot("r", "/r", _snap_files(), signals)
        dumped = snap.model_dump_json()
        restored = RepoGraphSnapshot.model_validate_json(dumped)
        assert restored == snap
        assert restored.model_dump_json() == dumped
        # Equivalent input in another order gives the same bytes.
        other = build_snapshot("r", "/r", _snap_files()[::-1], signals[::-1])
        assert other.model_dump_json() == dumped
        # The plain-dict form survives json.dumps / json.loads too.
        text = json.dumps(snap.model_dump(mode="json"), sort_keys=True)
        assert RepoGraphSnapshot.model_validate(json.loads(text)) == snap


# ---------------------------------------------------------------------------
# Task 8.3: DSA fixtures for the Hash Tables chapter
# Covers Requirements 5.6, 5.7, 5.21, 6.9, 6.10.
#
# Harness for all DSA chapter fixture tasks (8.3, 8.5, 8.7, 8.9, 8.11, 8.13,
# 8.14). A chapter task defines `DsaFixture` rows (positive) and plain
# (name, path, source) rows (negative look-alikes) and reuses:
#   scan_signals(path, source, chapter=None)  -> signals for one in-memory file
#   assert_positive(fixture)                  -> chapter, pattern, confidence,
#                                                Symbol range, evidence lines
#   assert_no_signals(name, signals, chapter) -> names fixture and signal on failure
# Expected values (confidence, lines, evidence text) are written out by hand
# from the design's confidence table and the fixture source. Every source
# string starts on line 1 so the line numbers in comments match the source.
# ---------------------------------------------------------------------------
import textwrap  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from backend.engines.dsa_scanner import scan_file  # noqa: E402


def dsa_src(text: str) -> str:
    """Dedent a fixture; the first source line is line 1."""
    return textwrap.dedent(text)


def scan_signals(path: str, source: str, chapter: str | None = None) -> list[DSASignal]:
    """Scan one in-memory file; optionally keep only one chapter's signals."""
    result = scan_file(path, source.encode("utf-8"))
    assert result.skipped == [], f"{path}: unexpectedly skipped: {result.skipped}"
    return [s for s in result.signals if chapter is None or s.chapter == chapter]


def assert_no_signals(
    fixture_name: str, signals: list[DSASignal], chapter: str | None = None
) -> None:
    """Fail naming the fixture and the first unexpected signal."""
    for signal in signals:
        if chapter is not None and signal.chapter != chapter:
            continue
        raise AssertionError(
            f"fixture {fixture_name!r}: unexpected signal "
            f"{signal.chapter} / {signal.pattern_name} "
            f"(confidence {signal.confidence}) for {signal.symbol_id} "
            f"at lines {signal.start_line}-{signal.end_line}; "
            f"evidence: {signal.evidence}"
        )


@dataclass(frozen=True)
class DsaFixture:
    name: str
    path: str
    source: str
    pattern: str
    confidence: float
    start_line: int  # Symbol range, by hand
    end_line: int
    evidence: tuple[str, ...]  # exact items, source order, by hand
    chapter: str = "Hash Tables"


_EVIDENCE_LINES = re.compile(r"at lines? (\d+)(?:-(\d+))?$")


def assert_positive(fx: DsaFixture) -> None:
    matches = [
        s for s in scan_signals(fx.path, fx.source, fx.chapter) if s.pattern_name == fx.pattern
    ]
    assert len(matches) == 1, f"{fx.name}: expected one {fx.pattern!r} signal, got {matches}"
    signal = matches[0]
    assert signal.chapter == fx.chapter, fx.name
    assert signal.file_path == fx.path, fx.name
    assert signal.confidence == fx.confidence, fx.name
    assert (signal.start_line, signal.end_line) == (fx.start_line, fx.end_line), fx.name
    assert signal.evidence == list(fx.evidence), fx.name
    for item in signal.evidence:
        found = _EVIDENCE_LINES.search(item)
        assert found is not None, f"{fx.name}: no line reference in {item!r}"
        first = int(found.group(1))
        last = int(found.group(2) or first)
        assert fx.start_line <= first <= last <= fx.end_line, f"{fx.name}: {item!r} outside Symbol"


_HASH = "Hash Tables"

_HASH_POSITIVE: list[DsaFixture] = [
    DsaFixture(  # lookup in a loop, create + lookup + insert (k=3)
        "py-lookup-with-insert",
        "lookup.py",
        dsa_src(
            """\
            def has_pair(nums, target):
                seen = {}
                for i, n in enumerate(nums):
                    if target - n in seen:
                        return True
                    seen[n] = i
                return False
            """
        ),
        "hash-table lookup",
        0.85,
        1,
        7,
        (
            "map seen created at line 2",
            "lookup in seen inside loop at line 4",
            "insert into seen at line 6",
        ),
    ),
    DsaFixture(  # create + lookup only (k=2)
        "py-lookup-no-insert",
        "lookup2.py",
        dsa_src(
            """\
            def count_known(words, known_list):
                known = set(known_list)
                total = 0
                for w in words:
                    if w in known:
                        total += 1
                return total
            """
        ),
        "hash-table lookup",
        0.70,
        1,
        7,
        ("set known created at line 2", "lookup in known inside loop at line 5"),
    ),
    DsaFixture(  # create + count update + in-loop (k=3)
        "py-frequency-in-loop",
        "freq.py",
        dsa_src(
            """\
            def count_words(words):
                counts = {}
                for w in words:
                    counts[w] = counts.get(w, 0) + 1
                return counts
            """
        ),
        "frequency counting",
        0.90,
        1,
        5,
        (
            "map counts created at line 2",
            "count update inside loop at line 4",
            "count update on counts at line 4",
        ),
    ),
    DsaFixture(  # create + count update, not in a loop (k=2)
        "py-frequency-outside-loop",
        "freq2.py",
        dsa_src(
            """\
            def bump(key):
                counts = {}
                counts[key] = counts.get(key, 0) + 1
                return counts
            """
        ),
        "frequency counting",
        0.75,
        1,
        4,
        ("map counts created at line 2", "count update on counts at line 3"),
    ),
    DsaFixture(  # create-set + guarded add in loop (k=3)
        "py-dedupe-guarded-add",
        "dedupe.py",
        dsa_src(
            """\
            def unique(items):
                seen = set()
                out = []
                for x in items:
                    if x not in seen:
                        seen.add(x)
                        out.append(x)
                return out
            """
        ),
        "de-duplication",
        0.85,
        1,
        8,
        (
            "set seen created at line 2",
            "guarded add inside loop at line 6",
            "guarded add to seen at line 6",
        ),
    ),
    DsaFixture(  # create-set + conversion back to a sequence (k=2)
        "py-dedupe-list-of-set",
        "dedupe2.py",
        dsa_src(
            """\
            def unique_values(items):
                return list(set(items))
            """
        ),
        "de-duplication",
        0.70,
        1,
        2,
        ("set converted to sequence at line 2", "set created at line 2"),
    ),
    DsaFixture(
        "js-frequency-map",
        "freq.js",
        dsa_src(
            """\
            function countChars(s) {
              const counts = new Map();
              for (const ch of s) {
                counts.set(ch, (counts.get(ch) ?? 0) + 1);
              }
              return counts;
            }
            """
        ),
        "frequency counting",
        0.90,
        1,
        7,
        (
            "map counts created at line 2",
            "count update inside loop at line 4",
            "count update on counts at line 4",
        ),
    ),
    DsaFixture(
        "ts-lookup-set",
        "lookup.ts",
        dsa_src(
            """\
            function hasDuplicate(nums: number[]): boolean {
              const seen = new Set<number>();
              for (const n of nums) {
                if (seen.has(n)) {
                  return true;
                }
                seen.add(n);
              }
              return false;
            }
            """
        ),
        "hash-table lookup",
        0.85,
        1,
        10,
        (
            "set seen created at line 2",
            "lookup in seen inside loop at line 4",
            "insert into seen at line 7",
        ),
    ),
    DsaFixture(
        "ts-dedupe-guarded-add",
        "dedupe.ts",
        dsa_src(
            """\
            function unique(items: string[]): string[] {
              const seen = new Set<string>();
              const out: string[] = [];
              for (const x of items) {
                if (!seen.has(x)) {
                  seen.add(x);
                  out.push(x);
                }
              }
              return out;
            }
            """
        ),
        "de-duplication",
        0.85,
        1,
        11,
        (
            "set seen created at line 2",
            "guarded add inside loop at line 6",
            "guarded add to seen at line 6",
        ),
    ),
    DsaFixture(  # Java method inside a class: Symbol range is the method, lines 2-8
        "java-frequency-merge",
        "Words.java",
        dsa_src(
            """\
            class Words {
                static Map<String, Integer> count(List<String> words) {
                    Map<String, Integer> counts = new HashMap<>();
                    for (String w : words) {
                        counts.merge(w, 1, Integer::sum);
                    }
                    return counts;
                }
            }
            """
        ),
        "frequency counting",
        0.90,
        2,
        8,
        (
            "map counts created at line 3",
            "count update inside loop at line 5",
            "count update on counts at line 5",
        ),
    ),
    DsaFixture(
        "java-lookup-containsKey",
        "Finder.java",
        dsa_src(
            """\
            class Finder {
                boolean hasPair(int[] nums, int target) {
                    Map<Integer, Integer> seen = new HashMap<>();
                    for (int n : nums) {
                        if (seen.containsKey(target - n)) {
                            return true;
                        }
                        seen.put(n, 1);
                    }
                    return false;
                }
            }
            """
        ),
        "hash-table lookup",
        0.85,
        2,
        11,
        (
            "map seen created at line 3",
            "lookup in seen inside loop at line 5",
            "insert into seen at line 8",
        ),
    ),
    DsaFixture(
        "java-dedupe-guarded-add",
        "Dedup.java",
        dsa_src(
            """\
            class Dedup {
                List<String> unique(List<String> items) {
                    Set<String> seen = new HashSet<>();
                    List<String> out = new ArrayList<>();
                    for (String s : items) {
                        if (!seen.contains(s)) {
                            seen.add(s);
                            out.add(s);
                        }
                    }
                    return out;
                }
            }
            """
        ),
        "de-duplication",
        0.85,
        2,
        12,
        (
            "set seen created at line 3",
            "guarded add inside loop at line 7",
            "guarded add to seen at line 7",
        ),
    ),
]

# Look-alikes that must produce zero Hash Tables signals (Req 5.7, 6.10).
_HASH_NEGATIVE: list[tuple[str, str, str]] = [
    ("py-returns-dict-literal", "n.py", dsa_src('def defaults():\n    return {"a": 1, "b": 2}\n')),
    ("py-returns-set-literal", "n.py", dsa_src("def vowels():\n    s = {1, 2, 3}\n    return s\n")),
    (
        "py-builds-dict-in-loop-and-returns",
        "n.py",
        dsa_src(
            """\
            def index(keys):
                d = {}
                for k in keys:
                    d[k] = k.upper()
                return d
            """
        ),
    ),
    (
        "py-declared-unused-set",
        "n.py",
        dsa_src("def f(items):\n    unused = set()\n    return len(items)\n"),
    ),
    (
        "py-membership-on-list",
        "n.py",
        dsa_src(
            """\
            def dup(items):
                seen = []
                for i in items:
                    if i in seen:
                        return True
                    seen.append(i)
                return False
            """
        ),
    ),
    (
        "py-membership-on-parameter",
        "n.py",
        dsa_src(
            """\
            def keep(items, allowed):
                out = []
                for i in items:
                    if i in allowed:
                        out.append(i)
                return out
            """
        ),
    ),
    (
        "py-count-update-on-list",
        "n.py",
        dsa_src(
            "def tally(xs):\n    counts = [0, 0, 0]\n"
            "    for x in xs:\n        counts[x] += 1\n    return counts\n"
        ),
    ),
    (
        "js-returns-map",
        "n.js",
        dsa_src("function make() {\n  const m = new Map();\n  m.set('a', 1);\n  return m;\n}\n"),
    ),
    (
        "js-declared-unused-set",
        "n.js",
        dsa_src("function f(items) {\n  const s = new Set();\n  return items.length;\n}\n"),
    ),
    (
        "ts-membership-on-parameter",
        "n.ts",
        dsa_src(
            """\
            function keep(items: string[], allowed: Set<string>): string[] {
              const out: string[] = [];
              for (const i of items) {
                if (allowed.has(i)) {
                  out.push(i);
                }
              }
              return out;
            }
            """
        ),
    ),
    (
        "ts-membership-on-array",
        "n.ts",
        dsa_src(
            """\
            function dup(items: string[]): boolean {
              const seen: string[] = [];
              for (const i of items) {
                if (seen.includes(i)) {
                  return true;
                }
                seen.push(i);
              }
              return false;
            }
            """
        ),
    ),
    (
        "java-returns-map",
        "N.java",
        dsa_src(
            """\
            class N {
                Map<String, Integer> build() {
                    Map<String, Integer> m = new HashMap<>();
                    m.put("a", 1);
                    return m;
                }
            }
            """
        ),
    ),
    (
        "java-declared-unused-set",
        "N.java",
        dsa_src(
            "class N {\n    int f() {\n        Set<String> s = new HashSet<>();\n"
            "        return 1;\n    }\n}\n"
        ),
    ),
    (
        "java-membership-on-parameter",
        "N.java",
        dsa_src(
            """\
            class N {
                int f(Set<String> allowed, List<String> items) {
                    int n = 0;
                    for (String i : items) {
                        if (allowed.contains(i)) {
                            n++;
                        }
                    }
                    return n;
                }
            }
            """
        ),
    ),
    (
        "java-membership-on-list",
        "N.java",
        dsa_src(
            """\
            class N {
                boolean dup(List<String> items) {
                    List<String> seen = new ArrayList<>();
                    for (String i : items) {
                        if (seen.contains(i)) {
                            return true;
                        }
                        seen.add(i);
                    }
                    return false;
                }
            }
            """
        ),
    ),
]


class TestHashTablesPositive:
    @pytest.mark.parametrize("fixture", _HASH_POSITIVE, ids=lambda fx: fx.name)
    def test_signal_matches_hand_written_expectation(self, fixture: DsaFixture) -> None:
        assert_positive(fixture)

    def test_covers_each_pattern_in_python_and_one_ecmascript_and_java_case(self) -> None:
        by_ext = {(fx.path.rsplit(".", 1)[1], fx.pattern) for fx in _HASH_POSITIVE}
        for pattern in ("hash-table lookup", "frequency counting", "de-duplication"):
            assert ("py", pattern) in by_ext
        assert any(ext in ("ts", "js") for ext, _ in by_ext)
        assert any(ext == "java" for ext, _ in by_ext)


class TestHashTablesNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _HASH_NEGATIVE, ids=lambda v: str(v)[:40])
    def test_look_alike_has_no_hash_table_signal(self, name: str, path: str, source: str) -> None:
        assert_no_signals(name, scan_signals(path, source), _HASH)

    def test_failure_message_names_fixture_and_signal(self) -> None:
        fx = _HASH_POSITIVE[0]
        with pytest.raises(AssertionError) as info:
            assert_no_signals("my-fixture", scan_signals(fx.path, fx.source), _HASH)
        message = str(info.value)
        assert "my-fixture" in message
        assert "Hash Tables" in message
        assert "hash-table lookup" in message


# ---------------------------------------------------------------------------
# Task 8.5: DSA fixtures for the Graphs & Trees chapter
# Covers Requirements 5.8, 5.9, 5.21, 6.9, 6.10.
# Reuses the task 8.3 harness (dsa_src, scan_signals, DsaFixture,
# assert_positive, assert_no_signals). Expected confidence comes from the design
# table: queue 0.60/0.75/0.90, stack 0.65/0.80, recursive 0.70/0.85 for k=1/2/3.
# ---------------------------------------------------------------------------
_GRAPH = "Graphs & Trees"
_GRAPH_POSITIVE: list[DsaFixture] = [
    DsaFixture(  # BFS: deque.popleft + visited + neighbor loop (k=3)
        "py-bfs-deque-visited",
        "bfs.py",
        dsa_src(
            """\
            def bfs(graph, start):
                visited = {start}
                queue = deque([start])
                while queue:
                    node = queue.popleft()
                    for nxt in graph[node]:
                        if nxt not in visited:
                            visited.add(nxt)
                            queue.append(nxt)
                return visited
            """
        ),
        "queue-based traversal",
        0.90,
        1,
        10,
        (
            "queue pop on queue inside loop at line 5",
            "loop over neighbors of popped value at lines 6-9",
            "visited visited tested and added at line 7",
        ),
        _GRAPH,
    ),
    DsaFixture(  # Req 5.8: pop(0) on a plain work list is a queue pop, k=1
        "py-pop-zero-work-list",
        "worklist.py",
        dsa_src(
            """\
            def drain(work):
                out = []
                while work:
                    item = work.pop(0)
                    out.append(item)
                return out
            """
        ),
        "queue-based traversal",
        0.60,
        1,
        6,
        ("queue pop on work inside loop at line 4",),
        _GRAPH,
    ),
    DsaFixture(  # stack DFS: pop() + push + visited + neighbor loop (k=3)
        "py-dfs-stack-visited",
        "dfs.py",
        dsa_src(
            """\
            def dfs(graph, start):
                visited = set()
                stack = [start]
                while stack:
                    node = stack.pop()
                    if node in visited:
                        continue
                    visited.add(node)
                    for nxt in graph[node]:
                        stack.append(nxt)
                return visited
            """
        ),
        "stack-based traversal",
        0.80,
        1,
        11,
        (
            "stack pop on stack in while loop at line 5",
            "visited visited tested and added at line 6",
            "loop over neighbors of popped value at lines 9-10",
        ),
        _GRAPH,
    ),
    DsaFixture(  # recursive tree walk over left and right (k=2)
        "py-recursive-left-right",
        "tree.py",
        dsa_src(
            """\
            def inorder(node, out):
                if node is None:
                    return out
                inorder(node.left, out)
                out.append(node.val)
                inorder(node.right, out)
                return out
            """
        ),
        "recursive node traversal",
        0.70,
        1,
        7,
        (
            "self-call to inorder at line 4",
            "child access in call arguments or loop iterable at line 4",
        ),
        _GRAPH,
    ),
    DsaFixture(  # JS BFS: shift + visited Set + neighbor loop (k=3)
        "js-bfs-shift-visited",
        "bfs.js",
        dsa_src(
            """\
            function bfs(graph, start) {
              const visited = new Set([start]);
              const queue = [start];
              while (queue.length > 0) {
                const node = queue.shift();
                for (const next of graph[node]) {
                  if (!visited.has(next)) {
                    visited.add(next);
                    queue.push(next);
                  }
                }
              }
              return visited;
            }
            """
        ),
        "queue-based traversal",
        0.90,
        1,
        14,
        (
            "queue pop on queue inside loop at line 5",
            "loop over neighbors of popped value at lines 6-11",
            "visited visited tested and added at line 7",
        ),
        _GRAPH,
    ),
    DsaFixture(  # Java BFS: ArrayDeque.poll + visited set + neighbor loop (k=3)
        "java-bfs-poll-visited",
        "G.java",
        dsa_src(
            """\
            class G {
                void bfs(Map<Integer, List<Integer>> g, int s) {
                    Queue<Integer> q = new ArrayDeque<>();
                    Set<Integer> seen = new HashSet<>();
                    q.add(s);
                    while (!q.isEmpty()) {
                        int n = q.poll();
                        for (int m : g.get(n)) {
                            if (seen.add(m)) {
                                q.add(m);
                            }
                        }
                    }
                }
            }
            """
        ),
        "queue-based traversal",
        0.90,
        2,
        14,
        (
            "queue pop on q inside loop at line 7",
            "loop over neighbors of popped value at lines 8-12",
            "visited seen tested and added at line 9",
        ),
        _GRAPH,
    ),
]
# Look-alikes that must produce zero Graphs & Trees signals (Req 5.9, 6.10).
_GRAPH_NEGATIVE: list[tuple[str, str, str]] = [
    (
        "py-nested-loops-over-sequences",
        "n.py",
        dsa_src(
            """\
            def pairs(a, b):
                out = []
                for x in a:
                    for y in b:
                        out.append((x, y))
                return out
            """
        ),
    ),
    (
        "py-loop-over-matrix",
        "n.py",
        dsa_src(
            """\
            def total(matrix):
                s = 0
                for row in matrix:
                    for cell in row:
                        s += cell
                return s
            """
        ),
    ),
    (
        "py-sequential-pop-no-visited",
        "n.py",
        dsa_src(
            """\
            def reverse(items):
                out = []
                while items:
                    out.append(items.pop())
                return out
            """
        ),
    ),
    (
        "py-recursion-without-node-access",
        "n.py",
        dsa_src("def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n"),
    ),
    (
        "js-nested-loops-over-arrays",
        "n.js",
        dsa_src(
            """\
            function pairs(a, b) {
              const out = [];
              for (const x of a) {
                for (const y of b) {
                  out.push([x, y]);
                }
              }
              return out;
            }
            """
        ),
    ),
    (
        "java-nested-loops-over-lists",
        "N.java",
        dsa_src(
            """\
            class N {
                int count(List<Integer> a, List<Integer> b) {
                    int n = 0;
                    for (int x : a) {
                        for (int y : b) {
                            n += x * y;
                        }
                    }
                    return n;
                }
            }
            """
        ),
    ),
]


class TestGraphsTreesPositive:
    @pytest.mark.parametrize("fixture", _GRAPH_POSITIVE, ids=lambda fx: fx.name)
    def test_signal_matches_hand_written_expectation(self, fixture: DsaFixture) -> None:
        assert_positive(fixture)

    def test_covers_each_pattern_with_a_python_and_an_ecmascript_and_java_case(self) -> None:
        patterns = {fx.pattern for fx in _GRAPH_POSITIVE}
        assert patterns == {
            "queue-based traversal",
            "stack-based traversal",
            "recursive node traversal",
        }
        extensions = {fx.path.rsplit(".", 1)[1] for fx in _GRAPH_POSITIVE}
        assert {"py", "js", "java"} <= extensions


class TestGraphsTreesNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _GRAPH_NEGATIVE, ids=lambda v: str(v)[:40])
    def test_look_alike_has_no_graphs_trees_signal(self, name: str, path: str, source: str) -> None:
        assert_no_signals(name, scan_signals(path, source), _GRAPH)


# ---------------------------------------------------------------------------
# Task 8.7: DSA fixtures for the Recursion & Dynamic Programming chapter
# Covers Requirements 5.10, 5.11, 5.12, 5.21, 6.9, 6.10.
# Reuses the task 8.3 harness (dsa_src, scan_signals, DsaFixture,
# assert_positive, assert_no_signals). Expected confidence comes from the design
# table: direct recursion 0.80/0.90/0.95, memoization (decorator) 0.85/0.90,
# memoization (manual) 0.90, for k=1/2/3 (k counts required plus optional kinds).
# Symbol ranges include decorator lines.
# ---------------------------------------------------------------------------
_REC = "Recursion & Dynamic Programming"
_REC_POSITIVE: list[DsaFixture] = [
    DsaFixture(  # self-call + base case (k=2)
        "py-factorial",
        "fact.py",
        dsa_src(
            """\
            def factorial(n):
                if n <= 1:
                    return 1
                return n * factorial(n - 1)
            """
        ),
        "direct recursion",
        0.90,
        1,
        4,
        (
            "base case with return before first self-call at lines 2-3",
            "self-call to factorial at line 4",
        ),
        _REC,
    ),
    DsaFixture(  # self-call + base case + two self-call sites (k=3)
        "py-fib-two-calls",
        "fibtwo.py",
        dsa_src(
            """\
            def fib(n):
                if n < 2:
                    return n
                return fib(n - 1) + fib(n - 2)
            """
        ),
        "direct recursion",
        0.95,
        1,
        4,
        (
            "base case with return before first self-call at lines 2-3",
            "self-call to fib at line 4",
            "second self-call to fib at line 4",
        ),
        _REC,
    ),
    DsaFixture(  # self-call only, no base-case if (k=1)
        "py-bare-self-call",
        "bare.py",
        dsa_src(
            """\
            def forever(n):
                return forever(n + 1)
            """
        ),
        "direct recursion",
        0.80,
        1,
        2,
        ("self-call to forever at line 2",),
        _REC,
    ),
    DsaFixture(  # decorator + self-call (k=2)
        "py-lru-cache",
        "lru.py",
        dsa_src(
            """\
            from functools import lru_cache

            @lru_cache(maxsize=None)
            def fib(n):
                if n < 2:
                    return n
                return fib(n - 1) + fib(n - 2)
            """
        ),
        "memoization",
        0.90,
        3,
        7,
        ("cache decorator @lru_cache(maxsize=None) at line 3", "self-call to fib at line 7"),
        _REC,
    ),
    DsaFixture(  # dotted decorator without a call (k=2)
        "py-functools-cache",
        "fcache.py",
        dsa_src(
            """\
            import functools

            @functools.cache
            def fib(n):
                if n < 2:
                    return n
                return fib(n - 1) + fib(n - 2)
            """
        ),
        "memoization",
        0.90,
        3,
        7,
        ("cache decorator @functools.cache at line 3", "self-call to fib at line 7"),
        _REC,
    ),
    DsaFixture(  # decorator on a function that never calls itself (k=1)
        "py-lru-cache-no-self-call",
        "lru1.py",
        dsa_src(
            """\
            from functools import lru_cache

            @lru_cache
            def square(n):
                return n * n
            """
        ),
        "memoization",
        0.85,
        3,
        5,
        ("cache decorator @lru_cache at line 3",),
        _REC,
    ),
    DsaFixture(  # manual memo: lookup, self-call, store on the same name (k=3)
        "py-manual-memo-dict",
        "memo.py",
        dsa_src(
            """\
            def fib(n, memo):
                if n in memo:
                    return memo[n]
                result = fib(n - 1, memo) + fib(n - 2, memo)
                memo[n] = result
                return result
            """
        ),
        "memoization",
        0.90,
        1,
        6,
        (
            "lookup in memo before self-call at line 2",
            "self-call to fib at line 4",
            "store in memo after self-call at line 5",
        ),
        _REC,
    ),
    DsaFixture(  # method recursing through self.f
        "py-method-self-call",
        "calc.py",
        dsa_src(
            """\
            class Calc:
                def total(self, n):
                    if n == 0:
                        return 0
                    return n + self.total(n - 1)
            """
        ),
        "direct recursion",
        0.90,
        2,
        5,
        (
            "base case with return before first self-call at lines 3-4",
            "self-call to total at line 5",
        ),
        _REC,
    ),
    DsaFixture(  # JavaScript
        "js-factorial",
        "fact.js",
        dsa_src(
            """\
            function factorial(n) {
              if (n <= 1) {
                return 1;
              }
              return n * factorial(n - 1);
            }
            """
        ),
        "direct recursion",
        0.90,
        1,
        6,
        (
            "base case with return before first self-call at lines 2-4",
            "self-call to factorial at line 5",
        ),
        _REC,
    ),
    DsaFixture(  # Java
        "java-factorial",
        "Fact.java",
        dsa_src(
            """\
            class Fact {
                static int factorial(int n) {
                    if (n <= 1) {
                        return 1;
                    }
                    return n * factorial(n - 1);
                }
            }
            """
        ),
        "direct recursion",
        0.90,
        2,
        7,
        (
            "base case with return before first self-call at lines 3-5",
            "self-call to factorial at line 6",
        ),
        _REC,
    ),
]

# Both memoization rows match (decorator and manual dict) on one Symbol. The
# rows share the pattern name, so one signal remains. Both rows give 0.90 here
# (decorator k=2, manual k=3); evidence is merged in source order.
_REC_BOTH_MEMO = DsaFixture(
    "py-decorator-plus-manual-memo",
    "both.py",
    dsa_src(
        """\
        from functools import lru_cache

        @lru_cache(maxsize=None)
        def fib(n, memo):
            if n in memo:
                return memo[n]
            result = fib(n - 1, memo) + fib(n - 2, memo)
            memo[n] = result
            return result
        """
    ),
    "memoization",
    0.90,
    3,
    9,
    (
        "cache decorator @lru_cache(maxsize=None) at line 3",
        "lookup in memo before self-call at line 5",
        "self-call to fib at line 7",
        "store in memo after self-call at line 8",
    ),
    _REC,
)

# Look-alikes that must produce zero Recursion & DP signals (Req 5.12, 6.10).
_REC_NEGATIVE: list[tuple[str, str, str]] = [
    (
        "py-repeated-calls-to-others",
        "others.py",
        dsa_src(
            """\
            def run(items):
                a = prep(items)
                b = prep(a)
                return finish(b)
            """
        ),
    ),
    (
        "py-cached-property-and-custom-cache",
        "notcache.py",
        dsa_src(
            """\
            from functools import cached_property

            class A:
                @cached_property
                def size(self):
                    return compute(1)

            @my_cache
            def g(n):
                return h(n)
            """
        ),
    ),
    (
        "py-mutual-recursion",
        "mutual.py",
        dsa_src(
            """\
            def is_even(n):
                if n == 0:
                    return True
                return is_odd(n - 1)

            def is_odd(n):
                if n == 0:
                    return False
                return is_even(n - 1)
            """
        ),
    ),
    (
        "js-calls-other-functions",
        "others.js",
        dsa_src(
            """\
            function run(items) {
              const a = prep(items);
              const b = prep(a);
              return finish(b);
            }
            """
        ),
    ),
]


class TestRecursionDpPositive:
    @pytest.mark.parametrize("fixture", _REC_POSITIVE, ids=lambda fx: fx.name)
    def test_signal_matches_hand_written_expectation(self, fixture: DsaFixture) -> None:
        assert_positive(fixture)

    def test_covers_python_javascript_and_java(self) -> None:
        extensions = {fx.path.rsplit(".", 1)[1] for fx in _REC_POSITIVE}
        assert {"py", "js", "java"} <= extensions

    def test_direct_recursion_and_memoization_names_differ(self) -> None:
        patterns = {fx.pattern for fx in _REC_POSITIVE}
        assert patterns == {"direct recursion", "memoization"}

    def test_memoized_function_also_reports_direct_recursion(self) -> None:
        signals = scan_signals("lru.py", _REC_POSITIVE[3].source, _REC)
        assert sorted(s.pattern_name for s in signals) == ["direct recursion", "memoization"]

    def test_both_memoization_rows_merge_into_one_signal(self) -> None:
        assert_positive(_REC_BOTH_MEMO)
        signals = scan_signals(_REC_BOTH_MEMO.path, _REC_BOTH_MEMO.source, _REC)
        assert [s.pattern_name for s in signals].count("memoization") == 1


class TestRecursionDpNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _REC_NEGATIVE, ids=lambda v: str(v)[:40])
    def test_look_alike_has_no_recursion_signal(self, name: str, path: str, source: str) -> None:
        assert_no_signals(name, scan_signals(path, source), _REC)


# ---------------------------------------------------------------------------
# Task 8.9: DSA fixtures for the Heaps & Priority Queues chapter
# Covers Requirements 5.13, 5.14, 5.21, 6.9, 6.10.
# Reuses the task 8.3 harness (dsa_src, scan_signals, DsaFixture,
# assert_positive, assert_no_signals). Expected confidence comes from the design
# table: heapq operations 0.80/0.90/0.95 and priority queue usage 0.75/0.90 for
# k=1/2/3. heapq k counts the required push-or-pop call, the push+pop pair, and
# heapify. Priority queue k counts creation plus put-like and get-like calls.
# ---------------------------------------------------------------------------
_HEAP = "Heaps & Priority Queues"
_HEAP_POSITIVE: list[DsaFixture] = [
    DsaFixture(  # heapify + push + pop (k=3)
        "py-heapify-push-pop",
        "heap_all.py",
        dsa_src(
            """\
            import heapq
            def smallest(xs):
                h = list(xs)
                heapq.heapify(h)
                heapq.heappush(h, 1)
                return heapq.heappop(h)
            """
        ),
        "heapq operations",
        0.95,
        2,
        6,
        (
            "heapq call heapq.heapify at line 4",
            "heapq call heapq.heappush at line 5",
            "heapq call heapq.heappop at line 6",
        ),
        _HEAP,
    ),
    DsaFixture(  # push + pop, bare names via `from heapq import` (k=2)
        "py-push-pop-bare-names",
        "heap_pair.py",
        dsa_src(
            """\
            from heapq import heappush, heappop
            def smallest(xs):
                h = []
                for x in xs:
                    heappush(h, x)
                return heappop(h)
            """
        ),
        "heapq operations",
        0.90,
        2,
        6,
        ("heapq call heappush at line 5", "heapq call heappop at line 6"),
        _HEAP,
    ),
    DsaFixture(  # bare push only (k=1)
        "py-push-only",
        "heap_push.py",
        dsa_src(
            """\
            import heapq
            def add(h, x):
                heapq.heappush(h, x)
            """
        ),
        "heapq operations",
        0.80,
        2,
        3,
        ("heapq call heapq.heappush at line 3",),
        _HEAP,
    ),
    DsaFixture(  # queue.PriorityQueue creation + put + get (k=3)
        "py-priority-queue-put-get",
        "pq.py",
        dsa_src(
            """\
            import queue
            def drain(xs):
                pq = queue.PriorityQueue()
                for x in xs:
                    pq.put(x)
                return pq.get()
            """
        ),
        "priority queue usage",
        0.90,
        2,
        6,
        (
            "pq created as PriorityQueue at line 3",
            "put-like call on pq at line 5",
            "get-like call on pq at line 6",
        ),
        _HEAP,
    ),
    DsaFixture(  # creation + put only (k=2)
        "py-priority-queue-put-only",
        "pq_put.py",
        dsa_src(
            """\
            import queue
            def fill(xs):
                pq = queue.PriorityQueue()
                pq.put(xs)
                return pq
            """
        ),
        "priority queue usage",
        0.75,
        2,
        5,
        ("pq created as PriorityQueue at line 3", "put-like call on pq at line 4"),
        _HEAP,
    ),
    DsaFixture(  # Java PriorityQueue offer + poll
        "java-priority-queue-offer-poll",
        "Pq.java",
        dsa_src(
            """\
            import java.util.PriorityQueue;
            class Pq {
                int smallest(int[] xs) {
                    PriorityQueue<Integer> pq = new PriorityQueue<>();
                    for (int x : xs) {
                        pq.offer(x);
                    }
                    return pq.poll();
                }
            }
            """
        ),
        "priority queue usage",
        0.90,
        3,
        9,
        (
            "pq created as PriorityQueue at line 4",
            "put-like call on pq at line 6",
            "get-like call on pq at line 8",
        ),
        _HEAP,
    ),
    DsaFixture(  # TypeScript MinHeap-style
        "ts-min-heap",
        "heap.ts",
        dsa_src(
            """\
            function smallest(xs: number[]) {
              const heap = new MinHeap();
              for (const x of xs) {
                heap.push(x);
              }
              return heap.pop();
            }
            """
        ),
        "priority queue usage",
        0.90,
        1,
        7,
        (
            "heap created as MinHeap at line 2",
            "put-like call on heap at line 4",
            "get-like call on heap at line 6",
        ),
        _HEAP,
    ),
]

# Look-alikes that must produce zero Heaps & Priority Queues signals (Req 5.14, 6.10).
_HEAP_NEGATIVE: list[tuple[str, str, str]] = [
    (
        "py-imports-heapq-no-call",
        "imp_heapq.py",
        dsa_src(
            """\
            import heapq
            def total(xs):
                return sum(xs)
            """
        ),
    ),
    (
        "py-imports-queue-no-call",
        "imp_queue.py",
        dsa_src(
            """\
            import queue
            from queue import PriorityQueue
            def total(xs):
                return sum(xs)
            """
        ),
    ),
    (
        "py-heapify-alone",  # design: heapify is optional, so it never matches by itself
        "heapify.py",
        dsa_src(
            """\
            import heapq
            def build(xs):
                heapq.heapify(xs)
                return xs
            """
        ),
    ),
    (
        "py-bare-heappush-without-heapq-import",
        "no_import.py",
        dsa_src(
            """\
            def add(h, x):
                heappush(h, x)
            """
        ),
    ),
    (
        "py-priority-queue-created-never-used",
        "pq_unused.py",
        dsa_src(
            """\
            import queue
            def make():
                pq = queue.PriorityQueue()
                return pq
            """
        ),
    ),
    (
        "ts-min-heap-never-used",
        "unused.ts",
        dsa_src(
            """\
            function make() {
              const heap = new MinHeap();
              return heap;
            }
            """
        ),
    ),
    (
        "java-priority-queue-never-used",
        "Unused.java",
        dsa_src(
            """\
            import java.util.PriorityQueue;
            class Unused {
                Object make() {
                    PriorityQueue<Integer> pq = new PriorityQueue<>();
                    return pq;
                }
            }
            """
        ),
    ),
    (
        "py-plain-list-append-pop",
        "plain_list.py",
        dsa_src(
            """\
            def stack_ops(xs):
                items = []
                for x in xs:
                    items.append(x)
                return items.pop()
            """
        ),
    ),
    (
        "py-variable-named-heap",
        "named_heap.py",
        dsa_src(
            """\
            def total(xs):
                heap = 0
                for x in xs:
                    heap += x
                return heap
            """
        ),
    ),
    (
        "js-variable-named-heap",
        "named_heap.js",
        dsa_src(
            """\
            function total(xs) {
              const heap = [];
              for (const x of xs) {
                heap.push(x);
              }
              return heap.pop();
            }
            """
        ),
    ),
]


class TestHeapsPriorityQueuesPositive:
    @pytest.mark.parametrize("fixture", _HEAP_POSITIVE, ids=lambda fx: fx.name)
    def test_signal_matches_hand_written_expectation(self, fixture: DsaFixture) -> None:
        assert_positive(fixture)

    def test_covers_python_typescript_and_java(self) -> None:
        extensions = {fx.path.rsplit(".", 1)[1] for fx in _HEAP_POSITIVE}
        assert {"py", "ts", "java"} <= extensions

    def test_covers_both_pattern_names(self) -> None:
        assert {fx.pattern for fx in _HEAP_POSITIVE} == {
            "heapq operations",
            "priority queue usage",
        }


class TestHeapsPriorityQueuesNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _HEAP_NEGATIVE, ids=lambda v: str(v)[:40])
    def test_look_alike_has_no_heaps_signal(self, name: str, path: str, source: str) -> None:
        assert_no_signals(name, scan_signals(path, source), _HEAP)


# ---------------------------------------------------------------------------
# Task 8.11: DSA fixtures for the Sorting & Binary Search chapter
# Covers Requirements 5.15, 5.16, 5.21, 6.9, 6.10.
# Reuses the task 8.3 harness (dsa_src, scan_signals, DsaFixture,
# assert_positive, assert_no_signals). Expected confidence comes from the design
# table: bisect usage 0.85/0.90 (k=1: one call site, k=2: a second site),
# binary search 0.80/0.90 (k=2: midpoint + narrowing, k=3: plus a loop condition
# comparing the boundaries; evidence is listed in source order), custom sort
# key 0.65/0.80 (k=2: sort call + key function, k=3: the key is a cmp_to_key
# call or a nested def).
# ---------------------------------------------------------------------------
_SORT = "Sorting & Binary Search"
_SORT_POSITIVE: list[DsaFixture] = [
    DsaFixture(  # one bisect call site (k=1)
        "py-bisect-left",
        "bisect_one.py",
        dsa_src(
            """\
            import bisect
            def find(xs, x):
                i = bisect.bisect_left(xs, x)
                return i
            """
        ),
        "bisect usage",
        0.85,
        2,
        4,
        ("bisect call bisect_left at line 3",),
        _SORT,
    ),
    DsaFixture(  # two distinct bisect call sites (k=2)
        "py-bisect-two-sites",
        "bisect_two.py",
        dsa_src(
            """\
            import bisect
            def insert(xs, x):
                i = bisect.bisect_left(xs, x)
                bisect.insort(xs, x)
                return i
            """
        ),
        "bisect usage",
        0.90,
        2,
        5,
        ("bisect call bisect_left at line 3", "bisect call insort at line 4"),
        _SORT,
    ),
    DsaFixture(  # midpoint + narrowing + loop condition (k=3)
        "py-binary-search-loop-condition",
        "bsearch.py",
        dsa_src(
            """\
            def search(xs, target):
                lo, hi = 0, len(xs) - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    if xs[mid] < target:
                        lo = mid + 1
                    elif xs[mid] > target:
                        hi = mid - 1
                    else:
                        return mid
                return -1
            """
        ),
        "binary search",
        0.90,
        1,
        11,
        (
            "loop condition compares lo and hi at lines 3-10",
            "midpoint of lo and hi at line 4",
            "boundary narrowed under comparison at line 6",
        ),
        _SORT,
    ),
    DsaFixture(  # midpoint + narrowing, `while True` has no boundary comparison (k=2)
        "py-binary-search-no-loop-condition",
        "bsearch_true.py",
        dsa_src(
            """\
            def search(xs, target):
                lo, hi = 0, len(xs) - 1
                while True:
                    mid = lo + (hi - lo) // 2
                    if xs[mid] < target:
                        lo = mid + 1
                    else:
                        hi = mid
                    if lo >= hi:
                        return lo
            """
        ),
        "binary search",
        0.80,
        1,
        10,
        (
            "midpoint of lo and hi at line 4",
            "boundary narrowed under comparison at line 6",
        ),
        _SORT,
    ),
    DsaFixture(  # key=lambda (k=2)
        "py-sorted-key-lambda",
        "sorted_key.py",
        dsa_src(
            """\
            def by_length(words):
                return sorted(words, key=lambda w: len(w))
            """
        ),
        "custom sort key",
        0.65,
        1,
        2,
        ("sorted call at line 2", "key function lambda w: len(w) at line 2"),
        _SORT,
    ),
    DsaFixture(  # list.sort with key (k=2)
        "py-list-sort-key",
        "sort_key.py",
        dsa_src(
            """\
            def order(rows):
                rows.sort(key=lambda r: r[0])
                return rows
            """
        ),
        "custom sort key",
        0.65,
        1,
        3,
        ("sort call at line 2", "key function lambda r: r[0] at line 2"),
        _SORT,
    ),
    DsaFixture(  # cmp_to_key key (k=3)
        "py-sort-cmp-to-key",
        "sort_cmp.py",
        dsa_src(
            """\
            import functools
            def order(rows, cmp):
                rows.sort(key=functools.cmp_to_key(cmp))
                return rows
            """
        ),
        "custom sort key",
        0.80,
        2,
        4,
        ("sort call at line 3", "key function functools.cmp_to_key(cmp) at line 3"),
        _SORT,
    ),
    DsaFixture(  # TypeScript binary search with Math.floor midpoint (k=3)
        "ts-binary-search",
        "bsearch.ts",
        dsa_src(
            """\
            function search(xs: number[], target: number): number {
              let lo = 0;
              let hi = xs.length - 1;
              while (lo <= hi) {
                const mid = Math.floor((lo + hi) / 2);
                if (xs[mid] < target) {
                  lo = mid + 1;
                } else {
                  hi = mid - 1;
                }
              }
              return -1;
            }
            """
        ),
        "binary search",
        0.90,
        1,
        13,
        (
            "loop condition compares lo and hi at lines 4-11",
            "midpoint of lo and hi at line 5",
            "boundary narrowed under comparison at line 7",
        ),
        _SORT,
    ),
    DsaFixture(  # JavaScript sort with a comparator arrow function (k=2)
        "js-sort-arrow-comparator",
        "sort_cmp.js",
        dsa_src(
            """\
            function order(rows) {
              rows.sort((a, b) => a.id - b.id);
              return rows;
            }
            """
        ),
        "custom sort key",
        0.65,
        1,
        4,
        ("sort call at line 2", "key function (a, b) => a.id - b.id at line 2"),
        _SORT,
    ),
    DsaFixture(  # Java binary search with (a + b) / 2 midpoint (k=3)
        "java-binary-search",
        "Search.java",
        dsa_src(
            """\
            class Search {
                int find(int[] xs, int target) {
                    int lo = 0;
                    int hi = xs.length - 1;
                    while (lo <= hi) {
                        int mid = (lo + hi) / 2;
                        if (xs[mid] < target) {
                            lo = mid + 1;
                        } else {
                            hi = mid - 1;
                        }
                    }
                    return -1;
                }
            }
            """
        ),
        "binary search",
        0.90,
        2,
        14,
        (
            "loop condition compares lo and hi at lines 5-12",
            "midpoint of lo and hi at line 6",
            "boundary narrowed under comparison at line 8",
        ),
        _SORT,
    ),
]

# Look-alikes that must produce zero Sorting & Binary Search signals (Req 5.16, 6.10).
_SORT_NEGATIVE: list[tuple[str, str, str]] = [
    (
        "py-midpoint-without-narrowing",  # midpoint, but boundary moves outside any comparison
        "mid_py.py",
        dsa_src(
            """\
            def middle(xs):
                lo, hi = 0, len(xs)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if xs[mid] < 0:
                        count = 1
                    lo = mid + 1
                return lo
            """
        ),
    ),
    (
        "ts-midpoint-without-narrowing",
        "mid_ts.ts",
        dsa_src(
            """\
            function middle(xs: number[]): number {
              let lo = 0;
              let hi = xs.length;
              while (lo < hi) {
                const mid = Math.floor((lo + hi) / 2);
                if (xs[mid] < 0) {
                  console.log(mid);
                }
                lo = mid + 1;
              }
              return lo;
            }
            """
        ),
    ),
    (
        "java-midpoint-without-narrowing",
        "Mid.java",
        dsa_src(
            """\
            class Mid {
                int middle(int[] xs) {
                    int lo = 0;
                    int hi = xs.length;
                    while (lo < hi) {
                        int mid = (lo + hi) / 2;
                        if (xs[mid] < 0) {
                            System.out.println(mid);
                        }
                        lo = mid + 1;
                    }
                    return lo;
                }
            }
            """
        ),
    ),
    (
        "py-sorted-without-key",
        "sorted_plain.py",
        dsa_src(
            """\
            def ordered(xs):
                return sorted(xs)
            """
        ),
    ),
    (
        "py-sorted-reverse-only",
        "sorted_reverse.py",
        dsa_src(
            """\
            def ordered(xs):
                return sorted(xs, reverse=True)
            """
        ),
    ),
    (
        "py-list-sort-without-key",
        "sort_plain.py",
        dsa_src(
            """\
            def ordered(xs):
                xs.sort()
                return xs
            """
        ),
    ),
    (
        "ts-sort-without-comparator",
        "sort_plain.ts",
        dsa_src(
            """\
            function ordered(xs: string[]) {
              xs.sort();
              return xs;
            }
            """
        ),
    ),
    (
        "java-collections-sort-without-comparator",
        "SortPlain.java",
        dsa_src(
            """\
            import java.util.Collections;
            import java.util.List;
            class SortPlain {
                void ordered(List<Integer> xs) {
                    Collections.sort(xs);
                }
            }
            """
        ),
    ),
    (
        "py-variable-named-mid-used-elsewhere",
        "named_mid.py",
        dsa_src(
            """\
            def doubled(xs):
                out = []
                for x in xs:
                    mid = x * 2
                    if x < 0:
                        out.append(mid)
                return out
            """
        ),
    ),
    (
        "js-variable-named-mid-used-elsewhere",
        "named_mid.js",
        dsa_src(
            """\
            function doubled(xs) {
              const out = [];
              for (const x of xs) {
                const mid = x * 2;
                if (x < 0) {
                  out.push(mid);
                }
              }
              return out;
            }
            """
        ),
    ),
    (
        "py-imports-bisect-no-call",
        "imp_bisect.py",
        dsa_src(
            """\
            import bisect
            from bisect import bisect_left
            def total(xs):
                return sum(xs)
            """
        ),
    ),
]


class TestSortingBinarySearchPositive:
    @pytest.mark.parametrize("fixture", _SORT_POSITIVE, ids=lambda fx: fx.name)
    def test_signal_matches_hand_written_expectation(self, fixture: DsaFixture) -> None:
        assert_positive(fixture)

    def test_covers_python_typescript_javascript_and_java(self) -> None:
        extensions = {fx.path.rsplit(".", 1)[1] for fx in _SORT_POSITIVE}
        assert {"py", "ts", "js", "java"} <= extensions

    def test_covers_all_three_pattern_names(self) -> None:
        assert {fx.pattern for fx in _SORT_POSITIVE} == {
            "bisect usage",
            "binary search",
            "custom sort key",
        }


class TestSortingBinarySearchNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _SORT_NEGATIVE, ids=lambda v: str(v)[:40])
    def test_look_alike_has_no_sorting_signal(self, name: str, path: str, source: str) -> None:
        assert_no_signals(name, scan_signals(path, source), _SORT)


# ---------------------------------------------------------------------------
# Task 8.13: DSA fixtures for the Sliding Window / Two Pointers chapter
# Covers Requirements 5.17, 5.18, 5.21, 6.9, 6.10.
# Reuses the task 8.3 harness (dsa_src, scan_signals, DsaFixture,
# assert_positive, assert_no_signals). Expected confidence comes from the design
# table: two pointers 0.75 / 0.90 (k=3: pointer init at opposite ends or a
# shared start + conditional move + both used as indices of one sequence;
# k=4: plus a loop condition comparing both pointers). Evidence is listed in
# source order. When both pointers move, the first pointer's move is reported.
# ---------------------------------------------------------------------------
_TWO = "Sliding Window / Two Pointers"
_TWO_POSITIVE: list[DsaFixture] = [
    DsaFixture(  # opposite ends, `while True` does not compare the pointers (k=3)
        "py-opposite-ends",
        "opposite.py",
        dsa_src(
            """\
            def pair_sum(xs, target):
                lo = 0
                hi = len(xs) - 1
                while True:
                    if xs[lo] + xs[hi] < target:
                        lo += 1
                    else:
                        hi -= 1
                return lo, hi
            """
        ),
        "two pointers",
        0.75,
        1,
        9,
        (
            "pointers lo and hi at opposite ends at line 2",
            "lo and hi index xs at line 5",
            "conditional move of lo at line 6",
        ),
        _TWO,
    ),
    DsaFixture(  # opposite ends with `while lo < hi` (k=4)
        "py-opposite-ends-bounded",
        "opposite_bounded.py",
        dsa_src(
            """\
            def pair_sum(xs, target):
                lo = 0
                hi = len(xs) - 1
                while lo < hi:
                    if xs[lo] + xs[hi] < target:
                        lo += 1
                    else:
                        hi -= 1
                return lo, hi
            """
        ),
        "two pointers",
        0.90,
        1,
        9,
        (
            "pointers lo and hi at opposite ends at line 2",
            "loop condition compares lo and hi at lines 4-8",
            "lo and hi index xs at line 5",
            "conditional move of lo at line 6",
        ),
        _TWO,
    ),
    DsaFixture(  # shared start, window pair over one string (k=3)
        "py-shared-start-window",
        "window.py",
        dsa_src(
            """\
            def window(s):
                left = 0
                right = 0
                while True:
                    if s[right] == s[left]:
                        right += 1
                    else:
                        left += 1
                return s[left:right]
            """
        ),
        "two pointers",
        0.75,
        1,
        9,
        (
            "pointers left and right at shared start at line 2",
            "left and right index s at line 5",
            "conditional move of left at line 8",
        ),
        _TWO,
    ),
    DsaFixture(  # JavaScript, opposite ends with a bounding condition (k=4)
        "js-opposite-ends-bounded",
        "pair.js",
        dsa_src(
            """\
            function pairSum(xs, t) {
              let lo = 0;
              let hi = xs.length - 1;
              while (lo < hi) {
                if (xs[lo] + xs[hi] < t) {
                  lo++;
                } else {
                  hi--;
                }
              }
              return [lo, hi];
            }
            """
        ),
        "two pointers",
        0.90,
        1,
        12,
        (
            "pointers lo and hi at opposite ends at line 2",
            "loop condition compares lo and hi at lines 4-10",
            "lo and hi index xs at line 5",
            "conditional move of lo at line 6",
        ),
        _TWO,
    ),
    DsaFixture(  # TypeScript, shared start (k=3)
        "ts-shared-start",
        "window.ts",
        dsa_src(
            """\
            function window(s: string): string {
              let left = 0;
              let right = 0;
              while (true) {
                if (s[right] === s[left]) {
                  right++;
                } else {
                  left++;
                }
              }
              return s.slice(left, right);
            }
            """
        ),
        "two pointers",
        0.75,
        1,
        12,
        (
            "pointers left and right at shared start at line 2",
            "left and right index s at line 5",
            "conditional move of left at line 8",
        ),
        _TWO,
    ),
    DsaFixture(  # Java, opposite ends with a bounding condition (k=4)
        "java-opposite-ends-bounded",
        "Pair.java",
        dsa_src(
            """\
            class Pair {
                static int[] find(int[] xs, int t) {
                    int lo = 0;
                    int hi = xs.length - 1;
                    while (lo < hi) {
                        if (xs[lo] + xs[hi] < t) {
                            lo++;
                        } else {
                            hi--;
                        }
                    }
                    return new int[] {lo, hi};
                }
            }
            """
        ),
        "two pointers",
        0.90,
        2,
        13,
        (
            "pointers lo and hi at opposite ends at line 3",
            "loop condition compares lo and hi at lines 5-11",
            "lo and hi index xs at line 6",
            "conditional move of lo at line 7",
        ),
        _TWO,
    ),
]

# Look-alikes that must produce zero Sliding Window / Two Pointers signals
# (Req 5.18, 6.10).
_TWO_NEGATIVE: list[tuple[str, str, str]] = [
    (
        "py-only-one-pointer-indexed",
        "one_indexed.py",
        dsa_src(
            """\
            def scan(xs, t):
                lo = 0
                hi = len(xs) - 1
                while lo < hi:
                    if xs[lo] < t:
                        lo += 1
                    else:
                        hi -= 1
                return lo
            """
        ),
    ),
    (
        "py-pointers-never-updated",
        "never_updated.py",
        dsa_src(
            """\
            def scan(xs, t):
                lo = 0
                hi = len(xs) - 1
                for _ in range(3):
                    if xs[lo] + xs[hi] < t:
                        print("small")
                return lo
            """
        ),
    ),
    (
        "py-pointers-updated-unconditionally",
        "unconditional.py",
        dsa_src(
            """\
            def scan(xs):
                lo = 0
                hi = len(xs) - 1
                while lo < hi:
                    print(xs[lo], xs[hi])
                    lo += 1
                    hi -= 1
            """
        ),
    ),
    (
        "py-pointers-index-different-sequences",
        "two_sequences.py",
        dsa_src(
            """\
            def merge_like(xs, ys):
                i = 0
                j = 0
                while True:
                    if xs[i] < ys[j]:
                        i += 1
                    else:
                        j += 1
            """
        ),
    ),
    (
        "py-single-counter-loop",
        "counter.py",
        dsa_src(
            """\
            def total(xs):
                i = 0
                s = 0
                while i < len(xs):
                    if xs[i] > 0:
                        s += xs[i]
                    i += 1
                return s
            """
        ),
    ),
    (
        "py-nested-matrix-loops",
        "matrix.py",
        dsa_src(
            """\
            def count(grid, n, m):
                c = 0
                for i in range(n):
                    for j in range(m):
                        if grid[i][j]:
                            c += 1
                return c
            """
        ),
    ),
    (
        "js-nested-matrix-loops",
        "matrix.js",
        dsa_src(
            """\
            function count(grid, n, m) {
              let c = 0;
              for (let i = 0; i < n; i++) {
                for (let j = 0; j < m; j++) {
                  if (grid[i][j]) {
                    c++;
                  }
                }
              }
              return c;
            }
            """
        ),
    ),
    (
        "java-pointers-index-different-arrays",
        "Two.java",
        dsa_src(
            """\
            class Two {
                static int f(int[] xs, int[] ys) {
                    int i = 0;
                    int j = 0;
                    while (i < 10) {
                        if (xs[i] < ys[j]) {
                            i++;
                        } else {
                            j++;
                        }
                    }
                    return i;
                }
            }
            """
        ),
    ),
]

# Design behavior: Req 5.17 needs only "at least one" pointer moved
# conditionally, so a loop where one pointer moves under a condition and the
# other moves unconditionally still matches once init and indexing hold.
_TWO_ONE_CONDITIONAL = DsaFixture(
    "py-one-pointer-conditional",
    "one_conditional.py",
    dsa_src(
        """\
        def scan(xs, t):
            lo = 0
            hi = len(xs) - 1
            while True:
                if xs[lo] < t:
                    lo += 1
                hi -= 1
                if xs[hi] < 0:
                    break
            return lo
        """
    ),
    "two pointers",
    0.75,
    1,
    10,
    (
        "pointers lo and hi at opposite ends at line 2",
        "lo and hi index xs at line 5",
        "conditional move of lo at line 6",
    ),
    _TWO,
)


class TestTwoPointersPositive:
    @pytest.mark.parametrize("fixture", _TWO_POSITIVE, ids=lambda fx: fx.name)
    def test_signal_matches_hand_written_expectation(self, fixture: DsaFixture) -> None:
        assert_positive(fixture)

    def test_covers_python_javascript_typescript_and_java(self) -> None:
        extensions = {fx.path.rsplit(".", 1)[1] for fx in _TWO_POSITIVE}
        assert {"py", "js", "ts", "java"} <= extensions

    def test_covers_both_confidence_levels(self) -> None:
        assert {fx.confidence for fx in _TWO_POSITIVE} == {0.75, 0.90}

    def test_only_one_conditionally_moved_pointer_still_matches(self) -> None:
        assert_positive(_TWO_ONE_CONDITIONAL)


class TestTwoPointersNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _TWO_NEGATIVE, ids=lambda v: str(v)[:40])
    def test_look_alike_has_no_two_pointers_signal(self, name: str, path: str, source: str) -> None:
        assert_no_signals(name, scan_signals(path, source), _TWO)


# ---------------------------------------------------------------------------
# Task 8.14: negative fixtures for non-pattern code (Req 5.19, 6.9, 6.10).
# Ordinary application code must produce zero signals in ANY chapter, so these
# scans use no chapter filter. Each fixture is (name, path, source).
# ---------------------------------------------------------------------------
_NON_PATTERN: list[tuple[str, str, str]] = [
    # --- CRUD operations -------------------------------------------------
    (
        "py-crud-repository",
        "user_repo.py",
        dsa_src(
            """\
            class UserRepository:
                def __init__(self, session):
                    self.session = session

                def create(self, name, email):
                    user = User(name=name, email=email)
                    self.session.add(user)
                    self.session.commit()
                    return user

                def get(self, user_id):
                    return self.session.query(User).filter(User.id == user_id).first()

                def update(self, user_id, **fields):
                    user = self.get(user_id)
                    if user is None:
                        raise LookupError(user_id)
                    for key, value in fields.items():
                        setattr(user, key, value)
                    self.session.commit()
                    return user

                def delete(self, user_id):
                    user = self.get(user_id)
                    if user is not None:
                        self.session.delete(user)
                        self.session.commit()
            """
        ),
    ),
    (
        "py-crud-service-list",
        "user_service.py",
        dsa_src(
            """\
            def list_active_users(session, limit):
                rows = session.query(User).filter(User.active.is_(True)).limit(limit).all()
                result = []
                for row in rows:
                    result.append({"id": row.id, "name": row.name})
                return result
            """
        ),
    ),
    (
        "ts-crud-repository",
        "userRepo.ts",
        dsa_src(
            """\
            export class UserRepository {
              constructor(private db: Db) {}

              async create(name: string, email: string): Promise<User> {
                const user = await this.db.insert("users", { name, email });
                return user;
              }

              async get(id: number): Promise<User | null> {
                return this.db.findOne("users", { id });
              }

              async update(id: number, fields: Partial<User>): Promise<User> {
                const existing = await this.get(id);
                if (existing === null) {
                  throw new Error("not found");
                }
                return this.db.update("users", id, fields);
              }

              async remove(id: number): Promise<void> {
                await this.db.delete("users", { id });
              }
            }
            """
        ),
    ),
    (
        "java-crud-repository",
        "UserRepository.java",
        dsa_src(
            """\
            public class UserRepository {
                private final EntityManager em;

                public UserRepository(EntityManager em) {
                    this.em = em;
                }

                public User create(String name, String email) {
                    User user = new User(name, email);
                    em.persist(user);
                    return user;
                }

                public User find(long id) {
                    return em.find(User.class, id);
                }

                public User update(long id, String name) {
                    User user = em.find(User.class, id);
                    if (user == null) {
                        throw new IllegalArgumentException("missing");
                    }
                    user.setName(name);
                    return em.merge(user);
                }

                public void delete(long id) {
                    User user = em.find(User.class, id);
                    if (user != null) {
                        em.remove(user);
                    }
                }
            }
            """
        ),
    ),
    # --- API routing -----------------------------------------------------
    (
        "py-fastapi-routes",
        "routes.py",
        dsa_src(
            """\
            from fastapi import APIRouter, HTTPException

            router = APIRouter()

            @router.get("/items/{item_id}")
            def read_item(item_id: int, db=None):
                item = db.get(item_id)
                if item is None:
                    raise HTTPException(status_code=404, detail="not found")
                return {"id": item.id, "name": item.name}

            @router.post("/items", status_code=201)
            def create_item(payload, db=None):
                item = db.create(payload)
                return {"id": item.id}
            """
        ),
    ),
    (
        "py-flask-route",
        "app.py",
        dsa_src(
            """\
            def register(app, service):
                @app.route("/health", methods=["GET"])
                def health():
                    return jsonify(status="ok")

                @app.route("/users/<int:user_id>", methods=["DELETE"])
                def remove_user(user_id):
                    service.delete(user_id)
                    return "", 204
            """
        ),
    ),
    (
        "js-express-routes",
        "routes.js",
        dsa_src(
            """\
            function register(app, service) {
              app.get("/users/:id", async (req, res) => {
                const user = await service.find(req.params.id);
                if (!user) {
                  return res.status(404).json({ error: "not found" });
                }
                return res.json(user);
              });

              app.post("/users", async (req, res) => {
                const created = await service.create(req.body);
                res.status(201).json(created);
              });
            }
            """
        ),
    ),
    (
        "java-spring-controller",
        "UserController.java",
        dsa_src(
            """\
            @RestController
            @RequestMapping("/users")
            public class UserController {
                private final UserService service;

                public UserController(UserService service) {
                    this.service = service;
                }

                @GetMapping("/{id}")
                public ResponseEntity<User> get(@PathVariable long id) {
                    return ResponseEntity.ok(service.find(id));
                }

                @PostMapping
                public ResponseEntity<User> create(@RequestBody UserRequest body) {
                    User created = service.create(body.getName(), body.getEmail());
                    return ResponseEntity.status(201).body(created);
                }
            }
            """
        ),
    ),
    # --- Configuration loading -------------------------------------------
    (
        "py-config-env-and-json",
        "config.py",
        dsa_src(
            """\
            import json
            import os

            def load_settings(path):
                defaults = {"host": "localhost", "port": 8000, "debug": False}
                settings = dict(defaults)
                if os.path.exists(path):
                    with open(path) as handle:
                        settings.update(json.load(handle))
                settings["host"] = os.environ.get("APP_HOST", settings["host"])
                settings["port"] = int(os.environ.get("APP_PORT", settings["port"]))
                return settings
            """
        ),
    ),
    (
        "py-config-yaml-defaults",
        "yaml_config.py",
        dsa_src(
            """\
            import yaml

            def read_config(stream):
                data = yaml.safe_load(stream) or {}
                name = data.get("name", "service")
                retries = data.get("retries", 3)
                return name, retries
            """
        ),
    ),
    (
        "ts-config-loader",
        "config.ts",
        dsa_src(
            """\
            export function loadConfig(raw: string | undefined): Config {
              const parsed = raw ? JSON.parse(raw) : {};
              return {
                host: process.env.APP_HOST ?? parsed.host ?? "localhost",
                port: Number(process.env.APP_PORT ?? parsed.port ?? 8000),
                debug: parsed.debug === true,
              };
            }
            """
        ),
    ),
    (
        "java-config-properties",
        "AppConfig.java",
        dsa_src(
            """\
            public class AppConfig {
                public static AppConfig load(String path) throws IOException {
                    Properties props = new Properties();
                    try (FileInputStream in = new FileInputStream(path)) {
                        props.load(in);
                    }
                    String host = props.getProperty("host", "localhost");
                    int port = Integer.parseInt(props.getProperty("port", "8000"));
                    return new AppConfig(host, port);
                }
            }
            """
        ),
    ),
    # --- Plain loops -----------------------------------------------------
    (
        "py-loop-sum",
        "loops.py",
        dsa_src(
            """\
            def total(values):
                result = 0
                for v in values:
                    result += v
                return result
            """
        ),
    ),
    (
        "py-loop-print-enumerate-build",
        "loops2.py",
        dsa_src(
            """\
            def report(names):
                lines = []
                for index, name in enumerate(names):
                    print(index, name)
                    lines.append(f"{index}: {name}")
                return lines
            """
        ),
    ),
    (
        "py-loop-while-countdown",
        "countdown.py",
        dsa_src(
            """\
            def countdown(n):
                while n > 0:
                    print(n)
                    n -= 1
            """
        ),
    ),
    (
        "js-loop-sum-and-print",
        "loops.js",
        dsa_src(
            """\
            function summarize(values) {
              let sum = 0;
              for (let i = 0; i < values.length; i++) {
                sum += values[i];
                console.log(i, values[i]);
              }
              return sum;
            }
            """
        ),
    ),
    (
        "java-loop-sum-and-build",
        "Loops.java",
        dsa_src(
            """\
            public class Loops {
                static List<String> label(int[] values) {
                    List<String> out = new ArrayList<>();
                    int sum = 0;
                    for (int i = 0; i < values.length; i++) {
                        sum += values[i];
                        out.add(i + ":" + values[i]);
                    }
                    System.out.println(sum);
                    return out;
                }
            }
            """
        ),
    ),
    # --- Simple transforms -----------------------------------------------
    (
        "py-transform-comprehension",
        "transforms.py",
        dsa_src(
            """\
            def clean(names):
                trimmed = [n.strip() for n in names]
                return [n.title() for n in trimmed if n]
            """
        ),
    ),
    (
        "py-transform-map-filter-format",
        "transforms2.py",
        dsa_src(
            """\
            def render(prices):
                positive = filter(lambda p: p > 0, prices)
                doubled = map(lambda p: p * 2, positive)
                return ", ".join("${:.2f}".format(p) for p in doubled)
            """
        ),
    ),
    (
        "ts-transform-map-filter",
        "transforms.ts",
        dsa_src(
            """\
            export function labels(users: User[]): string[] {
              return users
                .filter((u) => u.active)
                .map((u) => `${u.name} <${u.email}>`);
            }
            """
        ),
    ),
    (
        "java-transform-stream",
        "Transforms.java",
        dsa_src(
            """\
            public class Transforms {
                static List<String> upper(List<String> names) {
                    return names.stream()
                        .filter(n -> !n.isEmpty())
                        .map(String::toUpperCase)
                        .collect(Collectors.toList());
                }
            }
            """
        ),
    ),
]


class TestNonPatternCodeNegative:
    @pytest.mark.parametrize(("name", "path", "source"), _NON_PATTERN, ids=lambda v: str(v)[:40])
    def test_ordinary_code_has_no_signals_in_any_chapter(
        self, name: str, path: str, source: str
    ) -> None:
        assert_no_signals(name, scan_signals(path, source))

    def test_covers_each_category_in_python_and_another_language(self) -> None:
        names = {name for name, _, _ in _NON_PATTERN}
        for category in ("crud", "routes", "config", "loop", "transform"):
            in_cat = {n for n in names if category in n or (category == "routes" and "route" in n)}
            if category == "routes":
                in_cat |= {n for n in names if "controller" in n}
            assert any(n.startswith("py-") for n in in_cat), category
            assert any(not n.startswith("py-") for n in in_cat), category

    def test_failure_message_names_fixture_and_signal(self) -> None:
        source = dsa_src(
            """\
            def count_words(words):
                counts = {}
                for w in words:
                    counts[w] = counts.get(w, 0) + 1
                return counts
            """
        )
        with pytest.raises(AssertionError, match=r"'sanity'.*frequency counting"):
            assert_no_signals("sanity", scan_signals("s.py", source))


# ---------------------------------------------------------------------------
# Task 8.15: unit tests for scanner behavior
# Covers Requirements 5.3, 5.4, 5.5, 5.21, 5.22, 5.24, 5.25, 5.26.
#
# Reuses the DSA harness above (dsa_src, scan_signals, the positive fixture
# lists). Fixtures here are small and written by hand; the cross-chapter
# bounds checks run over every positive fixture already defined.
# ---------------------------------------------------------------------------
import ast as _py_ast  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
from typing import get_args as _get_args  # noqa: E402

from backend.domain.models import DSAChapter as _DSAChapter  # noqa: E402
from backend.engines import dsa_scanner as _dsa_scanner  # noqa: E402
from backend.engines.dsa_scanner import (  # noqa: E402
    CONFIDENCE_TABLE,
    MAX_EVIDENCE_ITEMS,
    MAX_EVIDENCE_LENGTH,
    SkipReason,
    scan_many,
)

_ALL_POSITIVE: list[DsaFixture] = [
    *_HASH_POSITIVE,
    *_GRAPH_POSITIVE,
    *_REC_POSITIVE,
    *_HEAP_POSITIVE,
    *_SORT_POSITIVE,
    *_TWO_POSITIVE,
]
_SIX_CHAPTERS = {
    "Hash Tables",
    "Graphs & Trees",
    "Recursion & Dynamic Programming",
    "Heaps & Priority Queues",
    "Sorting & Binary Search",
    "Sliding Window / Two Pointers",
}

_HAS_PAIR = dsa_src(
    """\
    def has_pair(nums, target):
        seen = {}
        for i, n in enumerate(nums):
            if target - n in seen:
                return True
            seen[n] = i
        return False
    """
)
_FACTORIAL = dsa_src(
    """\
    def fact(n):
        if n <= 1:
            return 1
        return n * fact(n - 1)
    """
)


def _all_fixture_signals() -> list[tuple[DsaFixture, DSASignal]]:
    pairs = []
    for fx in _ALL_POSITIVE:
        for signal in scan_signals(fx.path, fx.source):
            pairs.append((fx, signal))
    return pairs


def _sort_tuple(s: DSASignal) -> tuple[str, int, str, str]:
    return (s.file_path, s.start_line, s.chapter, s.pattern_name)


class TestScannerEvidenceAndChapters:
    def test_evidence_bounds_hold_for_every_fixture_signal(self) -> None:
        pairs = _all_fixture_signals()
        assert pairs
        for fx, signal in pairs:
            where = f"{fx.name}: {signal.pattern_name}"
            assert 1 <= len(signal.evidence) <= MAX_EVIDENCE_ITEMS, where
            for item in signal.evidence:
                assert 0 < len(item) <= MAX_EVIDENCE_LENGTH, where
                found = _EVIDENCE_LINES.search(item)
                assert found is not None, f"{where}: no line reference in {item!r}"
                assert item[: found.start()].strip(), f"{where}: no construct in {item!r}"
                first = int(found.group(1))
                last = int(found.group(2) or first)
                assert signal.start_line <= first <= last <= signal.end_line, where

    def test_very_long_identifiers_keep_evidence_within_200_chars(self) -> None:
        name = "very_long_identifier_" * 20
        source = dsa_src(
            f"""\
            def f(nums, target):
                {name} = {{}}
                for n in nums:
                    if target - n in {name}:
                        return True
                    {name}[n] = 1
                return False
            """
        )
        signals = scan_signals("long.py", source, "Hash Tables")
        assert signals
        for signal in signals:
            assert all(len(item) <= MAX_EVIDENCE_LENGTH for item in signal.evidence)

    def test_chapter_is_one_of_the_six_values(self) -> None:
        assert set(_get_args(_DSAChapter)) == _SIX_CHAPTERS
        for fx, signal in _all_fixture_signals():
            assert signal.chapter in _SIX_CHAPTERS, fx.name

    def test_every_chapter_is_exercised_by_positive_fixtures(self) -> None:
        assert {fx.chapter for fx in _ALL_POSITIVE} == _SIX_CHAPTERS


class TestScannerConfidenceTable:
    def test_table_is_non_decreasing_in_k_with_two_decimals(self) -> None:
        for key, row in CONFIDENCE_TABLE.items():
            values = [row[k] for k in sorted(row)]
            assert values == sorted(values), key
            for value in values:
                assert 0.0 < value <= 1.0, key
                assert round(value, 2) == value, key

    def test_confidence_for_matches_table_and_clamps(self) -> None:
        for key, row in CONFIDENCE_TABLE.items():
            for k, value in row.items():
                assert _dsa_scanner.confidence_for(key, k) == value, (key, k)
            assert _dsa_scanner.confidence_for(key, 0) == row[min(row)]
            assert _dsa_scanner.confidence_for(key, 99) == row[max(row)]

    def test_signal_confidence_is_a_table_value_for_its_pattern(self) -> None:
        allowed: dict[str, set[float]] = {}
        for key, row in CONFIDENCE_TABLE.items():
            pattern = "memoization" if key.startswith("memoization") else key
            allowed.setdefault(pattern, set()).update(row.values())
        for fx, signal in _all_fixture_signals():
            assert signal.confidence in allowed[signal.pattern_name], (fx.name, signal)


class TestScannerOrdering:
    def test_signals_sorted_and_unique_per_symbol_chapter_pattern(self) -> None:
        source = _HAS_PAIR + "\n" + _FACTORIAL.replace("fact", "fact2") + "\n" + _FACTORIAL
        signals = scan_signals("multi.py", source)
        assert len(signals) >= 3
        assert signals == sorted(signals, key=lambda s: (*_sort_tuple(s), s.end_line, s.symbol_id))
        keys = [(s.symbol_id, s.chapter, s.pattern_name) for s in signals]
        assert len(keys) == len(set(keys))

    def test_all_fixture_signals_are_sorted_and_unique(self) -> None:
        for fx in _ALL_POSITIVE:
            signals = scan_signals(fx.path, fx.source)
            assert [_sort_tuple(s) for s in signals] == sorted(_sort_tuple(s) for s in signals)
            keys = [(s.symbol_id, s.chapter, s.pattern_name) for s in signals]
            assert len(keys) == len(set(keys)), fx.name

    def test_scan_many_sorts_globally_across_files(self) -> None:
        # Deliberately passed out of path order.
        files = [
            ("z_mod.py", _HAS_PAIR),
            ("a_mod.py", _FACTORIAL),
            (
                "m_mod.js",
                "function fact(n) { if (n <= 1) { return 1; } return n * fact(n - 1); }\n",
            ),
        ]
        parsed = [parse_source(path, src.encode()) for path, src in files]
        result = scan_many(parsed)
        assert result.skipped == []
        assert {s.file_path for s in result.signals} == {"a_mod.py", "m_mod.js", "z_mod.py"}
        order = [_sort_tuple(s) for s in result.signals]
        assert order == sorted(order)
        assert order[0][0] == "a_mod.py"
        assert order[-1][0] == "z_mod.py"
        assert scan_many(list(reversed(parsed))).signals == result.signals


class TestScannerFileHandling:
    def test_parse_errors_skip_erroneous_symbols_but_scan_valid_ones(self) -> None:
        source = _HAS_PAIR + "\ndef broken(x:\n    return (1 +\n"
        parsed = parse_source("err.py", source.encode())
        assert parsed.analysis.parse_errors
        result = scan_parsed_safely(parsed)
        assert result.skipped == []
        assert {s.symbol_id for s in result.signals} == {
            sym.id for sym in parsed.analysis.symbols if sym.name == "has_pair"
        }
        assert any(s.pattern_name == "hash-table lookup" for s in result.signals)

    def test_unsupported_language_scan_file_is_reported_as_skipped(self) -> None:
        result = scan_file("thing.rb", b"def f\n  1\nend\n")
        assert result.signals == []
        assert [(s.file_path, s.reason) for s in result.skipped] == [
            ("thing.rb", SkipReason.UNSUPPORTED_LANGUAGE)
        ]

    def test_unsupported_language_via_scan_many_is_reported_as_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Every parser language has a scanner profile, so a ParsedFile can only
        # reach the scanner without one if the profile is absent. Remove Java's.
        java = parse_source("Lib.java", b"class Lib { int f(int n) { return n; } }\n")
        monkeypatch.delitem(_dsa_scanner._PROFILES, java.analysis.language)
        mixed = scan_many([parse_source("ok.py", _FACTORIAL.encode()), java])
        assert [(s.file_path, s.reason) for s in mixed.skipped] == [
            ("Lib.java", SkipReason.UNSUPPORTED_LANGUAGE)
        ]
        assert mixed.signals
        assert all(s.file_path == "ok.py" for s in mixed.signals)

    def test_file_without_functions_yields_zero_signals(self) -> None:
        source = "X = {}\nfor i in range(3):\n    X[i] = i\n"
        result = scan_file("flat.py", source.encode())
        assert result.signals == []
        assert result.skipped == []

    def test_class_symbols_are_not_scanned(self) -> None:
        source = dsa_src(
            """\
            class Holder:
                seen = {}
                for i in range(3):
                    if i in seen:
                        seen[i] = 1
            """
        )
        assert scan_signals("holder.py", source) == []

    def test_nested_function_is_scanned_as_its_own_symbol(self) -> None:
        source = dsa_src(
            """\
            def outer(items):
                def inner(n):
                    if n <= 1:
                        return 1
                    return n * inner(n - 1)
                return inner(len(items))
            """
        )
        parsed = parse_source("nested.py", source.encode())
        ids = {sym.name: sym for sym in parsed.analysis.symbols}
        assert {"outer", "inner"} <= set(ids)
        signals = scan_signals("nested.py", source)
        recursion = [s for s in signals if s.pattern_name == "direct recursion"]
        assert [s.symbol_id for s in recursion] == [ids["inner"].id]
        assert (recursion[0].start_line, recursion[0].end_line) == (2, 5)
        assert all(s.symbol_id != ids["outer"].id for s in recursion)


class TestScannerDeterminism:
    def test_repeat_runs_are_equal(self) -> None:
        for fx in _ALL_POSITIVE:
            first = scan_file(fx.path, fx.source.encode())
            second = scan_file(fx.path, fx.source.encode())
            assert first == second, fx.name

    def test_scanner_source_has_no_forbidden_imports_or_randomness(self) -> None:
        path = _Path(_dsa_scanner.__file__)
        tree = _py_ast.parse(path.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in _py_ast.walk(tree):
            if isinstance(node, _py_ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, _py_ast.ImportFrom):
                modules.add(node.module or "")
        roots = {m.split(".")[0] for m in modules}
        forbidden = {"fastapi", "mcp", "random", "starlette", "uvicorn"}
        assert not roots & forbidden, roots & forbidden
        for module in modules:
            lowered = module.lower()
            assert "frontend" not in lowered, module
            assert "llm" not in lowered, module
            assert not module.startswith("backend.api"), module
            assert not module.startswith("backend.mcp_server"), module
        names = {n.id for n in _py_ast.walk(tree) if isinstance(n, _py_ast.Name)}
        assert "random" not in names


def scan_parsed_safely(parsed):  # noqa: ANN001, ANN201
    """Scan a ParsedFile; any exception fails the test (nothing may be raised)."""
    return _dsa_scanner.scan_parsed(parsed)


# ---------------------------------------------------------------------------
# Smoke tests: configuration, layering, and scope (Task 11.1)
# Req 1.1, 1.4, 2.2, 2.24, 3.3, 4.2, 5.2, 6.18
# ---------------------------------------------------------------------------
import ast  # noqa: E402
import configparser  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENGINE_NAMES = ("ingestion", "ast_parser", "graph_engine", "dsa_scanner")
_FORBIDDEN_ENGINE_PREFIXES = (
    "fastapi",
    "mcp",
    "starlette",
    "frontend",
    "ui",
    "backend.api",
    "backend.mcp_server",
)
_LLM_PREFIXES = (
    "openai",
    "anthropic",
    "langchain",
    "litellm",
    "crewai",
    "google.generativeai",
    "ollama",
    "backend.llm",
    "llm",
)


def _imported_modules(path: Path) -> set[str]:
    """Return every absolute module name imported by the file (via ``ast``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import in {path}"
            assert node.module is not None
            modules.add(node.module)
    return modules


def _matches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == p or module.startswith(p + ".") for p in prefixes)


def _engine_path(name: str) -> Path:
    return _REPO_ROOT / "backend" / "engines" / f"{name}.py"


def test_pytest_ini_has_only_testpaths_and_pythonpath() -> None:
    parser = configparser.ConfigParser()
    parser.read(_REPO_ROOT / "pytest.ini", encoding="utf-8")
    assert parser.sections() == ["pytest"]
    # Spec #02 requirement 17.1 added asyncio_mode.
    assert dict(parser["pytest"]) == {
        "testpaths": "backend/tests",
        "pythonpath": ".",
        "asyncio_mode": "auto",
    }


def test_test_files_live_under_configured_testpaths() -> None:
    tests_root = _REPO_ROOT / "backend" / "tests"
    for rel in ("unit/test_ast_graph_engine.py", "properties/test_ast_graph_properties.py"):
        assert (tests_root / rel).is_file()
    assert Path(__file__).resolve().is_relative_to(tests_root)


def test_domain_models_import_only_stdlib_and_pydantic() -> None:
    modules = _imported_modules(_REPO_ROOT / "backend" / "domain" / "models.py")
    stdlib = set(sys.stdlib_module_names)
    for module in modules:
        top = module.split(".")[0]
        assert top in stdlib or top == "pydantic", f"disallowed import: {module}"


@pytest.mark.parametrize("name", _ENGINE_NAMES)
def test_engine_modules_import_no_api_mcp_or_frontend(name: str) -> None:
    for module in _imported_modules(_engine_path(name)):
        assert not _matches(module, _FORBIDDEN_ENGINE_PREFIXES), f"{name} imports {module}"


@pytest.mark.parametrize("name", ["dsa_scanner", "graph_engine"])
def test_scanner_and_graph_import_no_llm_module(name: str) -> None:
    for module in _imported_modules(_engine_path(name)):
        assert not _matches(module, _LLM_PREFIXES), f"{name} imports {module}"


def test_graph_engine_imports_no_tree_sitter() -> None:
    for module in _imported_modules(_engine_path("graph_engine")):
        assert not module.startswith("tree_sitter"), module


def test_ingestion_has_single_subprocess_invocation_site() -> None:
    tree = ast.parse(_engine_path("ingestion").read_text(encoding="utf-8"))
    run_refs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "subprocess"
        and node.attr in {"run", "Popen", "call", "check_call", "check_output", "getoutput"}
    ]
    assert len(run_refs) == 1
    # The single reference must be the default of the ``git_runner`` parameter.
    defaults = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = node.args
            positional = args.posonlyargs + args.args
            for arg, default in zip(
                positional[len(positional) - len(args.defaults) :], args.defaults, strict=True
            ):
                defaults.append((arg.arg, default))
            for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
                if kw_default is not None:
                    defaults.append((arg.arg, kw_default))
    assert [d for name, d in defaults if name == "git_runner" and d is run_refs[0]]
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (node.value.id == "os" and node.attr in {"system", "popen"})
        if isinstance(node, ast.Name):
            assert node.id != "Popen"
        if isinstance(node, ast.keyword) and node.arg == "shell":
            assert isinstance(node.value, ast.Constant) and node.value.value is False


def _py_files(rel: str) -> set[str]:
    base = _REPO_ROOT / rel
    if not base.exists():
        return set()
    return {
        p.relative_to(base).as_posix()
        for p in base.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    }


# Spec #03 adds these files (user-approved exception to Req 24.3)
@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        (
            "backend/api",
            {
                "main.py",
                "settings.py",
                "errors.py",
                "rate_limit.py",
                "crew_signature.py",
                "services.py",
                "schemas.py",
                "routes/repos.py",
                "routes/autopsy.py",
                "routes/mastery.py",
                "routes/crew.py",
            },
        ),
        ("backend/mcp_server", {"server.py"}),
        ("power", set()),
        ("crew", set()),
        ("ui", set()),
    ],
)
def test_no_new_python_files_outside_spec_scope(rel: str, expected: set[str]) -> None:
    assert _py_files(rel) == expected
