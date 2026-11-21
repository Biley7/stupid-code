# Baseline for Spec #03 (Mastery and Kiro-Native Integration)

Recorded by task 1.2 before any source or test change for this spec. All commands ran from `/Users/binayakroy/stupid-code`.

## Test baseline

Command: `LLM_PROVIDER=mock .venv/bin/python -m pytest -q`

Summary line:

```
770 passed in 17.29s
```

Exit code: 0. Failures: 0. Errors: 0.

Baseline_Count: **770** (matches the expected value). Task 18.1 expects 770 + 24 + 4 = 798 passed.

## Lint baseline

Command: `.venv/bin/ruff check backend`

```
All checks passed!
```

Exit code: 0.

Command: `.venv/bin/ruff format --check backend`

```
18 files already formatted
```

Exit code: 0.

## Git state

Command: `git rev-parse HEAD`

```
c0f899463879275d4df40671e8928f208f5f250f
```

Command: `git status --porcelain`

```
?? .kiro/specs/03-mastery-and-kiro-native/
```

The working tree had no modified tracked files. The only untracked path was this spec's own directory (`requirements.md`, `design.md`, `tasks.md`, `tasks.meta.json` at the time of recording). Any later change to a tracked file therefore belongs to this spec.

## Design mismatches

Recorded by task 1.1. I compared the signatures and behavior that `design.md` (Components and Interfaces, Data Models, Error Handling) relies on with the real Phase 1 and Phase 2 code at commit `c0f8994`. No source or test file was changed. Each entry gives the design's assumption, the real code, and how later tasks adapt. `design.md` and `tasks.md` are unchanged; the adaptations below take precedence where they differ.

### M1. `CacheStore._run` always commits (affects task 3.1)

- Design: `CacheStore.read(operation)` "reuses the existing private `_run`" and "calls `session.rollback()` instead of `commit()`".
- Real: `_run(self, operation: Callable[[Session], T]) -> T` opens `Session(self._engine)`, runs `operation(session)`, then always calls `session.commit()` (rollback only on exception). It has no rollback-only mode. It wraps only `SQLAlchemyError` and `OSError` into `CacheStoreError`; any other exception propagates unchanged after rollback.
- Adaptation: keep `_run` unchanged. `read` passes `_run` a wrapper that builds `CacheTransaction(session)`, computes the result, calls `session.rollback()`, and returns the result. `_run` then commits an empty transaction, which writes nothing. Results must be fully built domain models or dataclasses (`RepositoryRecord`) before the rollback, because the rollback expires ORM instances. `transact` passes `lambda session: operation(CacheTransaction(session))` to `_run`.

### M2. One session per transaction is a hard constraint (affects tasks 3.1, 6.x, 7.1)

- Design: `register_snapshot(tx, ...)` and all mastery writes run inside `CacheStore.transact`.
- Real: every existing public `CacheStore` method (`put_snapshot`, `get_snapshot`, ...) opens its own session through `_run`. A file database uses `QueuePool` with WAL. `:memory:` uses `StaticPool` with `check_same_thread=False`, so all sessions share one connection.
- Adaptation: inside `transact` or `read`, code uses only the `CacheTransaction` methods on the provided session and never calls a public `CacheStore` method. On a file database a nested session would wait for the SQLite write lock. On `:memory:` the nested session's commit would also commit the outer session's pending writes, which breaks all-or-nothing. `PedagogyEngine.explain_target` uses the public methods, so `DissectionService` calls it outside any transaction. That matches the design order: explain first, then `record_views` in its own transaction. `MasteryRow` has a composite key, so `session.get(MasteryRow, (repo_id, target_id))` takes the key tuple in column order.

### M3. `backend/domain/models.py` has no `datetime` import (affects task 2.1)

- Design (Data Models): "The module still imports only the standard library (`re`, `datetime`, `enum`, `typing`, `warnings`)", and `UtcTimestamp` uses `datetime.strptime`.
- Real imports: `re`, `warnings`, `enum.StrEnum`, `typing.Annotated, Literal`, and from pydantic `AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator`. There is no `datetime`, `field_validator`, or `StringConstraints`. Ruff selects `E,F,I,UP,B`, so an import appended at the end of the file fails E402.
- Adaptation (keeps "append only"): inside the `UtcTimestamp` validator function, import `datetime` locally (`from datetime import datetime`). Ruff does not select PLC0415. `test_domain_models_import_only_stdlib_and_pydantic` and the Phase 2 layering test walk every import, including function-local ones, and both allow the standard library. Build the other aliases only from names already imported: `Field(min_length=..., max_length=..., pattern=...)`, `AfterValidator`, `BeforeValidator`, `model_validator`, and the existing `_reject_bool`. If a new top-level import line turns out to be unavoidable, task 18.3 must record it as a justified deviation.

