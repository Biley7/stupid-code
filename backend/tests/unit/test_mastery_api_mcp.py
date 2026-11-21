"""Unit tests for Spec #03: mastery engine, REST API, Crew webhook, MCP tools, manifests.

Test plan: 1-6 Mastery_Engine state and vitals (this block). Later tasks append 7-24.
"""

import asyncio
import json
import re
import subprocess
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.api.crew_signature import InvalidSignature, verify_crew_signature
from backend.api.rate_limit import RateLimiter
from backend.api.routes import repos as repos_routes
from backend.api.settings import ApiSettings, ConfigurationError, load_api_settings
from backend.domain.models import MasteryState as S
from backend.domain.models import SocraticGrade
from backend.engines.analysis_pipeline import derive_github_repo_id, derive_local_repo_id
from backend.engines.llm_router import MOCK_SLICE_MARKER, LLMRouter, LLMSettings
from backend.engines.mastery import MasteryEngine, MasteryError, MasteryErrorKind, apply_pass
from backend.mcp_server.server import TOOL_NAMES
from backend.tests import mastery_support as ms
from backend.tests.mastery_support import CALLEE, CALLER, LONELY, TOP


def test_study_mode_default_persistence_and_validation(tmp_path: Path) -> None:
    cache = ms.make_cache(tmp_path / "c.db")
    engine = MasteryEngine(cache, ms.FixedGradeRouter(), ms.FixedClock())
    assert engine.get_study_mode("no-snapshot") is False
    assert cache.read(lambda tx: tx.get_study_mode("no-snapshot")) is None  # read wrote nothing
    assert engine.set_study_mode("no-snapshot", True) is True
    assert engine.set_study_mode("no-snapshot", True) is True  # idempotent
    assert MasteryEngine(cache, ms.FixedGradeRouter(), ms.FixedClock()).get_study_mode(
        "no-snapshot"
    )
    assert engine.get_study_mode("other") is False
    for bad in (1, "true", None):
        with pytest.raises(MasteryError) as bad_value:
            engine.set_study_mode("no-snapshot", bad)  # type: ignore[arg-type]
        assert bad_value.value.kind is MasteryErrorKind.INVALID_INPUT
    for bad_id in ("", "a/b", "x" * 101):
        with pytest.raises(MasteryError) as bad_repo:
            engine.get_study_mode(bad_id)
        assert bad_repo.value.kind is MasteryErrorKind.INVALID_INPUT
    assert engine.get_study_mode("no-snapshot") is True


def test_registration_and_view_transitions(tmp_path: Path) -> None:
    services, _, repo_id, root = ms.setup_tiny(tmp_path)
    engine = services.mastery
    initial = engine.get_record(repo_id, CALLER)
    assert (initial.state, initial.ease_factor, initial.interval_days) == (S.UNAUDITED, 2.5, 0)
    assert (initial.repetitions, initial.next_review_at, initial.last_verified_at) == (
        0,
        None,
        None,
    )
    assert set(ms.tiny_states(engine, repo_id).values()) == {S.UNAUDITED}
    engine.record_views(repo_id, [CALLER])  # Study Mode off: nothing is written
    assert engine.get_record(repo_id, CALLER) == initial
    engine.set_study_mode(repo_id, True)
    with pytest.raises(MasteryError) as unknown:
        engine.record_views(repo_id, [TOP, "main.py::nope"])
    assert unknown.value.kind is MasteryErrorKind.UNKNOWN_TARGET
    assert engine.get_record(repo_id, TOP).state is S.UNAUDITED  # all-or-nothing
    engine.record_views(repo_id, [CALLER, TOP])
    assert ms.run_check(engine, repo_id, CALLEE).new_state is S.MASTERED
    engine.record_views(repo_id, [CALLER, CALLEE])  # DISSECTED and MASTERED stay put
    assert ms.tiny_states(engine, repo_id) == {
        CALLER: S.DISSECTED, TOP: S.DISSECTED, LONELY: S.UNAUDITED, CALLEE: S.MASTERED,
    }  # fmt: skip
    before = engine.get_record(repo_id, CALLEE)
    ms.analyze(services, root)  # unchanged hashes write nothing
    assert engine.get_record(repo_id, CALLEE) == before
    assert engine.get_record(repo_id, CALLER).state is S.DISSECTED


