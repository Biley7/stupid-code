"""Shared, non-test builders for the Spec #02 test files.

Import as ``from backend.tests.support import ...`` (``pytest.ini`` puts the repository
root on ``sys.path``; ``backend`` and ``backend.tests`` are namespace packages).
"""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.domain.models import (
    AlternativeArchitecture,
    DSACard,
    EdgeType,
    ExplanationEnvelope,
    FileAnalysis,
    FlowStep,
    GraphEdge,
    L1SyntaxExplanation,
    L2FlowExplanation,
    L3ArchitectureExplanation,
    Language,
    PedagogyLens,
    ProvenanceReport,
    RepoGraphSnapshot,
    SpecDriftItem,
    SpecLink,
    SymbolKind,
    SymbolNode,
    SyntaxAnnotation,
    TopologyProfile,
)
from backend.engines.ast_parser import parse_source
from backend.engines.cache_store import CacheStore, ExplanationRow, SnapshotRow
from backend.engines.dsa_scanner import scan_many
from backend.engines.graph_engine import build_snapshot
from backend.engines.llm_router import LLMRouter, LLMRouterError, LLMSettings
from backend.engines.pedagogy import (
    PedagogyEngine,
    PedagogyError,
    PedagogyErrorKind,
    build_context_slice,
    complexity_for,
    render_user_prompt,
    resolve_target,
)
from backend.engines.spec_grounder import build_provenance
from backend.engines.topology import profile_topology

# Valid constructor kwargs for every Spec #02 model (ANN ... TOPO), and ``KW`` maps class -> kwargs.
ANN = dict(line_start=1, line_end=2, construct="x = 1", explanation="e", what_if_removed="w")
STEP = dict(step_number=1, location="a.py:f", action="call g", data_transformation="x to y")
CARD = dict(chapter="Hash Tables", pattern_name="Frequency counting", start_line=1, end_line=2,
             why_used_here="counts", time_complexity="O(n)", space_complexity="O(n)")  # fmt: skip
ALT = dict(pattern_name="Layered MVC", why_not_chosen="w", when_to_switch="s")
LINK = dict(spec_name="s", source_file="design.md", section_title="T", excerpt="t", confidence=0.9)
DRIFT = dict(drift_type="UNSPECIFIED_CODE", target="a.py", details="d")
METRICS = dict(
    max_depth=2.0, cross_folder_import_ratio=0.5, domain_isolation_score=1.0, entry_point_count=1.0
)
L1 = dict(target_id="a.py::f", language="python", summary="s", key_takeaway="k",
           annotations=[SyntaxAnnotation(**ANN)])  # fmt: skip
L2 = dict(target_id="a.py::f", execution_steps=[FlowStep(**STEP)], upstream_callers=[],
           downstream_callees=[], side_effects=[], dsa_cards=[DSACard(**CARD)])  # fmt: skip
L3 = dict(target_id="a.py", topology_pattern="Flat / Script", why_this_folder_structure="w",
           structural_evidence=["e"], alternatives=[AlternativeArchitecture(**ALT)])  # fmt: skip
ENV = dict(repo_id="r", target_id="a.py::f", ast_hash="h", lens="L1_SYNTAX", cached=False)
PROV = dict(repo_id="r", has_kiro_specs=True, recent_commits={"a.py": ["a|m"]}) | dict(
    spec_links={"a.py": [SpecLink(**LINK)]}, drift_items=[SpecDriftItem(**DRIFT)]
)
TOPO = dict(repo_id="r", detected_pattern="Flat / Script", confidence=0.5, evidence=["e"]) | dict(
    directory_roles={"a.py": "other"}, boundary_metrics=METRICS
)
KW: dict[type[BaseModel], dict[str, Any]] = {
    SpecLink: LINK, SpecDriftItem: DRIFT, SyntaxAnnotation: ANN, FlowStep: STEP,
    DSACard: CARD, AlternativeArchitecture: ALT, ProvenanceReport: PROV,
    TopologyProfile: TOPO, L1SyntaxExplanation: L1, L2FlowExplanation: L2,
    L3ArchitectureExplanation: L3, ExplanationEnvelope: {**ENV, "l1": L1SyntaxExplanation(**L1)},
}  # fmt: skip
KEY = ("r", "h", "a.py::f")  # (repo_id, ast_hash, target_id) of the ENV envelope
# Explanation envelopes for cache tests: E1 (L1), NEWER (E1 with a changed summary), E2, E3.
E1 = ExplanationEnvelope(**KW[ExplanationEnvelope])
NEWER = E1.model_copy(update={"l1": L1SyntaxExplanation(**{**L1, "summary": "newer"})})
E2 = ExplanationEnvelope(**{**ENV, "lens": PedagogyLens.L2_FLOW, "l2": L2FlowExplanation(**L2)})
E3 = ExplanationEnvelope(
    **{**ENV, "lens": PedagogyLens.L3_ARCHITECTURE, "l3": L3ArchitectureExplanation(**L3)}
)

_SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".java")


def write_repo(root: Path, files: dict[str, str]) -> Path:
    """Write ``files`` (relative path -> text) under ``root`` and return ``root``."""
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def make_snapshot(root: Path, files: dict[str, str], repo_id: str = "repo") -> RepoGraphSnapshot:
    """Write ``files`` and build a real snapshot with the Phase 1 parser, scanner, and graph."""
    write_repo(root, files)
    parsed = [
        parse_source(rel, text.encode("utf-8"))
        for rel, text in sorted(files.items())
        if rel.endswith(_SOURCE_SUFFIXES)
    ]
    signals = scan_many(parsed).signals
    return build_snapshot(repo_id, str(root), [p.analysis for p in parsed], signals)


def fa(path: str, imports: tuple[str, ...] = (), symbols: tuple[str, ...] = ()) -> FileAnalysis:
    """Hand-built Python ``FileAnalysis``; ``symbols`` are top-level function names."""
    # fmt: off
    nodes = [SymbolNode(
        id=f"{path}::{n}", name=n, qualname=n, kind=SymbolKind.FUNCTION, file_path=path,
        start_line=1, end_line=3, signature=f"def {n}()", ast_hash=f"h-{n}", decorators=[],
        is_async=False, raw_calls=[]) for n in symbols]
    # fmt: on
    return FileAnalysis(
        file_path=path,
        language=Language.PYTHON,
        loc=10,
        ast_hash=f"h-{path}",
        imports=list(imports),
        exports=[],
        symbols=nodes,
        parse_errors=[],
    )  # fmt: skip


def imp(src: str, dst: str) -> GraphEdge:
    return GraphEdge(source=src, target=dst, edge_type=EdgeType.IMPORTS)


def topo_snapshot(files: list[FileAnalysis], edges: list[GraphEdge], repo_id: str = "repo"):
    """Snapshot from hand-built files and edges, without parsing or graph building."""
    return RepoGraphSnapshot(
        repo_id=repo_id, root_path="/repo", files=files, edges=edges,
        vital_organs=[], cycles=[], dsa_signals=[],
    )  # fmt: skip


class CountingRouter:
    """Wraps the deterministic mock ``LLMRouter`` and counts ``generate_structured`` calls."""

    def __init__(self) -> None:
        self.inner = LLMRouter(LLMSettings(LLM_PROVIDER="mock"))
        self.calls = 0

    async def generate_structured[M: BaseModel](
        self, system_prompt: str, user_prompt: str, response_model: type[M]
    ) -> M:
        self.calls += 1
        return await self.inner.generate_structured(system_prompt, user_prompt, response_model)


class FailingRouter:
    """Router whose every call raises ``LLMRouterError`` (for degraded-path tests)."""

    def __init__(self, category: Any = "connection") -> None:
        self.category, self.calls = category, 0

    async def generate_structured(self, system_prompt: str, user_prompt: str, response_model: Any):
        self.calls += 1
        raise LLMRouterError("fake failure", provider="mock", category=self.category)


_SPEC_DOC = "# Design\n## Overview\nThe module {path} is described here.\n"
_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def func_src(name: str, value: int = 1) -> str:
    """Python source of one tiny top-level function."""
    return f"def {name}():\n    return {value}\n"


