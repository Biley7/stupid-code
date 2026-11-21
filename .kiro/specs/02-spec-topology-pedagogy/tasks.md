# Implementation Plan: Spec Topology and Pedagogy (Spec #02)

## Overview

The implementation language is Python, as used in design.md and Phase 1. Work follows the order you set: baseline, domain models, test configuration, then `spec_grounder.py`, `topology.py`, `llm_router.py`, `cache_store.py`, `pedagogy.py`, the unit tests, exactly four property tests, the full verification run, and a final report. Each task states what to implement and how it is validated. No Phase 1 file is modified, and no Phase 3 work is included. The unit and property test sub-tasks are required, not optional, because the user requires them.

## Tasks

- [x] 1. Baseline test run
  - [x] 1.1 Run the existing suite and record the passing count
    - Implement: run `pytest` from the repository root before touching any file. Record the exact pass count (expected 745) and the run's warnings, including any pytest-asyncio unset-loop-scope warning.
    - Validate: the run reports zero failures and zero errors. Any mismatch with 745 is reported in the final report, not silently accepted.
    - _Requirements: 17.8_

- [x] 2. Domain models appended to `backend/domain/models.py`
  - [x] 2.1 Append the enum and leaf models
    - Implement: after the last Phase 1 class, append `PedagogyLens`, `SpecLink`, `SpecDriftItem`, `SyntaxAnnotation`, `FlowStep`, `DSACard`, `AlternativeArchitecture`, using `_CONFIG`, strict types, `UnitFloat`, and the private `Literal` aliases from design.md. Field names and order match the design table. Change no existing line.
    - Validate: `git diff` shows only added lines in `models.py`; a quick import check passes; Phase 1 tests are unaffected.
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 1.12, 1.14_
  - [x] 2.2 Append the composite models, validators, and `__all__`
    - Implement: append `ProvenanceReport`, `TopologyProfile` (exact four `boundary_metrics` keys, ratio range checks, non-blank `repo_id`), `L1SyntaxExplanation`, `L2FlowExplanation` (with `llm_content_available: StrictBool = True`), `L3ArchitectureExplanation` (1 to 20 evidence entries), and `ExplanationEnvelope` (tier must match `lens`). End the file with `__all__ += [...]` listing the 13 names. Import only `re`, `enum`, `typing`, `math`, and `pydantic`.
    - Validate: `python -c "import backend.domain.models"` succeeds; the existing 745 tests still pass; detailed behavior is covered by unit tests 1 and 2 in task 11.1.
    - _Requirements: 1.1, 1.4, 1.5, 1.8, 1.10, 1.11, 1.12, 1.13, 1.14, 14.10_

- [x] 3. Test configuration
  - [x] 3.1 Update `pytest.ini` and `.gitignore`
    - Implement: add `asyncio_mode = auto` to the root `pytest.ini`, keeping `testpaths = backend/tests` and `pythonpath = .`. Add `asyncio_default_fixture_loop_scope = function` only if task 1.1 recorded an unset-scope warning. Add the line `data/*.db` to `.gitignore`.
    - Validate: `pytest --collect-only -q` still collects the baseline count with no new warnings.
    - _Requirements: 17.1_
  - [x] 3.2 Create `backend/tests/conftest.py`
    - Implement: an autouse fixture `_default_env` that sets `LLM_PROVIDER=mock` and `STUPID_CODE_DB_PATH=:memory:` and removes `GEMINI_API_KEY`. Add an opt-in `offline_guard` fixture that makes `socket.socket.connect` raise `AssertionError("network access attempted: ...")`, and wraps `Path.read_text`, `Path.read_bytes`, and `Path.open` to raise `AssertionError("read outside allowed roots: ...")` outside the repository root, the pytest temp directory, `sys.prefix`, and `sys.base_prefix`.
    - Validate: the full baseline suite still passes unchanged, since the guard is opt-in. The guard itself is exercised when it is enabled in the two new test files.
    - _Requirements: 17.6, 17.7, 17.8, 17.10_