def test_pass_fail_and_ast_change_transitions(tmp_path: Path) -> None:
    services, clock, repo_id, root = ms.setup_tiny(tmp_path)
    engine = services.mastery
    engine.set_study_mode(repo_id, True)
    failing = MasteryEngine(services.cache, ms.FixedGradeRouter(0.69), clock)
    verdict = ms.run_check(failing, repo_id, LONELY)
    assert (verdict.passed, verdict.new_state, verdict.next_review_at) == (False, S.UNAUDITED, None)
    assert engine.get_record(repo_id, LONELY).repetitions == 0
    engine.record_views(repo_id, [CALLER])
    assert ms.run_check(engine, repo_id, TOP).new_state is S.MASTERED
    assert ms.run_check(failing, repo_id, TOP).new_state is S.MASTERED  # a fail never demotes
    mastered = engine.get_record(repo_id, TOP)
    assert (mastered.repetitions, mastered.last_verified_at) == (1, "2025-01-01T00:00:00Z")
    assert ms.run_check(engine, repo_id, CALLEE).new_state is S.MASTERED
    (root / "util.py").write_text(ms.CALLEE_SRC.replace("x + 1", "x + 2"), encoding="utf-8")
    (root / "main.py").write_text(
        ms.CALLER_SRC.replace("result = callee(v)", "result = callee(v) + 1"), encoding="utf-8"
    )
    ms.analyze(services, root)
    stale = engine.get_record(repo_id, CALLEE)
    assert (stale.state, stale.repetitions, stale.interval_days, stale.next_review_at) == (
        S.STALE, 0, 0, None,
    )  # fmt: skip
    assert engine.get_record(repo_id, CALLER).state is S.UNAUDITED  # DISSECTED -> UNAUDITED
    assert engine.get_record(repo_id, TOP) == mastered  # untouched symbol keeps its record
    assert ms.run_check(engine, repo_id, CALLEE).new_state is S.MASTERED
    assert engine.get_record(repo_id, CALLEE).repetitions == 1


def test_review_schedule_intervals(tmp_path: Path) -> None:
    services, clock, repo_id, _ = ms.setup_tiny(tmp_path)
    engine = services.mastery
    engine.set_study_mode(repo_id, True)
    seen = []
    for _ in range(3):
        verdict = ms.run_check(engine, repo_id, CALLEE)
        record = engine.get_record(repo_id, CALLEE)
        seen.append((record.repetitions, record.interval_days, record.ease_factor))
        assert verdict.next_review_at == record.next_review_at
    assert seen == [(1, 1, 2.5), (2, 6, 2.5), (3, 15, 2.5)]  # 1, 6, round(6 * 2.5)
    assert record.next_review_at == "2025-01-16T00:00:00Z"
    clock.advance(days=10)
    ms.run_check(engine, repo_id, CALLEE)
    assert engine.get_record(repo_id, CALLEE).next_review_at == "2025-02-18T00:00:00Z"  # 38 days
    late = datetime(9999, 12, 31, tzinfo=UTC)
    with pytest.raises(MasteryError) as out_of_range:
        apply_pass(record, late)
    assert out_of_range.value.kind is MasteryErrorKind.REVIEW_DATE_OUT_OF_RANGE


def test_vitals_counts_percentage_and_file_states(tmp_path: Path) -> None:
    services, _, repo_id, root = ms.setup_tiny(tmp_path)
    engine = services.mastery
    assert engine.get_vitals(repo_id).study_mode_enabled is False
    engine.set_study_mode(repo_id, True)
    engine.record_views(repo_id, [TOP])
    ms.run_check(engine, repo_id, CALLER)
    ms.run_check(engine, repo_id, CALLEE)
    vitals = engine.get_vitals(repo_id)
    assert (vitals.total_modules, vitals.mastered_count, vitals.dissected_count) == (4, 2, 1)
    assert (vitals.unaudited_count, vitals.stale_count, vitals.mastery_percentage) == (1, 0, 50.0)
    assert vitals.due_for_review == [] and vitals.study_mode_enabled is True
    # main.py holds MASTERED, DISSECTED and UNAUDITED symbols: the weakest one wins.
    assert list(vitals.file_states.items()) == [("main.py", S.UNAUDITED), ("util.py", S.MASTERED)]
    assert engine.get_vitals(repo_id).model_dump_json() == vitals.model_dump_json()
    (root / "util.py").write_text(ms.CALLEE_SRC.replace("x + 1", "x + 3"), encoding="utf-8")
    ms.analyze(services, root)
    after = engine.get_vitals(repo_id)
    assert (after.stale_count, after.mastered_count, after.mastery_percentage) == (1, 1, 25.0)
    assert after.file_states["util.py"] is S.STALE
    with pytest.raises(MasteryError) as missing:
        engine.get_vitals("unknown-repo")
    assert missing.value.kind is MasteryErrorKind.UNKNOWN_REPOSITORY


