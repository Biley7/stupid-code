"""Unit tests for Spec #02: provenance, topology, router, cache, and pedagogy.

Test plan (shared builders live in ``backend/tests/support.py``):
  1-2 domain models    3-7 spec grounder    8-12 topology    13-14 LLM router
  15-16 cache store    17-20 pedagogy engine    21 layering (ast based import checks)
"""

import ast
import json
import shutil
import sys
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import backend.domain.models as models
import backend.engines.llm_router as llm_router

# isort: off
# fmt: off
from backend.domain.models import (
    DSACard, EdgeType, ExplanationEnvelope, FlowStep, GraphEdge, L1SyntaxExplanation,
    L2FlowExplanation, L3ArchitectureExplanation, PedagogyLens, SpecLink, SyntaxAnnotation,
    TopologyProfile,
)
from backend.engines.pedagogy import PedagogyEngine, PedagogyErrorKind as Kind
from backend.engines.cache_store import CacheSettings, CacheStore, CacheStoreError
from backend.engines.llm_router import LLMConfigError, LLMRouter, LLMRouterError, LLMSettings
from backend.engines.spec_grounder import (
    SkipReason, SpecGrounderError, build_provenance, build_spec_links, discover_specs,
)
from backend.engines.topology import (
    compute_boundary_metrics, compute_directory_roles, profile_topology,
)
from backend.tests.support import (
    ANN, BAD_ANNS, CARD, ENV, FG_SRC, FLOW_SRC, HEX_EDGES, HEX_PATHS, HEX_SRC, KW, E1, E2, E3, KEY,
    L2, L3, LENSES, LINK, LINK_FILES, METRICS, NEWER, ROUTER_SRC, TASKS_MD, EditRouter,
    FailingRouter, FakeClient, bad_annotation_edit, card_rows, db_rows, deterministic, edit_with,
    engine_with, expect_error, explain, fa, func_src, imp, journal_mode, l2_of, make_env,
    make_snapshot, rehash, run_git, signal_rows, slice_prompt, stored, symbol_of, tag_call,
    topo_snapshot, write_repo,
)
# fmt: on
# isort: on

pytestmark = pytest.mark.usefixtures("offline_guard")


# --- Domain models (tests 1-2); fixtures ANN, KW, ... live in support.py ---
def _rejects(cls: type[BaseModel], **override: Any) -> None:
    with pytest.raises(ValidationError):
        cls(**{**KW[cls], **override})


def test_domain_models_valid_and_nullable() -> None:
    built = [cls(**kw) for cls, kw in KW.items()]
    l2, l3 = built[-3], built[-2]
    env_l2 = ExplanationEnvelope(**{**ENV, "lens": PedagogyLens.L2_FLOW, "l2": l2})
    env_l3 = ExplanationEnvelope(**{**ENV, "lens": PedagogyLens.L3_ARCHITECTURE, "l3": l3})
    for model in [*built, env_l2, env_l3]:
        assert type(model).model_validate_json(model.model_dump_json()) == model
    assert isinstance(l2, L2FlowExplanation) and isinstance(l3, L3ArchitectureExplanation)
    assert l2.llm_content_available is True
    assert l3.spec_rationale is None
    assert (env_l2.l1, env_l2.l3, env_l3.l1, env_l3.l2) == (None, None, None, None)
    assert [lens.value for lens in PedagogyLens] == ["L1_SYNTAX", "L2_FLOW", "L3_ARCHITECTURE"]
    assert {c.__name__ for c in KW} | {"PedagogyLens"} <= set(models.__all__)
    assert len({c.__name__ for c in KW} | {"PedagogyLens"}) == 13
    fields = {c: list(c.model_fields) for c in (FlowStep, L2FlowExplanation, ExplanationEnvelope)}
    l2_fields = "target_id execution_steps upstream_callers downstream_callees side_effects "
    assert fields[FlowStep] == "step_number location action data_transformation".split()
    assert fields[L2FlowExplanation] == (l2_fields + "dsa_cards llm_content_available").split()
    assert fields[ExplanationEnvelope] == "repo_id target_id ast_hash lens cached l1 l2 l3".split()
    assert list(L3ArchitectureExplanation.model_fields)[-1] == "spec_rationale"


