# Implementation Report: Spec #03 Mastery and Kiro-Native Integration

All numbers in section G were produced by commands run while writing this report. Claims about code were checked by reading the code or running it.

## A. Spec artifacts

Directory `.kiro/specs/03-mastery-and-kiro-native/`:

| File | Purpose |
|---|---|
| `requirements.md` | 24 requirements, including the three user-confirmed decisions (clone depth D1, `root_path` ".", Property 2 stop rule) |
| `design.md` | Architecture, decisions D1 to D14, open risks R1 to R8, Phase 1/2 change log |
| `tasks.md` | 20 tasks with a dependency graph |
| `tasks.meta.json` | Task metadata |
| `baseline.md` | Task 1 measurements (770 tests, ruff state, git HEAD `c0f8994`), design mismatches M1 to M12, the approved Phase 1 scope-test exception |
| `phase12-hashes.txt` | `git hash-object` snapshot of Phase 1 and 2 files |
| `verification.md` | Integration, manifest, full-suite, and backward-compatibility results from tasks 17 and 18 |
| `implementation-report.md` | This report |

## B. Implementation summary

**Domain models** (modified): `backend/domain/models.py`, append only (153 lines added, 0 removed). Adds `MasteryState`, `ModuleMastery`, `SocraticQuestion`, `SocraticCheck`, `SocraticAnswerItem`, `SocraticVerdict`, `ComprehensionVitals`, `SocraticGrade`.

**Mastery engine** (new): `backend/engines/mastery.py` (state machine, schedule, Study Mode, question generation, grading, vitals). Also new: `backend/engines/analysis_pipeline.py` (ingest, parse, snapshot, provenance, topology, persist, `ensure_analysis`, repo-id derivation) and `backend/engines/dissection.py` (explain plus blast radius plus view recording).

**Cache/database** (modified): `backend/engines/cache_store.py`, additive (268 lines added, 1 import line widened). Adds `StudyModeRow`, `MasteryRow`, `RepositoryRow`, `RepositoryRecord`, `CacheTransaction`, `CacheStore.transact`, `CacheStore.read`. Also modified: `backend/engines/llm_router.py` (46 lines added: the `SocraticGrade` mock builder and its registry entry).

**API** (new unless noted): `backend/api/main.py` (modified, now `create_app` plus `app = create_app()`; `/health` unchanged), `settings.py`, `errors.py`, `rate_limit.py`, `crew_signature.py`, `services.py`, `schemas.py`, `routes/repos.py`, `routes/autopsy.py`, `routes/mastery.py`, `routes/crew.py`. Also modified: `.env.example` (5 lines), `.gitignore` (1 line, `data/repos/`), `backend/pyproject.toml` (`mcp>=2.3,<3`).

**MCP** (new): `backend/mcp_server/server.py` with five tools.

**Kiro IDE configuration** (new): `.kiro/settings/mcp.json` (server `stupid-code`, `.venv/bin/python backend/mcp_server/server.py`).

**Kiro Power** (new): `power/plugin.json`, `power/mcp.json`, `power/skills/code-autopsy/SKILL.md`.

**Kiro Crew App** (new): `crew/app.json`, `crew/agents/{autopsy-surgeon,socratic-examiner}.{json,md}`, `crew/skills/code-autopsy/SKILL.md`, `crew/ui/study-mode-control.mjs`.

**Agent hooks** (new): `.kiro/hooks/verify-engines.json` (PostFileSave, command), `.kiro/hooks/anti-vibe-coding.json` (PostToolUse, agent prompt).

**Tests** (new unless noted): `backend/tests/unit/test_mastery_api_mcp.py` (24 tests, 599 lines), `backend/tests/properties/test_mastery_properties.py` (4 Hypothesis tests), `backend/tests/mastery_support.py` (shared helpers, not a test file). Modified: `backend/tests/unit/test_ast_graph_engine.py` (approved exception, see I.1).

**Scripts** (new): `scripts/check_study_mode_parity.py`.

## C. Mastery behavior

Verified in `backend/engines/mastery.py` and by unit tests 2 and 3 and Property 1.

