# Implementation Plan: Mastery and Kiro-Native Integration (Spec #03)

## Overview

The implementation language is Python 3.14 (the design uses Python throughout). The plan follows the layering of `.kiro/steering/architecture.md`: `domain`, then `engines`, then the delivery layers `api` and `mcp_server`, then the Kiro-native packages, then tests, the integration script, and verification.

Rules that apply to every task:

- Phase 1 and Phase 2 files change only as listed in the design's "Phase 1 and Phase 2 Change Log". No Phase 1 or Phase 2 test file is edited, weakened, deleted, skipped, or marked xfail (Requirement 24.3).
- All commands run from `/Users/binayakroy/stupid-code` with `LLM_PROVIDER=mock` and the interpreter `.venv/bin/python`.
- Every new Python file carries type annotations on public functions and must pass `ruff check backend` and `ruff format --check backend` (Requirement 23.11).
- No frontend, Phase 4, or deployment file is created (Requirement 24.11).
- All test tasks are required. None is optional.
- The unit file `backend/tests/unit/test_mastery_api_mcp.py` is built up across several tasks. When all of them are done it holds exactly 24 test functions and fewer than 600 lines.
- The property file `backend/tests/properties/test_mastery_properties.py` holds exactly four Hypothesis tests.

## Tasks