def test_due_for_review_order_with_controlled_clock(tmp_path: Path) -> None:
    services, clock, repo_id, _ = ms.setup_tiny(tmp_path)
    engine = services.mastery
    engine.set_study_mode(repo_id, True)
    ms.run_check(engine, repo_id, TOP)  # passed first, but ties sort by target id
    ms.run_check(engine, repo_id, CALLER)
    clock.advance(days=1)
    ms.run_check(engine, repo_id, CALLEE)  # due on day 2
    clock.now = ms.START.replace(hour=12)
    assert engine.get_vitals(repo_id).due_for_review == []
    clock.now = ms.START.replace(day=2)  # exactly at next_review_at counts as due
    assert engine.get_vitals(repo_id).due_for_review == [CALLER, TOP]
    clock.now = ms.START.replace(day=3)
    assert engine.get_vitals(repo_id).due_for_review == [CALLER, TOP, CALLEE]
    assert engine.get_vitals(repo_id).mastered_count == 3


def test_socratic_check_is_grounded_and_deterministic(tmp_path: Path) -> None:
    services, _, repo_id, root = ms.setup_tiny(tmp_path)
    engine = services.mastery
    with pytest.raises(MasteryError) as off:
        engine.start_check(repo_id, CALLER)
    assert off.value.kind is MasteryErrorKind.STUDY_MODE_DISABLED
    engine.set_study_mode(repo_id, True)
    symbols, signals = ms.snapshot_symbols(services, repo_id)
    dsa_names = {s.pattern_name for s in signals}
    before = services.cache.read(lambda tx: tx.list_mastery(repo_id))
    counts = {}
    for target in (CALLER, TOP, LONELY):
        check = engine.start_check(repo_id, target)
        counts[target] = len(check.questions)
        assert check == engine.start_check(repo_id, target)  # same ids and text twice
        symbol = symbols[target]
        source = (root / symbol.file_path).read_text(encoding="utf-8")
        for question in check.questions:
            assert symbol.ast_hash[:16] in question.question_id
            path, _, span = question.line_reference.rpartition(":")
            first, last = (int(n) for n in span.split("-"))
            assert path == symbol.file_path
            assert symbol.start_line <= first <= last <= symbol.end_line
            assert 1 <= len(question.expected_concepts) <= 5
            for concept in question.expected_concepts:
                assert concept in source or concept in symbols or concept in dsa_names or any(
                    concept == s.name for s in symbols.values()
                )  # fmt: skip
    assert counts == {CALLER: 2, TOP: 2, LONELY: 1}
    assert services.cache.read(lambda tx: tx.list_mastery(repo_id)) == before  # no write


def test_mock_grader_and_answer_association(tmp_path: Path) -> None:
    router = ms.RecordingRouter(1.0)
    services, _, repo_id, _ = ms.setup_tiny(tmp_path, router)
    engine = services.mastery
    engine.set_study_mode(repo_id, True)
    check = engine.start_check(repo_id, CALLER)
    ids = [q.question_id for q in check.questions]
    answers = [(ids[0], "  first answer "), (ids[1], "second answer")]
    asyncio.run(engine.submit_answers(repo_id, CALLER, list(reversed(answers))))
    prompt, model = router.recorded[0]
    assert model is SocraticGrade
    sent = json.loads(prompt.partition(MOCK_SLICE_MARKER)[2])
    assert sent["answers"] == [
        {"question_id": ids[0], "answer": "first answer"},
        {"question_id": ids[1], "answer": "second answer"},
    ]
    concepts = [c for q in check.questions for c in q.expected_concepts]
    mock = LLMRouter(LLMSettings(LLM_PROVIDER="mock"))
    grade = asyncio.run(mock.generate_structured("s", prompt, SocraticGrade))
    distinct = set(concepts)
    hits = sum(1 for c in distinct if c.casefold() in "first answer second answer")
    assert grade.score == hits / len(distinct)
    stale_id = ids[0].rsplit("-", 1)[0] + "-" + "0" * 16
    ok = "x"
    bad_sets = [
        [(ids[0], ok)],
        [(ids[0], ok), ("sq1-unknown", ok)],
        [(ids[0], ok), (ids[0], ok)],
        [(ids[0], ok), (ids[1], "   ")],
        [(ids[0], ok), (ids[1], "y" * 2001)],
        [(stale_id, ok), (ids[1], ok)],
    ]
    for bad in bad_sets:
        with pytest.raises(MasteryError) as err:
            asyncio.run(engine.submit_answers(repo_id, CALLER, bad))
        assert err.value.kind is MasteryErrorKind.INVALID_ANSWERS
    assert len(router.recorded) == 1 and router.calls == 1  # rejected before the router