- **States:** `UNAUDITED`, `DISSECTED`, `MASTERED`, `STALE`. New records start `UNAUDITED`.
- **Allowed transitions** (`check_transition`): none to `UNAUDITED`; same state to itself; `UNAUDITED` to `DISSECTED`; any state to `MASTERED`; `MASTERED` to `STALE`; `DISSECTED` to `UNAUDITED`. Any other pair raises `INVALID_TRANSITION` and the transaction rolls back.
- **Views:** only with Study Mode on, `UNAUDITED` becomes `DISSECTED`. Other states do not change. Only L1 and L2 lenses record views; L3 does not.
- **AST-change rules** (`apply_hash_change`, run by `register_snapshot` on re-ingest): `MASTERED` becomes `STALE` with `repetitions=0`, `interval_days=0`, `next_review_at=None`; `DISSECTED` becomes `UNAUDITED`; `UNAUDITED` and `STALE` keep their state and take the new hash. Same hash writes nothing. Records for symbols that left the Snapshot are retained.
- **Review schedule** (`apply_pass`): `repetitions + 1`; interval 1 day, then 6, then `round(previous * ease_factor)`. With ease fixed at 2.5 the sequence is 1, 6, 15, 38, 95 (Python rounds 37.5 to 38). `ease_factor` stays 2.5. `next_review_at` is the Clock time plus the interval, truncated to seconds. A date past `9999-12-31T23:59:59Z` or an overflow raises `REVIEW_DATE_OUT_OF_RANGE` and writes nothing.
- **Threshold:** `PASS_THRESHOLD = 0.7`; `passed = grade.score >= 0.7`. Boundary tested: 0.69 fails with the record unchanged, 0.70 passes (unit test 9).
- **Grading is by the LLM only.** The router returns a `SocraticGrade` (score and feedback); the engine, not the LLM, decides `passed` and every transition. The check is built without any LLM call. Grading runs under a 30-second timeout. A router error, timeout, invalid output, or wrong type becomes `GRADING_UNAVAILABLE` with a fixed message and no record change (unit test 10). A fail writes nothing. A pass writes in one transaction.
- **Requirement 14.5 versus 14.12.** The two criteria conflict for one case: a failed check on a record that is already `MASTERED`. 14.5 says the verdict carries the prior record values (so `MASTERED` with the prior `next_review_at`). 14.12 says never return `MASTERED` with a non-null `next_review_at` when `passed` is false. The implementation follows 14.5: the verdict is built from the stored record (`mastery.py`, step 8 of `submit_answers`). Unit test 3 asserts that a failing grade on a `MASTERED` record returns `MASTERED` and does not demote it. For a record that was not `MASTERED`, a fail returns its prior state with `next_review_at=None`, which satisfies both criteria. See I.5.

## D. API summary

"Covered by" names the tests in `backend/tests/unit/test_mastery_api_mcp.py` (all through `TestClient`, mock provider, temporary database, git double for GitHub). Status is what I verified by running them in the 798-test run.

| Endpoint | Purpose | Covered by | Status |
|---|---|---|---|
| `GET /health` | Phase 1 health | Phase 1 `test_health.py` (unchanged, passes) | Verified |
| `POST /api/repos/ingest` | Ingest by local `path` or GitHub `url`; limits, 403 when `ALLOW_LOCAL_INGEST` is false, per-IP rate limit for `url` | `test_ingest_validation_truncation_and_local_ingest_disabled`, `test_github_rate_limit_with_controlled_clock`, `test_error_envelope_shape_on_non_2xx` | Verified (400, 422 `invalid_limit`, `truncated`, 403, 429 with `Retry-After`) |
| `GET /api/repos` | List stored repositories with Study Mode | `test_list_snapshot_and_explain_reads` | Verified |
| `GET /api/repos/{repo_id}/snapshot` | Stored Snapshot, provenance, topology; `root_path` replaced by `"."` | `test_list_snapshot_and_explain_reads` | Verified |
| `POST /api/repos/{repo_id}/explain` | L1/L2/L3 explanation plus blast radius; records a view when Study Mode is on | `test_list_snapshot_and_explain_reads`, `test_error_envelope_shape_on_non_2xx` | Verified for the success path and the envelope shape. The L1/L3 `llm_unavailable` 503 path is not asserted by a dedicated test; the error mapping was checked by reading `routes/autopsy.py` only |
| `GET /api/repos/{repo_id}/vitals` | `ComprehensionVitals`, read only | `test_study_mode_toggle_and_read_only_vitals`, `test_vitals_counts_percentage_and_file_states` (engine) | Verified |
| `POST /api/repos/{repo_id}/study-mode` | Set Study Mode, idempotent, strict boolean | `test_study_mode_toggle_and_read_only_vitals` | Verified |
| `POST /api/repos/{repo_id}/socratic/start` | Return 1 or 2 questions, empty `expected_concepts`, no LLM call | `test_socratic_start_and_submit_endpoints` | Verified |
| `POST /api/repos/{repo_id}/socratic/submit` | Grade answers, return `SocraticVerdict`, persist on pass | `test_socratic_start_and_submit_endpoints`, `test_failed_or_invalid_grading_grants_no_mastery` (engine) | Verified (precedence and every error code were not each tested; see I) |
| `POST /api/apps/stupid-code/crew` | Crew webhook: `autopsy_file`, `explain_folder_architecture`, `study_mode`; signature check when `KIRO_CREW_SECRET` is set | `test_crew_file_menu_actions`, `test_crew_study_mode_and_signatures` | Verified against the design's assumed body and signing rules; not verified against a real Crew host (see F, I) |