### M4. `UnitFloat` is not in `models.__all__` (no change needed)

- Real: `RelativePath`, `UnitFloat`, `_reject_bool`, and `_CONFIG = ConfigDict(frozen=True, extra="forbid")` all exist with the shapes the design assumes. `UnitFloat` is a module-level name but is not listed in `__all__`. `__all__` is a list literal followed by one `__all__ += [...]` block for Phase 2.
- Adaptation: use `UnitFloat` directly inside `models.py`. Do not add it to `__all__`; the trailing `__all__ += [...]` adds exactly the eight new names.

### M5. Ingestion kinds are `Enum`, not `StrEnum` (affects tasks 7.1, 9.1, 9.3, 9.4)

- Design: maps an `IngestionError` to the "lower-case kind" as the error code and returns warnings as `{kind, path, detail}`.
- Real: `IngestionErrorKind(Enum)` and `WarningKind(Enum)` have lower-case `.value` strings, but `str(kind)` gives `"IngestionErrorKind.NOT_FOUND"`. `IngestionError(kind, message, detail=None)` stores `.kind`, `.message`, and `.detail`, and `__str__` appends `detail`, which can hold the server path or git stderr. `IngestionWarning` (`kind`, `path`, `detail`) and `DiscoveryResult` (`root: Path`, `files: list[str]`, `truncated: bool`, `warnings: list[IngestionWarning]`) are frozen dataclasses, not Pydantic models.
- Adaptation: error code = `error.kind.value`, message = `error.message` (never `str(error)`). Serialize each warning as `{"kind": w.kind.value, "path": w.path, "detail": w.detail}`. `AnalysisResult.warnings` = `tuple(discovery.warnings) + tuple(read_warnings)`.

### M6. Ingestion constants are not exported (affects tasks 7.1, 9.3)

- Real: `MAX_FILE_BYTES = 524_288`, `DEFAULT_MAX_FILES = 500`, and `DEFAULT_MAX_TOTAL_BYTES = 20_971_520` exist in `ingestion.py` but are not in its `__all__`. `GitRunner = Callable[..., subprocess.CompletedProcess]` is exported. Signatures: `discover_local(path, *, max_files=DEFAULT_MAX_FILES, max_total_bytes=DEFAULT_MAX_TOTAL_BYTES)` and `discover_github(url, *, max_files, max_total_bytes, workspace: Path | None = None, git_runner: GitRunner = subprocess.run)`. Both validate the limits before the path or URL.
- Adaptation: import the constants explicitly by name (`from backend.engines.ingestion import MAX_FILE_BYTES, ...`). `ingestion.py` stays unchanged.

### M7. `parse_source` returns `ParsedFile`, not `FileAnalysis` (affects task 7.1)

- Design step 5: "`parse_source(rel, data)` per file, `scan_many(parsed).signals`, `build_snapshot(repo_id, str(result.root), analyses, signals)`". It does not say where `analyses` comes from.
- Real: `parse_source(file_path: str, source: bytes) -> ParsedFile` with fields `analysis: FileAnalysis`, `source`, `root`, and `symbol_nodes`. `scan_many(parsed_files: Sequence[ParsedFile]) -> ScanResult(signals, skipped)`. `build_snapshot(repo_id, root_path, files: Sequence[FileAnalysis], dsa_signals: Sequence[DSASignal]) -> RepoGraphSnapshot`. Parser failures raise `UnsupportedLanguageError` or `ParserInternalError`, both subclasses of `ParserError`. `parse_source` decodes with `errors="replace"`, so a non-UTF-8 file still parses.
- Adaptation: `parsed = [parse_source(rel, data) for ...]`, `signals = scan_many(parsed).signals`, `snapshot = build_snapshot(repo_id, str(root), [p.analysis for p in parsed], signals)`. This is the same sequence as `backend/tests/support.py::make_snapshot`. A symbol in a non-UTF-8 file is analyzed, but a later `read_target_source` call raises `SOURCE_UNREADABLE`, so explain and Socratic return `source_unreadable` for it. That outcome is expected.

### M8. Unknown graph targets raise `MissingTargetError`, and file paths are graph nodes (affects tasks 6.3, 7.2, 11.1)

- Design: `DissectionService.blast_radius` "raises `PedagogyError(UNKNOWN_TARGET)` for an id that is not a Snapshot symbol". The design also lists "A Graph_Engine `InvalidArgumentError` propagates".
- Real: `trace_blast_radius(graph, target_id, max_depth=3) -> BlastRadius` raises `InvalidArgumentError` for a `bool`, non-int, or negative `max_depth` (it has no upper bound), and then `MissingTargetError(target_id)` for an id that is not a graph node. `build_graph` also adds every file path as a node with `node_type="file"`. As a result, a file path passes `trace_blast_radius` without error and does not raise.
- Adaptation: `blast_radius` and `start_check` check membership in `build_symbol_index(snapshot)` or `trackable_symbols(snapshot)` before calling `trace_blast_radius`, and raise the typed unknown-target error themselves. The MCP layer enforces the 0 to 20 bound on `max_depth`. A `MissingTargetError` should then be unreachable; if one escapes, it maps to `internal_error`. For the L3 scope node (D6), the `symbols` count in `impact_score` only counts `node_type == "symbol"`, so the added `"scope"` node does not change it.

