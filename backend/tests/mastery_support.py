"""Shared, non-test helpers for the Spec #03 unit and property tests.

Import as ``from backend.tests.mastery_support import ...``. Everything here is offline:
in-memory databases, the mock provider, and a git double. There are no test functions.
"""

import asyncio
import hashlib
import hmac
import json
import subprocess
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from mcp.types import CallToolResult
from pydantic import BaseModel

from backend.api.main import create_app
from backend.api.rate_limit import RateLimiter
from backend.api.services import Services
from backend.api.settings import ApiSettings
from backend.domain.models import MasteryState, SocraticGrade
from backend.engines.analysis_pipeline import AnalysisResult, LocalSource, analyze_repository
from backend.engines.cache_store import CacheStore
from backend.engines.llm_router import LLMRouter, LLMRouterError, LLMSettings, StructuredLLM
from backend.engines.mastery import MasteryEngine
from backend.mcp_server.server import ToolServices, build_server

START = datetime(2025, 1, 1, tzinfo=UTC)

# Two modules: ``caller`` calls ``callee``; ``top`` uses heapq (a DSA signal);
# ``lonely`` has no caller or callee.
CALLEE_SRC = "def callee(x):\n    total = x + 1\n    return total\n"
CALLER_SRC = (
    "import heapq\n\nfrom util import callee\n\n\n"
    "def caller(v):\n    result = callee(v)\n    return result\n\n\n"
    "def top(h, x):\n    heapq.heappush(h, x)\n    return heapq.heappop(h)\n\n\n"
    "def lonely():\n    return 1\n"
)
TINY_REPO = {"util.py": CALLEE_SRC, "main.py": CALLER_SRC}


CALLER, TOP, LONELY, CALLEE = (
    "main.py::caller",
    "main.py::top",
    "main.py::lonely",
    "util.py::callee",
)


class FixedClock:
    """A settable Clock: ``clock()`` returns ``.now``; ``advance(days=...)`` moves it."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now = self.now + timedelta(**delta)


def write_tiny_repo(root: Path, files: Mapping[str, str] | None = None) -> Path:
    """Write ``files`` (default ``TINY_REPO``) under ``root`` and return ``root``."""
    for rel, text in (TINY_REPO if files is None else files).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def make_cache(db_path: Path | str | None = None) -> CacheStore:
    """A ``CacheStore``: in memory by default, or the given database file."""
    return CacheStore(str(db_path) if db_path is not None else ":memory:")


class FixedGradeRouter:
    """Returns ``SocraticGrade(score=score)``; every other model goes to the mock router."""

    def __init__(self, score: float = 1.0, feedback: str = "fixed") -> None:
        self.score, self.feedback, self.calls = score, feedback, 0
        self.inner = LLMRouter(LLMSettings(LLM_PROVIDER="mock"))

    async def generate_structured[M: BaseModel](
        self, system_prompt: str, user_prompt: str, response_model: type[M]
    ) -> M:
        if response_model is SocraticGrade:
            self.calls += 1
            return SocraticGrade(score=self.score, feedback=self.feedback)  # type: ignore[return-value]
        return await self.inner.generate_structured(system_prompt, user_prompt, response_model)


class RecordingRouter(FixedGradeRouter):
    """``FixedGradeRouter`` that also keeps each grading call's ``(user_prompt, model)``."""

    def __init__(self, score: float = 1.0) -> None:
        super().__init__(score)
        self.recorded: list[tuple[str, type[BaseModel]]] = []

    async def generate_structured[M: BaseModel](
        self, system_prompt: str, user_prompt: str, response_model: type[M]
    ) -> M:
        self.recorded.append((user_prompt, response_model))
        return await super().generate_structured(system_prompt, user_prompt, response_model)