def test_pass_threshold_boundary(tmp_path: Path) -> None:
    services, clock, repo_id, _ = ms.setup_tiny(tmp_path)
    services.mastery.set_study_mode(repo_id, True)
    before = services.mastery.get_record(repo_id, CALLEE)
    low = MasteryEngine(services.cache, ms.FixedGradeRouter(0.69), clock)
    verdict = ms.run_check(low, repo_id, CALLEE)
    assert (verdict.passed, verdict.new_state) == (False, S.UNAUDITED)
    assert services.mastery.get_record(repo_id, CALLEE) == before
    high = MasteryEngine(services.cache, ms.FixedGradeRouter(0.70), clock)
    verdict = ms.run_check(high, repo_id, CALLEE)
    assert (verdict.passed, verdict.new_state) == (True, S.MASTERED)
    assert services.mastery.get_record(repo_id, CALLEE).state is S.MASTERED


def test_failed_or_invalid_grading_grants_no_mastery(tmp_path: Path) -> None:
    services, clock, repo_id, _ = ms.setup_tiny(tmp_path)
    services.mastery.set_study_mode(repo_id, True)
    before = services.mastery.get_record(repo_id, CALLEE)
    for mode in ("error", "timeout", "invalid"):
        router = ms.FailingGradeRouter(mode, sleep=1.0)
        engine = MasteryEngine(services.cache, router, clock, grading_timeout_seconds=0.05)
        with pytest.raises(MasteryError) as err:
            ms.run_check(engine, repo_id, CALLEE)
        assert err.value.kind is MasteryErrorKind.GRADING_UNAVAILABLE
        assert str(err.value) == "grading is unavailable"
        assert "fake failure" not in str(err.value) and router.calls == 1
        assert services.mastery.get_record(repo_id, CALLEE) == before


def test_ingest_validation_truncation_and_local_ingest_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, client = ms.api_client(tmp_path)
    root = ms.write_tiny_repo(tmp_path / "repo")
    assert client.post("/api/repos/ingest", content=b"{nope").status_code == 400
    both = {"path": str(root), "url": "https://github.com/a/b"}
    assert client.post("/api/repos/ingest", json=both).status_code == 400
    bad = client.post("/api/repos/ingest", json={"path": str(root), "max_files": 0})
    assert (bad.status_code, bad.json()["error"]["code"]) == (422, "invalid_limit")
    ok = client.post("/api/repos/ingest", json={"path": str(root)})
    assert (ok.status_code, ok.json()["truncated"], ok.json()["summary"]["file_count"]) == (
        200, False, 2,
    )  # fmt: skip
    cut = client.post("/api/repos/ingest", json={"path": str(root), "max_files": 1})
    assert (cut.status_code, cut.json()["truncated"]) == (200, True)
    calls: list[object] = []
    monkeypatch.setattr(repos_routes, "analyze_repository", lambda *a, **k: calls.append(a))
    _, _, locked = ms.api_client(tmp_path, settings=ApiSettings(allow_local_ingest=False))
    denied = locked.post("/api/repos/ingest", json={"path": str(root)})
    assert (denied.status_code, denied.json()["error"]["code"]) == (403, "local_ingest_disabled")
    assert calls == []