- [x] 4. Checkpoint - Foundation
  - Run the full suite. The baseline count must still pass with zero failures. Ensure all tests pass, ask the user if questions arise.

- [x] 5. `backend/engines/spec_grounder.py`
  - [x] 5.1 Discovery, safe reads, and section parsing
    - Implement: `SpecGrounderError`, `SkipReason`, `SkippedSpecFile`, `ParsedSection`, `GrounderResult`, and `discover_specs(repo_root)`. Include the lstat and symlink checks, the 524,288-byte limit (exactly 524,288 is read), UTF-8 decoding, ordered discovery, fence-aware ATX heading parsing with `text` and `own_text`, and `has_kiro_specs`. Read-only access; create nothing under the repo root.
    - Validate: unit test 3 (task 11.2) covers missing documents, absent `.kiro`, the 524,288 and 524,289 byte files, and invalid UTF-8.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 16.8_
  - [x] 5.2 Linking and drift detection
    - Implement: evidence matching with confidences 0.90 (path), 0.75 (qualname), 0.70 (unique name), 0.50 (heading), the innermost-section rule (D1), the uniqueness rules (D2), the excerpt window, link ordering, and no links from steering. Implement `UNSPECIFIED_CODE` and `UNIMPLEMENTED_SPEC` drift using Core_Implementation_File and Referenced_Task_Path rules, placeholder filtering, ambiguous-suffix handling, dedup, and ordering. Use `graph_engine.build_graph` data only; add no parsing of source.
    - Validate: unit tests 4, 5, and 6 (task 11.2).
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 16.3, 16.7_
  - [x] 5.3 Git history and `build_provenance`
    - Implement: the single `git log -n 20 --pretty=format:%h|%s --name-only` call with an argument list, `shell=False`, the scrubbed `_GIT_ENV`, a 10-second kill timer, and a 1,048,576-byte output cap. Parse Commit_Records per Snapshot file (newest first, capped at 20). Any failure returns an empty mapping. `build_provenance(snapshot, repo_root=None)` returns a `ProvenanceReport` and raises `SpecGrounderError` for an invalid Snapshot or unreadable root before building anything.
    - Validate: unit test 7 (task 11.2) uses a temporary git repo and a directory without `.git`, and compares two runs for equality.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 16.6_

- [x] 6. `backend/engines/topology.py`
  - [x] 6.1 Directory roles and boundary metrics
    - Implement: derived sets `F`, `D`, `E` (dropping invalid, call, and self edges), role assignment by name then by contents, entry-point detection, and the four `boundary_metrics` formulas with zero-denominator handling. Values are rounded to 4 places.
    - Validate: unit tests 11 and 12 (task 11.3) check a hand-computed fixture and the empty and unknown-edge cases.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.9, 8.10_
  - [x] 6.2 Pattern scoring, classification, evidence, and `profile_topology`
    - Implement: the N, I, and D signals for the five patterns, the naming precondition, ordering by `(-score, name)`, the 0.3 threshold fallback to `Flat / Script`, the confidence caps (0.5 for a single supporting signal, 0.6 for a margin under 0.1), the evidence list (sorted, at most 200 characters each), and the empty-Snapshot short circuit. The function is pure, with no I/O, and returns `TopologyProfile(repo_id=snapshot.repo_id, ...)`.
    - Validate: unit tests 8, 9, 10, and 12 (task 11.3) plus property test 4 (task 12.4).
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 8.8, 8.11, 16.3, 16.6_