### M9. An L2 explanation degrades instead of raising `LLM_FAILURE` (affects tasks 7.2, 9.5, 9.7, 11.1, 15.4)

- Design: maps `PedagogyError(LLM_FAILURE)` to 503 `llm_unavailable` for explain and Crew, and to `llm_unavailable` in MCP, with no distinction between lenses.
- Real: `PedagogyEngine(cache, router, *, llm_timeout_seconds=30.0).explain_target(repo_id, target_id, lens, force_refresh=False)` handles a router error, a timeout, or a `ValidationError` differently by lens. For L2 it returns a degraded envelope (`llm_content_available=False`) that is not cached. Only L1 and L3 raise `LLM_FAILURE`. `INVALID_OUTPUT` can still be raised for any lens during normalization. `PedagogyErrorKind` values are `UNKNOWN_TARGET`, `MISSING_DATA`, `SOURCE_UNREADABLE`, `LLM_FAILURE`, and `INVALID_OUTPUT`, matching the design tables.
- Adaptation: keep the mapping tables. `DissectionService` treats a degraded L2 envelope as a successful result, so with Study Mode on the view is recorded. Crew `autopsy_file` (always L2) and the MCP `dissect_symbol` default lens therefore do not return 503 `llm_unavailable` on a router failure. Tests that expect `llm_unavailable` must use L1 or L3.

### M10. Spec_Grounder exposes no full steering text (affects task 7.1, fingerprint)

- Design step 6: the fingerprint includes `"steering": [[source_file, sha256(own_text)] ...]` from `discover_specs(root)`.
- Real: `discover_specs(repo_root: Path) -> GrounderResult(sections, skipped, has_kiro_specs, documents)`. `documents` holds the full text only of spec documents (`SpecDocument(spec_name, source_file, text)`). Steering content exists only as `ParsedSection` entries with `origin="steering"`, `source_file=<file name>`, and `own_text`, so text before a steering file's first heading is in no section. `discover_specs` raises `SpecGrounderError` when the root is not a readable directory. `build_provenance(snapshot, repo_root=None)` calls `discover_specs` itself and also raises `SpecGrounderError`.
- Adaptation: write one steering entry per steering section, in section order. Pre-heading steering text is not fingerprinted, but it does not affect provenance either, because spec links come from sections and drift detection reads only spec `documents`. Reuse therefore stays correct. A `SpecGrounderError` raised while computing the fingerprint maps to `AnalysisPipelineError(step="provenance")`.

### M11. Phase 1 discovery accepts in-root file symlinks (affects task 7.1)

- Design: `_read_discovered` opens with `O_RDONLY | O_NOFOLLOW` and "refuses symlinks".
- Real: `_walk` follows `entry.is_file()` and accepts a symlinked file whose real path lies inside the root. It skips files over `MAX_FILE_BYTES` and files with a NUL byte in their first 8,192 bytes.
- Adaptation: none to the design. A discovered in-root symlink fails the `O_NOFOLLOW` open and becomes an `ENTRY_UNREADABLE` warning. This matches `pedagogy.read_target_source`, which also refuses symlinks. Test fixtures must not expect a symlinked file to be analyzed.

### M12. Test environment facts later test tasks depend on (affects tasks 15.x, 17.1)

- `conftest.py` autouse `_default_env` sets `LLM_PROVIDER=mock` and `STUPID_CODE_DB_PATH=:memory:`, and removes `GEMINI_API_KEY`. Every `CacheStore()` built from the environment inside a test is therefore a separate, empty in-memory database. In-process tests must inject one shared `CacheStore` into both `Services` and `ToolServices`. Subprocess tests must pass a temporary file database in `env`.
- `offline_guard` is opt-in. It blocks `socket.connect` and `Path.read_text`, `Path.read_bytes`, and `Path.open` reads outside the repository root, the pytest temp directory, the system temp directory, and `sys.prefix`.
- `MCPServer.call_tool(name, arguments, context=None)` returns `CallToolResult | InputRequiredResult`. Tests check `isinstance(result, CallToolResult)` before reading `structured_content`. `StdioServerParameters` has the fields `command`, `args`, `env`, `cwd`, `encoding`, and `encoding_error_handler`, and its `env` is merged over the SDK's default inherited environment, so `PATH` and `HOME` stay available. `MCPServer`'s `resource_security` path checks apply only to resource templates, not to tool arguments.
- Layering tests that must keep passing: `test_new_modules_respect_layering` (modules `spec_grounder`, `topology`, `llm_router`, `cache_store`, `pedagogy`) asserts no `fastapi`, `mcp`, or `starlette` import, no bare `exec`, `eval`, `compile`, or `__import__` call, `subprocess` imported only by `spec_grounder`, and an engine-import graph among those five equal to `{pedagogy: {cache_store, llm_router}}`. The Phase 1 tests check the four Phase 1 engines and require exactly one `subprocess.run` reference in `ingestion.py`. The new engines are in neither list. `analysis_pipeline` may import `subprocess` for the `git_runner` default.