def test_list_snapshot_and_explain_reads(tmp_path: Path) -> None:
    services, _, client = ms.api_client(tmp_path)
    assert client.get("/api/repos").json() == []
    root = ms.write_tiny_repo(tmp_path / "repo")
    repo_id = ms.ingest_path(client, root)
    listed = client.get("/api/repos").json()
    assert listed == [
        {"repo_id": repo_id, "file_count": 2, "symbol_count": 4, "study_mode_enabled": False}
    ]
    stored = services.cache.read(lambda tx: tx.get_snapshot(repo_id))
    body = client.get(f"/api/repos/{repo_id}/snapshot").json()
    assert body["snapshot"]["root_path"] == "."
    assert body["snapshot"] == {**stored.model_dump(mode="json"), "root_path": "."}
    assert client.get("/api/repos/no-such/snapshot").status_code == 404
    url = f"/api/repos/{repo_id}/explain"
    records = lambda: services.cache.read(lambda tx: tx.list_mastery(repo_id))  # noqa: E731
    before = records()
    reply = client.post(url, json={"target_id": CALLER, "lens": "L1_SYNTAX"})
    assert reply.status_code == 200
    assert set(reply.json()) == {"envelope", "blast_radius"}
    assert records() == before  # Study Mode off
    client.post(f"/api/repos/{repo_id}/study-mode", json={"enabled": True})
    assert client.post(url, json={"target_id": CALLER, "lens": "L1_SYNTAX"}).status_code == 200
    states = {r.target_id: r.state for r in records()}
    assert states[CALLER] is S.DISSECTED and states[TOP] is S.UNAUDITED
    before = records()
    arch = client.post(url, json={"target_id": repo_id, "lens": "L3_ARCHITECTURE"})
    assert arch.status_code == 200 and records() == before
    assert (
        client.post(url, json={"target_id": "x.py::nope", "lens": "L1_SYNTAX"}).status_code == 404
    )


def test_study_mode_toggle_and_read_only_vitals(tmp_path: Path) -> None:
    services, _, client = ms.api_client(tmp_path)
    repo_id = ms.ingest_path(client, ms.write_tiny_repo(tmp_path / "repo"))
    url = f"/api/repos/{repo_id}/study-mode"
    for value in (True, True, False):
        reply = client.post(url, json={"enabled": value})
        assert (reply.status_code, reply.json()) == (
            200, {"repo_id": repo_id, "study_mode_enabled": value},
        )  # fmt: skip
    for bad in ({"enabled": "true"}, {"enabled": 1}, {}, [True]):
        assert client.post(url, json=bad).status_code == 422
    assert services.mastery.get_study_mode(repo_id) is False
    services.mastery.set_study_mode(repo_id, True)
    before = services.cache.read(lambda tx: tx.list_mastery(repo_id))
    vitals = client.get(f"/api/repos/{repo_id}/vitals")
    assert vitals.status_code == 200
    assert vitals.json()["total_modules"] == 4 and vitals.json()["study_mode_enabled"] is True
    assert services.cache.read(lambda tx: tx.list_mastery(repo_id)) == before
    assert client.get("/api/repos/unknown/vitals").status_code == 404


def test_socratic_start_and_submit_endpoints(tmp_path: Path) -> None:
    services, _, client = ms.api_client(tmp_path)
    repo_id = ms.ingest_path(client, ms.write_tiny_repo(tmp_path / "repo"))
    base = f"/api/repos/{repo_id}/socratic"
    off = client.post(f"{base}/start", json={"target_id": CALLER})
    assert (off.status_code, off.json()["error"]["code"]) == (409, "study_mode_disabled")
    client.post(f"/api/repos/{repo_id}/study-mode", json={"enabled": True})
    start = client.post(f"{base}/start", json={"target_id": CALLER})
    questions = start.json()["questions"]
    assert start.status_code == 200 and len(questions) == 2
    assert all(q["expected_concepts"] == [] for q in questions)
    answers = [{"question_id": q["question_id"], "answer": "my answer"} for q in questions]
    done = client.post(f"{base}/submit", json={"target_id": CALLER, "answers": answers})
    assert done.status_code == 200
    assert (done.json()["passed"], done.json()["new_state"]) == (True, "MASTERED")
    assert done.json()["next_review_at"] is not None
    assert services.mastery.get_record(repo_id, CALLER).state is S.MASTERED
    unknown = client.post(f"{base}/start", json={"target_id": "main.py::nope"})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "unknown_target")
    wrong = client.post(f"{base}/submit", json={"target_id": CALLER, "answers": answers[:1]})
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "invalid_answers")
    missing = client.post("/api/repos/nope/socratic/start", content=b"not json")
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "repo_not_found")


