"""Property tests for mastery and the Kiro-native surfaces (Spec #03).

The file holds exactly four Hypothesis tests, one per design property (the fourth drives the
MCP tools in process). Shared helpers:

* ``EXPECTED_AFTER``: the transition table for events that the engine accepts.
* ``new_target(root)``: writes a one-function repository and returns the file path.
* ``rewrite_target(path, version)``: rewrites the function so its ``ast_hash`` changes.

Each example uses its own ``TemporaryDirectory`` and an in-memory ``CacheStore``, with the mock
provider and no network access.
"""

import asyncio
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.domain.models import MasteryState, ModuleMastery, PedagogyLens
from backend.engines.mastery import MasteryError, MasteryErrorKind
from backend.mcp_server.server import build_server
from backend.tests.mastery_support import (
    FixedClock,
    FixedGradeRouter,
    analyze,
    make_cache,
    make_services,
    tool_services,
)

os.environ.setdefault("LLM_PROVIDER", "mock")

pytestmark = pytest.mark.usefixtures("offline_guard")

# Shared by every property in this file.
PROPERTY_SETTINGS = settings(
    derandomize=True, max_examples=50, deadline=timedelta(milliseconds=500)
)

S = MasteryState
# (state before, event) -> state after, for an accepted event.
EXPECTED_AFTER: dict[tuple[MasteryState, str], MasteryState] = {
    **{(s, "pass_check"): S.MASTERED for s in S},
    **{(s, "fail_check"): s for s in S},
    **{(s, "view"): s for s in S},
    (S.UNAUDITED, "view"): S.DISSECTED,
    **{(s, "ast_changed"): s for s in S},
    (S.MASTERED, "ast_changed"): S.STALE,
    (S.DISSECTED, "ast_changed"): S.UNAUDITED,
}


REJECTIONS = {
    MasteryErrorKind.INVALID_TRANSITION,
    MasteryErrorKind.UNKNOWN_TARGET,
    MasteryErrorKind.REVIEW_DATE_OUT_OF_RANGE,
}


def target_source(version: int) -> str:
    return f"def target(x):\n    total = x + {version}\n    return total\n"


def new_target(root: Path) -> Path:
    path = root / "mod.py"
    path.write_text(target_source(0), encoding="utf-8")
    return path


def rewrite_target(path: Path, version: int) -> None:
    path.write_text(target_source(version), encoding="utf-8")


# Feature: 03-mastery-and-kiro-native, Property 1: Mastery events keep a valid state and never grant mastery on failure  # noqa: E501
# Validates: Requirements 3.3, 3.4, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.14, 3.15, 6.7, 22.2
@PROPERTY_SETTINGS
@given(
    events=st.lists(
        st.sampled_from(["view", "pass_check", "fail_check", "ast_changed"]),
        min_size=1,
        max_size=30,
    )
)
def test_mastery_events_keep_valid_state(events: list[str]) -> None:
    router = FixedGradeRouter()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = new_target(root)
        services = make_services(root, router, FixedClock())
        try:
            engine = services.mastery
            result = analyze(services, root)
            repo_id = result.repo_id
            target_id = next(
                s.id for f in result.snapshot.files for s in f.symbols if s.name == "target"
            )
            engine.set_study_mode(repo_id, True)

            def record() -> ModuleMastery:
                found = engine.get_record(repo_id, target_id)
                assert found is not None
                return found

            assert record().state is S.UNAUDITED
            version = 0
            for event in events:
                before = record()
                expected = EXPECTED_AFTER[(before.state, event)]
                try:
                    if event == "view":
                        engine.record_views(repo_id, [target_id])
                    elif event == "ast_changed":
                        version += 1
                        rewrite_target(path, version)
                        analyze(services, root)
                    else:
                        router.score = 1.0 if event == "pass_check" else 0.0
                        check = engine.start_check(repo_id, target_id)
                        answers = [(q.question_id, "target total") for q in check.questions]
                        asyncio.run(engine.submit_answers(repo_id, target_id, answers))
                except MasteryError as exc:
                    # Only these rejections are legitimate here (the date overflow comes from
                    # long pass streaks); a rejected event leaves the record unchanged.
                    assert exc.kind in REJECTIONS, exc.kind
                    assert record() == before
                    continue
                after = record()
                assert after.state in set(S)
                assert after.interval_days >= 0
                assert after.repetitions >= 0
                if event == "fail_check" and before.state is not S.MASTERED:
                    assert after.state is not S.MASTERED
                assert after.state is expected
        finally:
            services.cache.close()