Signature cases tested: valid `X-Kiro-Signature`, valid and stale `X-Crew-Proxy` under a controlled Clock, invalid values, both headers, neither header, unset secret, repeated header and naive Clock through `verify_crew_signature`.

## E. MCP summary

Server: `backend/mcp_server/server.py`, SDK `mcp` 2.3.0, `MCPServer`, stdio. Exactly five tools.

| Tool | Behavior | Tested by |
|---|---|---|
| `dissect_symbol` | Analyze (or reuse), then explain a symbol with a lens | `test_mcp_tools_succeed_on_valid_input`, `test_mcp_tools_fail_cleanly_on_invalid_input`, Property 4 |
| `trace_blast_radius` | Callers and callees to a depth of 0 to 20 | same three tests; `max_depth` `True` and `21` rejected in the invalid-input test |
| `analyze_folder_architecture` | Stored topology, zero LLM calls | same three tests |
| `check_spec_drift` | Drift items and `has_kiro_specs` from provenance | same three tests |
| `get_comprehension_vitals` | Vitals for an analyzed repo; `repo_not_analyzed` otherwise; no write | same three tests, plus the parity script |

Evidence:
- In-process: `test_mcp_tools_succeed_on_valid_input` asserts `list_tools` returns exactly the five names and each result is JSON-serializable with `ok: true`. `test_mcp_tools_fail_cleanly_on_invalid_input` covers `invalid_repo_path`, `unknown_target`, `invalid_lens`, `invalid_max_depth`, `repo_not_analyzed`. These tests use the in-process server, not a subprocess.
- Real subprocess: not part of the pytest suite. It was checked in task 11.3 (throwaway), in task 18.2 (`list_tools()` over stdio returned exactly the five names, recorded in `verification.md`), and permanently by `scripts/check_study_mode_parity.py`, which starts the server with `StdioServerParameters` and calls `get_comprehension_vitals` (rerun now: `PARITY OK`, exit 0). The launch failure with a missing `.venv/bin/python` is covered by `test_manifests_hooks_and_launch_config`.

## F. Kiro-native integrations