def test_error_envelope_shape_on_non_2xx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    services, _, client = ms.api_client(tmp_path)
    repo_id = ms.ingest_path(client, ms.write_tiny_repo(tmp_path / "repo"))

    async def boom(*_args, **_kwargs):
        raise RuntimeError("secret-path /Users/x SELECT * FROM t")

    monkeypatch.setattr(type(services.dissection), "dissect", boom)
    replies = [
        client.get("/api/nothing-here"),
        client.get("/api/repos/ingest"),
        client.post(f"/api/repos/{repo_id}/study-mode", json={"enabled": "x"}),
        client.post(
            f"/api/repos/{repo_id}/explain", json={"target_id": CALLER, "lens": "L1_SYNTAX"}
        ),
    ]
    assert [r.status_code for r in replies] == [404, 405, 422, 500]
    for reply in replies:
        body = reply.json()
        assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
        assert body["error"]["code"] and body["error"]["message"]
        for leak in ("/Users", "SELECT", "Traceback", "RuntimeError", "secret-path"):
            assert leak not in reply.text
    assert replies[3].json()["error"]["code"] == "internal_error"


def test_github_rate_limit_with_controlled_clock(tmp_path: Path) -> None:
    clock = ms.FixedClock()
    services = ms.make_services(tmp_path, None, clock, git_runner=ms.git_double(ms.TINY_REPO))
    limiter = RateLimiter(5, 60)
    client = ms.make_client(services, rate_limiter=limiter)
    url = {"url": "https://github.com/octo/demo"}
    for _ in range(5):
        assert client.post("/api/repos/ingest", json=url).status_code == 200
        clock.advance(seconds=1)
    blocked = client.post("/api/repos/ingest", json=url)
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (429, "rate_limited")
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60
    local = client.post("/api/repos/ingest", json={"path": str(ms.write_tiny_repo(tmp_path / "r"))})
    assert local.status_code == 200  # path requests are not counted
    assert client.post("/api/repos/ingest", json=url).status_code == 429
    clock.advance(seconds=60)
    assert client.post("/api/repos/ingest", json=url).status_code == 200


CREW = "/api/apps/stupid-code/crew"


def test_crew_file_menu_actions(tmp_path: Path) -> None:
    services, _, client = ms.api_client(tmp_path)
    root = ms.write_tiny_repo(tmp_path / "repo", {**ms.TINY_REPO, "pkg/mod.py": ms.CALLEE_SRC})
    repo_id = ms.ingest_path(client, root)
    assert "pkg" in services.cache.read(lambda tx: tx.get_topology(repo_id)).directory_roles
    send = lambda **body: client.post(CREW, json={"repo_id": repo_id, **body})  # noqa: E731
    file_reply = send(action="autopsy_file", path="main.py")
    assert file_reply.status_code == 200 and file_reply.json()["truncated"] is False
    ids = [s["target_id"] for s in file_reply.json()["symbols"]]
    assert ids == [CALLER, TOP, LONELY]  # sorted by start line
    assert all(set(s) >= {"envelope", "blast_radius"} for s in file_reply.json()["symbols"])
    assert file_reply.json()["symbols"][0]["envelope"]["lens"] == "L2_FLOW"
    for path in (".", "pkg"):
        folder = send(action="explain_folder_architecture", path=path)
        assert folder.status_code == 200 and folder.json()["envelope"]["lens"] == "L3_ARCHITECTURE"
    for action in ("autopsy_file", "explain_folder_architecture"):
        for bad in ("../x.py", "/etc/passwd", "a\\b.py", "nope/none.py"):
            reply = send(action=action, path=bad)
            assert (reply.status_code, reply.json()["error"]["code"]) == (404, "unknown_target")
    gone = client.post(CREW, json={"action": "study_mode", "repo_id": "nope", "enabled": True})
    assert (gone.status_code, gone.json()["error"]["code"]) == (404, "repo_not_found")