### Confirmed without mismatch

| Design dependency | Real code |
|---|---|
| `CacheStore(db_path=None, settings=None)`, `_TABLES` (list of `__table__` objects passed to `create_all(tables=_TABLES)`), `CacheStoreError`, `__all__` (7 names) | as assumed; no test inspects table names or `_TABLES` |
| `_MOCK_BUILDERS: dict[type[BaseModel], Callable[[Mapping[str, Any]], BaseModel]]` with L1, L2, and L3 entries; `_generate_mock` catches `KeyError, IndexError, TypeError, ValueError, AttributeError` (not `ZeroDivisionError`) and maps them to `LLMRouterError(category="validation")`; an unsupported model raises `LLMRouterError` | as assumed; the design's `ValueError` guard for an empty concept list is required |
| `_items(mapping, key) -> list`, `_text(mapping, key) -> str`, `MOCK_SLICE_MARKER = "CONTEXT_SLICE_JSON:\n"` | present with those signatures |
| `StructuredLLM.generate_structured(system_prompt, user_prompt, response_model: type[T]) -> T` (Protocol); `LLMRouterError(message, *, provider="", category="provider")`; `LLMConfigError`; `LLMSettings` defaults `LLM_PROVIDER` to `mock` | as assumed |
| `read_target_source(root_path: str, file_path: str) -> str`, `build_symbol_index(snapshot) -> dict[str, SymbolNode]`, `canonical_json(obj) -> str`, `MAX_SOURCE_LINES = 400`, `resolve_target` accepting `repo_id` or a `directory_roles` key for L3 | as assumed |
| `build_graph(files: Sequence[FileAnalysis]) -> nx.DiGraph` (callers and callees sorted in `BlastRadius`) | as assumed |
| `validate_github_url(url) -> GitHubRepoRef(owner, repo, clone_url)`: exact `https://` prefix and exact host `github.com`; strips one trailing `/` and a `.git` suffix | as assumed (findings 6 and 7); `normalize_github_url` must lower-case the scheme and host first |
| `discover_github` clone argv uses `--depth 30`; the git double receives the destination as `argv[-1]` | as assumed (D1) |
| `profile_topology(snapshot) -> TopologyProfile`; `build_provenance(snapshot, repo_root=None) -> ProvenanceReport` | as assumed |
| `backend/api/main.py`: `app = FastAPI(title="Stupid Code")` and `GET /health` returning `{"status": "ok", "service": "stupid-code"}`; `test_health.py` imports `app` at module level | as assumed (finding 11) |
| `.kiro/steering/architecture.md` layering (`api` and `mcp_server` call `engines`, which use `domain`) | matches the design's import rules |
| `backend/pyproject.toml` has `"mcp>=1.0"`; installed mcp 2.3.0, fastapi 0.165.0, starlette 1.10.0, pydantic 2.14.4, hypothesis 6.170.17, anyio 4.16.0; `mcp.server.mcpserver.MCPServer` provides `tool`, `run`, `list_tools`, `call_tool`, and `run_stdio_async`; `mcp.Client` accepts an `MCPServer` or `StdioServerParameters` | as assumed (finding 1) |
| `backend/mcp_server/` exists (only `.gitkeep`); `backend/api/routes/` does not exist yet; `power/` and `crew/` hold only `.gitkeep` | consistent with the design's new-file list |

## Approved exception: Phase 1 scope test

User-approved exception to Requirement 24.3. Only the parametrize list of
`backend/tests/unit/test_ast_graph_engine.py::test_no_new_python_files_outside_spec_scope` changed
(plus one comment line above it: `# Spec #03 adds these files (user-approved exception to Req 24.3)`):

- `("backend/api", {"main.py"})` became `("backend/api", {main.py, settings.py, errors.py, rate_limit.py, crew_signature.py, services.py, schemas.py, routes/repos.py, routes/autopsy.py, routes/mastery.py, routes/crew.py})`
- `("backend/mcp_server", set())` became `("backend/mcp_server", {"server.py"})`
- `power`, `crew`, `ui` stay `set()`. No other line in the file changed.