- [x] 7. `backend/engines/llm_router.py`
  - [x] 7.1 Settings, errors, and the `LLMRouter` shell
    - Implement: `LLMRouterError` (provider and category), `LLMConfigError`, `LLMSettings` (pydantic-settings, `env_file=None`, `SecretStr` key, `.env.example` defaults), the `StructuredLLM` protocol, and `LLMRouter.__init__` validation for provider name, blank Gemini key, and empty model or base-URL settings. Add the dispatch in `generate_structured`. SDK imports happen lazily inside the provider paths. Never log keys or prompts.
    - Validate: unit test 14 (task 11.4) covers provider selection, invalid `LLM_PROVIDER`, the missing key not being echoed, and `sys.modules` showing no SDK imported for `mock`.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.8, 9.9, 9.10, 9.11, 10.10, 16.1_
  - [x] 7.2 Deterministic mock provider
    - Implement: the mock builders for `L1SyntaxExplanation`, `L2FlowExplanation`, and `L3ArchitectureExplanation`. They parse the `CONTEXT_SLICE_JSON:` marker, use only values from the slice, embed `ast_hash[:12]`, and use no randomness, clock, or network. An unsupported model raises `LLMRouterError(category="validation")`.
    - Validate: unit test 13 (task 11.4) checks equal output across calls, schema validity, and rejection of an unsupported model.
    - _Requirements: 9.6, 10.1, 10.2, 10.3, 16.6_
  - [x] 7.3 Gemini and Ollama providers
    - Implement: the Gemini path (`client.models.generate_content` with JSON mime type and `response_schema`, one attempt, 60-second timeout) and the Ollama path (`openai.AsyncOpenAI` with `base_url`, `api_key="ollama"`, a JSON-schema instruction, one retry with the same prompts, a separate 60-second timeout per attempt). Map SDK errors by class name to `timeout`, `connection`, `provider`, or `validation`. Messages contain no prompt text or key.
    - Validate: unit test 15 (task 11.4) uses fake clients injected with `monkeypatch`: Ollama is called twice then fails, Gemini is called once, and error text has no prompt or key. No real network call is made.
    - _Requirements: 9.6, 9.7, 9.8, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

- [x] 8. `backend/engines/cache_store.py`
  - [x] 8.1 Tables, settings, and put/get for all four object types
    - Implement: `CacheStoreError`, `CacheSettings` (empty value maps to `./data/stupid_code.db`), the four SQLModel tables with the unique constraint on `(repo_id, ast_hash, target_id, lens)`, `CacheStore` with `:memory:` (StaticPool), file paths (parent directory creation and WAL), one session per operation with commit and rollback, replace-on-write, and the `put_*` and `get_*` methods. `put_provenance` and `put_topology` key rows by the object's own `repo_id`.
    - Validate: unit tests 16 and 18 (task 11.5).
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.10, 11.12, 11.13_
  - [x] 8.2 Read validation, corrupt-row handling, and error wrapping
    - Implement: validate payloads with `model_validate_json` on read, delete a row that fails validation and return a miss, wrap `SQLAlchemyError` and `OSError` as `CacheStoreError` (class name and path only), and add `close`, `__enter__`, and `__exit__`.
    - Validate: unit tests 17 and 18 (task 11.5) cover miss after an `ast_hash` change, lens isolation, corrupt row deleted, and an unwritable path raising `CacheStoreError`.
    - _Requirements: 11.7, 11.8, 11.9, 11.11, 11.13_

- [x] 9. Checkpoint - Engines before pedagogy
  - Run the full suite and `ruff check` on the new engine files. Ensure all tests pass, ask the user if questions arise.