- [x] 1. Baseline measurements before any change
  - [x] 1.1 Re-inspect the Phase 1 and Phase 2 code the design depends on
    - Read only what is needed: the public names and signatures of `backend/engines/cache_store.py` (`CacheStore`, `_run`, `_TABLES`, `CacheStoreError`, `__all__`), `llm_router.py` (`_MOCK_BUILDERS`, `_generate_mock`, `StructuredLLM`, `LLMRouterError`), `pedagogy.py` (`read_target_source`, `build_symbol_index`, `canonical_json`, `PedagogyError` kinds, `explain_target`), `graph_engine.py` (`build_graph`, `trace_blast_radius`), `ingestion.py` (`discover_local`, `discover_github`, `validate_github_url`, `IngestionError` kinds, `GitRunner`, `MAX_FILE_BYTES`), `spec_grounder.py` (`discover_specs`, `build_provenance`), `topology.py` (`profile_topology`), `backend/domain/models.py` (`_CONFIG`, `RelativePath`, `UnitFloat`, `__all__`), `backend/api/main.py`, `backend/tests/conftest.py`, `backend/tests/support.py`, `.kiro/steering/architecture.md`
    - Confirm each name and signature the design uses exists. Write any mismatch into `.kiro/specs/03-mastery-and-kiro-native/baseline.md` under a "Design mismatches" heading and adapt the later tasks to the real signature. Do not edit `design.md`
    - _Requirements: 1.1, 3.16, 4.2, 9.1, 23.5, 24.3_

  - [x] 1.2 Record the test and lint baseline
    - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q` and copy the summary line (expected `770 passed`) into `.kiro/specs/03-mastery-and-kiro-native/baseline.md`
    - Run `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend` and record both results (expected: check passes, 18 files already formatted)
    - Record `git rev-parse HEAD` and `git status --porcelain` so later diffs can separate pre-existing changes from this spec's changes
    - If the count is not 770, record the real number and use it as the Baseline_Count in every later task and in the final report
    - _Requirements: 24.1, 24.2, 24.4_

  - [x] 1.3 Snapshot hashes of Phase 1 and Phase 2 files
    - Create `.kiro/specs/03-mastery-and-kiro-native/phase12-hashes.txt` with one `<git hash-object output>  <path>` line for every file under `backend/tests/` (including `conftest.py`, `support.py`, and every test file), plus `pytest.ini`
    - Add the same kind of lines for every Phase 1 and Phase 2 source file the design lists in its change log (`backend/domain/models.py`, `backend/engines/cache_store.py`, `backend/engines/llm_router.py`, `backend/api/main.py`, `backend/pyproject.toml`, `.env.example`, `.gitignore`) and for the untouched engines (`ingestion.py`, `ast_parser.py`, `dsa_scanner.py`, `graph_engine.py`, `spec_grounder.py`, `topology.py`, `pedagogy.py`)
    - Use `git hash-object <file>` on the working-tree content so the snapshot is valid even with uncommitted changes
    - _Requirements: 24.3, 21.9_

- [x] 2. Domain models and dependency constraint
  - [x] 2.1 Append the mastery models to `backend/domain/models.py`
    - Append only, after the Phase 2 block. Add the private aliases (`RepoId`, `_Id500`, `_Text`, `_Concept`, `UtcTimestamp`, `_EaseFloat`, `_Percent`, `_Count`) and the models `MasteryState` (StrEnum, four values), `ModuleMastery`, `SocraticQuestion`, `SocraticCheck`, `SocraticAnswerItem`, `SocraticVerdict`, `ComprehensionVitals` (with `file_states: dict[RelativePath, MasteryState]` and the rule `len(file_states) <= total_modules`), and `SocraticGrade`
    - Reuse the existing `_CONFIG` (frozen, `extra="forbid"`) and strict field types. Reject NaN, infinity, booleans, and string-typed numbers. Enforce every bound and length rule of Requirement 1 (criteria 10 to 13, 17 to 21)
    - Add a trailing `__all__ += [...]` with the eight names. Do not change any existing line. Import only the standard library and Pydantic
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20, 1.21_

  - [x] 2.2 Change the `mcp` constraint in `backend/pyproject.toml`
    - Change `"mcp>=1.0"` to `"mcp>=2.3,<3"`. Change nothing else in the file
    - Confirm with `.venv/bin/python -c "from mcp.server.mcpserver import MCPServer"` that the installed SDK provides the class
    - _Requirements: 16.1, 16.2_

- [x] 3. Cache_Store additions
  - [x] 3.1 Add the mastery tables and transactional access to `backend/engines/cache_store.py`
    - Add the tables `StudyModeRow`, `MasteryRow` (composite key `repo_id`, `target_id`; payload is `ModuleMastery` JSON), and `RepositoryRow`, and add them to `_TABLES`
    - Add the frozen dataclass `RepositoryRecord` and the class `CacheTransaction` with the typed methods listed in the design (`get_snapshot`, `get_provenance`, `get_topology`, `put_snapshot`, `put_provenance`, `put_topology`, `get_repository`, `list_repositories` ordered by `repo_id`, `put_repository`, `get_study_mode` returning `None` when no row exists, `set_study_mode`, `list_mastery` ordered by `target_id`, `get_mastery`, `put_mastery`)
    - An invalid stored payload raises `CacheStoreError` naming the table only. It never deletes the row and never includes row content
    - Add `CacheStore.transact(operation)` (commit on success, roll back on any exception, non-database exceptions such as `MasteryError` propagate unchanged) and `CacheStore.read(operation)` (always rolls back, so a read path cannot write). Both reuse the existing private `_run`
    - Keep every existing method signature and behavior. Keep the Phase 2 layering facts: `cache_store` imports no engine module. Update `__all__`
    - _Requirements: 2.1, 2.9, 2.10, 3.16, 4.3, 8.7, 11.1, 11.7, 13.2, 23.3, 23.4, 23.5_

- [x] 4. LLM_Router mock grader
  - [x] 4.1 Add the additive `SocraticGrade` mock builder to `backend/engines/llm_router.py`
    - Import `SocraticGrade`. Add `_build_socratic_grade(context)`: concepts are the distinct `expected_concepts` of all questions, `score = hits / len(concepts)` where a hit is a concept that occurs case-insensitively in any submitted answer, unrounded. `feedback` is a 1 to 1,000 character string
    - Raise `ValueError` when the concept list is empty, so the existing handler turns it into `LLMRouterError(category="validation")`
    - Register it as one new entry in `_MOCK_BUILDERS`. Document the grading slice shape in the module docstring. Keep every existing builder and the rejection of unsupported response models (the existing `SpecLink` rejection test must still pass). `llm_router` still imports only `domain`
    - Run the existing LLM router tests and `test_new_modules_respect_layering` to confirm nothing regressed
    - _Requirements: 7.8, 23.5, 24.3_

- [x] 5. Checkpoint - domain, cache, and router changes
  - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q` and confirm the Baseline_Count tests still pass with 0 failures
  - Run `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Mastery_Engine in `backend/engines/mastery.py`
  - [x] 6.1 Create the module core: Clock helpers, errors, validation, and Study Mode
    - Create `backend/engines/mastery.py`. Define `Clock`, `system_clock`, `read_clock` (accepts only a timezone-aware datetime with a zero UTC offset, wraps any Clock exception into `MasteryError(INVALID_CLOCK)`), `format_utc` (truncates fractions), the constants `PASS_THRESHOLD`, `INITIAL_EASE`, `GRADING_TIMEOUT_SECONDS`, `MAX_REVIEW_AT`, `MasteryErrorKind`, and `MasteryError` (messages never hold row content, prompts, or answers)
    - Add `validate_repo_id` (1 to 100 characters from `A-Z a-z 0-9 . _ -`), `trackable_symbols` (symbol ids of at most 500 characters, decision D7), and the `MasteryEngine` class with its constructor
    - Implement `get_study_mode` (returns `False` and writes nothing when no row exists) and `set_study_mode` (accepts only a real `bool`; works for a `repo_id` with no Snapshot; idempotent). Wrap `CacheStoreError` into `MasteryError(STORAGE)` with `__cause__` set. Study Mode never touches records, hashes, cached explanations, Snapshot, provenance, or topology
    - Import only `domain`, `cache_store`, `llm_router`, `graph_engine`, and `pedagogy`. Import no `fastapi`, `starlette`, or `mcp`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 6.1, 6.11, 8.10, 23.1, 23.3_

  - [x] 6.2 Add registration, the state machine, views, and review scheduling to `mastery.py`
    - Implement `plan_registration`, `apply_view`, `apply_pass`, `apply_hash_change`, and `check_transition` following the transition table of the design. `apply_pass` sets `repetitions + 1`, `interval_days` 1, then 6, then `round(previous * ease_factor)`, `next_review_at` as Clock time plus `interval_days` days, `last_verified_at`, and keeps `ease_factor` at 2.5. An `OverflowError` or a date after `9999-12-31T23:59:59Z` raises `MasteryError(REVIEW_DATE_OUT_OF_RANGE)` and writes nothing
    - Implement `register_snapshot(tx, snapshot)` (new records `UNAUDITED`; a changed `ast_hash` moves `MASTERED` to `STALE` with reset schedule fields, `DISSECTED` to `UNAUDITED`, and keeps `UNAUDITED` and `STALE`; same hash writes nothing; records for symbols no longer in the Snapshot are retained) so it runs inside a caller-provided transaction
    - Implement `record_views(repo_id, target_ids)` in one transaction: only when Study Mode is on, `UNAUDITED` becomes `DISSECTED`, other states are unchanged, unknown targets raise `UNKNOWN_TARGET` and change nothing. Implement `get_record`
    - Run `check_transition` before every write so a disallowed pair raises `INVALID_TRANSITION` and the transaction rolls back
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.12, 23.4_

  - [x] 6.3 Add deterministic Socratic question generation to `mastery.py`
    - Implement `generate_check` and `MasteryEngine.start_check`. Check order: Repo_Id rule, Study Mode on (else `STUDY_MODE_DISABLED`), stored Snapshot (else `UNKNOWN_REPOSITORY`), trackable Target (else `UNKNOWN_TARGET`). Build the graph, take direct callers and callees with `trace_blast_radius(graph, id, 1)`, read the Target source with `pedagogy.read_target_source` (map `SOURCE_UNREADABLE`), and select the Target's `DSASignal` entries. Make no LLM call and no write
    - Extract local names with the assignment and `return` patterns from the design, dropping keywords and receivers, and keep at most four. Build question 0 always, and question 1 from the first available source (DSA signal, then callees, then callers). Clip prompt parts and cut each prompt to 500 characters
    - `line_reference` is `<file_path>:<start>-<end>` inside the Target range. `expected_concepts` has 1 to 5 distinct strings drawn from the Target source, Snapshot symbol names, or DSA pattern names. `question_id` follows the design formula and embeds the first 16 characters of the Target `ast_hash` (decision D11)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.15, 7.16, 7.17_

  - [x] 6.4 Add Socratic grading to `mastery.py`
    - Implement `async submit_answers(repo_id, target_id, answers)` with the eight steps of the design: preconditions, regenerate the check, reject a mismatched `ast_hash` prefix (`INVALID_ANSWERS`, "the check no longer matches the current code"), reject a wrong count, unknown id, repeated id, or empty or over-2,000-character answer before any router call, build the grading slice, call `router.generate_structured(GRADING_SYSTEM_PROMPT, ..., SocraticGrade)` inside `asyncio.wait_for(..., 30)`
    - Map `LLMRouterError`, `TimeoutError`, `ValidationError`, and wrong result type to `GRADING_UNAVAILABLE` with the fixed message "grading is unavailable". Re-validate the grade. `passed = score >= 0.7`. On pass, in one transaction re-read the record, apply `apply_pass(record, read_clock(clock))`, run `check_transition`, and write. On fail, write nothing
    - Return a `SocraticVerdict` with the record's values after the step. Start no timer (Requirement 7.14). Never include provider text, prompts, or answers in errors
    - _Requirements: 3.6, 3.7, 6.2, 6.3, 6.4, 7.7, 7.9, 7.10, 7.11, 7.12, 7.13, 7.14, 7.15, 7.17, 23.8_

  - [x] 6.5 Add vitals and `file_states` to `mastery.py`
    - Implement `compute_vitals` and `MasteryEngine.get_vitals`. Read the Clock exactly once, then one `cache.read` (Snapshot, Study Mode, Mastery_Records). Raise `UNKNOWN_REPOSITORY` when no Snapshot is stored and a validation error for a bad `repo_id`
    - Counted records are those whose `target_id` is a trackable Snapshot symbol. Compute `total_modules`, the four state counts, `mastery_percentage = round(100 * mastered / total, 2)` (0.0 when total is 0), `due_for_review` (MASTERED, `next_review_at <= now`, sorted by `(next_review_at, target_id)`), and `study_mode_enabled`
    - Compute `file_states` by the weakest-link rule (STALE, then UNAUDITED, then DISSECTED, then MASTERED), one entry per Snapshot file with a counted symbol, keys inserted in sorted Unicode code point order. Derive it with no write and no new persisted state
    - Study Mode changes only `study_mode_enabled`. Vitals make no write, no LLM call, and start no check. A database or Clock failure raises an error with no partial vitals and no row content
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.14, 8.15_

- [x] 7. Analysis_Pipeline and Dissection_Service
  - [x] 7.1 Create `backend/engines/analysis_pipeline.py`
    - Define `LocalSource`, `GitHubSource`, `PipelineStep`, `AnalysisPipelineError`, `NoAnalyzableFilesError`, and `AnalysisResult` as in the design
    - Implement `normalize_github_url` (lower-case scheme and host only), `derive_local_repo_id` (`local-<slug>-<16 hex of sha256(realpath)>`), and `derive_github_repo_id` (`gh-<slug>-<12 hex>`, owner and repo lower-cased, trailing `/` and `.git` removed). Ids use only `A-Z a-z 0-9 . _ -` and are 1 to 100 characters
    - Implement `analyze_repository`: discover through the Ingestion_Engine (an `IngestionError` propagates unchanged), read the discovered files with `O_NOFOLLOW`, regular-file, and 524,288-byte guards (an unreadable file becomes an `ENTRY_UNREADABLE` warning), raise `NoAnalyzableFilesError` when nothing was read, then call `parse_source`, `scan_many`, `build_snapshot`, `build_provenance`, and `profile_topology`. A step failure becomes `AnalysisPipelineError(step)` with the exception class name only
    - Compute the content fingerprint from file hashes, the truncation flag, and the spec and steering documents from `discover_specs`. Persist the Snapshot, provenance, topology, `RepositoryRecord`, and `mastery.register_snapshot` in one `cache.transact`. A persistence failure becomes `AnalysisPipelineError(persist)` and leaves earlier data unchanged
    - Implement `ensure_analysis(path)`: run discovery, reads, and the fingerprint, return stored data with `reused=True` when the fingerprint matches, otherwise run the full pipeline
    - Import no `fastapi`, `starlette`, or `mcp`. Contain no parsing, graph, DSA, provenance, or topology logic
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 10.13, 16.8, 16.11, 23.6_

  - [x] 7.2 Create `backend/engines/dissection.py`
    - Define `InvalidLensError`, `DissectionResult`, `DEFAULT_MAX_DEPTH = 3`, and `DissectionService` with `dissect`, `dissect_many`, and `blast_radius`
    - `dissect_many`: validate the lens first (`InvalidLensError` before any engine call), call `pedagogy.explain_target` for each id (a `PedagogyError` propagates unchanged), load the Snapshot once, build the graph, and call `trace_blast_radius` with the given `max_depth` (default 3). For `L3_ARCHITECTURE`, trace on a graph copy that holds the scope as an isolated `node_type="scope"` node (decision D6)
    - When the lens is L1 or L2 and Study Mode is on, call `mastery.record_views` once after every result exists. For L3 or Study Mode off, call no view operation. Return no partial result when any step fails. `blast_radius` raises `PedagogyError(UNKNOWN_TARGET)` for an id that is not a Snapshot symbol
    - Import no `fastapi`, `starlette`, or `mcp`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 15.13_

- [x] 8. Checkpoint - engines complete
  - Run a throwaway smoke script (not committed) that analyzes a small temporary Python repository with the mock provider, sets Study Mode, dissects one symbol, starts and submits a check, and reads vitals, to confirm the engines work together
  - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q`, then `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. FastAPI application
  - [x] 9.1 Create `backend/api/settings.py` and `backend/api/errors.py`
    - `settings.py`: `ConfigurationError(variable)` (message names the variable, never its value), frozen `ApiSettings` (`crew_secret` hidden from `repr`), and `load_api_settings(environ)`. Parse `STUPID_CODE_CORS_ORIGINS` (comma split, trim, drop empties, default to the four localhost origins, refuse `*`), `ALLOW_LOCAL_INGEST` (trim; `true`/`1`/`false`/`0` case-insensitive; unset or empty is true; anything else is a configuration error), `STUPID_CODE_GITHUB_RATE_LIMIT` (integer 1 to 1,000, default 5), `STUPID_CODE_GITHUB_RATE_WINDOW_SECONDS` (integer 1 to 3,600, default 60), and `KIRO_CREW_SECRET`. The database path stays with the existing `CacheSettings`
    - `errors.py`: `ApiError(status, code, message)`, the Error_Envelope builder, the exception handlers (`ApiError`, `RequestValidationError` to 422 `validation_error` with field locations only, Starlette `HTTPException` 404 `not_found` and 405 `method_not_allowed`, `CacheStoreError` to 500 `storage_error`), the pure-ASGI `CatchAllMiddleware` (500 `internal_error`, logs only the exception class name, keeps serving), and the mapping helpers for `IngestionError`, `AnalysisPipelineError`, `PedagogyError`, and `MasteryError` using the tables in the design's Error Handling section
    - Responses never include stack traces, server paths, SQL, provider text, credentials, or prompts
    - _Requirements: 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 10.3, 10.4, 10.5, 10.15, 10.16, 10.17, 12.5, 12.6, 12.7, 12.8, 14.6, 14.8, 14.10, 14.11, 23.8, 23.9_

  - [x] 9.2 Create `backend/api/rate_limit.py` and `backend/api/crew_signature.py`
    - `rate_limit.py`: `RateDecision` and `RateLimiter(limit, window_seconds)` with `check_and_count(client_ip, now)`. Sliding-window log in a `dict[str, deque[float]]` under one `threading.Lock`; drop entries at or older than the window and delete empty keys; a rejected request is not recorded; `retry_after_seconds = max(1, ceil(window - (now - oldest)))`. Use no external dependency and the injected Clock only
    - `crew_signature.py`: `InvalidSignature` and the pure function `verify_crew_signature(secret, headers, method, path_with_query, raw_body, now)` with the exact rule order of the design: invalid `now` rejects; a repeated `X-Kiro-Signature` rejects; one `X-Kiro-Signature` decides alone (`sha256=<64 lower-case hex>` HMAC of the raw body); otherwise one `X-Crew-Proxy` value `<10 to 12 digit timestamp>:<64 lower-case hex>` within 60 seconds, signed text `timestamp:METHOD:path[?query]:sha256hex(body)`; neither header rejects. Compare with `hmac.compare_digest`. Import only `hmac`, `hashlib`, `re`, `datetime`, and typing. Log and return no secret, header value, computed value, or signed string
    - _Requirements: 10.8, 10.9, 10.10, 10.11, 10.12, 10.22, 15.5, 15.6, 15.7, 15.8_

  - [x] 9.3 Create `backend/api/services.py` and `backend/api/schemas.py`
    - `services.py`: the `Services` dataclass (cache, router, clock, mastery, pedagogy, dissection, `git_runner`, `workspace`), `Services.from_environment()`, and `get_services(request)` that creates the shared instance lazily under a lock on first use, so importing `backend.api.main` opens no database and builds no router (decision D9). Tests override it with a temporary database, the mock router, a fixed Clock, and a git double
    - `schemas.py`: Pydantic models for every request and response body: `parse_ingest_body` with `IngestCommand` (the body checks and limit checks of Requirement 10 criteria 2 and 6, including the 1 MiB body cap and rejection of booleans, floats, strings, and `null` limits), `IngestResponse` with the summary counts and warnings (relative paths only), `RepoSummary`, `SnapshotResponse`, `ExplainRequest` (strict `lens` literal, `target_id` 1 to 500 characters), `ExplainResponse` (exactly envelope and blast radius), `StudyModeRequest` (`enabled: StrictBool`), `StudyModeResponse`, `SocraticStartRequest`, `SocraticSubmitRequest`, and the discriminated Crew request union with `extra="forbid"` and the Crew response models
    - _Requirements: 9.13, 9.15, 10.1, 10.2, 10.6, 11.1, 11.4, 12.1, 12.2, 12.3, 13.3, 13.6, 14.9, 15.1, 15.10, 23.7_

  - [x] 9.4 Create `backend/api/routes/repos.py`
    - Implement `POST /api/repos/ingest` with the check order of Requirement 10.21: body checks (400 `malformed_request`), limit checks (422 `invalid_limit`), `ALLOW_LOCAL_INGEST` for `path` (403 `local_ingest_disabled` before any file-system call), the Rate_Limiter for `url` (429 `rate_limited` with `Retry-After`, using `request.client.host` and ignoring `X-Forwarded-For`), then `analyze_repository` in `run_in_threadpool`. Map ingestion and pipeline errors with the design table. Return 200 with `truncated: true` when discovery truncates
    - Implement `GET /api/repos` (read from the registry plus Study Mode, sorted by `repo_id`, no ingestion) and `GET /api/repos/{repo_id}/snapshot` (stored Snapshot, provenance, and topology, with the Snapshot `root_path` replaced by `"."`; 404 `repo_not_found` for an unknown or malformed `repo_id` without querying the Cache_Store when malformed; 500 `storage_error` for an unreadable payload). Neither endpoint calls the LLM_Router or changes any record
    - Handlers stay thin: validate, call one engine function, map the result
    - _Requirements: 9.3, 9.14, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.14, 10.18, 10.19, 10.20, 10.21, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x] 9.5 Create `backend/api/routes/autopsy.py`
    - Implement `POST /api/repos/{repo_id}/explain`: check the Repo_Id rule and stored repository (404 `repo_not_found`), validate the body (422 `validation_error`), call `DissectionService.dissect` in `run_in_threadpool` (async calls through `asyncio.run` in the worker thread, decision D10), and return exactly `{envelope, blast_radius}` with no quiz or gate field
    - Map `PedagogyError` kinds: `UNKNOWN_TARGET` 404 `unknown_target`, `SOURCE_UNREADABLE` 409 `source_unreadable`, `LLM_FAILURE` 503 `llm_unavailable`, `INVALID_OUTPUT` 502 `invalid_llm_output`. Any non-2xx leaves records and Study Mode unchanged. The mastery update stays inside the Dissection_Service
    - _Requirements: 9.3, 9.14, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12_

  - [x] 9.6 Create `backend/api/routes/mastery.py`
    - Implement `GET /api/repos/{repo_id}/vitals` (returns the Mastery_Engine's `ComprehensionVitals` unmodified, no write, no LLM call) and `POST /api/repos/{repo_id}/study-mode` (strict boolean `enabled`, idempotent, same 200 body for a changed or unchanged value, 422 `validation_error` for a non-boolean, non-object, or missing field)
    - Implement `POST /api/repos/{repo_id}/socratic/start` and `socratic/submit` with the precedence of Requirement 14: read the raw body (at most 1 MiB), then `repo_not_found`, then `validation_error`, then `study_mode_disabled` (409), then `unknown_target`, then `invalid_answers` (422), then `grading_unavailable` (503). `start` returns the check with every `expected_concepts` replaced by an empty list and makes no LLM call. `submit` returns the `SocraticVerdict` and never reports `MASTERED` with a non-null `next_review_at` for a failed or unavailable grading
    - Map `CacheStoreError` to 500 `storage_error` and leave the persisted Study Mode unchanged
    - _Requirements: 9.3, 9.14, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10, 14.11, 14.12_

  - [x] 9.7 Create `backend/api/routes/crew.py`
    - Implement `POST /api/apps/stupid-code/crew` (decision D13). Order: read the raw body (more than 1,048,576 bytes gives 422 `validation_error`), when `KIRO_CREW_SECRET` is set call `verify_crew_signature` before parsing (inputs: raw header pairs, `request.method`, raw path plus `?` and the raw query string when present, `read_clock(services.clock)`; any `InvalidSignature` or invalid Clock gives 401 `invalid_signature`), parse the discriminated union (422 `validation_error`), check the repository (404 `repo_not_found`), apply the path guard (absolute path, `..` segment, or backslash gives 404 `unknown_target` with no file read), then dispatch
    - `autopsy_file`: the path must be a Snapshot file; sort symbols by `(start_line, id)`, keep at most 10 (`truncated: true` when more), and call `dissect_many(..., "L2_FLOW")`. `explain_folder_architecture`: `"."` maps to `target_id = repo_id`, any other path must be a directory in the stored `TopologyProfile`; call `dissect(..., "L3_ARCHITECTURE")`. `study_mode`: `set_study_mode` then `get_vitals`. With no secret, read no signature header
    - Start no ingestion and ignore `ALLOW_LOCAL_INGEST`. Any 5xx returns no partial symbol list and leaves records unchanged
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.10, 15.11, 15.12, 15.13, 15.14, 23.2_

  - [x] 9.8 Rewrite `backend/api/main.py` with `create_app` and mount the routers
    - Replace the module body with `create_app(settings=None, *, services=None, rate_limiter=None)` and `app = create_app()`. Keep `GET /health` with the same path, handler, and response. Import creates no database connection and no LLM_Router
    - Add `CORSMiddleware` (allow-list only, `allow_credentials=False`, methods `GET` and `POST`, headers `Content-Type`, `X-Kiro-Signature`, `X-Crew-Proxy`), the `CatchAllMiddleware`, the exception handlers, and the four routers (`repos`, `autopsy`, `mastery`, `crew`). Close the Cache_Store in the lifespan shutdown when the app created it. A configuration error raised in `create_app` stops startup
    - Run `backend/tests/unit/test_health.py` to confirm `GET /health` still passes
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.11, 9.13, 9.14, 9.15_

  - [x] 9.9 Update `.env.example` and `.gitignore`
    - Append exactly five lines to `.env.example`: `KIRO_CREW_SECRET=`, `STUPID_CODE_CORS_ORIGINS=`, `STUPID_CODE_GITHUB_RATE_LIMIT=5`, `STUPID_CODE_GITHUB_RATE_WINDOW_SECONDS=60`, `ALLOW_LOCAL_INGEST=true`. No secret value
    - Append the line `data/repos/` to `.gitignore` (decision D14). Add no rule that ignores `.kiro/` or the two hook files
    - _Requirements: 23.12, 20.1_

- [x] 10. Checkpoint - REST API complete
  - Run a throwaway `TestClient` smoke check against `create_app` with a temporary database and the mock provider: ingest a temporary repository, list, snapshot, explain, toggle Study Mode, vitals, Socratic start and submit, and a Crew request
  - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q` (the Phase 1 and Phase 2 suite, including `test_health.py`, must still pass), then `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. MCP server and workspace configuration
  - [x] 11.1 Create `backend/mcp_server/server.py`
    - Start with the `if __package__ in (None, ""):` bootstrap that puts the workspace root first on `sys.path`, then the single SDK import `from mcp.server.mcpserver import MCPServer` (decision: only one line changes on an SDK rename)
    - Define `ToolServices` (cache, router, clock) with `from_environment()` (the Cache_Store reads `STUPID_CODE_DB_PATH`), `build_server(services=None)`, and `main()` (runs `server.run("stdio")`; on `LLMConfigError` or `CacheStoreError` writes one line naming the problem to stderr and exits 1). Write nothing to stdout except protocol messages and log only to stderr
    - Register exactly five tools with `@server.tool`: `dissect_symbol(repo_path, target_id, lens="L2_FLOW")`, `trace_blast_radius(repo_path, target_id, max_depth=3)`, `analyze_folder_architecture(repo_path)`, `check_spec_drift(repo_path)`, `get_comprehension_vitals(repo_path)`. Type every parameter as `Annotated[Any, Field(description=..., json_schema_extra={"type": ...})]` with a default of `None` so raw values reach our own Pydantic validation (finding 2). Validate: `repo_path` (string, 1 to 4,096 characters, no NUL, readable directory, else `invalid_repo_path`), `target_id` (1 to 500 characters), `lens` (else `invalid_lens`), `max_depth` (an `int`, not a `bool`, 0 to 20, else `invalid_max_depth`)
    - Each tool is a thin wrapper run through `anyio.to_thread.run_sync`: the first four call `ensure_analysis` then `DissectionService.dissect`, `DissectionService.blast_radius`, the stored topology (zero LLM calls), or the provenance drift items and `has_kiro_specs`; `get_comprehension_vitals` derives `repo_id` with `derive_local_repo_id`, runs no analysis, makes no write, and returns `repo_not_analyzed` when nothing is stored. Return `{"ok": true, ...}` built with `model_dump(mode="json")`, or `{"ok": false, "error": {"code", "message"}}` using the MCP table of the design. Catch `Exception` last and return `internal_error`. Results hold no credential, provider text, stack trace, or path outside the requested `repo_path`
    - Accept an injected Cache_Store, LLM_Router, and Clock. With `LLM_PROVIDER=mock`, make no network call
    - _Requirements: 16.1, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12, 16.13, 16.14, 16.15, 16.16, 16.17, 16.18, 16.19, 16.20, 16.21, 16.22, 16.23, 16.24, 16.25, 23.2, 23.7_

  - [x] 11.2 Create `.kiro/settings/mcp.json`
    - One server entry `stupid-code` under `mcpServers` with `"command": ".venv/bin/python"` and `"args": ["backend/mcp_server/server.py"]`. No `env`, no absolute or home path, no secret
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5_

  - [x] 11.3 Verify the MCP server in process and through a real subprocess
    - In process: build the server with temporary services and confirm `await server.list_tools()` returns exactly the five tool names
    - Subprocess: with `mcp.Client(StdioServerParameters(command=".venv/bin/python", args=["backend/mcp_server/server.py"], cwd=<workspace root>, env={"LLM_PROVIDER": "mock", "STUPID_CODE_DB_PATH": <temp db>}))`, confirm `initialize` answers within 10 seconds and `tools/list` returns exactly the five names. Confirm nothing but protocol messages reaches stdout
    - Confirm that running `sh -c '.venv/bin/python backend/mcp_server/server.py'` in an empty temporary directory exits non-zero with `.venv/bin/python` named on stderr
    - These are throwaway verification commands; the permanent versions are the unit test and the integration script
    - _Requirements: 16.3, 16.18, 17.6, 17.7, 18.9_

- [x] 12. Checkpoint - MCP server
  - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q`, then `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Kiro Power, Crew App, and hooks
  - [x] 13.1 Create the Power package under `power/`
    - `power/plugin.json` with `$schema`, `name` `stupid-code`, `version` `0.1.0`, `description`, `author` object, `keywords` (1 to 20 non-empty strings), and `license`, and no field the Agent Plugins 1.0.0 manifest does not define; it references no path
    - `power/mcp.json` with `$schema` and one `mcpServers` entry `stupid-code` (`type` `stdio`, `command` `.venv/bin/python`, `args` `["backend/mcp_server/server.py"]`), the same command and script as `.kiro/settings/mcp.json`
    - `power/skills/code-autopsy/SKILL.md` (at most 200 lines) with front matter `name: code-autopsy` and a `description` that contains "Stupid Code", and sections: when to use, inputs (repository path and target symbol), tools (the five exact names), lenses, evidence rule (ground every statement in tool output; invent no code, symbols, lines, callers, callees, or specs), failures (report the failing tool and its `error.code` when a Tool_Result is missing or `ok` is false), and Study Mode (read `study_mode_enabled` from `get_comprehension_vitals`, no quiz while off, mastery decided by the backend)
    - No secret, absolute path, or home-directory path in any file
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7, 18.8, 18.10_

  - [x] 13.2 Create the Crew manifest and agent files under `crew/`
    - `crew/app.json` with `name` `stupid-code`, `version`, `displayName` (at most 60 characters), `description` (at most 280 characters), `author`, `agents` (`agents/autopsy-surgeon.json`, `agents/socratic-examiner.json`), `skills` (`skills/code-autopsy`), `permissions.api`, and `contributes` holding exactly two `fileMenuItems` ("Autopsy File" on `tree-context` and `file-overflow`; "Explain Folder Architecture" on `folder-row`), both with `endpoint` `/api/apps/stupid-code/crew`, and exactly one `sessionControls` entry "Study Mode" with `entryPoint` `ui/study-mode-control.mjs`. Use only fields the Crew manifest reference defines and relative paths with no `..`
    - `crew/agents/autopsy-surgeon.json` and `crew/agents/socratic-examiner.json` with `name`, `description`, `prompt` set to `file://./<matching>.md`, and `includeMcpJson: true`
    - `crew/agents/autopsy-surgeon.md` and `crew/agents/socratic-examiner.md` as plain prompt text with no front matter, covering Requirement 19.9 and 19.10 (the examiner grades through the REST `socratic/start` and `socratic/submit` endpoints, applies the 0.7 threshold only as reported by the backend, reveals no expected answer before the user answers, and declares mastery only after a passing verdict)
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.8, 19.9, 19.10, 19.12_

  - [x] 13.3 Create the Crew skill and the session-control module
    - `crew/skills/code-autopsy/SKILL.md` with one titled section for each of: tool usage, file context, the three lenses, Study Mode, the Socratic workflow, mastery, evidence grounding, and handling of a missing tool or a failed backend. Use the same tool names, the same 0.7 Pass_Threshold, and the same Study Mode rules as the Power skill
    - `crew/ui/study-mode-control.mjs` (at most 100 lines, no `@kirocrew/app-sdk` import unless a documented capability is needed): export `mount(element, context)` that renders one checkbox "Study Mode", posts `{"action": "study_mode", "repo_id", "enabled"}` with `fetch` to `/api/apps/stupid-code/crew`, shows the persisted value from the response, disables itself when no repository id is available, and returns an unmount function. No Phase 4 UI, React code, or route is added
    - _Requirements: 19.1, 19.4, 19.7, 19.11, 19.12_

  - [x] 13.4 Create the two v1 hook files in `.kiro/hooks/`
    - `.kiro/hooks/verify-engines.json`: `version` `v1`, one hook with `trigger` `PostFileSave`, `matcher` `(^|.*/)backend/engines/[^/]+\.py$` (JSON-escaped), and `action` `{"type": "command", "command": ".venv/bin/python -m pytest -q"}`. The command contains none of `;`, `&`, `|`, `>`, `<`, a backtick, or `$(`
    - `.kiro/hooks/anti-vibe-coding.json`: `version` `v1`, one hook with `trigger` `PostToolUse`, `matcher` `^(fs_write|fs_append|str_replace|smart_relocate|semantic_rename)$`, and an `agent` action whose prompt contains the literals `get_comprehension_vitals`, `study_mode_enabled`, `dissect_symbol`, and `25`. The prompt tells the agent to read `study_mode_enabled`; to take no action (no message, no other tool) when the value is false, the tool is unavailable, `ok` is false, or the value is not a boolean; when true, to flag a file of more than 25 lines (blank lines count, a final line break adds none) with its repository-relative path and line count and call `dissect_symbol` on at least one symbol in it; to flag a file at most once per session while unchanged, never flag a file of 25 lines or fewer, and never delete, revert, or modify user code
    - No `.kiro.hook` file anywhere, no secret, no absolute or home-directory path
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8, 20.9, 20.10, 20.11, 20.12, 23.13_

  - [x] 13.5 Verify the manifests, matchers, and ignore rules
    - Parse `.kiro/settings/mcp.json`, `power/plugin.json`, `power/mcp.json`, `crew/app.json`, `crew/agents/*.json`, and both hook files with `json.load` and confirm every declared path exists and is relative
    - Check the verify-engines matcher with both `re.search` and `re.fullmatch`, on the relative form and on `/ws/` plus the path: it must match `backend/engines/mastery.py` and `backend/engines/__init__.py`, and none of `backend/engines/sub/helper.py`, `backend/engines/mastery.pyc`, `backend/engines/mastery.py.bak`, `backend/engines_old/mastery.py`, `backend/tests/unit/test_mastery_api_mcp.py`, `backend/api/main.py`, `README.md`, `frontend/src/App.tsx`
    - Check the anti-vibe matcher: it must match `fs_write`, `fs_append`, `str_replace`, `smart_relocate`, `semantic_rename`, and none of `read_file`, `read_code`, `list_directory`, `grep_search`, `file_search`, `delete_file`, `execute_bash`
    - Run `git check-ignore -v .kiro/hooks/verify-engines.json .kiro/hooks/anti-vibe-coding.json` and confirm no rule ignores them; confirm no `*.kiro.hook` file exists
    - These are throwaway checks; the permanent version is unit test 21
    - _Requirements: 17.1, 17.3, 18.2, 18.3, 19.2, 19.8, 20.1, 20.2, 20.6, 20.11_