def run_git(root: Path, *args: str) -> str:
    """Run ``git`` in ``root`` with a fixed identity and no global config; return stdout."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    done = subprocess.run([*_GIT, *args], cwd=root, env=env, check=True, capture_output=True)
    return done.stdout.decode()


def make_env(
    tmp_path: Path,
    files: dict[str, str],
    *,
    router: Any = None,
    spec: bool = False,
    git: bool = False,
    repo_id: str = "repo",
) -> SimpleNamespace:
    """Build a ready pedagogy environment under ``tmp_path`` (no network, in-memory cache).

    ``spec=True`` adds a Kiro design doc that mentions the first source file;
    ``git=True`` commits all files in a local git repo before provenance is built.
    Returns ``.snapshot .provenance .topology .cache .router .engine``, with the cache
    already holding the first three.
    """
    files = dict(files)
    if spec:
        first = next(p for p in files if p.endswith(_SOURCE_SUFFIXES))
        files[".kiro/specs/demo/design.md"] = _SPEC_DOC.format(path=first)
    snapshot = make_snapshot(tmp_path, files, repo_id)
    if git:
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
            run_git(tmp_path, *args)
    provenance, topology = build_provenance(snapshot), profile_topology(snapshot)
    cache = CacheStore(":memory:")
    cache.put_snapshot(snapshot)
    cache.put_provenance(provenance)
    cache.put_topology(topology)
    router = router if router is not None else CountingRouter()
    return SimpleNamespace(
        snapshot=snapshot, provenance=provenance, topology=topology, cache=cache,
        router=router, engine=PedagogyEngine(cache, router),
    )  # fmt: skip


def db_rows(store: CacheStore, kind: str, corrupt: bool = False) -> list[Any]:
    """Rows of a table (``"snapshot"`` or ``"explanation"``) in a ``CacheStore``.

    ``corrupt=True`` first overwrites each payload with invalid JSON."""
    row_type = {"snapshot": SnapshotRow, "explanation": ExplanationRow}[kind]
    with Session(store._engine) as session:
        rows = list(session.exec(select(row_type)).all())
        if corrupt:
            for row in rows:
                row.payload = "{not json"
                session.add(row)
            session.commit()
        return rows


def journal_mode(store: CacheStore) -> Any:
    """SQLite ``PRAGMA journal_mode`` value as seen through the store's engine."""
    with store._engine.connect() as conn:  # type: ignore[union-attr]
        return conn.exec_driver_sql("PRAGMA journal_mode").scalar()


def slice_prompt(env: SimpleNamespace, lens: PedagogyLens, target_id: str) -> str:
    """User prompt (marker plus canonical slice JSON) built by the real pedagogy builders."""
    target = resolve_target(env.snapshot, env.topology, target_id, lens)
    return render_user_prompt(
        build_context_slice(env.snapshot, env.provenance, env.topology, target)
    )