class FailingGradeRouter(FixedGradeRouter):
    """Grading fails. ``mode``: ``"error"`` raises ``LLMRouterError``, ``"timeout"`` sleeps
    ``sleep`` seconds (patch ``GRADING_TIMEOUT_SECONDS`` below it), ``"invalid"`` returns a
    non-``SocraticGrade`` object. Other models go to the mock router."""

    def __init__(self, mode: str = "error", sleep: float = 5.0) -> None:
        super().__init__()
        self.mode, self.sleep = mode, sleep

    async def generate_structured(  # type: ignore[override]
        self, system_prompt: str, user_prompt: str, response_model: Any
    ) -> Any:
        if response_model is not SocraticGrade:
            return await self.inner.generate_structured(system_prompt, user_prompt, response_model)
        self.calls += 1
        if self.mode == "error":
            raise LLMRouterError("fake failure", provider="mock", category="connection")
        if self.mode == "timeout":
            await asyncio.sleep(self.sleep)
        return {"score": 2}


GitDouble = Callable[..., subprocess.CompletedProcess]


def git_double(files: Mapping[str, str]) -> GitDouble:
    """A ``git_runner`` that "clones" by writing ``files`` into ``argv[-1]``."""

    def run(argv: list[str], *_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess:
        write_tiny_repo(Path(argv[-1]), files)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    return run


def make_services(
    tmp_path: Path | None = None,
    router: StructuredLLM | None = None,
    clock: Callable[[], datetime] | None = None,
    *,
    cache: CacheStore | None = None,
    git_runner: GitDouble | None = None,
) -> Services:
    """Wire the shared engines over an in-memory cache, a ``FixedGradeRouter`` (score 1.0),
    and a ``FixedClock``. ``tmp_path`` becomes the clone workspace for GitHub ingestion."""
    return Services.build(
        cache if cache is not None else make_cache(),
        router if router is not None else FixedGradeRouter(),
        clock if clock is not None else FixedClock(),
        git_runner=git_runner if git_runner is not None else subprocess.run,
        workspace=tmp_path,
    )


def analyze(services: Services, root: Path) -> AnalysisResult:
    """Analyze the local directory ``root`` through ``analyze_repository`` and persist it."""
    return analyze_repository(
        LocalSource(str(root)), cache=services.cache, mastery=services.mastery
    )


def make_client(
    services: Services,
    *,
    settings: ApiSettings | None = None,
    rate_limiter: RateLimiter | None = None,
) -> TestClient:
    """``TestClient`` over ``create_app`` with explicit settings (default ``ApiSettings()``,
    so no environment variable is read), the given services, and an optional limiter."""
    app = create_app(
        settings if settings is not None else ApiSettings(),
        services=services,
        rate_limiter=rate_limiter,
    )
    return TestClient(app)


def tool_services(
    cache: CacheStore | None = None,
    router: StructuredLLM | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ToolServices:
    """``ToolServices`` for ``build_server``. Pass the same ``cache`` as ``make_services`` to
    share data between the REST API and the MCP tools in one process."""
    return ToolServices(
        cache=cache if cache is not None else make_cache(),
        router=router if router is not None else FixedGradeRouter(),
        clock=clock if clock is not None else FixedClock(),
    )


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign_kiro(body: bytes, secret: str) -> dict[str, str]:
    """Headers for the ``X-Kiro-Signature`` scheme."""
    return {"X-Kiro-Signature": f"sha256={_hmac_hex(secret, body)}"}


def sign_proxy(
    secret: str, timestamp: int, method: str, path_with_query: str, body: bytes
) -> dict[str, str]:
    """Headers for the ``X-Crew-Proxy`` scheme (``timestamp`` in Unix seconds)."""
    signed = f"{timestamp}:{method.upper()}:{path_with_query}:{hashlib.sha256(body).hexdigest()}"
    return {"X-Crew-Proxy": f"{timestamp}:{_hmac_hex(secret, signed.encode('utf-8'))}"}


def setup_tiny(tmp_path: Path, router=None):
    """Analyze the tiny repo; return ``(services, clock, repo_id, repo_root)``."""
    clock = FixedClock()
    services = make_services(tmp_path, router, clock)
    root = write_tiny_repo(tmp_path / "repo")
    return services, clock, analyze(services, root).repo_id, root


def run_check(engine: MasteryEngine, repo_id: str, target_id: str):
    """Start and submit a check for ``target_id`` and return the verdict."""
    check = engine.start_check(repo_id, target_id)
    answers = [(q.question_id, "an answer") for q in check.questions]
    return asyncio.run(engine.submit_answers(repo_id, target_id, answers))


def tiny_states(engine: MasteryEngine, repo_id: str) -> dict[str, MasteryState]:
    return {t: engine.get_record(repo_id, t).state for t in (CALLER, TOP, LONELY, CALLEE)}


def snapshot_symbols(services: Services, repo_id: str) -> tuple[dict, list]:
    snapshot = services.cache.read(lambda tx: tx.get_snapshot(repo_id))
    return {s.id: s for f in snapshot.files for s in f.symbols}, snapshot.dsa_signals


def api_client(
    tmp_path: Path, router=None, settings: ApiSettings | None = None, **kw: Any
) -> tuple[Services, FixedClock, TestClient]:
    """Services plus a TestClient over them."""
    clock = FixedClock()
    services = make_services(tmp_path, router, clock, **kw)
    return services, clock, make_client(services, settings=settings)


def ingest_path(client: TestClient, root: Path) -> str:
    """Ingest ``root`` through the API and return its repo id."""
    response = client.post("/api/repos/ingest", json={"path": str(root)})
    assert response.status_code == 200
    return response.json()["repo_id"]


def call_tool(server: Any, name: str, **arguments: Any) -> dict[str, Any]:
    """Call an MCP tool in process; return its JSON-serializable ``structured_content``."""
    result = asyncio.run(server.call_tool(name, arguments))
    assert isinstance(result, CallToolResult) and result.structured_content is not None
    json.dumps(result.structured_content)
    return result.structured_content


def mcp_setup(tmp_path: Path):
    """``(server, services, router, repo_id, root)``: one cache shared by API and MCP."""
    cache, router, clock = make_cache(), RecordingRouter(), FixedClock()
    services = make_services(tmp_path, router, clock, cache=cache)
    root = write_tiny_repo(tmp_path / "repo")
    server = build_server(tool_services(cache, router, clock))
    return server, services, router, analyze(services, root).repo_id, root


# -- manifest, layering, and model helpers (unit tests 21 to 24) -----------------------

ROOT = Path(__file__).resolve().parents[2]
PATH_KEYS = {"command", "args", "entryPoint", "agents", "skills"}
SECRET_KEY = r"secret|token|api[_-]?key|password"
ENGINE_MATCH = (
    ["backend/engines/mastery.py", "backend/engines/__init__.py"],
    ["backend/engines/sub/helper.py", "backend/engines/mastery.pyc", "README.md",
     "backend/engines/mastery.py.bak", "backend/engines_old/mastery.py", "backend/api/main.py",
     "backend/tests/unit/test_mastery_api_mcp.py", "frontend/src/App.tsx"],
)  # fmt: skip
WRITE_TOOLS = ["fs_write", "fs_append", "str_replace", "smart_relocate", "semantic_rename"]
READ_TOOLS = ["read_file", "read_code", "list_directory", "grep_search", "file_search"]
BANNED_IMPORTS = ("fastapi", "starlette", "mcp", "backend.api", "backend.mcp_server")
CREW_SECTIONS = ["tool usage", "file context", "lenses", "study mode", "socratic workflow",
                 "mastery", "evidence grounding", "missing tool"]  # fmt: skip


def load_json(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def walk_strings(node: Any, key: str = "") -> list[tuple[str, str]]:
    """Every ``(nearest dict key, string)`` pair in a JSON document."""
    if isinstance(node, str):
        return [(key, node)]
    if not isinstance(node, dict | list):
        return []
    items = node.items() if isinstance(node, dict) else ((key, v) for v in node)
    return [pair for k, v in items for pair in walk_strings(v, k)]


def walk_keys(node: Any) -> list[tuple[str, Any]]:
    if isinstance(node, dict):
        return [(k, v) for k, v in node.items()] + [p for v in node.values() for p in walk_keys(v)]
    return [p for v in node for p in walk_keys(v)] if isinstance(node, list) else []


def is_relative(path: str) -> bool:
    import re

    return not (
        path.startswith(("/", "~")) or re.match(r"[A-Za-z]:", path) or ".." in path.split("/")
    )


def find_files(suffix: str) -> list[str]:
    import os

    skip = {".venv", ".git", "node_modules", ".hypothesis"}
    return [
        os.path.join(d, f)
        for d, dirs, names in os.walk(ROOT)
        if not dirs.__setitem__(slice(None), [x for x in dirs if x not in skip])
        for f in names
        if f.endswith(suffix)
    ]


def imported_modules(path: Path) -> set[str]:
    import ast

    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{a.name}" for a in node.names)
    return found


def has_cycle(graph: Mapping[str, set[str]]) -> bool:
    state: dict[str, int] = {}

    def visit(name: str) -> bool:
        if state.get(name) == 1:
            return True
        if state.get(name) == 2:
            return False
        state[name] = 1
        hit = any(visit(n) for n in graph.get(name, ()))
        state[name] = 2
        return hit

    return any(visit(n) for n in graph)


def valid_models() -> list[BaseModel]:
    """One valid instance of each new Pydantic model."""
    from backend.domain.models import (
        ComprehensionVitals,
        ModuleMastery,
        SocraticAnswerItem,
        SocraticCheck,
        SocraticQuestion,
        SocraticVerdict,
    )

    question = SocraticQuestion(
        question_id="q1", target_id="a.py::f", prompt="Why?", line_reference="a.py:1-2",
        expected_concepts=["loop"],
    )  # fmt: skip
    return [
        ModuleMastery(repo_id="r", target_id="a.py::f", ast_hash="h", state=MasteryState.STALE),
        question,
        SocraticCheck(repo_id="r", target_id="a.py::f", questions=[question]),
        SocraticAnswerItem(question_id="q1", answer="because"),
        SocraticVerdict(
            target_id="a.py::f",
            passed=True,
            score=0.8,
            feedback="ok",
            new_state=MasteryState.MASTERED,
            next_review_at="2025-01-02T00:00:00Z",
        ),  # fmt: skip
        ComprehensionVitals(
            repo_id="r",
            study_mode_enabled=False,
            total_modules=2,
            unaudited_count=1,
            dissected_count=1,
            mastered_count=0,
            stale_count=0,
            mastery_percentage=0.0,
            due_for_review=[],
            file_states={"a.py": MasteryState.UNAUDITED},
        ),  # fmt: skip
        SocraticGrade(score=0.5, feedback="fine"),
    ]


MANIFESTS = [".kiro/settings/mcp.json", "power/mcp.json", "power/plugin.json", "crew/app.json"]
HOOKS = [".kiro/hooks/verify-engines.json", ".kiro/hooks/anti-vibe-coding.json"]
SKILLS = ["power/skills/code-autopsy/SKILL.md", "crew/skills/code-autopsy/SKILL.md"]
GH = "https://github.com/octo/demo"
GH_SAME = [
    GH,
    f"{GH}/",
    f"{GH}.git",
    "HTTPS://GitHub.com/octo/demo",
    "https://github.com/Octo/Demo",
]
GH_OTHER = [f"{GH}2", "https://github.com/a-b/c", "https://github.com/a/b-c"]
BAD_SETTINGS = [
    ("STUPID_CODE_CORS_ORIGINS", "*"),
    ("ALLOW_LOCAL_INGEST", "yes"),
    ("STUPID_CODE_GITHUB_RATE_LIMIT", "0"),
]


def manifest_docs() -> dict[str, Any]:
    """Every manifest, hook, and Crew agent file, parsed, keyed by repository path."""
    agents = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "crew/agents").glob("*.json"))
    return {name: load_json(name) for name in [*MANIFESTS, *HOOKS, *agents]}


def check_documents(docs: Mapping[str, Any]) -> None:
    """Paths are relative, no home paths, no non-empty secret-like key, declared files exist."""
    import re

    for doc in docs.values():
        for key, text in walk_strings(doc):
            assert not text.startswith(("~", "/Users", "/home"))
            assert not text.startswith("/") or text.startswith("/api/")  # endpoint URLs
            if key in PATH_KEYS or text.startswith("file://"):
                assert is_relative(text.removeprefix("file://"))
        assert not [k for k, v in walk_keys(doc) if re.search(SECRET_KEY, k, re.I) and v]
    app = docs["crew/app.json"]
    declared = [*app["agents"], *(f"{s}/SKILL.md" for s in app["skills"])]
    declared += [c["entryPoint"] for c in app["contributes"]["sessionControls"]]
    assert all((ROOT / "crew" / path).is_file() for path in declared)
    for name, doc in docs.items():
        if name.startswith("crew/agents/"):
            prompt = doc["prompt"].removeprefix("file://")
            assert (ROOT / name).parent.joinpath(prompt).is_file()


def matcher_flags(matcher: str, paths: list[str]) -> list[bool]:
    """For each path (relative and under ``/ws/``): search and fullmatch results, flattened."""
    import re

    forms = [f for p in paths for f in (p, f"/ws/{p}")]
    return [bool(fn(matcher, f)) for f in forms for fn in (re.search, re.fullmatch)]


def skill_problems() -> list[str]:
    """Front matter and length problems of both skill files, plus missing Crew sections."""
    bad = []
    for skill in SKILLS:
        lines = (ROOT / skill).read_text(encoding="utf-8").splitlines()
        if lines[:2] != ["---", "name: code-autopsy"] or lines[3] != "---" or len(lines) > 200:
            bad.append(skill)
        if "Stupid Code" not in lines[2]:
            bad.append(f"{skill} description")
    heads = " | ".join(
        line.lower() for line in (ROOT / SKILLS[1]).read_text().splitlines() if line[:3] == "## "
    )
    return bad + [s for s in CREW_SECTIONS if s not in heads]


def engine_graph() -> dict[str, set[str]]:
    engines = ROOT / "backend/engines"
    files = [p for p in engines.glob("*.py") if p.stem != "__init__"]
    stems = {p.stem for p in files}
    return {
        p.stem: {m.split(".")[2] for m in imported_modules(p) if m.startswith("backend.engines.")}
        & stems
        for p in files
    }


def banned_imports(name: str) -> list[str]:
    return [
        m
        for m in imported_modules(ROOT / "backend/engines" / f"{name}.py")
        if any(m == b or m.startswith(f"{b}.") for b in BANNED_IMPORTS)
    ]


def bad_model_cases(models: list[BaseModel]) -> list[tuple[type[BaseModel], BaseModel, dict]]:
    """``(class, valid instance, override)`` triples that must each fail validation."""
    mastery, _, _, _, verdict, vitals, grade = models
    nan, inf = float("nan"), float("inf")
    cases: list[tuple[BaseModel, dict]] = [(grade, {"score": v}) for v in (nan, inf, True, "0.5")]
    cases += [(grade, {"score": v}) for v in (1.5, -0.1, None)]
    cases += [(grade, {"extra": 1}), (grade, {"feedback": ""}), (verdict, {"passed": 1})]
    cases += [(verdict, {"score": 2})]
    cases += [(mastery, {"next_review_at": t}) for t in ("2025-01-01", "2025-13-01T00:00:00Z")]
    cases += [(mastery, {"ease_factor": True}), (mastery, {"interval_days": -1})]
    cases += [(vitals, {"total_modules": 0}), (vitals, {"mastery_percentage": nan})]
    return [(type(m), m, change) for m, change in cases]