- [x] 14. Checkpoint - Kiro-native packages
  - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q` and `.venv/bin/ruff check backend`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Test suites (all required)
  - [x] 15.1 Create the shared helper module `backend/tests/mastery_support.py`
    - Not a test file. Provide `FixedClock` (settable datetime), `FixedGradeRouter(score)` (returns `SocraticGrade`, delegates other models to the mock `LLMRouter`), `RecordingRouter` (records the user prompt and response model), `FailingGradeRouter(mode)` (raises `LLMRouterError`, sleeps past a short timeout, or returns an invalid object), `git_double(files)` (writes the files into `argv[-1]` and returns `CompletedProcess(returncode=0)`), `make_services(tmp_path, router, clock)`, `make_client(...)` (`create_app` plus `TestClient`), `sign_kiro(body, secret)`, `sign_proxy(secret, timestamp, method, path_with_query, body)`, and small source fixtures (a module with a caller, a callee, and a `heapq` function; an isolated function; a two-file repository)
    - Offline only: temporary or in-memory databases, mock provider, no network, no real `.env`
    - _Requirements: 21.8, 22.7_

  - [x] 15.2 Write unit tests 1 to 6 (Mastery_Engine) in `backend/tests/unit/test_mastery_api_mcp.py`
    - Create the file with its imports and these functions, each with at least one assertion on a resulting value or state: `test_study_mode_default_persistence_and_validation`, `test_registration_and_view_transitions`, `test_pass_fail_and_ast_change_transitions`, `test_review_schedule_intervals`, `test_vitals_counts_percentage_and_file_states` (includes the weakest-link value for a file in mixed states, key order, and byte-identical repeat), `test_due_for_review_order_with_controlled_clock`
    - Keep the file compact: the final file has exactly 24 tests and fewer than 600 lines
    - _Requirements: 21.1, 21.2, 2.2, 2.3, 2.4, 2.8, 2.11, 2.12, 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9, 6.1, 6.3, 6.9, 6.11, 8.1, 8.2, 8.3, 8.4, 8.8, 8.11, 8.14_

  - [x] 15.3 Write unit tests 7 to 10 (Socratic workflow) in the same file
    - `test_socratic_check_is_grounded_and_deterministic`, `test_mock_grader_and_answer_association`, `test_pass_threshold_boundary` (0.69 fails with the record unchanged, 0.70 passes), `test_failed_or_invalid_grading_grants_no_mastery` (router error, timeout, and invalid output each give `GRADING_UNAVAILABLE` with no record change and a clean message)
    - _Requirements: 21.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13, 7.15, 7.16_

  - [x] 15.4 Write unit tests 11 to 16 (REST API) in the same file
    - `test_ingest_validation_truncation_and_local_ingest_disabled` (a 400 case, a 422 `invalid_limit` case, `truncated: true`, and, inside this function, a `path` request with `ALLOW_LOCAL_INGEST` false returning 403 `local_ingest_disabled` with ingestion never started), `test_list_snapshot_and_explain_reads`, `test_study_mode_toggle_and_read_only_vitals`, `test_socratic_start_and_submit_endpoints`, `test_error_envelope_shape_on_non_2xx`, `test_github_rate_limit_with_controlled_clock` (git double; the 6th request is rejected with `Retry-After`; accepted after the window; `path` requests unaffected)
    - All through FastAPI `TestClient` with the git subprocess replaced by a test double
    - _Requirements: 21.4, 9.9, 9.10, 9.11, 10.1, 10.2, 10.6, 10.7, 10.8, 10.9, 10.10, 10.18, 10.21, 11.1, 11.4, 12.1, 12.9, 12.11, 13.1, 13.3, 13.6, 14.1, 14.2, 14.4, 14.6, 14.7_

  - [x] 15.5 Write unit tests 17 and 18 (Crew_Webhook) in the same file
    - `test_crew_file_menu_actions` (`autopsy_file` returns L2 symbols sorted by start line, `explain_folder_architecture` for `"."` and for a directory, `..` path gives `unknown_target`) and `test_crew_study_mode_and_signatures`
    - The signature cases run inside the second function and add no test function: valid `X-Kiro-Signature` accepted; valid `X-Crew-Proxy` within 60 seconds of a controlled Clock accepted; invalid `X-Kiro-Signature`, invalid `X-Crew-Proxy`, stale `X-Crew-Proxy`, both headers with an invalid `X-Kiro-Signature` and a valid `X-Crew-Proxy`, and neither header each give 401 `invalid_signature`; an unset secret accepts an unsigned request; direct `verify_crew_signature` calls cover a repeated header and a naive Clock value
    - _Requirements: 21.5, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.9_

  - [x] 15.6 Write unit tests 19 and 20 (MCP tools) in the same file
    - `test_mcp_tools_succeed_on_valid_input` (`list_tools` returns exactly the five names; each tool returns `ok: true` through the shared engines; `json.dumps` succeeds) and `test_mcp_tools_fail_cleanly_on_invalid_input` (each tool returns `ok: false` with an `error` object for `invalid_repo_path`, `unknown_target`, `invalid_lens`, `invalid_max_depth` with `True` and `21`, and `repo_not_analyzed`; no record changes)
    - _Requirements: 21.6, 16.3, 16.4, 16.6, 16.7, 16.8, 16.9, 16.10, 16.12, 16.13, 16.14, 16.15, 16.16_

  - [x] 15.7 Write unit tests 21 to 24 (manifests, layering, ids and settings, models) and finalize the file
    - `test_manifests_hooks_and_launch_config`: parse every manifest and hook, check declared paths exist and are relative, no absolute or home path, no non-empty secret-like key, the hook shape, the matcher path table (search and full match, relative and absolute form), the anti-vibe positive and negative tool names, the required prompt literals, the Power and Crew skill front matter and 200-line limit, and the missing `.venv/bin/python` launch failure
    - `test_engine_layering_and_import_graph_is_acyclic`: `ast`-based check that `mastery`, `analysis_pipeline`, and `dissection` import no `fastapi`, `starlette`, `mcp`, `backend.api`, or `backend.mcp_server`, and that the import graph of `backend/engines/*.py` has 0 cycles
    - `test_repo_id_derivation_and_api_settings`: equivalent spellings give one id, different directories or repositories (same basename, `a-b/c` versus `a/b-c`) give different ids, regex and length; `ConfigurationError` names the variable for CORS `*`, `ALLOW_LOCAL_INGEST=yes`, and rate limit `0`
    - `test_new_domain_models_validate_and_round_trip`: NaN, infinity, bool, `"0.5"`, bounds, extra field, bad timestamp, and `file_states` longer than `total_modules` are rejected; one valid instance of each model round-trips
    - Finalize: confirm with `grep -c "^def test_\|^async def test_"` that the file has exactly 24 tests and with `wc -l` that it has fewer than 600 lines, then run the file alone and confirm 24 passed in under 60 seconds
    - _Requirements: 21.1, 21.7, 21.10, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.16, 1.20, 1.21, 4.5, 4.6, 9.4, 9.7, 10.15, 10.17, 17.1, 17.3, 17.7, 18.2, 18.5, 19.2, 20.1, 20.2, 20.6, 20.12, 23.1_

  - [x] 15.8 Create the property file and write Property 1
    - Create `backend/tests/properties/test_mastery_properties.py` with a module-level warm-up that loads the tree-sitter grammars once, shared `settings` values (`derandomize=True`, `max_examples` at most 50, `deadline=timedelta(milliseconds=500)`, no `suppress_health_check`), and `LLM_PROVIDER=mock`. Each test is a synchronous `@given` function that calls `asyncio.run(...)` inside the body and uses `tempfile.TemporaryDirectory()` and no fixtures
    - **Property 1: Mastery events keep a valid state and never grant mastery on failure**
      - Strategy: `st.lists(st.sampled_from(["view", "pass_check", "fail_check", "ast_changed"]), min_size=1, max_size=30)`, one record starting `UNAUDITED` with Study Mode on, using `FixedGradeRouter` for pass and fail
      - After every event assert: the state is one of the four values, `interval_days >= 0` and `repetitions >= 0`, a `fail_check` never moves a non-`MASTERED` state to `MASTERED`, a rejected event leaves the persisted record equal to its prior value, and the expected next state from the transition table
    - Add the tag comment `# Feature: 03-mastery-and-kiro-native, Property 1: Mastery events keep a valid state and never grant mastery on failure`
    - **Validates: Requirements 3.3, 3.4, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.14, 3.15, 6.7, 22.2**

  - [x] 15.9 Write Property 2 in the property file
    - **Property 2: Consecutive passes follow the review schedule**
      - Strategy: `st.integers(min_value=1, max_value=20)` passes on one fresh record with a Clock fixed at `2025-01-01T00:00:00Z`
      - After each accepted pass assert: `repetitions` rose by exactly 1, `interval_days` is at least its previous value and equals 1, then 6, then `round(previous * ease_factor)`, `next_review_at` equals Clock plus `interval_days` days, and `ease_factor` stays 2.5
      - On the first pass whose date would exceed `9999-12-31T23:59:59Z` (pass 17), assert `REVIEW_DATE_OUT_OF_RANGE` is raised, the record equals its value before that pass, and apply no later pass in that example
    - Add the tag comment `# Feature: 03-mastery-and-kiro-native, Property 2: Consecutive passes follow the review schedule`
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.12, 22.3**

  - [x] 15.10 Write Property 3 in the property file
    - **Property 3: Study Mode toggles change nothing but the flag**
      - Strategy: `st.lists(st.booleans(), min_size=1, max_size=20)` of `set_study_mode` operations on a repository with at least one Mastery_Record and one cached `ExplanationEnvelope`
      - Assert after the sequence: the record count, every stored record and `ast_hash`, every cached `ExplanationEnvelope`, the Snapshot, provenance, and topology equal their values before the first operation, and the Study Mode value read equals the last value set
    - Add the tag comment `# Feature: 03-mastery-and-kiro-native, Property 3: Study Mode toggles change nothing but the flag`
    - **Validates: Requirements 2.5, 2.6, 22.4**

  - [x] 15.11 Write Property 4 in the property file and finalize it
    - **Property 4: Every MCP tool returns a JSON-serializable Tool_Result**
      - Strategy: repositories of 1 to 10 generated functions with distinct identifiers from a fixed alphabet and a call-edge choice per function, written to one or two files under a `TemporaryDirectory`, analyzed into a fresh temporary database
      - Call each of the five tools through `server.call_tool` with inputs valid for the Snapshot and read `structured_content`. Assert `json.dumps(result)` succeeds and `result["ok"]` exists and is a `bool`
    - Add the tag comment `# Feature: 03-mastery-and-kiro-native, Property 4: Every MCP tool returns a JSON-serializable Tool_Result`
    - Finalize: confirm the file has exactly four `@given` tests and no other Hypothesis test, every `@settings` has `derandomize=True`, `max_examples` from 1 to 50, `deadline` at most 500 ms, and no `suppress_health_check`; run it alone and confirm 4 passed in under 60 seconds
    - **Validates: Requirements 16.4, 16.6, 16.7, 16.8, 16.9, 16.10, 22.5**

- [x] 16. Checkpoint - new tests
  - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest backend/tests/unit/test_mastery_api_mcp.py -q` (24 passed, under 60 seconds) and `LLM_PROVIDER=mock .venv/bin/python -m pytest backend/tests/properties/test_mastery_properties.py -q` (4 passed, under 60 seconds)
  - Run `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend`
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Integration check script
  - [x] 17.1 Create `scripts/check_study_mode_parity.py`
    - Create a temporary two-file Python repository and a temporary database file; set `LLM_PROVIDER=mock` and `STUPID_CODE_DB_PATH`
    - API side: build `create_app` on that database with `Services` and use `TestClient` for `POST /api/repos/ingest {"path": ...}`, `POST /api/repos/{id}/study-mode {"enabled": true}`, and `GET /api/repos/{id}/vitals`. Value A is the vitals `study_mode_enabled`
    - MCP side: start the real server with `mcp.Client(StdioServerParameters(command=".venv/bin/python", args=["backend/mcp_server/server.py"], env=..., cwd=<workspace root>))`, check that `list_tools()` returns exactly the five names, and read value B from `get_comprehension_vitals(repo_path=...)`
    - Print `API study_mode_enabled=<A>` and `MCP study_mode_enabled=<B>`. Exit 0 only when both surfaces succeeded and `A == B`; otherwise print which surface returned which value or error code and exit 1. Clean up the temporary files
    - _Requirements: 24.7, 24.8, 16.19, 17.6, 18.9_

  - [x] 17.2 Run the integration script
    - Run `LLM_PROVIDER=mock .venv/bin/python scripts/check_study_mode_parity.py` from the workspace root and confirm exit code 0 and matching values. Fix any mismatch in the engines or surfaces, not in the script
    - Record the printed output for report section H
    - _Requirements: 24.7, 24.8_

- [x] 18. Final verification and backward-compatibility review
  - [x] 18.1 Run the full suite and lint
    - Run `LLM_PROVIDER=mock .venv/bin/python -m pytest -q` and confirm 0 failed, 0 errors, and a passed total equal to the Baseline_Count plus 24 plus 4 (798 when the baseline is 770). Copy the summary line for the report
    - Run `.venv/bin/ruff check backend` and `.venv/bin/ruff format --check backend` and confirm both exit 0 with 0 violations and 0 files to reformat
    - Fix any failure at its source. Never weaken, skip, or xfail a test
    - _Requirements: 21.10, 21.11, 22.8, 23.11, 24.1, 24.2, 24.4_

  - [x] 18.2 Validate the manifests and list the MCP tools
    - Parse `.kiro/settings/mcp.json`, `power/plugin.json`, `power/mcp.json`, `crew/app.json`, `.kiro/hooks/verify-engines.json`, and `.kiro/hooks/anti-vibe-coding.json` with `json.load` and confirm each parses without error
    - List the MCP_Server tools and confirm exactly `dissect_symbol`, `trace_blast_radius`, `analyze_folder_architecture`, `check_spec_drift`, and `get_comprehension_vitals`
    - Confirm that every deliverable of Requirement 24.5 exists as a non-empty file or directory
    - _Requirements: 24.5, 24.6, 17.6, 18.9_

  - [x] 18.3 Backward-compatibility review
    - Re-hash every file in `phase12-hashes.txt` with `git hash-object` and confirm every Phase 1 and Phase 2 test file, `conftest.py`, `support.py`, `pytest.ini`, and the untouched engines are byte-identical to the snapshot
    - Run `git diff` on `backend/domain/models.py` (append only, no changed or removed existing line), `backend/engines/cache_store.py` (additive), `backend/engines/llm_router.py` (one builder, one registry entry, docstring), `backend/api/main.py`, `backend/pyproject.toml` (`mcp` line only), `.env.example` (exactly five added lines), and `.gitignore` (one added line), and compare each with the design's change log. Record a justification for any difference
    - Confirm that no file under a `frontend/` directory, no React or web UI file, no container, CI, or hosting file, and no `*.kiro.hook` file was added, and that no Phase 1 or Phase 2 test was skipped or marked xfail (`git diff` and `grep` for `skip` and `xfail` on the unchanged test files)
    - _Requirements: 24.3, 24.11, 21.9, 23.5, 20.1_

- [x] 19. Checkpoint - everything verified
  - Ensure the full suite, ruff, the manifest checks, the integration script, and the backward-compatibility review all pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 20. Implementation report
  - [x] 20.1 Write the A to J implementation report
    - Create `.kiro/specs/03-mastery-and-kiro-native/implementation-report.md` with exactly ten lettered sections in this order: A spec artifacts, B implementation summary, C mastery behavior, D API summary, E MCP summary, F Kiro-native integrations, G test results, H integration verification, I limitations, J completion status
    - Section G states the Baseline_Count measured in task 1.2, the new unit test count (24), the new property test count (4), and the final passed total, each copied from an actual pytest summary line, plus the ruff results
    - Section H quotes the output of the integration script. Section F records the hook and Crew items that need a manual check against a real Kiro IDE and Crew host (design Open Risks R1 and R2) and the result of the manual check if it was done
    - Section I lists each unmet requirement number with a one-sentence reason, and the known risks R1 to R8 that still apply. Section J is exactly one of COMPLETE, PARTIALLY COMPLETE, or BLOCKED, and is not COMPLETE if any requirement is listed in section I as unmet
    - _Requirements: 24.2, 24.9, 24.10_

## Notes

- Every test task is required. No task carries the optional marker.
- Checkpoints before the new tests exist (tasks 5, 8, 10, 12, 14) run the existing suite, ruff, and a throwaway smoke check. Tasks 16 and 19 run the new tests.
- Verification tasks marked "throwaway" (11.3, 13.5) use ad hoc commands. Their permanent counterparts are unit test 21, unit test 19, and the integration script.
- If a design signature differs from the real Phase 1 or Phase 2 code (task 1.1), adapt the new code and record the mismatch in `baseline.md`. Do not edit `requirements.md`, `design.md`, or `.config.kiro`.
- Property tests validate universal properties (4 of them, fixed by Requirement 22). Unit tests validate examples, boundaries, error codes, and manifests.
- This workflow only plans. Open `tasks.md` and click "Start task" next to a task to begin implementation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["6.1"] },
    { "id": 4, "tasks": ["6.2"] },
    { "id": 5, "tasks": ["6.3"] },
    { "id": 6, "tasks": ["6.4"] },
    { "id": 7, "tasks": ["6.5"] },
    { "id": 8, "tasks": ["7.1", "7.2"] },
    { "id": 9, "tasks": ["9.1", "9.2", "9.9", "11.1", "11.2", "13.1", "13.2", "13.3", "13.4"] },
    { "id": 10, "tasks": ["9.3", "11.3", "13.5"] },
    { "id": 11, "tasks": ["9.4", "9.5", "9.6", "9.7"] },
    { "id": 12, "tasks": ["9.8"] },
    { "id": 13, "tasks": ["15.1"] },
    { "id": 14, "tasks": ["15.2", "15.8"] },
    { "id": 15, "tasks": ["15.3", "15.9"] },
    { "id": 16, "tasks": ["15.4", "15.10"] },
    { "id": 17, "tasks": ["15.5", "15.11"] },
    { "id": 18, "tasks": ["15.6"] },
    { "id": 19, "tasks": ["15.7"] },
    { "id": 20, "tasks": ["17.1"] },
    { "id": 21, "tasks": ["17.2"] },
    { "id": 22, "tasks": ["18.1", "18.2"] },
    { "id": 23, "tasks": ["18.3"] },
    { "id": 24, "tasks": ["20.1"] }
  ]
}
```