def test_crew_study_mode_and_signatures(tmp_path: Path) -> None:
    services, clock, client = ms.api_client(tmp_path, settings=ApiSettings(crew_secret="s3cret"))
    repo_id = ms.ingest_path(client, ms.write_tiny_repo(tmp_path / "repo"))
    body = json.dumps({"action": "study_mode", "repo_id": repo_id, "enabled": True}).encode()
    now = int(clock.now.timestamp())
    sign = lambda ts: ms.sign_proxy("s3cret", ts, "POST", CREW, body)  # noqa: E731
    post = lambda headers: client.post(CREW, content=body, headers=headers)  # noqa: E731
    rejected = [
        ms.sign_kiro(body, "wrong"),
        {"X-Crew-Proxy": f"{now}:{'0' * 64}"},
        sign(now - 61),
        {},
        {**ms.sign_kiro(body, "wrong"), **sign(now)},
    ]
    for headers in rejected:
        reply = post(headers)
        assert (reply.status_code, reply.json()["error"]["code"]) == (401, "invalid_signature")
        assert services.mastery.get_study_mode(repo_id) is False
    ok = post(ms.sign_kiro(body, "s3cret"))
    assert ok.status_code == 200 and ok.json()["study_mode_enabled"] is True
    assert (
        ok.json()["vitals"]["study_mode_enabled"] is True
        and ok.json()["vitals"]["total_modules"] == 4
    )
    off = json.dumps({"action": "study_mode", "repo_id": repo_id, "enabled": False}).encode()
    proxy = ms.sign_proxy("s3cret", now + 60, "POST", CREW, off)
    reply = client.post(CREW, content=off, headers=proxy)
    assert reply.status_code == 200 and reply.json()["study_mode_enabled"] is False
    open_client = ms.make_client(services)  # no secret: unsigned requests are accepted
    assert open_client.post(CREW, content=body).json()["study_mode_enabled"] is True
    pair = [("X-Kiro-Signature", v) for v in ms.sign_kiro(body, "s3cret").values()] * 2
    for headers, when in ((pair, clock.now), ([], datetime(2025, 1, 1))):
        with pytest.raises(InvalidSignature):
            verify_crew_signature("s3cret", headers, "POST", CREW, body, when)


def test_mcp_tools_succeed_on_valid_input(tmp_path: Path) -> None:
    server, services, router, repo_id, root = ms.mcp_setup(tmp_path)
    call, repo = partial(ms.call_tool, server), str(root)
    names = [t.name for t in asyncio.run(server.list_tools())]
    assert sorted(names) == sorted(TOOL_NAMES) and len(names) == 5
    records = lambda: services.cache.read(lambda tx: tx.list_mastery(repo_id))  # noqa: E731
    services.mastery.set_study_mode(repo_id, True)
    reply = call("dissect_symbol", repo_path=repo, target_id=CALLER, lens="L1_SYNTAX")
    assert reply["ok"] is True and set(reply) >= {"envelope", "blast_radius"}
    assert ms.tiny_states(services.mastery, repo_id)[CALLER] is S.DISSECTED
    before = records()
    arch = call("dissect_symbol", repo_path=repo, target_id=repo_id, lens="L3_ARCHITECTURE")
    assert arch["ok"] is True and records() == before  # L3 records no view
    flat = call("trace_blast_radius", repo_path=repo, target_id=CALLER, max_depth=0)["blast_radius"]
    assert flat["downstream_callees"] == flat["upstream_callers"] == []
    deep = call("trace_blast_radius", repo_path=repo, target_id=CALLER, max_depth=1)
    assert CALLEE in deep["blast_radius"]["downstream_callees"]
    calls = len(router.recorded)
    assert call("analyze_folder_architecture", repo_path=repo)["ok"] is True
    assert len(router.recorded) == calls  # no LLM call
    drift = call("check_spec_drift", repo_path=repo)
    assert drift["ok"] is True and isinstance(drift["has_kiro_specs"], bool)
    assert isinstance(drift["drift_items"], list)
    vitals = call("get_comprehension_vitals", repo_path=repo)
    assert vitals["ok"] is True and vitals["vitals"]["study_mode_enabled"] is True
    assert vitals["vitals"]["total_modules"] == 4 and records() == before


def test_mcp_tools_fail_cleanly_on_invalid_input(tmp_path: Path) -> None:
    server, services, _, repo_id, root = ms.mcp_setup(tmp_path)
    repo, before = str(root), services.cache.read(lambda tx: tx.list_mastery(repo_id))
    ghost, fresh = str(tmp_path / "missing"), str(ms.write_tiny_repo(tmp_path / "new"))
    sym = {"repo_path": repo, "target_id": CALLER}
    cases = [
        ("dissect_symbol", {"repo_path": "", "target_id": CALLER}, "invalid_repo_path"),
        ("check_spec_drift", {"repo_path": ghost}, "invalid_repo_path"),
        ("dissect_symbol", {**sym, "target_id": "main.py::nope"}, "unknown_target"),
        ("dissect_symbol", {**sym, "lens": "L9"}, "invalid_lens"),
        ("trace_blast_radius", {**sym, "max_depth": True}, "invalid_max_depth"),
        ("trace_blast_radius", {**sym, "max_depth": 21}, "invalid_max_depth"),
        ("get_comprehension_vitals", {"repo_path": fresh}, "repo_not_analyzed"),
    ]
    for name, args, code in cases:
        reply = ms.call_tool(server, name, **args)
        assert reply["ok"] is False and set(reply["error"]) == {"code", "message"}
        assert reply["error"]["code"] == code and str(tmp_path) not in reply["error"]["message"]
    assert services.cache.read(lambda tx: tx.list_mastery(repo_id)) == before