| Item | Status | Verified | Assumed |
|---|---|---|---|
| MCP config `.kiro/settings/mcp.json` | Present; parses | JSON parses; the same command starts the server in the parity script | That Kiro starts it from the workspace root (R3) |
| Power `power/` | Present; `plugin.json`, `mcp.json`, skill | JSON parses; skill front matter and 200-line limit checked in unit test 21 | That the Agent Plugins 1.0.0 manifest is what the installed IDE accepts; not installed in a real IDE |
| Crew App `crew/app.json` | Present | JSON parses; declared paths exist and are relative (unit test 21) | The manifest field set, and that the host reads it as written |
| Crew agents (`autopsy-surgeon`, `socratic-examiner`) and skill | Present | Files exist, JSON parses, prompts reference `file://./...md` | Host loading behavior; that the examiner agent can reach the REST API (R5) |
| Crew gateway and host request body | Webhook accepts `{action, repo_id, path|enabled}` | Our own validation and tests | The host's real body, how the gateway reaches the API, and its signing details (R1) |
| Session control `crew/ui/study-mode-control.mjs` | Present, 100 lines or fewer, exports `mount(element, context)` returning an unmount function | File read: it posts `{action: "study_mode", repo_id, enabled}` to the endpoint. No JS test was run | The export shape and the `context` fields (`repoId`, `studyModeEnabled`) are assumptions, noted in the file header. Not executed in a browser or Crew host |
| Hook `verify-engines.json` | PostFileSave, command `.venv/bin/python -m pytest -q`, matcher `(^|.*/)backend/engines/[^/]+\.py$` | Matcher table tested with `re.search` and `re.fullmatch` in unit test 21; no ignore rule hides the file | That the IDE passes a path this regex matches. Where the PostFileSave output appears is unverified (R2) |
| Hook `anti-vibe-coding.json` | PostToolUse, agent prompt, matcher `^(fs_write\|fs_append\|str_replace\|smart_relocate\|semantic_rename)$` | Prompt literals (`get_comprehension_vitals`, `study_mode_enabled`, `dissect_symbol`, `25`) tested; the matcher accepts those five names and rejects read-only tools | The tool names come from this runtime's tool list. The installed IDE's tool IDs and whether it matches by regex were not checked (R2) |

No hook or manifest was run inside a real Kiro IDE or Crew host. That manual check was not done.

## G. Test results

Fresh runs while writing this report, from `/Users/binayakroy/stupid-code`:

- Baseline_Count (task 1.2, before any change): `770 passed in 17.29s`.
- New unit tests: 24. `LLM_PROVIDER=mock .venv/bin/python -m pytest -q backend/tests/unit/test_mastery_api_mcp.py` gave `24 passed in 1.08s`. File has 599 lines.
- New property tests: 4. `... backend/tests/properties/test_mastery_properties.py` gave `4 passed in 2.19s`.
- Full suite: `LLM_PROVIDER=mock .venv/bin/python -m pytest -q -rs` gave `798 passed in 19.93s`. That equals 770 + 24 + 4. 0 failed, 0 errors, 0 skipped (`-rs` printed no skip lines). `verification.md` also records 0 xfailed.
- `.venv/bin/ruff check backend scripts`: `All checks passed!`
- `.venv/bin/ruff format --check backend scripts`: `36 files already formatted`.

## H. Integration verification

Shared logic and persistence:
- The REST routes, the Crew webhook, and the MCP tools are thin wrappers. Transitions, scheduling, grading, and vitals live in `MasteryEngine`; analysis in `analysis_pipeline`; explanation plus blast radius in `DissectionService`. Persistence goes through one `CacheStore` (SQLite, path from `STUPID_CODE_DB_PATH`). The layering test checks that the three new engines import no `fastapi`, `starlette`, `mcp`, `backend.api`, or `backend.mcp_server` and that the engine import graph has no cycle.
- The Power and Crew App reach the same engines through the MCP server (`mcp.json`) and the Crew webhook. The `socratic-examiner` agent grades through the REST endpoints.
- Shared-cache tests: the unit tests inject one `CacheStore` into both the API `Services` and the MCP `ToolServices` (`make_services`, `tool_services` in `mastery_support.py`).
- Both processes must use the same database file. The default path is relative to the working directory (R4).

Parity script output (rerun now, exit 0):

```
[set True] API study_mode_enabled=True
[set True] MCP study_mode_enabled=True
[set False] API study_mode_enabled=False
[set False] MCP study_mode_enabled=False
PARITY OK
```

The script ingests a temporary repository through the API, sets Study Mode through the API, and reads the value through the REST vitals endpoint and through a real stdio MCP subprocess sharing a temporary database file.

## I. Limitations

Unmet requirements (also the basis for section J):