def test_domain_models_reject_invalid() -> None:
    for cls, kw in KW.items():
        with pytest.raises(ValidationError):
            cls(**kw, description="extra")
        with pytest.raises(ValidationError):
            setattr(cls(**kw), next(iter(cls.model_fields)), "changed")
    for bad in (float("nan"), float("inf"), float("-inf"), -0.1, 1.1, True):
        _rejects(SpecLink, confidence=bad)
        _rejects(TopologyProfile, confidence=bad)
    for good in (0.0, 1.0):
        assert SpecLink(**{**LINK, "confidence": good}).confidence == good
    for key in ("cross_folder_import_ratio", "domain_isolation_score"):
        _rejects(TopologyProfile, boundary_metrics={**METRICS, key: 1.1})
    for metrics in (
        {**METRICS, "max_depth": -1.0}, {**METRICS, "max_depth": True}, {**METRICS, "x": 1.0},
        {**METRICS, "entry_point_count": float("nan")},
        {k: v for k, v in METRICS.items() if k != "max_depth"},
    ):  # fmt: skip
        _rejects(TopologyProfile, boundary_metrics=metrics)
    _rejects(TopologyProfile, repo_id="  ")
    zero_depth = {**KW[TopologyProfile], "boundary_metrics": {**METRICS, "max_depth": 0.0}}
    assert TopologyProfile(**zero_depth)
    for cls, kw, start, end in (
        (SyntaxAnnotation, ANN, "line_start", "line_end"),
        (DSACard, CARD, "start_line", "end_line"),
    ):
        _rejects(cls, **{start: 0})
        _rejects(cls, **{start: 3, end: 2})
        assert cls(**{**kw, start: 2, end: 2})
    _rejects(FlowStep, step_number=0)
    for field in ("location", "action", "data_transformation"):
        _rejects(FlowStep, **{field: "  "})
    for field in ("summary", "key_takeaway"):
        _rejects(L1SyntaxExplanation, **{field: " "})
    for evidence in ([], ["e"] * 21):
        _rejects(L3ArchitectureExplanation, structural_evidence=evidence)
    for evidence in (["e"], ["e"] * 20):
        assert L3ArchitectureExplanation(**{**L3, "structural_evidence": evidence})
    l1, l2 = KW[ExplanationEnvelope]["l1"], L2FlowExplanation(**L2)
    _rejects(ExplanationEnvelope, lens=PedagogyLens.L2_FLOW)  # wrong tier
    _rejects(ExplanationEnvelope, l2=l2)  # extra tier
    _rejects(ExplanationEnvelope, l1=None)  # missing tier
    assert ExplanationEnvelope(**{**ENV, "l1": l1}).l2 is None


# --- Spec grounder (tests 3-7) ---
_KIRO = ".kiro/specs"