def test_manifests_hooks_and_launch_config(tmp_path: Path) -> None:
    docs = ms.manifest_docs()
    ms.check_documents(docs)
    assert len([n for n in docs if n.startswith("crew/agents/")]) == 2
    mcp, power = (docs[n]["mcpServers"]["stupid-code"] for n in ms.MANIFESTS[:2])
    assert mcp["command"] == power["command"] == ".venv/bin/python"
    assert mcp["args"] == power["args"] == ["backend/mcp_server/server.py"]
    assert (ms.ROOT / mcp["args"][0]).is_file() and docs[ms.MANIFESTS[2]]["name"] == "stupid-code"
    verify, anti = (docs[h]["hooks"][0] for h in ms.HOOKS)
    assert [docs[h]["version"] for h in ms.HOOKS] == ["v1", "v1"]
    assert (verify["trigger"], anti["trigger"]) == ("PostFileSave", "PostToolUse")
    assert verify["action"] == {"type": "command", "command": ".venv/bin/python -m pytest -q"}
    yes, no = ms.ENGINE_MATCH
    assert ms.matcher_flags(verify["matcher"], yes) == [True] * 4 * len(yes)
    assert ms.matcher_flags(verify["matcher"], no) == [False] * 4 * len(no)
    assert set(ms.matcher_flags(anti["matcher"], ms.WRITE_TOOLS)[::4]) == {True}
    assert not any(ms.matcher_flags(anti["matcher"], [*ms.READ_TOOLS, "delete_file"])[::4])
    prompt = anti["action"]["prompt"]
    assert all(x in prompt for x in ("get_comprehension_vitals", "study_mode_enabled", "25"))
    assert "dissect_symbol" in prompt and ms.skill_problems() == []
    assert ms.find_files(".kiro.hook") == []
    run = subprocess.run(
        ["sh", "-c", ".venv/bin/python backend/mcp_server/server.py"],
        cwd=tmp_path, capture_output=True, text=True,
    )  # fmt: skip
    assert run.returncode != 0 and ".venv/bin/python" in run.stderr


def test_engine_layering_and_import_graph_is_acyclic() -> None:
    for name in ("mastery", "analysis_pipeline", "dissection"):
        assert ms.banned_imports(name) == []
    graph = ms.engine_graph()
    assert "cache_store" in graph and ms.has_cycle(graph) is False
    assert ms.has_cycle({"a": {"b"}, "b": {"a"}}) is True


def test_repo_id_derivation_and_api_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dirs = [tmp_path / "x" / "app", tmp_path / "y" / "app", tmp_path / "x" / "other"]
    for d in dirs:
        d.mkdir(parents=True)
    ids = [derive_local_repo_id(str(d)) for d in dirs]
    assert len(set(ids)) == 3 and ids[0].startswith("local-app-")
    assert derive_local_repo_id(f"{dirs[0]}/") == ids[0]
    monkeypatch.chdir(tmp_path / "x")
    assert derive_local_repo_id("app") == derive_local_repo_id("./app/") == ids[0]
    same = {derive_github_repo_id(u) for u in ms.GH_SAME}
    other = [derive_github_repo_id(u) for u in ms.GH_OTHER]
    assert len(same) == 1 and len({*same, *other}) == 4
    assert all(re.fullmatch(r"[A-Za-z0-9._-]{1,100}", i) for i in [*ids, *same, *other])
    for variable, value in ms.BAD_SETTINGS:
        with pytest.raises(ConfigurationError) as err:
            load_api_settings({variable: value})
        assert err.value.variable == variable and value not in str(err.value)
    assert load_api_settings({}).allow_local_ingest is True


def test_new_domain_models_validate_and_round_trip() -> None:
    models = ms.valid_models()
    assert {m.value for m in S} == {"UNAUDITED", "DISSECTED", "MASTERED", "STALE"}
    for model in models:
        assert type(model).model_validate_json(model.model_dump_json()) == model
    for cls, valid, change in ms.bad_model_cases(models):
        with pytest.raises(ValidationError):
            cls(**{**valid.model_dump(), **change})