1. **Requirement 24.3 and 21.9 (Phase 1/2 test files byte-identical):** one Phase 1 test file, `backend/tests/unit/test_ast_graph_engine.py`, changed (+18 / -2). Its `test_no_new_python_files_outside_spec_scope` parametrize list now allows the new `backend/api` and `backend/mcp_server` files, plus one comment line. This is a user-approved exception (approved in the session) recorded in `baseline.md`. No test was skipped, weakened, or marked xfail.
2. **Requirement 14.12:** a failed check on a record that is already `MASTERED` returns `MASTERED` with its non-null `next_review_at`, because 14.5 requires the prior values. The two criteria cannot both hold in that case, and the implementation follows 14.5 (see C). The user approved following 14.5 (an already-MASTERED module stays MASTERED).

Other known limitations and decisions:

3. **Clone depth (D1):** the clone uses the Phase 1 `--depth 30`, not depth 1. Requirement 23.6 now states depth 30 (user-confirmed), so this is not an unmet item. The original design wording of depth 1 was superseded.
4. **Snapshot `root_path`:** `GET /snapshot` replaces `root_path` with `"."` (confirmed D5). The stored value is unchanged.
5. **Property 2 stops at pass 17** (D12, Requirement 22.3). Passes beyond 16 are never exercised.
6. **Crew host unknowns (R1):** the host request body, the session-control export shape and `context` fields, the `X-Crew-Proxy` signing details (hex encoding, Unix seconds, upper-case method, path-plus-query form), and replay protection inside the 60-second window are undocumented. We follow the design's assumptions. A replayed signed request inside 60 seconds is accepted.
7. **Hook assumptions (R2):** tool names in the anti-vibe matcher come from this runtime. Whether the IDE matches by regex, and where PostFileSave output is shown, are unverified. The 60-second hook default must cover the suite (about 20 seconds now).
8. **`.venv/bin/python` is a relative command (R3):** it depends on the process working directory. The default database path has the same property (R4).
9. **Concurrent ingest (R7):** no per-`repo_id` lock was added. Two simultaneous ingests of one repository can return 500 `storage_error`.
10. **L2 degraded envelope:** when the router fails, an L2 explanation returns a degraded envelope (`llm_content_available=false`, not cached) rather than an error. So Crew `autopsy_file` and the default MCP lens do not return `llm_unavailable`. A view is still recorded when Study Mode is on. Only L1 and L3 return 503.
11. **Untracked long ids (R6/D7):** symbols whose id exceeds 500 characters are not tracked for mastery.
12. **Session control** cannot read the stored Study Mode value on mount. It only uses `context.studyModeEnabled` if the host provides it, and otherwise starts unchecked.
13. **Unit test file size:** `test_mastery_api_mcp.py` is 599 lines, one under the 600 limit. Little room remains.
14. **Property 4** only asserts that `json.dumps` works and that `result["ok"]` is a `bool`.
15. **`.kiro/settings/mcp.json` was created by the user.** A permission rule prevented the agent from writing under `.kiro/settings`. The file content matches the task.
16. **Ruff and format:** both pass for `backend` and `scripts`. The task named only `backend`; I also ran `scripts`.
17. **`mastery_support.py` carries assertion-adjacent helpers** (`run_check`, `tiny_states`, `ingest_path`, and similar). It is a helper module, not a test file, but test logic is split between it and the test file.
18. **Coverage gaps in tests:** the Requirement 14 error-precedence order, and the 503 `llm_unavailable` and 502 `invalid_llm_output` explain paths, are not each tested end to end. The code maps them as designed.
19. **MCP real-subprocess check is not a pytest test.** It runs in the parity script and was run manually in tasks 11.3 and 18.2.
20. **Manual checks not done:** no run in a real Kiro IDE or Crew host (R1, R2).

## J. Completion status

**COMPLETE**

Justification: 798 tests pass (770 baseline + 24 unit + 4 property), ruff is clean, the integration script exits 0, all deliverables exist, and every manifest parses.

Approved deviations (both confirmed by the user):

- Requirement 24.3 (and 21.9): the Phase 1 allowlist test `test_no_new_python_files_outside_spec_scope` in `backend/tests/unit/test_ast_graph_engine.py` was updated to allow the new Spec #03 files. No test was skipped, weakened, or marked xfail.
- Requirement 14.12 vs 14.5: a failed check on an already `MASTERED` record leaves it `MASTERED` with its existing `next_review_at`, following 14.5.

Not verified (assumptions, listed in section I): the Kiro IDE and Crew host integrations (R1, R2) have not been run in a real host.