# Feature: 03-mastery-and-kiro-native, Property 2: Consecutive passes follow the review schedule
# Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.12, 22.3
@settings(derandomize=True, max_examples=20, deadline=timedelta(milliseconds=500))
@given(passes=st.integers(min_value=1, max_value=20))
def test_consecutive_passes_follow_review_schedule(passes: int) -> None:
    router = FixedGradeRouter(1.0)
    clock = FixedClock()
    now = clock()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        new_target(root)
        services = make_services(root, router, clock)
        try:
            engine = services.mastery
            result = analyze(services, root)
            repo_id = result.repo_id
            target_id = next(
                s.id for f in result.snapshot.files for s in f.symbols if s.name == "target"
            )
            engine.set_study_mode(repo_id, True)

            def record() -> ModuleMastery:
                found = engine.get_record(repo_id, target_id)
                assert found is not None
                return found

            assert record().ease_factor == 2.5
            for k in range(1, passes + 1):
                before = record()
                check = engine.start_check(repo_id, target_id)
                answers = [(q.question_id, "target total") for q in check.questions]
                try:
                    asyncio.run(engine.submit_answers(repo_id, target_id, answers))
                except MasteryError as exc:
                    # Only the first pass whose date passes 9999-12-31T23:59:59Z is rejected.
                    assert exc.kind is MasteryErrorKind.REVIEW_DATE_OUT_OF_RANGE
                    assert k == 17
                    assert record() == before
                    break
                after = record()
                assert after.repetitions == before.repetitions + 1
                assert after.interval_days >= before.interval_days
                if k == 1:
                    assert after.interval_days == 1
                elif k == 2:
                    assert after.interval_days == 6
                else:
                    assert after.interval_days == round(before.interval_days * 2.5)
                due = now + timedelta(days=after.interval_days)
                assert after.next_review_at == due.strftime("%Y-%m-%dT%H:%M:%SZ")
                assert after.ease_factor == 2.5
            else:
                assert passes <= 16
        finally:
            services.cache.close()


# Feature: 03-mastery-and-kiro-native, Property 3: Study Mode toggles change nothing but the flag
# Validates: Requirements 2.5, 2.6, 22.4
@PROPERTY_SETTINGS
@given(toggles=st.lists(st.booleans(), min_size=1, max_size=20))
def test_study_mode_toggles_change_only_the_flag(toggles: list[bool]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        new_target(root)
        services = make_services(root, FixedGradeRouter(), FixedClock())
        try:
            engine, cache = services.mastery, services.cache
            result = analyze(services, root)
            repo_id = result.repo_id
            symbol = next(s for f in result.snapshot.files for s in f.symbols if s.name == "target")
            asyncio.run(
                services.pedagogy.explain_target(repo_id, symbol.id, PedagogyLens.L1_SYNTAX)
            )
            other = "other-repo"
            engine.set_study_mode(other, True)

            def observe() -> tuple[object, ...]:
                envelope = cache.get_explanation(
                    repo_id, symbol.ast_hash, symbol.id, PedagogyLens.L1_SYNTAX
                )
                assert envelope is not None
                records = cache.read(lambda tx: tx.list_mastery(repo_id))
                return (
                    records,
                    envelope,
                    cache.get_snapshot(repo_id),
                    cache.get_provenance(repo_id),
                    cache.get_topology(repo_id),
                )

            before = observe()
            assert before[0]  # at least one Mastery_Record
            for enabled in toggles:
                engine.set_study_mode(repo_id, enabled)
                assert observe() == before
                assert engine.get_study_mode(repo_id) is enabled
            assert engine.get_study_mode(repo_id) is toggles[-1]
            assert engine.get_study_mode(other) is True
        finally:
            services.cache.close()


def generated_repo_source(calls: list[int]) -> str:
    """One module of ``len(calls)`` functions ``fn_0``..; ``calls[i]`` picks a callee or none."""
    count = len(calls)
    blocks = []
    for i, choice in enumerate(calls):
        callee = choice % count if choice >= 0 and choice % count != i else None
        body = f"    return fn_{callee}(x)\n" if callee is not None else "    return x\n"
        blocks.append(f"def fn_{i}(x):\n{body}")
    return "\n\n".join(blocks)


# Feature: 03-mastery-and-kiro-native, Property 4: Every MCP tool returns a JSON-serializable Tool_Result  # noqa: E501
# Validates: Requirements 16.4, 16.6, 16.7, 16.8, 16.9, 16.10, 22.5
@settings(derandomize=True, max_examples=15, deadline=timedelta(milliseconds=500))
@given(calls=st.lists(st.integers(min_value=-1, max_value=9), min_size=1, max_size=10))
def test_every_mcp_tool_returns_json_serializable_result(calls: list[int]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "mod.py").write_text(generated_repo_source(calls), encoding="utf-8")
        cache = make_cache()
        try:
            server = build_server(tool_services(cache, FixedGradeRouter(), FixedClock()))
            repo = str(root)
            target_id = "mod.py::fn_0"
            invocations = [
                ("dissect_symbol", {"repo_path": repo, "target_id": target_id, "lens": "L2_FLOW"}),
                ("trace_blast_radius", {"repo_path": repo, "target_id": target_id, "max_depth": 3}),
                ("analyze_folder_architecture", {"repo_path": repo}),
                ("check_spec_drift", {"repo_path": repo}),
                ("get_comprehension_vitals", {"repo_path": repo}),
            ]
            for name, args in invocations:
                result = asyncio.run(server.call_tool(name, args))
                payload = result.structured_content
                assert isinstance(payload, dict), name
                json.dumps(payload)
                assert isinstance(payload.get("ok"), bool), name
        finally:
            cache.close()