class FakeClient:
    """Offline stand-in for an Ollama (``chat.completions.create``) or Gemini
    (``models.generate_content``) client. Each call pops one scripted reply: a ``str`` is
    returned as the reply text, an exception is raised. ``calls`` counts calls and ``config``
    keeps the last Gemini ``config`` argument."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies, self.calls, self.config = list(replies), 0, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._ollama))
        self.models = SimpleNamespace(generate_content=self._gemini)

    def _next(self) -> str:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def _ollama(self, **_kwargs: Any) -> SimpleNamespace:
        message = SimpleNamespace(content=self._next())
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def _gemini(self, *, config: Any, **_kwargs: Any) -> SimpleNamespace:
        self.config = config
        return SimpleNamespace(text=self._next())


# Sources for the pedagogy tests: ``f`` (lines 1-3) and ``g`` (lines 6-7) in one module.
FG_SRC = "def f(x):\n    y = x + 1\n    return y\n\n\ndef g():\n    return 2\n"
# Calls: entry -> a -> b -> c -> d and zed -> b; ``top`` has a real heapq DSASignal; ``crud`` none.
FLOW_SRC = (
    "import heapq\n\n\ndef entry():\n    return a()\n\n\ndef zed():\n    return b()\n\n\n"
    "def a():\n    return b()\n\n\ndef b():\n    return c()\n\n\ndef c():\n    return d()\n\n\n"
    "def d():\n    return 1\n\n\ndef top(h, x):\n    heapq.heappush(h, x)\n"
    "    return heapq.heappop(h)\n\n\ndef crud(db, k):\n    db[k] = 1\n    return db\n"
)
# A hexagonal layout (domain <- engines <- api <- main); the spec doc mentions domain/models.py.
HEX_SRC = {
    "domain/models.py": "class Item:\n    pass\n",
    "domain/rules.py": "from domain.models import Item\n\n\ndef rule(i):\n    return Item\n",
    "engines/svc.py": "from domain.rules import rule\n\n\ndef run():\n    return rule(1)\n",
    "api/routes.py": "from engines.svc import run\n\n\ndef get():\n    return run()\n",
    "main.py": "from api.routes import get\n\n\ndef main():\n    return get()\n",
}


class EditRouter(CountingRouter):
    """``CountingRouter`` whose results go through ``edit(result, call_number)``, so a test
    can inject bad or call-numbered output."""

    def __init__(self, edit: Any) -> None:
        super().__init__()
        self.edit = edit

    async def generate_structured(self, system_prompt: str, user_prompt: str, response_model: Any):
        result = await super().generate_structured(system_prompt, user_prompt, response_model)
        return self.edit(result, self.calls)


def edit_with(**update: Any) -> Any:
    """``EditRouter`` edit that overwrites fields of the result (no validation)."""
    return lambda result, _calls: result.model_copy(update=update)


def tag_call(result: Any, calls: int) -> Any:
    """``EditRouter`` edit that appends ``v<call number>`` to the L1 summary or L3 explanation
    text; an L2 result is returned unchanged."""
    field = next((f for f in ("summary", "why_this_folder_structure") if hasattr(result, f)), "")
    if not field:
        return result
    return result.model_copy(update={field: f"{getattr(result, field)} v{calls}"})


async def expect_error(
    engine: PedagogyEngine, target_id: str, lens: PedagogyLens, kind: PedagogyErrorKind
) -> str:
    """Assert ``explain_target`` raises ``PedagogyError`` of ``kind``; return its message,
    after checking that it holds no prompt text or source code."""
    with pytest.raises(PedagogyError) as info:
        await engine.explain_target("repo", target_id, lens)
    message = str(info.value)
    assert info.value.kind is kind
    assert not any(leak in message for leak in ("CONTEXT_SLICE", "You explain", "y = x + 1"))
    return message


def rehash(snapshot: RepoGraphSnapshot, symbol_id: str, ast_hash: str) -> RepoGraphSnapshot:
    """Copy of ``snapshot`` where one symbol has a different ``ast_hash``."""
    files = [
        f.model_copy(update={"symbols": [
            s.model_copy(update={"ast_hash": ast_hash}) if s.id == symbol_id else s
            for s in f.symbols
        ]})
        for f in snapshot.files
    ]  # fmt: skip
    return snapshot.model_copy(update={"files": files})


GOOD_ANN = ANN | dict(line_start=2, line_end=2, construct="y = x + 1")  # a line of ``f``
BAD_ANNS = (  # outside ``f`` (a line of ``g``), and a construct that is not on the cited line
    ANN | dict(line_start=6, line_end=6, construct="return 2"),
    ANN | dict(line_start=2, line_end=2, construct="no such text"),
)


def bad_annotation_edit(bad: dict[str, Any]) -> Any:
    """``EditRouter`` edit: a valid annotation 0 followed by the invalid annotation 1 ``bad``."""
    return edit_with(annotations=[SyntaxAnnotation(**GOOD_ANN), SyntaxAnnotation(**bad)])


def engine_with(env: SimpleNamespace, edit: Any) -> PedagogyEngine:
    """Engine over ``env``'s cache whose router passes its results through ``edit``."""
    return PedagogyEngine(env.cache, EditRouter(edit))


def explain(engine: PedagogyEngine, target_id: str, lens: PedagogyLens, **kwargs: Any):
    """``engine.explain_target`` for the ``repo`` repository (a coroutine)."""
    return engine.explain_target("repo", target_id, lens, **kwargs)