def test_spec_discovery_handles_missing_and_oversize(tmp_path: Path) -> None:
    bare = discover_specs(tmp_path)  # an empty directory
    assert (bare.sections, bare.skipped, bare.has_kiro_specs) == ((), (), False)
    root = write_repo(tmp_path / "repo", {
        f"{_KIRO}/b-spec/requirements.md": "# Req B\n",
        f"{_KIRO}/a-spec/tasks.md": "# Task A\n",
        f"{_KIRO}/a-spec/design.md": "# Design A\n## Sub\n",
        f"{_KIRO}/a-spec/requirements.md": "# Req A\n",
        ".kiro/steering/guide.md": "# Guide\n",
        ".kiro/steering/nested/hidden.md": "# Hidden\n",
    })  # fmt: skip
    found = discover_specs(root)
    assert found.has_kiro_specs and found.skipped == ()
    assert [(s.origin, s.spec_name, s.source_file, s.title) for s in found.sections] == [
        ("spec", "a-spec", "design.md", "Design A"), ("spec", "a-spec", "design.md", "Sub"),
        ("spec", "a-spec", "requirements.md", "Req A"), ("spec", "a-spec", "tasks.md", "Task A"),
        ("spec", "b-spec", "requirements.md", "Req B"), ("steering", None, "guide.md", "Guide"),
    ]  # fmt: skip
    big = {"c-spec": b"# Max\n".ljust(524_288, b"x"), "d-spec": b"# Over\n".ljust(524_289, b"x"),
           "e-spec": b"# Bad\n\xff\xfe"}  # fmt: skip
    for name, data in big.items():
        (root / _KIRO / name).mkdir()
        (root / _KIRO / name / "design.md").write_bytes(data)

    def listing() -> list[tuple[str, int]]:
        return [(p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*")]

    before = sorted(listing())
    found = discover_specs(root)
    assert sorted(listing()) == before
    assert [(s.path, s.reason) for s in found.skipped] == [
        (f"{_KIRO}/d-spec/design.md", SkipReason.OVERSIZE),
        (f"{_KIRO}/e-spec/design.md", SkipReason.INVALID_ENCODING),
    ]  # fmt: skip
    assert [s.title for s in found.sections if s.spec_name == "c-spec"] == ["Max"]
    assert not any(s.title == "Hidden" for s in found.sections)


def test_spec_links_are_grounded_and_ordered(tmp_path: Path) -> None:
    snap = make_snapshot(tmp_path, LINK_FILES)
    sections = discover_specs(tmp_path).sections
    links = build_spec_links(snap, sections)
    assert list(links) == ["backend/engine.py"]  # unrelated files and steering: no links
    found = links["backend/engine.py"]
    assert [(k.confidence, k.spec_name, k.source_file, k.section_title) for k in found] == [
        (0.90, "alpha", "design.md", "Path section"), (0.90, "beta", "requirements.md", "Where"),
        (0.75, "alpha", "design.md", "Symbol section"),
        (0.50, "alpha", "design.md", "About the engine module"),
    ]  # fmt: skip
    assert [k.confidence for k in found] == sorted((k.confidence for k in found), reverse=True)
    for link in found:
        text = next(s.text for s in sections if s.title == link.section_title)
        assert link.excerpt in text and len(link.excerpt) <= 300
    assert len(found[2].excerpt) == 300 and "run_engine" in found[2].excerpt
    report = build_provenance(snap)
    assert (report.has_kiro_specs, report.recent_commits, report.spec_links) == (True, {}, links)
    assert set(links) <= {f.file_path for f in snap.files}


def test_unspecified_code_drift_is_conservative(tmp_path: Path) -> None:
    code = {f"core/{n}.py": func_src(f"{n}_one") for n in ("a", "b", "c", "__init__")}
    code |= {"core/consts.py": "X = 1\n", "tests/test_x.py": func_src("test_x")}
    spec = {f"{_KIRO}/s/design.md": "Preamble mentions core/c.py only.\n\n# Overview\nNothing.\n"}
    snap = make_snapshot(tmp_path / "with", {**code, **spec})
    items = build_provenance(snap).drift_items
    want = [("UNSPECIFIED_CODE", "core/a.py"), ("UNSPECIFIED_CODE", "core/b.py")]
    assert [(i.drift_type, i.target) for i in items] == want
    assert items == sorted(items, key=lambda i: (i.drift_type, i.target))
    steering = {".kiro/steering/rules.md": "# Rules\nUse core/a.py.\n"}
    bare = make_snapshot(tmp_path / "without", {**code, **steering})
    assert build_provenance(bare).drift_items == []


def test_unimplemented_spec_ignores_examples_and_ambiguous(tmp_path: Path) -> None:
    files = {"backend/real.py": func_src("real_fn"), "a/lib/util.py": "X = 1\n",
             "b/lib/util.py": "X = 1\n", f"{_KIRO}/alpha/tasks.md": TASKS_MD}  # fmt: skip
    snap = make_snapshot(tmp_path, files)
    first = build_provenance(snap)
    drift = [(i.drift_type, i.target) for i in first.drift_items]
    assert drift == [("UNIMPLEMENTED_SPEC", "backend/missing_mod.py")]
    assert "alpha" in first.drift_items[0].details
    assert build_provenance(snap) == first


def test_git_history_is_attached_and_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    root = tmp_path / "gitrepo"
    root.mkdir()
    git = partial(run_git, root)
    git("init", "-q")
    state = {"notes.txt": "n\n"}
    for i in range(22):
        state["a.py"] = func_src("a", i)
        if i == 5:
            state["b.py"] = func_src("b")
        if i == 10:
            state["notes.txt"] = "n10\n"
        write_repo(root, state)
        git("add", "-A")
        git("commit", "-q", "-m", f"c{i}")
    snap = make_snapshot(root, state)
    status = git("status", "--porcelain")
    report = build_provenance(snap)
    assert git("status", "--porcelain") == status == ""
    assert set(report.recent_commits) == {"a.py", "b.py"}  # notes.txt is not a Snapshot file
    expected = git("log", "-n", "20", "--pretty=format:%h|%s", "--", "a.py").split("\n")
    assert report.recent_commits["a.py"] == expected
    subjects = {k: [r.split("|", 1)[1] for r in v] for k, v in report.recent_commits.items()}
    assert subjects == {"a.py": [f"c{i}" for i in range(21, 1, -1)], "b.py": ["c5"]}
    assert build_provenance(snap) == report
    plain = make_snapshot(tmp_path / "plain", {"a.py": func_src("a")})
    assert build_provenance(plain).recent_commits == {}
    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: None)
    assert build_provenance(snap).recent_commits == {}
    with pytest.raises(SpecGrounderError):
        build_provenance("not a snapshot")  # type: ignore[arg-type]
    with pytest.raises(SpecGrounderError):
        build_provenance(snap, tmp_path / "missing")


# --- Topology (tests 8-12); paths are space separated, edges are "source>target" tokens ---
def topo_profile(paths: str, edges: str = "", repo_id: str = "repo") -> TopologyProfile:
    files, pairs = [fa(p) for p in paths.split()], [imp(*e.split(">")) for e in edges.split()]
    return profile_topology(topo_snapshot(files, pairs, repo_id))


def test_hexagonal_fixture_is_classified() -> None:
    profile = topo_profile(HEX_PATHS, HEX_EDGES, "hx")
    assert (profile.detected_pattern, profile.repo_id) == ("Hexagonal / Clean Architecture", "hx")
    # naming 1.0 (3 groups), imports 1.0 (3 of 3 inward), distribution 5/6: 0.8 + 0.2 * 0.8333.
    assert profile.confidence == 0.9667
    assert profile.evidence == sorted(profile.evidence)
    assert all(0 < len(item) <= 200 for item in profile.evidence)
    for seen in ("directory domain has role domain", "directory api has role api",
                 "imports engines -> domain (2 files)", "entry point main.py",
                 "pattern Hexagonal / Clean Architecture score 0.9667 (naming 1.0000, "
                 "imports 1.0000, distribution 0.8333)"):  # fmt: skip
        assert seen in profile.evidence


def test_flat_script_fixture_and_confidence_caps() -> None:
    flat = topo_profile("a.py b.py c.py")  # 0.3 * 1 + 0.3 * 0.5 (no edges) + 0.4 * 1
    assert (flat.detected_pattern, flat.confidence) == ("Flat / Script", 0.85)

    ft = lambda text: text.replace("@", "features/")  # noqa: E731
    sl = ft("@a/a1.py @a/a2.py @b/b1.py @b/b2.py")
    same = ft("@a/a1.py>@a/a2.py @b/b1.py>@b/b2.py")
    cross = ft("@a/a1.py>@b/b1.py @a/a1.py>@b/b2.py @a/a2.py>@b/b1.py @a/a2.py>@b/b2.py "
               "@b/b1.py>@a/a1.py")  # fmt: skip
    # Only naming >= 0.3 (imports 0.2857, distribution 0.2857): score 0.5714 capped to 0.5.
    deep = " ".join(f"{d}/deep/f{i}.py" for d in ("shared", "widgets") for i in range(5))
    single = topo_profile(f"{sl} {deep}", f"{same} {cross}")
    assert (single.detected_pattern, single.confidence) == ("Feature-Sliced", 0.5)
    assert any("score 0.5714 (naming 1.0000, imports 0.2857" in e for e in single.evidence)
    # Feature-Sliced 0.8889 vs Flat / Script 0.8222 differ by < 0.1: capped to 0.6.
    shallow = "shared/s1.py shared/s2.py shared/s3.py widgets/w1.py widgets/w2.py"
    close = topo_profile(f"{sl} {shallow}", same)
    assert (close.detected_pattern, close.confidence) == ("Feature-Sliced", 0.6)
    assert any("score 0.8889" in e for e in close.evidence)
    for p in (flat, single, close, topo_profile("models/m.py views/v.py")):
        assert 0.0 <= p.confidence <= 1.0


def test_topology_is_deterministic_under_reordering() -> None:
    files = [fa(p) for p in HEX_PATHS.split()]
    edges = [imp(*e.split(">")) for e in HEX_EDGES.split()]
    base = profile_topology(topo_snapshot(files, edges))
    for f, e in ((files[::-1], edges[::-1]), (files, edges + edges[:3]), (files, edges)):
        again = profile_topology(topo_snapshot(f, e))
        assert again == base and again.model_dump_json() == base.model_dump_json()


def test_directory_roles_and_metrics_match_hand_computed_values() -> None:
    paths = ("domain/a.py domain/sub/b.py domain/sub/deep/c.py engines/e.py engines/f.py "
             "api/routes.py ui/page.py tests/test_a.py config/s.py pkg/checks/test_x.py "
             "pkg/checks/y_test.py svc/launch/main.py widgets/w.tsx main.py")  # fmt: skip
    # 8 distinct valid edges (7 cross-directory); the last four tokens are ignored.
    # From domain: a>sub/b and deep/c>a stay inside, sub/b>e and a>e leave.
    edges = ("api/routes.py>engines/e.py engines/e.py>domain/a.py domain/a.py>domain/sub/b.py "
             "domain/sub/b.py>engines/e.py domain/sub/deep/c.py>domain/a.py "
             "domain/a.py>engines/e.py main.py>api/routes.py engines/e.py>engines/f.py "
             "engines/e.py>engines/e.py api/routes.py>engines/e.py api/routes.py>nowhere.py "
             "ghost.py>main.py")  # fmt: skip
    calls = GraphEdge(source="api/routes.py", target="domain/a.py", edge_type=EdgeType.CALLS)
    links = [imp(*e.split(">")) for e in edges.split()]
    snap = topo_snapshot([fa(p) for p in paths.split()], [*links, calls])
    roles = compute_directory_roles(snap)
    assert roles == {"api": "api", "config": "config", "domain": "domain", "domain/sub": "other",
                     "domain/sub/deep": "other", "engines": "engines", "pkg": "other",
                     "pkg/checks": "tests", "svc": "other", "svc/launch": "entry_points",
                     "tests": "tests", "ui": "ui", "widgets": "ui"}  # fmt: skip
    assert list(roles) == sorted(roles)
    want = {"max_depth": 3.0, "cross_folder_import_ratio": 0.875,
            "domain_isolation_score": 0.5, "entry_point_count": 2.0}  # fmt: skip
    metrics = compute_boundary_metrics(snap, roles)
    assert metrics == want and list(metrics) == list(want)
    assert all(type(v) is float for v in metrics.values())
    assert profile_topology(snap).boundary_metrics == want


def test_topology_empty_and_malformed_graphs() -> None:
    empty = topo_profile("")
    assert (empty.detected_pattern, empty.confidence) == ("Flat / Script", 0.0)
    assert (empty.directory_roles, empty.evidence) == ({}, [])
    zero = dict.fromkeys(("max_depth", "cross_folder_import_ratio", "entry_point_count"), 0.0)
    assert empty.boundary_metrics == {**zero, "domain_isolation_score": 1.0}
    for edges in ("", "a.py>a.py pkg/b.py>pkg/b.py", "a.py>x.py y.py>a.py"):
        profile = topo_profile("a.py pkg/b.py", edges)
        assert profile.boundary_metrics["cross_folder_import_ratio"] == 0.0
        assert profile.boundary_metrics["domain_isolation_score"] == 1.0
        assert 0.0 <= profile.confidence <= 1.0 and profile.evidence
        assert profile.directory_roles == {"pkg": "other"}


# --- LLM router (tests 13-14) ---
async def test_mock_router_is_deterministic_and_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in [n for n in sys.modules if n.split(".")[0] in ("openai", "google")]:
        monkeypatch.delitem(sys.modules, name)  # a fresh import would re-add them
    monkeypatch.delenv("LLM_PROVIDER")
    router = LLMRouter()
    assert router.provider == "mock"
    one = make_env(tmp_path / "one", ROUTER_SRC)
    two = make_env(tmp_path / "two", {"a.py": func_src("f", 5) + "\n\n" + func_src("g", 2)})
    for lens, target, model in LENSES:
        prompt = slice_prompt(one, lens, target)
        first = await router.generate_structured("system", prompt, model)
        again = await router.generate_structured("other system", prompt, model)
        assert isinstance(first, model) and first == again
        assert model.model_validate_json(first.model_dump_json()) == first
        other = await router.generate_structured("system", slice_prompt(two, lens, target), model)
        assert other != first  # the ast_hash embedded in the text differs
    prompt = slice_prompt(one, PedagogyLens.L1_SYNTAX, "a.py::f")
    for bad_args in (("s", prompt, SpecLink), ("s", "no marker here", L1SyntaxExplanation)):
        with pytest.raises(LLMRouterError) as info:
            await router.generate_structured(*bad_args)
        assert (info.value.provider, info.value.category) == ("mock", "validation")
    assert not any(n.split(".")[0] in ("openai", "google") for n in sys.modules)
    secret = "sk-secret-123"
    for bad in ("MOCK", "", "openai"):
        with pytest.raises(LLMConfigError, match="mock, gemini, ollama"):
            LLMRouter(LLMSettings(LLM_PROVIDER=bad))
    for key, extra, named in (
        ("", {}, "GEMINI_API_KEY"), (" \t", {}, "GEMINI_API_KEY"),
        (secret, {"GEMINI_MODEL": " "}, "GEMINI_MODEL"),
        (secret, {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": ""}, "OLLAMA_MODEL"),
        (secret, {"LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": ""}, "OLLAMA_BASE_URL"),
    ):  # fmt: skip
        settings = LLMSettings(**{"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": key, **extra})
        with pytest.raises(LLMConfigError) as info:
            LLMRouter(settings)
        assert named in str(info.value) and info.value.category == "configuration"
        assert secret not in str(info.value) + repr(settings)


async def test_provider_invalid_responses_use_bounded_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key, env = "sk-fake-key-456", make_env(tmp_path, ROUTER_SRC)
    prompt = slice_prompt(env, PedagogyLens.L2_FLOW, "a.py::f")
    valid = await LLMRouter().generate_structured("s", prompt, L2FlowExplanation)
    valid = valid.model_dump_json()

    async def run(provider: str, fake: FakeClient) -> L2FlowExplanation:
        monkeypatch.setattr(llm_router, f"_make_{provider}_client", lambda _settings: fake)
        settings = LLMSettings(LLM_PROVIDER=provider, GEMINI_API_KEY=key)
        return await LLMRouter(settings).generate_structured("SYS-TEXT", prompt, L2FlowExplanation)

    async def fails(provider: str, *replies: str | Exception, category: str) -> int:
        fake = FakeClient(*replies)
        with pytest.raises(LLMRouterError) as info:
            await run(provider, fake)
        assert (info.value.provider, info.value.category) == (provider, category)
        assert not any(leak in str(info.value) for leak in (key, "SYS-TEXT", prompt[:80], "boom"))
        return fake.calls

    def sdk_error(name: str) -> Exception:
        return type(name, (Exception,), {})(f"boom {key} SYS-TEXT {prompt[:80]}")

    assert await fails("ollama", "not json", '{"x": 1}', category="validation") == 2
    assert await fails("gemini", "not json", category="validation") == 1
    assert await fails("ollama", sdk_error("APITimeoutError"), category="timeout") == 1
    assert await fails("gemini", sdk_error("APIConnectionError"), category="connection") == 1
    assert await fails("gemini", TimeoutError("boom"), category="timeout") == 1
    assert await fails("ollama", sdk_error("OddError"), category="provider") == 1
    retry = FakeClient("not json", valid)
    assert (await run("ollama", retry)).model_dump_json() == valid and retry.calls == 2
    gemini = FakeClient(valid)
    await run("gemini", gemini)
    assert gemini.config.response_mime_type == "application/json"
    assert "additionalProperties" not in json.dumps(gemini.config.response_schema)
    assert "additionalProperties" in json.dumps(L2FlowExplanation.model_json_schema())


def test_cache_store_hit_miss_hash_change_and_lens_isolation(tmp_path: Path) -> None:
    env, (l1, l2, l3) = make_env(tmp_path, {"a.py": func_src("f")}), PedagogyLens
    with CacheStore(":memory:") as empty, env.cache as store:  # env.cache holds the 3 put objects
        kinds = ("snapshot", "provenance", "topology")
        got = [getattr(s, f"get_{k}")("repo") for s in (empty, store) for k in kinds]
        assert got == [None] * 3 + [env.snapshot, env.provenance, env.topology]
        assert store.get_snapshot("other") is None and empty.get_explanation(*KEY, l1) is None
        get = partial(store.get_explanation, *KEY)
        store.put_explanation(E1)
        assert get(l1) == E1
        store.put_explanation(NEWER)  # same key: replaced, still one row
        assert get(l1) == NEWER and len(db_rows(store, "explanation")) == 1
        assert store.get_explanation("r", "h2", "a.py::f", l1) is None  # hash change: miss
        store.put_explanation(NEWER.model_copy(update={"ast_hash": "h2"}))
        assert get(l1) == NEWER and get(l2) is None  # old row stays; no cross-lens hit
        store.put_explanation(E2), store.put_explanation(E3)
        assert (get(l1), get(l2), get(l3)) == (NEWER, E2, E3)
        assert len(db_rows(store, "explanation")) == 4
        for other in (("r2", "h", "a.py::f"), ("r", "h", "a.py::g")):  # other repo, target
            assert store.get_explanation(*other, l1) is None


def test_cache_store_file_path_wal_corruption_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CacheStore(str(path := tmp_path / "nested" / "dir" / "cache.db"))
    assert path.parent.is_dir() and journal_mode(store) == "wal"
    store.put_snapshot(snap := topo_snapshot([fa("a.py")], []))
    store.close()
    with CacheStore(str(path)) as store:  # data persists across close and reopen
        assert store.get_snapshot("repo") == snap
        store.put_explanation(E1)
        for kind, args in (("explanation", (*KEY, E1.lens)), ("snapshot", ("repo",))):
            read = partial(getattr(store, f"get_{kind}"), *args)  # a corrupt row is a miss
            assert len(db_rows(store, kind, corrupt=True)) == 1  # and is deleted
            assert read() is None and read() is None and db_rows(store, kind) == []
    with pytest.raises(CacheStoreError, match="closed"):
        store.get_snapshot("repo")
    for value, expected in (("", "./data/stupid_code.db"), ("x.db", "x.db")):
        monkeypatch.setenv("STUPID_CODE_DB_PATH", value)
        assert CacheSettings().stupid_code_db_path == expected
    (tmp_path / "afile").write_text("secret-payload")
    with pytest.raises(CacheStoreError, match=r"Error on cache database .*afile") as info:
        CacheStore(str(tmp_path / "afile" / "x.db"))
    assert "secret-payload" not in str(info.value)


# --- Pedagogy engine (tests 17-20) ---
LS1, LS2, LS3 = PedagogyLens


async def test_l1_explanation_is_grounded_and_bad_output_rejected(tmp_path: Path) -> None:
    env = make_env(tmp_path, {"a.py": FG_SRC})
    sym = symbol_of(env.snapshot, "a.py::f")
    for bad in BAD_ANNS:
        engine = engine_with(env, bad_annotation_edit(bad))
        assert "annotation 1" in await expect_error(engine, "a.py::f", LS1, Kind.INVALID_OUTPUT)
    assert stored(env, LS1) == []
    got = await explain(env.engine, "a.py::f", LS1)
    assert (got.cached, got.ast_hash, got.l2, got.l3) == (False, sym.ast_hash, None, None)
    l1, lines = got.l1, FG_SRC.split("\n")
    assert (l1.target_id, l1.language.value) == ("a.py::f", "python")
    assert l1.summary.strip() and l1.key_takeaway.strip() and l1.annotations
    for a in l1.annotations:
        assert sym.start_line <= a.line_start <= a.line_end <= sym.end_line
        assert a.construct in "\n".join(lines[a.line_start - 1 : a.line_end])
    (tmp_path / "a.py").unlink()  # g is not cached, so its source is read and is now missing
    await expect_error(env.engine, "a.py::g", LS1, Kind.SOURCE_UNREADABLE)
    await expect_error(env.engine, "a.py::nope", LS1, Kind.UNKNOWN_TARGET)
    idle = PedagogyEngine(CacheStore(":memory:"), unused := FailingRouter())
    missing = await expect_error(idle, "a.py::f", LS1, Kind.MISSING_DATA)
    assert all(n in missing for n in ("snapshot", "provenance report", "topology profile"))
    assert (env.router.calls, unused.calls, len(stored(env, LS1))) == (1, 0, 1)


async def test_l2_flow_callers_dsa_cards_and_degraded_result(tmp_path: Path) -> None:
    env = make_env(tmp_path, {"a.py": FLOW_SRC})
    sigs = env.snapshot.dsa_signals
    assert [s.symbol_id for s in sigs] == ["a.py::top"]  # real scanner output; crud has none
    sigs = [*sigs, sigs[0].model_copy(update={"pattern_name": "invented pattern"})]
    env.cache.put_snapshot(env.snapshot.model_copy(update={"dsa_signals": sigs}))
    dead, targets = FailingRouter(), ("a.py::top", "a.py::b")
    for _ in range(2):  # a degraded result is never stored, so the retry is no cache hit
        down = await l2_of(PedagogyEngine(env.cache, dead), *targets)
    assert dead.calls == 4 and db_rows(env.cache, "explanation") == []
    assert not any(d.llm_content_available or d.execution_steps for d in down)
    top, b, crud = full = await l2_of(env.engine, *targets, "a.py::crud")
    assert (b.upstream_callers, b.downstream_callees) == (["a.py::a", "a.py::zed"], ["a.py::c"])
    assert crud.dsa_cards == [] and top.execution_steps and top.llm_content_available
    assert card_rows(top.dsa_cards) == signal_rows(sigs)
    table = [("O(log n) per push or pop", "O(n)"), ("not determined",) * 2]
    assert [r[4:] for r in signal_rows(sigs)] == table
    for card, sig in zip(top.dsa_cards, sigs, strict=True):
        assert card.why_used_here == "" or any(e in card.why_used_here for e in sig.evidence)
    assert [deterministic(d) for d in down] == [deterministic(f) for f in full[:2]]


async def test_l3_architecture_uses_topology_and_spec_evidence(tmp_path: Path) -> None:
    envs = {spec: make_env(tmp_path / str(spec), HEX_SRC, spec=spec) for spec in (True, False)}
    ghost = engine_with(envs[True], edit_with(structural_evidence=["x/ghost.py"]))
    assert "x/ghost.py" in await expect_error(ghost, "repo", LS3, Kind.INVALID_OUTPUT)
    await expect_error(envs[True].engine, "nope", LS3, Kind.UNKNOWN_TARGET)
    assert stored(envs[True], LS3) == []
    for has_spec, env in envs.items():
        got = await explain(env.engine, "repo", LS3)
        l3, paths = got.l3, {f.file_path for f in env.snapshot.files}
        assert (got.cached, got.l1, got.l2, l3.target_id) == (False, None, None, "repo")
        assert l3.topology_pattern == env.topology.detected_pattern
        assert 1 <= len(l3.structural_evidence) <= 20 and 1 <= len(l3.alternatives) <= 3
        assert all(e in env.topology.evidence or e in paths for e in l3.structural_evidence)
        for alt in l3.alternatives:
            assert alt.pattern_name != l3.topology_pattern and alt.why_not_chosen.strip()
            assert alt.when_to_switch.strip()
        excerpts = [k.excerpt for links in env.provenance.spec_links.values() for k in links]
        assert bool(excerpts) is has_spec is (l3.spec_rationale is not None)
        assert not has_spec or any(x in l3.spec_rationale for x in excerpts)
    plain = envs[False]
    plain.cache.put_topology(plain.topology.model_copy(update={"confidence": 0.3333}))
    why = (await explain(plain.engine, "repo", LS3)).l3.why_this_folder_structure
    assert "0.33" in why and "low confidence" in why.lower()
    assert (await explain(plain.engine, "domain", LS3)).l3.target_id == "domain"


async def test_cache_hit_skips_llm_and_force_refresh_regenerates(tmp_path: Path) -> None:
    router = EditRouter(tag_call)  # tags each fresh result with its call number
    env, f = make_env(tmp_path, {"a.py": FG_SRC}, router=router), "a.py::f"
    for target, lens in ((f, LS1), ("repo", LS3)):
        n, first = router.calls, await explain(env.engine, target, lens)
        rows, again = stored(env, lens), await explain(env.engine, target, lens)
        assert (first.cached, again.cached, router.calls) == (False, True, n + 1)
        assert again.model_copy(update={"cached": False}) == first and stored(env, lens) == rows
        forced = await explain(env.engine, target, lens, force_refresh=True)
        assert (forced.cached, router.calls, len(stored(env, lens))) == (False, n + 2, 1)
        assert stored(env, lens) != rows and stored(env, lens)[0].count(f" v{n + 2}") == 1
    n, other = router.calls, await explain(env.engine, f, LS2)  # L1 row is no L2 hit
    assert (other.cached, router.calls) == (False, n + 1)
    env.cache.put_snapshot(rehash(env.snapshot, f, "changed"))
    new = await explain(env.engine, f, LS1)
    assert (new.cached, new.ast_hash, router.calls) == (False, "changed", n + 2)
    old = symbol_of(env.snapshot, f).ast_hash
    assert sorted(stored(env, LS1, "ast_hash")) == sorted([old, "changed"])


def test_new_modules_respect_layering() -> None:
    mods = ("spec_grounder", "topology", "llm_router", "cache_store", "pedagogy")

    def scan(rel: str) -> tuple[set[str], set[str], set[str]]:  # top-level imports, engines, calls
        src = Path(__file__).resolve().parents[3].joinpath(rel).read_text("utf-8")
        names, calls = set(), set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                names |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                names |= {n.module, *(f"{n.module}.{a.name}" for a in n.names)}
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                calls.add(n.func.id)
        eng = {x.split(".")[2] for x in names if x.startswith("backend.engines.")}
        return {x.split(".")[0] for x in names}, eng, calls

    tops, eng, _ = scan("backend/domain/models.py")
    assert tops <= {*sys.stdlib_module_names, "pydantic"} and not eng
    scans, graph = {m: scan(f"backend/engines/{m}.py") for m in mods}, {}
    for m, (tops, eng, calls) in scans.items():
        assert not {"fastapi", "mcp", "starlette"} & tops, m
        assert not {"exec", "eval", "compile", "__import__"} & calls, m
        assert ("subprocess" in tops) is (m == "spec_grounder"), m
        graph[m] = eng & set(mods)
    assert graph == {**dict.fromkeys(mods, set()), "pedagogy": {"cache_store", "llm_router"}}
    while graph:  # toposort: peel modules whose new-engine imports are all peeled
        leaves = [m for m, e in graph.items() if not e & graph.keys()]
        assert leaves, f"import cycle among {sorted(graph)}"
        graph = {m: e for m, e in graph.items() if m not in leaves}