- [x] 10. `backend/engines/pedagogy.py`
  - [x] 10.1 Errors, Target hash, and Context_Slice with 1-hop slicing
    - Implement: `PedagogyErrorKind`, `PedagogyError`, the frozen `ContextSlice`, and `canonical_json`. Compute `Target_AST_Hash` (symbol hash for L1 and L2, the sha256 digest for L3). Build the slice for L1 and L2 using `graph_engine.build_graph` and `trace_blast_radius(..., max_depth=1)` for direct callers and callees only, at most 10 Spec_Links, only the Target's `dsa_signals`, the topology profile, and commits for the Target file. Read only the Target file under the repo root (safe read, 524,288-byte limit, 400-line cap). Build the L3 slice from topology, drift items, up to 20 Spec_Links, and up to 200 eligible paths. Resolve targets; unknown targets raise `UNKNOWN_TARGET`.
    - Validate: unit tests 19, 20, and 23 (task 11.6) check slice contents, depth-1 callers and callees, and no other file's content.
    - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6, 12.11, 12.12, 12.13, 12.15, 16.3, 16.6_
  - [x] 10.2 Lens normalization, DSA complexity table, and degraded L2
    - Implement: L1 checks (annotation line range, `line_start <= line_end`, `construct` substring of the source lines, at least one annotation, offending index in the error). L2 normalization (overwrite callers and callees, DSA cards from the Target's signals only, complexity from the fixed table with `not determined` fallback, `why_used_here` accepted only when it contains signal evidence, steps renumbered 1..n, at most 30). L3 checks (evidence membership, 1 to 20 entries, 1 to 3 alternatives, low-confidence prefix, `spec_rationale` null when there are no links). Add the degraded L2 builder with `llm_content_available=False`.
    - Validate: unit tests 19 to 22 (task 11.6) plus property tests 3 and 4 (tasks 12.3 and 12.4).
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_
  - [x] 10.3 `PedagogyEngine.explain_target` flow and wiring
    - Implement: `PedagogyEngine(cache, router, llm_timeout_seconds=30.0)` and `explain_target(repo_id, target_id, lens, force_refresh=False)`. Order: load Snapshot, report, and profile (`MISSING_DATA` naming each missing item), resolve the Target, compute the hash, check the cache (a hit returns `cached=True` with zero router calls and no write), build the slice, call the router under `asyncio.wait_for`, normalize, build the envelope with only the matching tier, then `put_explanation`. L1 and L3 router failures raise `LLM_FAILURE`; L2 returns the degraded result without persisting it.
    - Validate: unit tests 19 to 23 (task 11.6) and property tests 1 and 2 (tasks 12.1 and 12.2).
    - _Requirements: 12.1, 12.2, 12.3, 12.7, 12.8, 12.9, 12.10, 12.13, 12.14, 12.15, 13.7, 14.10, 15.9_

- [x] 11. Unit tests in `backend/tests/unit/test_spec_topology_pedagogy.py`
  - [x] 11.1 Create the file, helpers, and the model tests (tests 1 and 2)
    - Implement: module-level `pytestmark = pytest.mark.usefixtures("offline_guard")`, helper builders (`make_snapshot`, `write_repo`, `CountingRouter`), and tests 1 and 2: valid construction from the exact field lists, field order, `llm_content_available` default, nullable fields, round trip of every new model, rejection of extra fields, mutation, NaN, infinity, out-of-range values, bad line numbers, blank text, and a wrong envelope tier, plus acceptance of the boundary values.
    - Validate: `pytest backend/tests/unit/test_spec_topology_pedagogy.py -q` passes.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.13, 17.2, 17.4_
  - [x] 11.2 Spec grounder tests (tests 3 to 7)
    - Implement: discovery and size limits, grounded link confidence order and excerpt length, `UNSPECIFIED_CODE`, `UNIMPLEMENTED_SPEC` with all ignore rules, and git history in a `tmp_path` repo (with `git init`, local `user.name` and `user.email`) plus a directory with no `.git` and equal reports from two runs.
    - Validate: all pass offline; git tests touch only the temporary repo.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8, 3.1, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.9, 5.1, 5.2, 5.4, 5.7, 6.4, 17.4, 17.9_
  - [x] 11.3 Topology tests (tests 8 to 12)
    - Implement: hexagonal fixture (score 1.0 on a domain, engines, api layout, and `repo_id` match), flat fixture and the 0.5 and 0.6 confidence caps, determinism with shuffled files and edges, hand-computed roles and metrics with sorted evidence of at most 200 characters, and the empty Snapshot and unknown-edge cases.
    - Validate: all pass; values match hand calculations.
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.8, 7.9, 7.10, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8, 8.9, 8.10, 8.11, 17.4_
  - [x] 11.4 Router tests (tests 13 to 15)
    - Implement: mock determinism and supported and unsupported models, provider selection and configuration errors (missing Gemini key not echoed, no SDK in `sys.modules` for `mock`), and fake-client invalid-response behavior (Ollama two calls, Gemini one call, no prompt or key in the error).
    - Validate: all pass with no network access.
    - _Requirements: 9.2, 9.4, 9.5, 9.7, 9.8, 9.10, 9.11, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 17.4, 17.6_
  - [x] 11.5 Cache tests (tests 16 to 18)
    - Implement: miss, hit, replace on the same key, one row per key, and `put_topology` and `put_provenance` keyed by their own `repo_id`; miss after an `ast_hash` change and lens isolation; `:memory:`, a file path with a missing parent directory and WAL, a corrupt row deleted and treated as a miss, and an unwritable path raising `CacheStoreError`.
    - Validate: all pass using `tmp_path` only.
    - _Requirements: 11.1, 11.2, 11.3, 11.5, 11.6, 11.7, 11.8, 11.9, 11.11, 11.13, 17.4_
  - [x] 11.6 Pedagogy tests (tests 19 to 23)
    - Implement as `async def` tests: L1 valid and rejection of a bad range or non-substring `construct` with the index; L2 callers and callees equal to depth-1 Graph_Engine sets, DSA cards from real signals, the `not determined` fallback, and empty signals; degraded L2 with nothing stored; L3 pattern, evidence membership, alternatives, low-confidence text, null `spec_rationale`, and a rejected unknown path; cache hit with zero router calls and an unchanged row, force refresh with exactly one new call, and precondition errors with no call and no write.
    - Validate: all pass; `CountingRouter` counts confirm the call numbers.
    - _Requirements: 12.3, 12.4, 12.7, 12.8, 12.9, 12.13, 12.14, 12.15, 13.1, 13.4, 14.1, 14.3, 14.4, 14.7, 14.9, 14.10, 15.1, 15.2, 15.3, 15.6, 15.7, 15.8, 17.4_
  - [x] 11.7 Layering test (test 24) and size check
    - Implement: an `ast`-based test that no new engine or `models.py` imports `fastapi` or `mcp`, `models.py` imports only allowed modules, the new modules have no import cycle, and `exec`, `eval`, and `subprocess` do not appear outside `spec_grounder`. Then confirm the file has 20 to 25 test functions (24 planned) and fewer than 600 lines.
    - Validate: the test passes; `grep -c "^def test_\|^async def test_"` and `wc -l` confirm the count and length.
    - _Requirements: 1.12, 16.1, 16.2, 16.4, 17.2_

- [x] 12. Hypothesis property tests in `backend/tests/properties/test_pedagogy_properties.py`
  - [x] 12.1 Create the file, generators, and Property 1
    - Implement: module-level `offline_guard` usage, a repository generator (1 to 3 files, 1 to 4 symbols, hex `ast_hash`, source in a per-example `tempfile.TemporaryDirectory`, call edges, 0 to 3 DSASignals), and one synchronous `@given` test calling `asyncio.run(...)` once, with `@settings(max_examples=100, deadline=timedelta(milliseconds=500))`.
    - **Property 1: Explanation caching is idempotent**
    - **Validates: Requirements 12.7, 12.8, 17.5.1**
    - Validate: passes; tagged with the `# Feature: 02-spec-topology-pedagogy, Property 1: ...` comment.
    - _Requirements: 12.7, 12.8, 17.3, 17.5, 17.9_
  - [x] 12.2 Property 2
    - Implement: one `@given` test that explains under hash `h1`, replaces the stored Snapshot with `h2`, and checks `cached == False`, one extra router call, `ast_hash == h2`, and different content.
    - **Property 2: A changed AST hash is a cache miss**
    - **Validates: Requirements 12.8, 12.9, 17.5.2**
    - Validate: passes with the same settings limits.
    - _Requirements: 12.8, 12.9, 17.5_
  - [x] 12.3 Property 3
    - Implement: one `@given` test over Snapshots where the Target has no signals and other symbols have any, asserting `dsa_cards == []`; for Targets with signals, each card matches a signal of that Target.
    - **Property 3: DSA cards come only from the Target's own signals**
    - **Validates: Requirements 14.3, 14.7, 14.8, 17.5.3**
    - Validate: passes with the same settings limits.
    - _Requirements: 14.3, 14.7, 14.8, 17.5_
  - [x] 12.4 Property 4
    - Implement: one `@given` test over layouts including empty, isolated-node, self-edge, unknown-path, duplicate-edge, and no-edge cases, asserting `profile_topology` does not raise and `cross_folder_import_ratio`, `domain_isolation_score`, and `confidence` are within 0.0 to 1.0.
    - **Property 4: Boundary ratios stay within 0 and 1**
    - **Validates: Requirements 7.7, 8.7, 17.5.4**
    - Validate: passes; then confirm the file contains exactly four `@given` tests (`grep -c "@given"` returns 4).
    - _Requirements: 7.7, 8.7, 17.3, 17.5_

- [x] 13. Checkpoint - New tests
  - Run both new test files by themselves and confirm they finish within 60 seconds. Ensure all tests pass, ask the user if questions arise.

- [x] 14. Full verification
  - [x] 14.1 Full pytest run from the repository root
    - Implement: run `pytest` and compare to task 1.1. Fix only new code on failure. Do not weaken, delete, skip, or xfail any existing test.
    - Validate: zero failures and zero errors; the total equals the baseline plus the new tests (24 unit and 4 property).
    - _Requirements: 16.5, 17.8, 17.11_
  - [x] 14.2 Ruff check and format check
    - Implement: run `ruff check` and `ruff format --check` with the repository config. Apply `ruff format` and fixes to new files only. If anything changes, re-run the full `pytest`.
    - Validate: both commands exit 0 with zero violations.
    - _Requirements: 16.9_

- [x] 15. Final report
  - [x] 15.1 Report the results in the final message
    - Implement: no code. Report the baseline count and the final count, the number of unit tests and file length, confirmation of exactly four property tests, the `ruff` results, the list of files changed (confirming no Phase 1 file was modified), the single additive field `llm_content_available` (D5), and any deviation or open question.
    - Validate: every figure comes from the command output of tasks 1.1, 11.7, 12.4, 14.1, and 14.2.
    - _Requirements: 16.5, 17.8_

## Notes

- All test sub-tasks are required, not optional, because the user requires the unit and property tests.
- Each requirement is referenced by number for traceability. Property tests are annotated with their design property number.
- Phase 3 work (FSRS, Study Mode, MCP expansion, UI) is out of scope.
- Do not run long-running watchers; use `pytest` single runs.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2"] },
    { "id": 3, "tasks": ["5.1", "6.1", "7.1", "8.1"] },
    { "id": 4, "tasks": ["5.2", "6.2", "7.2", "8.2"] },
    { "id": 5, "tasks": ["5.3", "7.3"] },
    { "id": 6, "tasks": ["10.1"] },
    { "id": 7, "tasks": ["10.2"] },
    { "id": 8, "tasks": ["10.3"] },
    { "id": 9, "tasks": ["11.1", "12.1"] },
    { "id": 10, "tasks": ["11.2", "12.2"] },
    { "id": 11, "tasks": ["11.3", "12.3"] },
    { "id": 12, "tasks": ["11.4", "12.4"] },
    { "id": 13, "tasks": ["11.5"] },
    { "id": 14, "tasks": ["11.6"] },
    { "id": 15, "tasks": ["11.7"] },
    { "id": 16, "tasks": ["14.1"] },
    { "id": 17, "tasks": ["14.2"] },
    { "id": 18, "tasks": ["15.1"] }
  ]
}
```