async def l2_of(engine: PedagogyEngine, *targets: str) -> list[L2FlowExplanation]:
    """L2 results for ``targets``; each envelope must be uncached with only ``l2`` set."""
    results = []
    for target in targets:
        got = await explain(engine, target, PedagogyLens.L2_FLOW)
        assert (got.cached, got.l1, got.l3) == (False, None, None)
        results.append(got.l2)
    return results


def symbol_of(snapshot: RepoGraphSnapshot, symbol_id: str) -> SymbolNode:
    return next(s for f in snapshot.files for s in f.symbols if s.id == symbol_id)


def card_rows(cards: list[DSACard]) -> list[tuple[Any, ...]]:
    """DSA cards as (chapter, pattern, start, end, time, space) tuples."""
    return [
        (c.chapter, c.pattern_name, c.start_line, c.end_line, c.time_complexity, c.space_complexity)
        for c in cards
    ]


def signal_rows(signals: list[Any]) -> list[tuple[Any, ...]]:
    """What ``card_rows`` must give for ``signals``: lines copied, complexity from the table."""
    return [
        (
            s.chapter,
            s.pattern_name,
            s.start_line,
            s.end_line,
            *complexity_for(s.chapter, s.pattern_name),
        )
        for s in signals
    ]


def deterministic(l2: L2FlowExplanation) -> tuple[Any, ...]:
    """The parts of an L2 result that do not depend on the LLM (cards without the LLM text)."""
    cards = [c.model_copy(update={"why_used_here": ""}) for c in l2.dsa_cards]
    return (l2.upstream_callers, l2.downstream_callees, cards)


def stored(env: SimpleNamespace, lens: PedagogyLens, column: str = "payload") -> list[Any]:
    """One column of the stored explanation rows for ``lens``."""
    return [getattr(r, column) for r in db_rows(env.cache, "explanation") if r.lens == lens.value]


_KIRO = ".kiro/specs"
# Repo files for the spec-link tests: ``run_engine`` is named in a design section, the module path
# in two others, "the engine module" only in a heading; steering must not link.
LINK_FILES = {
    "backend/engine.py": func_src("run_engine"),
    "backend/util.py": func_src("helper"),
    "backend/unrelated.py": func_src("zzz_unique"),
    f"{_KIRO}/alpha/design.md": (
        "# Design\n## Path section\nSee backend/engine.py for details.\n"
        f"## Symbol section\n{'filler words ' * 40}\nCalls `run_engine` here.\n"
        "## About the engine module\nNo path mentioned here.\n"
    ),
    f"{_KIRO}/beta/requirements.md": "# Req\n## Where\nLives in backend/engine.py.\n",
    ".kiro/steering/rules.md": "# Rules\nbackend/engine.py and `run_engine`.\n",
}
# A tasks.md with one implemented path, one missing path, ignorable examples, and a fenced path.
TASKS_MD = (
    "# Tasks\n- [ ] 1. Implement `backend/real.py`\n"
    "- [ ] 2. Create `backend/missing_mod.py`\n"
    "- [ ] 3. Ignore: <dir>/x.py {x}/y.py backend/*.py backend/... backend/example_a.py "
    "/abs/path.py ../x.py https://host.io/mod.py foo.py lib/util.py\n"
    "```\n- [ ] `backend/fenced_missing.py`\n```\n"
)


HEX_PATHS = "domain/models.py domain/rules.py engines/a.py engines/b.py api/routes.py main.py"
HEX_EDGES = ("api/routes.py>engines/a.py engines/a.py>domain/models.py "
              "engines/b.py>domain/rules.py "
              "engines/a.py>engines/b.py main.py>api/routes.py")  # fmt: skip

ROUTER_SRC = {"a.py": func_src("f") + "\n\n" + func_src("g", 2)}
LENSES = ((PedagogyLens.L1_SYNTAX, "a.py::f", L1SyntaxExplanation),
           (PedagogyLens.L2_FLOW, "a.py::f", L2FlowExplanation),
           (PedagogyLens.L3_ARCHITECTURE, "repo", L3ArchitectureExplanation))  # fmt: skip
