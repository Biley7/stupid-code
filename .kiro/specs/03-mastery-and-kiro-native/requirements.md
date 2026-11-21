# Requirements Document

## Introduction

Spec #03 turns Stupid Code (Code Autopsy Edition) from a deterministic analysis and explanation engine into an interactive comprehension and mastery system. It builds on completed Phase 1 (`01-ast-graph-engine`) and Phase 2 (`02-spec-topology-pedagogy`) and adds seven areas: mastery domain models, a toggleable Study Mode with a mastery and review-interval engine, a FastAPI REST API, a FastMCP server with workspace MCP configuration, a Kiro Power and a Kiro Crew App package, Kiro agent hooks, and the unit and Hypothesis property tests that verify them.

Analysis stays deterministic wherever possible. The LLM explains and grades but never replaces a deterministic engine, and never decides a mastery state: the Mastery_Engine decides every state transition from a validated score. Study Mode is optional. With Study Mode off (Autopsy Mode) the product stays fast and frictionless. Every surface (REST API, MCP server, Power, Crew App, hooks) calls the same shared backend engines and reads the same persisted Study Mode state.

Layering follows `.kiro/steering/architecture.md`: `domain` depends on nothing in this project, `engines` use `domain`, and the delivery layers `api` and `mcp_server` call `engines`. Analyzed repositories are untrusted and no analyzed code is executed or imported.

### Phase 1 and Phase 2 Preservation (Scope Lock)

All Phase 1 and Phase 2 models, AST and graph behavior, ingestion safety, DSA scanning, Spec Grounding, Topology Profiling, the structured LLM router, the SQLite cache, the three-tier Pedagogy_Engine, and the existing API behavior are preserved. `backend/domain/models.py` is extended by appending only. Any change to a Phase 1 or Phase 2 file must be minimal, backward-compatible, and justified in the design document. No existing test is weakened, deleted, skipped, or marked xfail.

### Out of Scope

Phase 4, the frontend (React, TypeScript, React Flow, Tailwind), any Crew UI beyond what the Crew package manifest strictly requires, styling, deployment, additional DSA categories, unrelated refactors, and new product features. The Phase 4 UI will consume the `ComprehensionVitals.file_states` field defined in Requirement 1 and Requirement 8, but no UI that renders the field is built here.

### Observations and Confirmed Decisions

Each item below was verified against the repository on the date of writing. The user confirmed every decision recorded here. The design must implement each decision and record how it did so.

1. **Baseline test count.** `LLM_PROVIDER=mock .venv/bin/python -m pytest -q` reports **770 passed in 16.78 s**, with no failures, errors, or skips. This matches the stated 770 and no discrepancy exists. (Spec #02 recorded 745; its 25 new unit and property tests account for the difference.) Baseline Ruff: `ruff check backend` passes and `ruff format --check backend` reports 18 files already formatted. The venv runs Python 3.14.7.
2. **MCP SDK binding (confirmed).** `backend/pyproject.toml` declares `mcp>=1.0` and the venv holds `mcp 2.3.0`. In this version `from mcp.server.fastmcp import FastMCP` raises `ModuleNotFoundError`; the equivalent class is `mcp.server.mcpserver.MCPServer`. The standalone `fastmcp` package is not installed. Decision: Requirement 16 binds to `MCPServer` from the installed `mcp` 2.3.0 SDK and requires the dependency constraint in `pyproject.toml` to match it.
3. **Shared pipeline, dissection service, and `repo_id` convention (confirmed).** No orchestrator composes ingestion, parsing, DSA scanning, graph building, provenance, topology, and caching; Spec #02 left it to "the delivery layer". Both the REST API and the MCP server need it, and `architecture.md` forbids core logic in routes and MCP handlers. Decision: Requirement 4 adds one shared engine-layer Analysis_Pipeline and defines the `repo_id` convention, and Requirement 5 adds one shared Dissection_Service. Every surface reuses both.
4. **Additive mock grading (confirmed).** `LLMRouter._generate_mock` raises `LLMRouterError` for any response model other than `L1SyntaxExplanation`, `L2FlowExplanation`, and `L3ArchitectureExplanation`, and an existing Spec #02 test relies on that rejection using `SpecLink`. Decision: `llm_router.py` gains one additive mock builder for `SocraticGrade` and keeps every existing mock behavior, including that rejection (Requirement 7 criterion 8).
5. **Grading schema (confirmed).** Requirement 7 requires the LLM grade to be validated against a domain schema, and the seven requested models do not include one. Decision: Requirement 1 adds the single helper model `SocraticGrade`.
6. **Time convention.** `datetime`, `time`, and `uuid` appear only in test files, so the project's time conventions reduce to the string-typed `next_review_at` and `last_verified_at` fields. Decision: Requirement 6 defines UTC ISO 8601 strings and an injectable Clock.
7. **`ease_factor` update rule (confirmed).** The request says a pass "updates ease_factor" yet forbids another algorithm or added parameters, and the schedule formula uses a fixed initial ease of 2.5 with no quality input. Decision: Requirement 6 criterion 6 persists `ease_factor` with its current value (2.5) on every pass.
8. **Hook file format (decided).** The current Kiro hook schema is the v1 JSON format: one file per hook set at `.kiro/hooks/<id>.json` with the shape `{"version": "v1", "hooks": [{"name", "trigger", "matcher"?, "action"}]}`, where `action` is `{"type": "command", "command": ...}` or `{"type": "agent", "prompt": ...}`. Decision: Requirement 20 uses `.kiro/hooks/verify-engines.json` (trigger `PostFileSave`, command action) and `.kiro/hooks/anti-vibe-coding.json` (trigger `PostToolUse` on the agent's file-write tools, agent action), and no legacy `.kiro.hook` file is created. The anti-vibe hook uses `PostToolUse` rather than `PostFileCreate` because `PostToolUse` fires only after the agent's own tool calls, so it covers agent-generated files and agent edits. `PostFileCreate` fires for any new file in the workspace, including files made by the user, Git, or build tools, and does not fire for edits. The matcher for `PostToolUse` is tested against the tool name, so the design must confirm the exact file-write tool names of the installed Kiro agent. In the v1 semantics a command's exit code 2 blocks only for `PreToolUse`, `UserPromptSubmit`, and `PreTaskExec`, and stdout is forwarded to the session only for `SessionStart`, `UserPromptSubmit`, and `PreToolUse`. A failing `pytest` run after `PostFileSave` therefore cannot block the save, and Requirement 20 criterion 5 requires the design to verify where the installed Kiro version shows that command's output.
9. **Crew manifest additions (confirmed).** The Kiro Crew manifest reference (kiro.dev/docs/crew/apps/manifest) says `agents` lists paths to agent JSON files, while the request asks for `crew/agents/*.md`. File-tree actions map to `contributes.fileMenuItems` (surfaces `tree-context`, `file-overflow`, `folder-row`) whose `endpoint` is an app-local route. A composer control maps to `contributes.sessionControls`, whose required `entryPoint` is an ESM module. Decision: Requirement 19 keeps the Markdown agents, adds a companion JSON agent file per agent, and adds one minimal ESM module for the Study Mode session control.
10. **Socratic endpoints while Study Mode is off (confirmed).** Autopsy Mode has no quiz. Decision: Requirement 14 rejects `socratic/start` and `socratic/submit` with HTTP 409 and `code` `study_mode_disabled` while Study Mode is off.
11. **Truncation versus HTTP 422 (confirmed).** Phase 1 ingestion truncates at 500 files or 20 MB and reports a truncation indicator rather than failing. Decision: Requirement 10 returns HTTP 200 with `truncated: true` and reserves HTTP 422 for invalid or over-ceiling limit parameters and other guardrail failures.
12. **Local-path ingestion over HTTP (decided).** `POST /api/repos/ingest` with a local `path` lets an HTTP caller make the server parse any readable directory, which suits local development but not a hosted web deployment. Decision: Requirement 10 adds the boolean setting `ALLOW_LOCAL_INGEST` (default true). When it is false, the ingest endpoint rejects `path` requests with HTTP 403 and `code` `local_ingest_disabled` and still accepts GitHub `url` requests. The setting restricts only that HTTP endpoint. The Crew_Webhook is unaffected because it reads stored Snapshots and starts no ingestion (Requirement 15 criterion 14). The MCP_Server is unaffected because it runs locally over stdio and analyzes local paths by design (Requirement 16 criterion 25).
13. **Mastery granularity and AST hash transitions (confirmed).** `explain` accepts symbol ids for L1 and L2, so file-level and directory-level mastery records could never leave `UNAUDITED`. Decision: mastery is persisted per symbol only, and L3 explanations do not change mastery. A changed `ast_hash` moves `MASTERED` to `STALE` and `DISSECTED` to `UNAUDITED` (Requirement 3 criteria 8 and 9).
14. **Question generation and grading (confirmed).** Decision: the Mastery_Engine generates Socratic questions deterministically from the stored Snapshot (Requirement 7 criteria 2 to 6), and the LLM is used only to grade answers (Requirement 7 criterion 7). The Mastery_Engine, not the LLM, decides every state transition.
15. **File-level mastery rollup (decided).** The Phase 4 UI needs a per-file view, but per-file records would duplicate per-symbol state. Every `SymbolNode.file_path` equals the `FileAnalysis.file_path` of the file that contains the symbol, so a per-file state can be derived from per-symbol records without new storage. Decision: `ComprehensionVitals` gains the derived, read-only field `file_states`, computed by the weakest-link rule in Requirement 8 criteria 11 to 14. No new persisted state is added.
16. **Three conflicts resolved after design review (confirmed).** The design found three places where approved requirements conflicted with Phase 1 behavior or with each other. The user confirmed each resolution, and the requirements now state it:
    - **Clone depth.** Phase 1 Requirement 1.23 and an existing Phase 1 test fix the GitHub clone at `--depth 30` with hooks disabled, and Spec #02 provenance reads up to 20 recent commits. Decision: this spec keeps that clone unchanged and does not introduce a depth-1 clone (Requirement 10 criterion 13, Requirement 23 criterion 6).
    - **Snapshot `root_path`.** `RepoGraphSnapshot.root_path` is a server file-system path, which Requirement 9 criterion 10 forbids in any response body. Decision: `GET /api/repos/{repo_id}/snapshot` returns the stored Snapshot with `root_path` replaced by `"."` and every other field unchanged (Requirement 11 criterion 4).
    - **Review-date overflow in the property test.** The review interval grows by a factor of 2.5, so pass 17 from a Clock of `2025-01-01T00:00:00Z` would pass the maximum date of Requirement 6 criterion 12. Decision: the second property generates up to 20 passes, requires the review-date-out-of-range error on the first pass that would exceed `9999-12-31T23:59:59Z`, requires the record to stay unchanged on that pass, and stops there (Requirement 22 criterion 3).
17. **Crew gateway signature (decided; partly undocumented).** The Kiro Crew docs (kiro.dev/docs/crew/apps and kiro.dev/docs/crew/apps/sdk) say the gateway signs each proxied backend request with `X-Crew-Proxy: <timestamp>:<hmac-sha256>`. The SDK page defines the signature as HMAC-SHA256 over `timestamp:method:/api/path[?query]:sha256(body)`, keyed with the app secret, with timestamps within ±60 seconds of the current time and a constant-time comparison. Decision: the Crew_Webhook accepts either `X-Kiro-Signature` (the original scheme) or `X-Crew-Proxy`, selected by the rule in Requirement 15 criterion 5: a present `X-Kiro-Signature` must be valid and decides alone, otherwise `X-Crew-Proxy` is evaluated, and a request with neither header gets HTTP 401 `invalid_signature` (criterion 6). The documentation does not specify the following, so the requirements use the most conservative compatible rule and the design must confirm or adjust each item:
    - The text encoding of the HMAC and of `sha256(body)`. Rule used: 64-character lowercase hexadecimal for both, and no other encoding is accepted.
    - The unit of the timestamp. Rule used: decimal Unix seconds, which matches the documented ±60 second window.
    - The form of `method`. Rule used: the upper-case HTTP method.
    - Which path is signed, because the gateway serves the backend at `/apps/{name}/api/*` while the signed text names `/api/path`. Rule used: the request path and raw query string exactly as the API_App receives them.
    - Whether the "app secret" that keys the signature is the value of `KIRO_CREW_SECRET`. Rule used: the same secret keys both schemes.
    - Replay protection. The documentation defines no nonce, so a captured request can be replayed within the 60 second window. This is accepted as an open risk for the design.

## Glossary

- **Domain_Models**: The Pydantic v2 module `backend/domain/models.py`.
- **Mastery_Engine**: The module `backend/engines/mastery.py`. It owns Study Mode state, mastery records, state transitions, Socratic question generation and grading, review scheduling, and comprehension vitals.
- **Analysis_Pipeline**: The single engine-layer function (module chosen in the design) that runs safe ingestion, the AST_Parser, the DSA_Scanner, the Graph_Engine snapshot build, the Spec_Grounder, the Topology_Profiler, mastery initialization, and Cache_Store persistence for one repository.
- **Dissection_Service**: The single engine-layer function (module chosen in the design) that returns an `ExplanationEnvelope` and a `BlastRadius` for one target and records the mastery view event. REST, MCP, and Crew all call it.
- **Pedagogy_Engine**, **LLM_Router**, **Cache_Store**, **Graph_Engine**, **Spec_Grounder**, **Topology_Profiler**, **Ingestion_Engine**, **AST_Parser**, **DSA_Scanner**: The Phase 1 and Phase 2 engines in `backend/engines/`.
- **API_App**: The FastAPI application in `backend/api/main.py` and its routers in `backend/api/routes/`.
- **Rate_Limiter**: The in-memory per-client-IP request counter in the `api` layer that limits GitHub clone requests.
- **Crew_Webhook**: The route `backend/api/routes/crew.py` that receives Kiro Crew actions and, WHERE `KIRO_CREW_SECRET` is set, authenticates each request by an `X-Kiro-Signature` header or an `X-Crew-Proxy` header (Requirement 15 criteria 5 to 8).
- **MCP_Server**: The module `backend/mcp_server/server.py`.
- **MCP_Config**: The file `.kiro/settings/mcp.json`.
- **Power_Package**: The directory `power/`.
- **Crew_Package**: The directory `crew/`.
- **Hook_Files**: The v1 Kiro hook files `.kiro/hooks/verify-engines.json` and `.kiro/hooks/anti-vibe-coding.json`.
- **Verify_Engines_Hook**: The hook file `.kiro/hooks/verify-engines.json`.
- **Anti_Vibe_Hook**: The hook file `.kiro/hooks/anti-vibe-coding.json`.
- **Local_Ingest_Setting**: The environment variable `ALLOW_LOCAL_INGEST`, read by the API_App at startup, that decides whether `POST /api/repos/ingest` accepts a local `path`. Accepted values are defined in Requirement 10 criterion 16.
- **File_State**: The derived Mastery_State of one Snapshot file, computed from the Mastery_Records of the symbols in that file by the rule in Requirement 8 criterion 11.
- **Test_Suite**: All tests under `backend/tests/`, including the two new files named in Requirement 21 and Requirement 22.
- **Repo_Id**: The stable, URL-path-safe repository identifier defined in Requirement 4 criterion 5.
- **Target**: A symbol id (`<Relative_Path>::<Qualname>`) present in the stored Snapshot. A Mastery_Target is always a Target; files and directories are not Mastery_Targets.
- **Mastery_State**: A `MasteryState` value: `UNAUDITED`, `DISSECTED`, `MASTERED`, or `STALE`.
- **Mastery_Record**: A persisted `ModuleMastery` identified by `(repo_id, target_id)` and bound to exactly one `ast_hash`.
- **Study_Mode**: The per-repository boolean `study_mode_enabled`. Study_Mode off is Autopsy Mode and Study_Mode on is the active mastery mode.
- **Pass_Threshold**: The Socratic score of 0.7. A score of 0.7 or higher passes.
- **Socratic_Check**: One `SocraticCheck` of one or two `SocraticQuestion` items for one Target.
- **Clock**: An injectable callable that returns the current UTC time, so that scheduling is deterministic in tests.
- **Review_Schedule**: The interval rule defined in Requirement 6 criterion 3.
- **Error_Envelope**: The JSON body `{"error": {"code": <string>, "message": <string>}}` returned by every non-2xx API response.
- **Tool_Result**: The JSON object returned by an MCP tool: `{"ok": true, ...}` on success or `{"ok": false, "error": {"code": <string>, "message": <string>}}` on failure.
- **Baseline_Count**: The number of tests passing before this spec's changes: 770.

## Requirements

### Requirement 1: Mastery and Study Mode Domain Models

**User Story:** As a developer, I want strict, serializable mastery schemas, so that the engine, REST API, MCP server, and Crew App share one validated contract.

#### Acceptance Criteria

1. THE Domain_Models SHALL append the names `MasteryState`, `ModuleMastery`, `SocraticQuestion`, `SocraticCheck`, `SocraticAnswerItem`, `SocraticVerdict`, `ComprehensionVitals`, and `SocraticGrade` to `backend/domain/models.py` and to `__all__`, without altering any existing line of a Phase 1 or Phase 2 definition.
2. THE Domain_Models SHALL define `MasteryState` as a string enum with exactly the values `UNAUDITED`, `DISSECTED`, `MASTERED`, and `STALE`.
3. THE Domain_Models SHALL define `ModuleMastery` with exactly the fields `repo_id`, `target_id`, `ast_hash`, `state` (`MasteryState`), `ease_factor` (float, default 2.5), `interval_days` (integer, default 0), `repetitions` (integer, default 0), `next_review_at` (string or null, default null), and `last_verified_at` (string or null, default null).
4. THE Domain_Models SHALL define `SocraticQuestion` with exactly the fields `question_id`, `target_id`, `prompt`, `line_reference` (string), and `expected_concepts` (list of strings).
5. THE Domain_Models SHALL define `SocraticCheck` with exactly the fields `repo_id`, `target_id`, and `questions` (list of 1 to 2 `SocraticQuestion` items), and `SocraticAnswerItem` with exactly the fields `question_id` and `answer`.
6. THE Domain_Models SHALL define `SocraticVerdict` with exactly the fields `target_id`, `passed` (boolean), `score` (float), `feedback`, `new_state` (`MasteryState`), and `next_review_at` (string or null).
7. THE Domain_Models SHALL define `ComprehensionVitals` with exactly the fields `repo_id`, `study_mode_enabled` (boolean), `total_modules`, `unaudited_count`, `dissected_count`, `mastered_count`, `stale_count` (all integers), `mastery_percentage` (float), `due_for_review` (list of target id strings), and `file_states` (mapping from repository-relative file path string to `MasteryState`).
8. THE Domain_Models SHALL define `SocraticGrade` with a `score` field (float from 0.0 to 1.0 inclusive) and a `feedback` field (1 to 1,000 characters after trimming), as the response schema the LLM_Router validates for grading.
9. THE Domain_Models SHALL configure each new model as frozen (assignment to a field after construction raises an error), extra-forbidding, and strict (no type coercion, so the string `"0.5"` is rejected for a float field), using the same Pydantic v2 `ConfigDict` settings as the existing Phase 1 and Phase 2 models.
10. IF a score, `mastery_percentage`, or `ease_factor` value is NaN, infinite, or a boolean, THEN THE Domain_Models SHALL reject the model with a validation error identifying the field.
11. IF a `SocraticVerdict.score` is below 0.0 or above 1.0, THEN THE Domain_Models SHALL reject the model with a validation error, and values of exactly 0.0 and 1.0 SHALL be accepted.
12. IF a `ModuleMastery.ease_factor` is below 1.3, or `interval_days` or `repetitions` is negative or not an integer, THEN THE Domain_Models SHALL reject the model with a validation error identifying the field, and a value of exactly 1.3 for `ease_factor` and exactly 0 for the other two fields SHALL be accepted.
13. IF `ComprehensionVitals.mastery_percentage` is below 0.0 or above 100.0, or any count field is negative or not an integer, THEN THE Domain_Models SHALL reject the model with a validation error identifying the field, and values of exactly 0.0 and 100.0 SHALL be accepted.
14. IF a model is constructed with a field that is not defined on that model, THEN THE Domain_Models SHALL reject the model with a validation error identifying the extra field.
15. THE Domain_Models SHALL import only the Python standard library and Pydantic, and SHALL contain no FastAPI, HTTP, or provider-SDK import.
16. FOR ALL valid new models, serializing with `model_dump_json` and parsing with `model_validate_json` SHALL produce a model equal to the original (round-trip property).
17. IF a `repo_id` is not 1 to 100 characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, and `-`, or any of `target_id`, `ast_hash`, `question_id`, or `line_reference` is empty or longer than 500 characters, or a `prompt` is empty or longer than 1,000 characters after trimming, THEN THE Domain_Models SHALL reject the model with a validation error identifying the field.
18. IF a `SocraticQuestion.expected_concepts` list has more than 10 items, or any item is empty or longer than 100 characters after trimming, THEN THE Domain_Models SHALL reject the model with a validation error identifying the field.
19. IF a `SocraticAnswerItem.answer` is empty or longer than 2,000 characters after trimming, or a `SocraticVerdict.feedback` is empty or longer than 1,000 characters after trimming, THEN THE Domain_Models SHALL reject the model with a validation error identifying the field.
20. IF a `next_review_at` or `last_verified_at` value is not null and is not a UTC ISO 8601 string with a `Z` suffix and whole-second precision (for example `2025-01-31T12:00:00Z`), THEN THE Domain_Models SHALL reject the model with a validation error identifying the field.
21. IF a `ComprehensionVitals.file_states` key does not satisfy the existing Phase 1 `RelativePath` rule, a value is not a `MasteryState`, or the number of entries exceeds `total_modules`, THEN THE Domain_Models SHALL reject the model with a validation error identifying `file_states`, and an empty mapping SHALL be accepted.

### Requirement 2: Persisted Study Mode

**User Story:** As a developer, I want Study Mode stored per repository, so that every surface sees the same setting after a restart.

#### Acceptance Criteria

1. THE Mastery_Engine SHALL persist `study_mode_enabled` per `repo_id` in the existing SQLite database through the Cache_Store infrastructure, without creating a second database file or a second database connection target.
2. WHEN Study_Mode is read for a `repo_id` that has no stored setting, THE Mastery_Engine SHALL return `False` and SHALL NOT write a row.
3. WHEN Study_Mode is set to a boolean value for a valid `repo_id`, THE Mastery_Engine SHALL persist that value, including for a `repo_id` that has no Snapshot yet, and SHALL return the persisted value.
4. WHEN a new Cache_Store is opened on the same database file, THE Mastery_Engine SHALL return, for each `repo_id`, the Study_Mode value persisted by the previous Cache_Store.
5. WHEN Study_Mode is toggled from one value to the other, THE Mastery_Engine SHALL leave every Mastery_Record, stored `ast_hash`, cached `ExplanationEnvelope`, `RepoGraphSnapshot`, `ProvenanceReport`, and `TopologyProfile` of that repository equal to its value before the toggle.
6. WHEN Study_Mode is set to the value it already holds, THE Mastery_Engine SHALL return that value and SHALL leave every stored Study_Mode value and Mastery_Record unchanged (idempotent set).
7. WHILE Study_Mode is off, THE Mastery_Engine SHALL return the same results for every repository read (Snapshot, provenance, topology, explanation, blast radius, and vitals) as it returns while Study_Mode is on, SHALL add no Socratic question to any result, and SHALL refuse no read.
8. WHEN Study_Mode is set for one `repo_id`, THE Mastery_Engine SHALL leave the Study_Mode value of every other `repo_id` unchanged.
9. IF the database cannot be read while the Study_Mode value is read, THEN THE Mastery_Engine SHALL raise an error that wraps the `CacheStoreError`, and the error SHALL contain no stored row content.
10. IF the database cannot be written while Study_Mode is set, THEN THE Mastery_Engine SHALL raise an error that wraps the `CacheStoreError`, SHALL leave the previously persisted value unchanged so that a later read returns it, and the error SHALL contain no stored row content.
11. IF the value passed to set Study_Mode is not a boolean (including `None`, integers 0 and 1, and strings), THEN THE Mastery_Engine SHALL raise a validation error identifying the value as invalid and SHALL leave the persisted value unchanged.
12. IF the `repo_id` passed to read or set Study_Mode does not satisfy the Repo_Id rule (1 to 100 characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, `-`), THEN THE Mastery_Engine SHALL raise a validation error identifying `repo_id` as invalid and SHALL read or write no row.

### Requirement 3: Mastery Tracking and State Transitions

**User Story:** As a learner, I want modules to move through mastery states based on real evidence, so that mastery reflects verified understanding of the current code.

#### Acceptance Criteria

1. WHEN a Snapshot is registered with the Mastery_Engine, THE Mastery_Engine SHALL create one `UNAUDITED` Mastery_Record for each symbol in the Snapshot that has no Mastery_Record for the same `(repo_id, target_id)`, binding `ast_hash` to the symbol's `ast_hash`, with `ease_factor` 2.5, `interval_days` 0, `repetitions` 0, `next_review_at` null, and `last_verified_at` null, regardless of the Study_Mode value.
2. THE Mastery_Engine SHALL store at most one Mastery_Record per `(repo_id, target_id)`, so that registering the same Snapshot repeatedly creates no duplicate record and changes no existing record.
3. WHILE Study_Mode is on, WHEN an explanation view is recorded for a Target whose Mastery_Record is `UNAUDITED`, THE Mastery_Engine SHALL change the state to `DISSECTED` and leave `ast_hash` and every schedule field unchanged.
4. WHEN an explanation view is recorded for a Target whose Mastery_Record is `DISSECTED`, `MASTERED`, or `STALE`, THE Mastery_Engine SHALL leave the Mastery_Record unchanged.
5. WHILE Study_Mode is off, WHEN an explanation view is recorded, THE Mastery_Engine SHALL leave every Mastery_Record unchanged.
6. WHEN a Socratic check for a Target passes with a validated score of 0.7 or higher, THE Mastery_Engine SHALL change the Mastery_Record state to `MASTERED`, regardless of whether the prior state was `UNAUDITED`, `DISSECTED`, `MASTERED`, or `STALE`, and SHALL apply the schedule fields defined in Requirement 6.
7. IF a Socratic check for a Target fails with a validated score below 0.7, THEN THE Mastery_Engine SHALL leave the Mastery_Record state, `ast_hash`, and every schedule field unchanged.
8. WHEN a registered Snapshot shows a different `ast_hash` for a Target whose Mastery_Record is `MASTERED`, THE Mastery_Engine SHALL rebind the record to the new `ast_hash`, set the state to `STALE`, reset `repetitions` and `interval_days` to 0, set `next_review_at` to null, and leave `ease_factor` and `last_verified_at` unchanged, regardless of the Study_Mode value.
9. WHEN a registered Snapshot shows a different `ast_hash` for a Target whose Mastery_Record is `DISSECTED`, THE Mastery_Engine SHALL rebind the record to the new `ast_hash` and set the state to `UNAUDITED`, leaving the schedule fields unchanged, regardless of the Study_Mode value.
10. WHEN a registered Snapshot shows a different `ast_hash` for a Target whose Mastery_Record is `UNAUDITED` or `STALE`, THE Mastery_Engine SHALL rebind the record to the new `ast_hash` and keep the state and the schedule fields unchanged.
11. THE Mastery_Engine SHALL define exactly the four Mastery_State values `UNAUDITED`, `DISSECTED`, `MASTERED`, and `STALE`, and SHALL NOT introduce another state.
12. WHEN a Mastery_Record is rebound to a new `ast_hash`, THE Mastery_Engine SHALL NOT keep the state `MASTERED` or `DISSECTED` on that record, so that no verification earned against an earlier `ast_hash` counts as mastery of the current `ast_hash`.
13. WHEN a Snapshot no longer contains a Target that has a Mastery_Record, THE Mastery_Engine SHALL retain that record unchanged and SHALL exclude it from comprehension vitals, and WHEN a later registered Snapshot contains that Target again, THE Mastery_Engine SHALL treat the record under criteria 8 to 10 by comparing `ast_hash`.
14. IF a Mastery_Engine operation receives a `target_id` that is not a symbol in the stored Snapshot of the repository, THEN THE Mastery_Engine SHALL raise an unknown-target error identifying the `target_id` and SHALL create or modify no Mastery_Record.
15. IF a transition is requested that is not defined in criteria 1, 3, 6, 8, 9, or 10, THEN THE Mastery_Engine SHALL raise an invalid-transition error identifying the current state and the requested state and SHALL leave every persisted Mastery_Record unchanged.
16. IF a failure occurs while writing a Mastery_Record or while registering a Snapshot, THEN THE Mastery_Engine SHALL raise an error and SHALL leave every previously committed Mastery_Record unchanged, so that no partially registered Snapshot is persisted.

### Requirement 4: Shared Analysis Pipeline and Repository Identity

**User Story:** As a developer, I want one pipeline that turns a repository into stored analysis, so that REST, MCP, and Crew never duplicate analysis logic.

#### Acceptance Criteria

1. WHEN a local directory path or a public GitHub HTTPS URL is supplied, THE Analysis_Pipeline SHALL return the `repo_id`, the `RepoGraphSnapshot`, the `ProvenanceReport`, the `TopologyProfile`, the truncation indicator, and the ingestion warnings. The truncation indicator SHALL be true if and only if the Ingestion_Engine reports truncation at the Phase 1 limits of 500 files or 20 MB, and the run SHALL still complete successfully in that case.
2. THE Analysis_Pipeline SHALL obtain files from the Ingestion_Engine, per-file analysis from the AST_Parser, signals from the DSA_Scanner, the snapshot from the Graph_Engine, provenance from the Spec_Grounder, and topology from the Topology_Profiler, and SHALL contain no parsing, graph, DSA, provenance, or topology logic of its own.
3. WHEN the Analysis_Pipeline completes all analysis steps, THE Analysis_Pipeline SHALL persist the Snapshot, the provenance report, and the topology profile through the Cache_Store, and SHALL register the Snapshot with the Mastery_Engine. Persistence and registration SHALL succeed or fail as one unit, so that a failure in any of them leaves no partial data for that `repo_id`.
4. WHEN the Analysis_Pipeline runs twice on unchanged repository content, THE Analysis_Pipeline SHALL produce equal Snapshot, provenance, and topology values, SHALL return the same `repo_id`, and SHALL create no duplicate Mastery_Record.
5. THE Analysis_Pipeline SHALL derive a `repo_id` that is deterministic for the same source, contains only the characters `A-Z`, `a-z`, `0-9`, `.`, `_`, and `-`, has a length of 1 to 100 characters, and is identical for the same local directory or GitHub repository regardless of the calling surface. The derivation SHALL treat the following as the same source:
   - For a local directory, equivalent spellings of one directory, such as a trailing path separator or a relative path versus its absolute form.
   - For a GitHub URL, spellings that differ only by a trailing `/`, a trailing `.git`, or the letter case of the host.
6. THE Analysis_Pipeline SHALL derive different `repo_id` values for two sources that are different directories or different GitHub repositories, including two directories that share the same final path segment.
7. THE Analysis_Pipeline SHALL read repository files only through the Ingestion_Engine and the AST_Parser and SHALL NOT execute, import, or install any analyzed code.
8. IF the source contains zero supported source files, THEN THE Analysis_Pipeline SHALL raise a typed error identifying that no analyzable files exist, SHALL persist nothing, and SHALL leave previously stored data for the `repo_id` unchanged.
9. IF the Ingestion_Engine raises an `IngestionError`, THEN THE Analysis_Pipeline SHALL propagate the typed error unchanged, SHALL persist nothing, and SHALL leave previously stored data for the `repo_id` unchanged.
10. IF a step after ingestion fails, THEN THE Analysis_Pipeline SHALL leave previously stored data for the `repo_id` unchanged, including the Snapshot, provenance report, topology profile, and every Mastery_Record, and SHALL raise a typed error that names the failed step without exposing file contents.
11. WHEN the Analysis_Pipeline runs on a repository whose `repo_id` already has stored data and whose content has changed, THE Analysis_Pipeline SHALL replace the stored Snapshot, provenance report, and topology profile with the new values, and SHALL register the new Snapshot so that the Mastery_Engine applies the `ast_hash` change rules of Requirement 3.
12. THE Analysis_Pipeline SHALL import no FastAPI or MCP module.

### Requirement 5: Dissection Service

**User Story:** As a developer, I want one function that explains a target and measures its blast radius, so that every surface returns identical content.

#### Acceptance Criteria

1. WHEN a `repo_id`, a Target, and a lens are provided, THE Dissection_Service SHALL return one result containing the `ExplanationEnvelope` produced by the Pedagogy_Engine for that Target and lens, and the `BlastRadius` produced by the Graph_Engine for that Target.
2. THE Dissection_Service SHALL build the graph from the stored Snapshot of the `repo_id` with the Graph_Engine, SHALL NOT recompute call resolution, and SHALL NOT re-ingest or re-parse the repository.
3. WHILE Study_Mode is on for the `repo_id`, WHEN the Dissection_Service has obtained an `ExplanationEnvelope` for a Target with lens `L1_SYNTAX` or `L2_FLOW`, THE Dissection_Service SHALL record exactly one explanation view for that Target through the Mastery_Engine before returning.
4. WHILE Study_Mode is off for the `repo_id`, WHEN the Dissection_Service returns an explanation, THE Dissection_Service SHALL return the explanation and blast radius, SHALL call no Mastery_Engine view-recording operation, and SHALL leave every Mastery_Record unchanged.
5. WHEN the lens is `L3_ARCHITECTURE`, THE Dissection_Service SHALL return the envelope and blast radius, SHALL record no explanation view, and SHALL leave every Mastery_Record unchanged, regardless of the Study_Mode value.
6. IF the lens is not one of `L1_SYNTAX`, `L2_FLOW`, or `L3_ARCHITECTURE`, THEN THE Dissection_Service SHALL raise an invalid-lens error before any Pedagogy_Engine, Graph_Engine, or LLM_Router call, SHALL record no mastery view, and SHALL leave every Mastery_Record unchanged.
7. IF the repository data is missing, the Target is not a symbol in the stored Snapshot, the source is unreadable, or the LLM_Router fails with no deterministic fallback, THEN THE Dissection_Service SHALL propagate the typed `PedagogyError` unchanged, SHALL return no partial result, SHALL record no mastery view, and SHALL leave every Mastery_Record unchanged.
8. WHERE no `max_depth` is supplied, THE Dissection_Service SHALL compute the `BlastRadius` with the Graph_Engine default depth of 3 for every lens, and WHERE a `max_depth` is supplied, THE Dissection_Service SHALL pass it to the Graph_Engine unchanged.
9. IF recording the explanation view through the Mastery_Engine fails, THEN THE Dissection_Service SHALL propagate the Mastery_Engine error, SHALL return no result, and SHALL leave the Mastery_Record unchanged.
10. WHEN the Dissection_Service is called twice with the same `repo_id`, Target, lens, and `max_depth` against an unchanged Snapshot, THE Dissection_Service SHALL return equal `BlastRadius` values.
11. THE Dissection_Service SHALL import no FastAPI or MCP module.

### Requirement 6: Review Scheduling

**User Story:** As a learner, I want mastered modules scheduled for review at growing intervals, so that retention is reinforced at predictable times.

#### Acceptance Criteria

1. THE Mastery_Engine SHALL obtain the current time only from the Clock and SHALL format `next_review_at` and `last_verified_at` as UTC ISO 8601 strings of the form `YYYY-MM-DDTHH:MM:SSZ`, with whole-second precision obtained by truncating fractional seconds.
2. WHEN a Socratic check passes, THE Mastery_Engine SHALL increase `repetitions` by exactly 1 from the value stored in the Mastery_Record (0 for a new or reset record) and SHALL set `last_verified_at` to the Clock time of the pass.
3. WHEN a Socratic check passes, THE Mastery_Engine SHALL set `interval_days` to 1 if the new `repetitions` value is 1, to 6 if the new `repetitions` value is 2, and otherwise to `round(previous_interval_days * ease_factor)` using the Python built-in `round`, where `previous_interval_days` is the `interval_days` stored before the pass.
4. WHEN a Socratic check passes, THE Mastery_Engine SHALL set `next_review_at` to the Clock time of the pass plus `interval_days` × 24 hours.
5. THE Mastery_Engine SHALL use an initial `ease_factor` of 2.5 for every new Mastery_Record.
6. WHEN a Socratic check passes, THE Mastery_Engine SHALL persist `ease_factor` with its current value (2.5 for every record), and SHALL apply no other ease adjustment formula.
7. THE Mastery_Engine SHALL keep `interval_days` and `repetitions` at integer values of 0 or above in every persisted record.
8. WHEN the same sequence of pass events is applied with the same Clock values to two fresh Mastery_Records, THE Mastery_Engine SHALL produce equal records.
9. WHEN 5 consecutive passes are applied to one fresh Mastery_Record, THE Mastery_Engine SHALL produce `repetitions` values of 1, 2, 3, 4, and 5 and `interval_days` values of 1, 6, 15, 38, and 95 in that order.
10. THE Mastery_Engine SHALL add no scheduling parameter and SHALL use no scheduling algorithm other than the one defined in this requirement.
11. IF the Clock raises an error or returns a value that is not a timezone-aware UTC time, THEN THE Mastery_Engine SHALL raise an error indicating an invalid clock value and SHALL leave the Mastery_Record unchanged.
12. IF a passing check would produce a `next_review_at` later than `9999-12-31T23:59:59Z`, THEN THE Mastery_Engine SHALL raise an error indicating that the review date is out of range and SHALL leave the Mastery_Record unchanged.

### Requirement 7: Socratic Question Generation and Grading

**User Story:** As a learner, I want one or two code-grounded questions that are graded against my answers, so that mastery means real understanding of the code.

#### Acceptance Criteria

1. WHILE Study_Mode is on, WHEN a Socratic check is requested for a Target, THE Mastery_Engine SHALL return a `SocraticCheck` containing the requested `repo_id` and `target_id` and 1 or 2 `SocraticQuestion` items.
2. THE Mastery_Engine SHALL derive each question deterministically from the stored Snapshot, using only the Target's real symbol name and signature, its real source lines, its direct callers and callees from the Graph_Engine, the names of variables that the Target source assigns or returns, and its `DSASignal` entries.
3. THE Mastery_Engine SHALL set each `line_reference` to the form `<file_path>:<start_line>-<end_line>`, where `start_line` is at most `end_line` and both lie within the Target symbol's line range. THE Mastery_Engine SHALL set `prompt` to 1 to 500 characters. THE Mastery_Engine SHALL set `expected_concepts` to a list of 1 to 5 distinct strings, each of which occurs in the Target source, the Snapshot symbol ids, or the DSA signal pattern names.
4. THE Mastery_Engine SHALL set each `question_id` as a deterministic function of `repo_id`, `target_id`, the Target `ast_hash`, and the question index, so that the same Snapshot yields the same ids and different question indexes yield different ids.
5. WHEN a Socratic check is requested for a Target that has at least one direct caller, direct callee, or DSA signal, THE Mastery_Engine SHALL return exactly 2 questions.
6. THE Mastery_Engine SHALL reference no file, line, symbol, caller, callee, or dependency that is absent from the Snapshot or the Target source.
7. WHEN answers are submitted for a Socratic check, THE Mastery_Engine SHALL call `LLM_Router.generate_structured` with `SocraticGrade` as the response model and a user prompt built from the original questions, their expected concepts, the Target's source context, and the submitted answers.
8. WHERE `LLM_PROVIDER` is `mock`, THE LLM_Router SHALL return a deterministic `SocraticGrade` without a network call. Its `score` SHALL equal the number of distinct expected concepts that occur as case-insensitive substrings of the submitted answers, divided by the number of distinct expected concepts, with no rounding. Its `feedback` SHALL be 1 to 1,000 characters. This is a minimal additive change to `llm_router.py` that preserves every existing mock behavior, including the rejection of unsupported response models.
9. WHEN a validated `SocraticGrade` is returned, THE Mastery_Engine SHALL set `passed` to true if and only if `score >= 0.7`, so that a score of exactly 0.7 passes and 0.69 fails. THE Mastery_Engine SHALL copy `score` and `feedback` from the grade to the `SocraticVerdict`. THE Mastery_Engine SHALL derive `new_state` and `next_review_at` from its own transition and scheduling rules.
10. WHEN a validated `SocraticGrade` is returned, THE Mastery_Engine SHALL return a `SocraticVerdict` with `new_state` of `MASTERED` and a non-null `next_review_at` if the check passed, and with the Mastery_Record's unchanged state and unchanged `next_review_at` if the check failed.
11. IF the LLM_Router raises an error, does not respond within 30 seconds, or returns output that fails `SocraticGrade` validation, THEN THE Mastery_Engine SHALL raise a grading-unavailable error, SHALL leave every Mastery_Record unchanged, and SHALL NOT include provider error text, credentials, or prompt text in the error.
12. IF the number of submitted answers differs from the number of questions, an answer references a `question_id` that is not part of the check, a `question_id` appears more than once, or an answer is empty or longer than 2,000 characters after trimming, THEN THE Mastery_Engine SHALL raise an invalid-answers error before any LLM_Router call and SHALL leave every Mastery_Record unchanged.
13. IF the Target `ast_hash` at submission time differs from the `ast_hash` from which the question ids were derived, THEN THE Mastery_Engine SHALL raise an invalid-answers error identifying a mismatched check, SHALL make no LLM_Router call, and SHALL leave every Mastery_Record unchanged.
14. THE Mastery_Engine SHALL NOT start, require, or enforce a countdown timer, so that a client-side 60-second check requires no backend timer and the backend accepts a submission at any time.
15. WHILE Study_Mode is off, WHEN a Socratic check is requested or answers are submitted for a Target, THE Mastery_Engine SHALL raise a study-mode-disabled error, SHALL create no question, SHALL make no LLM_Router call, and SHALL leave every Mastery_Record unchanged.
16. WHEN a Socratic check is requested for a Target that has no direct caller, no direct callee, and no DSA signal, THE Mastery_Engine SHALL return exactly 1 question.
17. IF a Socratic check is requested or answers are submitted for a `target_id` that is not a symbol in the stored Snapshot of the repository, THEN THE Mastery_Engine SHALL raise the unknown-target error defined in Requirement 3 criterion 14, SHALL make no LLM_Router call, and SHALL leave every Mastery_Record unchanged.

### Requirement 8: Comprehension Vitals

**User Story:** As a developer, I want a read-only summary of comprehension, so that I can see what is verified, stale, or due for review.

#### Acceptance Criteria

1. WHEN vitals are requested for a repository, THE Mastery_Engine SHALL return a `ComprehensionVitals` whose `repo_id` equals the requested `repo_id` and whose `total_modules` equals the number of Mastery_Records for that `repo_id` whose `target_id` is a symbol id in the stored Snapshot of that repository. Each such record is a counted record, and its symbol is a counted symbol, as used in criteria 2, 4, and 11 to 13.
2. THE Mastery_Engine SHALL set `unaudited_count`, `dissected_count`, `mastered_count`, and `stale_count` to the number of counted records whose state is `UNAUDITED`, `DISSECTED`, `MASTERED`, and `STALE` respectively, so that the four counts sum to `total_modules`, and SHALL exclude every Mastery_Record whose `target_id` is absent from the stored Snapshot from `total_modules` and from all four counts.
3. THE Mastery_Engine SHALL set `mastery_percentage` to `round(100 * mastered_count / total_modules, 2)` using the Python built-in `round` if `total_modules` is greater than 0, and to `0.0` if `total_modules` is 0, so that the value lies from 0.0 to 100.0 inclusive (for example, 1 of 3 counted records `MASTERED` gives 33.33 and 2 of 3 gives 66.67).
4. THE Mastery_Engine SHALL read the Clock exactly once per vitals request and SHALL set `due_for_review` to the `target_id` values of counted records whose state is `MASTERED` and whose `next_review_at` is non-null and is at or before that Clock time, including a record whose `next_review_at` equals that Clock time. The list SHALL be sorted by `next_review_at` ascending and then by `target_id` in ascending Unicode code point order, SHALL hold no duplicate, SHALL hold at most `mastered_count` entries, and SHALL include no record whose `target_id` is absent from the stored Snapshot.
5. THE Mastery_Engine SHALL set `study_mode_enabled` to the Study_Mode value persisted for the requested `repo_id`, and to `false` if no Study_Mode value is stored for that `repo_id`.
6. WHILE Study_Mode is off, THE Mastery_Engine SHALL compute every `ComprehensionVitals` field other than `study_mode_enabled` by the same rules as WHILE Study_Mode is on, so that two vitals requests with the same Clock value that differ only in the stored Study_Mode value return results that differ only in `study_mode_enabled`.
7. WHEN vitals are requested, THE Mastery_Engine SHALL create no Mastery_Record, change no Mastery_Record or Study_Mode value, start no Socratic check, make no LLM_Router call, and perform no write to the database.
8. WHEN vitals are requested twice with an unchanged database and the same Clock value, THE Mastery_Engine SHALL return equal `ComprehensionVitals` values whose `model_dump_json` output is byte-identical, including the order of `due_for_review` entries and of `file_states` keys.
9. IF the requested `repo_id` has no stored Snapshot, THEN THE Mastery_Engine SHALL raise an unknown-repository error that identifies the `repo_id`, SHALL return no vitals, and SHALL change no stored data.
10. IF the database cannot be read during a vitals request, or the Clock raises an error or returns a value that is not a timezone-aware UTC time, THEN THE Mastery_Engine SHALL raise an error that exposes no Mastery_Record row content, SHALL return no partial vitals, and SHALL change no stored data, regardless of whether any counted record is `MASTERED`.
11. WHEN vitals are requested, THE Mastery_Engine SHALL set `file_states` to exactly one entry per Snapshot file that contains at least one counted symbol, where a symbol belongs to the Snapshot file whose `file_path` equals the symbol's `SymbolNode.file_path`, so that every counted symbol contributes to exactly one entry and the number of entries is at most `total_modules`. The entry key SHALL be the file's `file_path` from the stored Snapshot. The entry value SHALL be the File_State given by this weakest-link rule, applied to the counted symbols of that file:
   - `STALE` if any symbol is `STALE`.
   - Otherwise `UNAUDITED` if any symbol is `UNAUDITED`.
   - Otherwise `DISSECTED` if any symbol is `DISSECTED`.
   - Otherwise `MASTERED`, which holds only when every symbol is `MASTERED`.
12. THE Mastery_Engine SHALL omit from `file_states` every Snapshot file that contains no counted symbol, including every file that contains zero symbols, and SHALL include no key that is not a `file_path` in the stored Snapshot, so that `file_states` is an empty mapping if `total_modules` is 0.
13. THE Mastery_Engine SHALL derive `file_states` only from the counted records defined in criterion 1, excluding every Mastery_Record whose `target_id` is absent from the stored Snapshot, SHALL persist no file-level state, and SHALL perform no database write to compute `file_states`.
14. THE Mastery_Engine SHALL insert the `file_states` keys in ascending Unicode code point order of the full `file_path` string (for example, `a/z.py` before `b.py`, and `B.py` before `a.py`), so that the serialized JSON of equal vitals is byte-identical across calls.
15. IF the requested `repo_id` does not satisfy the Repo_Id rule (1 to 100 characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, `-`), THEN THE Mastery_Engine SHALL raise a validation error identifying `repo_id` as invalid, SHALL read no Mastery_Record, SHALL return no vitals, and SHALL change no stored data.

### Requirement 9: REST API Application and Configuration

**User Story:** As a developer, I want a configured FastAPI app with consistent errors, so that clients can rely on one predictable HTTP contract.

#### Acceptance Criteria

1. THE API_App SHALL keep the existing `GET /health` route and its response unchanged.
2. THE API_App SHALL mount routers from `backend/api/routes/repos.py`, `autopsy.py`, `mastery.py`, and `crew.py` in `backend/api/main.py`.
3. THE API_App SHALL keep route handlers thin: each handler SHALL validate input, call one shared engine function, and map the result or typed error to an HTTP response, and SHALL contain no parsing, graph, topology, provenance, scoring, or scheduling logic.
4. WHEN the environment variable `STUPID_CODE_CORS_ORIGINS` is set to a non-empty value, THE API_App SHALL read the allowed CORS origins from it as a comma-separated list, trimming whitespace around each entry and ignoring empty entries.
5. WHEN `STUPID_CODE_CORS_ORIGINS` is unset or empty, THE API_App SHALL allow exactly `http://localhost:5173`, `http://localhost:3000`, `http://127.0.0.1:5173`, and `http://127.0.0.1:3000`.
6. THE API_App SHALL allow a Vercel origin only WHEN that exact origin string appears in `STUPID_CODE_CORS_ORIGINS`.
7. IF `STUPID_CODE_CORS_ORIGINS` contains the entry `*`, THEN THE API_App SHALL refuse to start with a configuration error that names the variable `STUPID_CODE_CORS_ORIGINS`, and SHALL serve no request.
8. THE API_App SHALL send no credentials-bearing CORS response (`allow_credentials` false) and SHALL send no `Access-Control-Allow-Origin` header for an origin that is not allowed.
9. THE API_App SHALL return every non-2xx response, including request-body, path, and query validation failures (HTTP 422), as an Error_Envelope with a non-empty `message` and a stable machine-readable `code` that is the same for the same failure cause across requests.
10. THE API_App SHALL include no stack trace, file-system path of the server, SQL text, provider error text, credential, or prompt text in any response body.
11. IF an unexpected exception occurs in a handler, THEN THE API_App SHALL return HTTP 500 with an Error_Envelope whose `code` is `internal_error`, SHALL log the exception class name without request headers, request body, or credentials, and SHALL keep serving later requests.
12. IF a `CacheStoreError` occurs, THEN THE API_App SHALL return HTTP 500 with an Error_Envelope whose `code` is `storage_error`, and SHALL leave previously committed data unchanged.
13. THE API_App SHALL open the Cache_Store and LLM_Router through one dependency provider that tests can override with a temporary database and the mock provider.
14. WHILE a blocking ingestion, parsing, or SQLite request is in progress, THE API_App SHALL answer `GET /health` with HTTP 200 within 1 second, by running that blocking work off the event loop.
15. THE API_App SHALL type every request and response body with a Pydantic model.

### Requirement 10: Repository Ingest Endpoint and GitHub Rate Limit

**User Story:** As a developer, I want to ingest a local directory or a public GitHub repository over HTTP, so that analysis and mastery tracking start from one call.

#### Acceptance Criteria

1. WHEN a client sends `POST /api/repos/ingest` with exactly one of `path` (local directory, accepted while the Local_Ingest_Setting is true, see criterion 18) or `url` (public GitHub HTTPS URL), and the request passes every check of criterion 21, THE API_App SHALL call the Analysis_Pipeline and return HTTP 200 with the `repo_id`, the Snapshot summary counts, the `ProvenanceReport`, the `TopologyProfile`, the truncation indicator, and the ingestion warnings.
2. IF the request body is not valid JSON, is not a JSON object, contains neither `path` nor `url`, contains both, or contains a `path` or `url` value that is not a string, is empty after trimming, or is longer than 4,096 characters, THEN THE API_App SHALL return HTTP 400 with an Error_Envelope whose `code` is `malformed_request` (for these causes on this endpoint, HTTP 400 replaces the HTTP 422 of Requirement 9 criterion 9), SHALL start no ingestion, and SHALL NOT count the request against the Rate_Limiter.
3. IF the Ingestion_Engine raises `EMPTY_PATH`, `MALFORMED_PATH`, or any `URL_*` error kind, THEN THE API_App SHALL return HTTP 400 with an Error_Envelope whose `code` is the lowercase error kind name (for example `empty_path`), and SHALL store no Snapshot and create no Mastery_Record.
4. IF the Ingestion_Engine raises `NOT_FOUND`, `NOT_A_DIRECTORY`, `NOT_READABLE`, `INVALID_LIMIT`, `DESTINATION_OUTSIDE_WORKSPACE`, or `GIT_FAILED`, THEN THE API_App SHALL return HTTP 422 with an Error_Envelope whose `code` is the lowercase error kind name, and IF the repository contains no supported source files, THEN THE API_App SHALL return HTTP 422 with an Error_Envelope whose `code` is `no_supported_files`. In each case THE API_App SHALL store no Snapshot and create no Mastery_Record.
5. IF the Ingestion_Engine raises `GIT_TIMEOUT`, THEN THE API_App SHALL return HTTP 504, and IF it raises `GIT_NOT_INSTALLED`, `ROOT_FILESYSTEM_ERROR`, or `CLEANUP_FAILED`, THEN THE API_App SHALL return HTTP 500, each with an Error_Envelope whose `code` is the lowercase error kind name and whose body carries no git stderr text. In each case THE API_App SHALL store no Snapshot and create no Mastery_Record.
6. IF a request supplies `max_files` or `max_total_bytes` with a value below 1, above the Ingestion_Engine default (500 files, 20,971,520 bytes), or not an integer (including null, a boolean, a float, or a string), THEN THE API_App SHALL return HTTP 422 with an Error_Envelope whose `code` is `invalid_limit`, SHALL start no ingestion, and SHALL NOT count the request against the Rate_Limiter. A supplied integer from 1 to the default inclusive SHALL be accepted, and an omitted field SHALL mean the Ingestion_Engine default.
7. WHEN discovery truncates the repository at a limit, THE API_App SHALL return HTTP 200 with `truncated` set to true.
8. WHEN a request that passes the checks of criteria 2 and 6 supplies `url`, THE Rate_Limiter SHALL count the request against the client IP before the Analysis_Pipeline starts, and SHALL allow it only if fewer than the configured limit of counted requests from that client IP are inside the window. With the defaults (5 requests, 60 seconds), the 5th request inside one window is allowed and the 6th is rejected. A request counted at Clock time t SHALL be inside the window at a later Clock time t' while t' − t is less than the window length in seconds. A counted request SHALL stay counted whatever its outcome, including HTTP 200, a `URL_*` error, `GIT_FAILED`, or `GIT_TIMEOUT`.
9. IF a client IP exceeds the GitHub clone request limit, THEN THE API_App SHALL return HTTP 429 with an Error_Envelope whose `code` is `rate_limited` and a `Retry-After` header equal to the whole seconds, rounded up and at least 1, until the oldest counted request of that client IP leaves the window. THE API_App SHALL start no clone, SHALL store no Snapshot, SHALL create no Mastery_Record, and SHALL NOT count the rejected request toward the limit.
10. WHEN a request supplies `path`, THE Rate_Limiter SHALL NOT count the request, and a client IP that is currently rate limited for `url` requests SHALL still receive normal handling of `path` requests.
11. THE Rate_Limiter SHALL keep its counters in process memory, use the injected Clock for all timing, use no external dependency, and release each client's expired counters when that client sends a later request. WHEN more `url` requests than the remaining allowance arrive concurrently from one client IP, THE Rate_Limiter SHALL allow exactly the remaining allowance and reject the rest with HTTP 429.
12. THE Rate_Limiter SHALL base each allow or reject decision only on the configured limit, the window length, the client IP, and the Clock times of the counted requests, so that replaying the same sequence of client IPs and Clock times produces the same decisions on every run.
13. THE API_App SHALL run the Analysis_Pipeline with the existing ingestion guardrails and SHALL clone GitHub repositories only through the Ingestion_Engine's existing shallow, hook-disabled `git clone` with `--depth 30`, unchanged from Phase 1.
14. WHEN ingestion succeeds, THE API_App SHALL leave Study_Mode and every existing Mastery_Record of the repository unchanged, apart from the registration rules of Requirement 3.
15. IF `STUPID_CODE_GITHUB_RATE_LIMIT` is set to a value that is not an integer from 1 to 1,000, or `STUPID_CODE_GITHUB_RATE_WINDOW_SECONDS` is set to a value that is not an integer from 1 to 3,600, THEN THE API_App SHALL refuse to start with a configuration error that names the variable, and SHALL serve no request.
16. THE API_App SHALL read the Local_Ingest_Setting once at startup, after trimming surrounding whitespace: an unset or empty value SHALL mean true, the values `true` and `1` (letters matched case-insensitively) SHALL mean true, and the values `false` and `0` (letters matched case-insensitively) SHALL mean false. A change to `ALLOW_LOCAL_INGEST` after startup SHALL have no effect until the API_App restarts.
17. IF `ALLOW_LOCAL_INGEST` is set to any value other than those accepted in criterion 16 (for example `yes`, `off`, or `2`), THEN THE API_App SHALL refuse to start with a configuration error that names the variable `ALLOW_LOCAL_INGEST`, and SHALL serve no request.
18. WHILE the Local_Ingest_Setting is false, WHEN a request to `POST /api/repos/ingest` passes the checks of criteria 2 and 6 and supplies `path`, THE API_App SHALL return HTTP 403 with an Error_Envelope whose `code` is `local_ingest_disabled` and whose `message` contains no part of the supplied `path`. THE API_App SHALL start no ingestion, SHALL read, stat, or resolve no file-system path, SHALL store no Snapshot, SHALL create no Mastery_Record, and SHALL NOT count the request against the Rate_Limiter. This applies to every `path` string that passes criterion 2, including one the Ingestion_Engine would reject with `MALFORMED_PATH` or `NOT_FOUND`.
19. WHILE the Local_Ingest_Setting is false, WHEN a request to `POST /api/repos/ingest` supplies `url`, THE API_App SHALL handle the request exactly as WHILE the Local_Ingest_Setting is true, including the Rate_Limiter rules of criteria 8 to 11.
20. THE Local_Ingest_Setting SHALL change the behavior of `POST /api/repos/ingest` only, and every other API_App route SHALL return the same results whether the Local_Ingest_Setting is true or false.
21. WHEN `POST /api/repos/ingest` receives a request, THE API_App SHALL apply its checks in this order and SHALL stop at the first check that rejects the request: (1) the body checks of criterion 2 (HTTP 400 `malformed_request`); (2) the limit checks of criterion 6 (HTTP 422 `invalid_limit`); (3) for a `path` request, the Local_Ingest_Setting check of criterion 18 (HTTP 403 `local_ingest_disabled`); (4) for a `url` request, the Rate_Limiter check of criteria 8 and 9 (HTTP 429 `rate_limited`); (5) the Analysis_Pipeline, whose errors map by criteria 3 to 5. A request rejected at any step SHALL cause no effect of a later step. For example, a `path` request with `max_files` of 0 while the Local_Ingest_Setting is false receives HTTP 422 `invalid_limit`, and a `url` request rejected at step 1 or 2 is not counted.
22. THE Rate_Limiter SHALL use the direct peer address of the connection as the client IP and SHALL ignore the `X-Forwarded-For` header. THE API_App SHALL read the limit from `STUPID_CODE_GITHUB_RATE_LIMIT` and the window length in seconds from `STUPID_CODE_GITHUB_RATE_WINDOW_SECONDS`, and WHEN either variable is unset or empty, THE API_App SHALL use 5 for the limit and 60 for the window.

### Requirement 11: Repository List and Snapshot Endpoints

**User Story:** As a developer, I want to list stored repositories and fetch stored analysis, so that clients never re-ingest to read results.

#### Acceptance Criteria

1. WHEN a client sends `GET /api/repos`, THE API_App SHALL return HTTP 200 with a JSON list of stored repositories read from persisted data, each item containing `repo_id`, `file_count` (integer, 0 or greater), `symbol_count` (integer, 0 or greater), and `study_mode_enabled` (boolean), sorted by `repo_id` ascending in Unicode code point order.
2. THE API_App SHALL perform no ingestion and no re-analysis while serving `GET /api/repos`.
3. WHEN no repository is stored, THE API_App SHALL return HTTP 200 with an empty list.
4. WHEN a client sends `GET /api/repos/{repo_id}/snapshot` for a stored repository, THE API_App SHALL return HTTP 200 with a JSON body containing the stored `RepoGraphSnapshot`, `ProvenanceReport`, and `TopologyProfile`, and SHALL NOT rebuild any of them. Every field of each value SHALL equal the stored value, except that THE API_App SHALL replace the `root_path` field of the `RepoGraphSnapshot` with the string `"."`, so that no server file-system path appears in the response (Requirement 9 criterion 10). The stored `root_path` SHALL remain unchanged in the database.
5. IF `repo_id` is 1 to 100 characters from `A-Z`, `a-z`, `0-9`, `.`, `_`, and `-` and does not match a stored repository, THEN THE API_App SHALL return HTTP 404 with an Error_Envelope whose `code` is `repo_not_found`.
6. IF `repo_id` contains a character outside `A-Z`, `a-z`, `0-9`, `.`, `_`, and `-`, or is longer than 100 characters, THEN THE API_App SHALL return HTTP 404 with an Error_Envelope whose `code` is `repo_not_found`, without querying the Cache_Store.
7. IF a stored repository exists but one of its `RepoGraphSnapshot`, `ProvenanceReport`, or `TopologyProfile` cannot be read from persisted data, THEN THE API_App SHALL return HTTP 500 with an Error_Envelope whose `code` is `storage_error`, SHALL NOT include row content in the message, and SHALL leave stored data unchanged.
8. THE API_App SHALL serve both endpoints without calling the LLM_Router and without modifying any Mastery_Record or Study_Mode value.

### Requirement 12: Explain Endpoint

**User Story:** As a learner, I want an explanation and blast radius for a target, so that I can dissect code at the lens I choose.

#### Acceptance Criteria

1. WHEN a client sends `POST /api/repos/{repo_id}/explain` with a JSON body containing a string `target_id` and a string `lens`, THE API_App SHALL call the Dissection_Service and return HTTP 200 with a body containing exactly the `ExplanationEnvelope` and the `BlastRadius`, and no Socratic question, quiz, or gate field.
2. THE API_App SHALL accept `lens` values `L1_SYNTAX`, `L2_FLOW`, and `L3_ARCHITECTURE`, matched case-sensitively, and no others.
3. IF the request body is not valid JSON, `lens` is not an accepted value, or `target_id` is missing, is not a string, is empty, or is longer than 500 characters, THEN THE API_App SHALL return HTTP 422 with an Error_Envelope whose `code` is `validation_error`, and SHALL call neither the Dissection_Service nor the LLM_Router.
4. IF `repo_id` is not stored, contains a character outside `A-Z`, `a-z`, `0-9`, `.`, `_`, and `-`, or is longer than 100 characters, THEN THE API_App SHALL return HTTP 404 with an Error_Envelope whose `code` is `repo_not_found`.
5. IF the Target is not a symbol in the stored Snapshot of the repository for the requested lens, THEN THE API_App SHALL return HTTP 404 with an Error_Envelope whose `code` is `unknown_target`.
6. IF the Pedagogy_Engine raises `SOURCE_UNREADABLE`, THEN THE API_App SHALL return HTTP 409 with an Error_Envelope whose `code` is `source_unreadable`.
7. IF the Pedagogy_Engine raises `LLM_FAILURE`, THEN THE API_App SHALL return HTTP 503 with an Error_Envelope whose `code` is `llm_unavailable`.
8. IF the Pedagogy_Engine raises `INVALID_OUTPUT`, THEN THE API_App SHALL return HTTP 502 with an Error_Envelope whose `code` is `invalid_llm_output`.
9. WHILE Study_Mode is on, WHEN an explanation for an L1 or L2 Target is returned with HTTP 200, THE API_App SHALL leave the mastery update to the Dissection_Service, so that a Mastery_Record that was `UNAUDITED` is `DISSECTED` after the response and a Mastery_Record that was `DISSECTED`, `MASTERED`, or `STALE` is unchanged.
10. WHILE Study_Mode is off, THE API_App SHALL return the explanation and blast radius with HTTP 200 and SHALL change no Mastery_Record and no Study_Mode value.
11. WHEN the lens is `L3_ARCHITECTURE`, THE API_App SHALL change no Mastery_Record, whether Study_Mode is on or off.
12. IF the endpoint returns any non-2xx response, THEN THE API_App SHALL leave every Mastery_Record and the Study_Mode value of the repository unchanged.

### Requirement 13: Vitals and Study Mode Endpoints

**User Story:** As a developer, I want to read vitals and switch Study Mode over HTTP, so that any client can drive the same mastery state.

#### Acceptance Criteria

1. WHEN a client sends `GET /api/repos/{repo_id}/vitals` for a stored repository, THE API_App SHALL return HTTP 200 with the `ComprehensionVitals` returned by the Mastery_Engine, unmodified, including `total_modules`, `unaudited_count`, `dissected_count`, `mastered_count`, `stale_count`, `mastery_percentage`, `due_for_review`, `file_states`, and `study_mode_enabled`.
2. THE API_App SHALL perform no database write, no mastery transition, and no LLM_Router call while serving `GET /api/repos/{repo_id}/vitals`.
3. WHEN a client sends `POST /api/repos/{repo_id}/study-mode` with a JSON body whose only field is `enabled` with a JSON boolean value, THE API_App SHALL persist the value through the Mastery_Engine and return HTTP 200 with `repo_id` and the persisted `study_mode_enabled`.
4. WHEN a client sends `POST /api/repos/{repo_id}/study-mode` with the value already persisted, THE API_App SHALL return HTTP 200 with the same body as for a changed value and SHALL leave all stored data unchanged.
5. WHEN Study_Mode is changed, THE API_App SHALL leave all Mastery_Records, AST hashes, cached explanations, the Snapshot, provenance, and topology of the repository unchanged, and a following `GET /api/repos/{repo_id}/vitals` request SHALL report the new `study_mode_enabled` value.
6. IF the request body of `POST /api/repos/{repo_id}/study-mode` is not valid JSON, is not a JSON object, omits `enabled`, or has an `enabled` value that is not a JSON boolean (including the strings `"true"` and `"false"` and the integers 0 and 1), THEN THE API_App SHALL return HTTP 422 with an Error_Envelope whose `code` is `validation_error`, and SHALL leave the persisted Study_Mode unchanged.
7. IF `repo_id` is not stored, contains a character outside `A-Z`, `a-z`, `0-9`, `.`, `_`, and `-`, or is longer than 100 characters, THEN THE API_App SHALL return HTTP 404 with an Error_Envelope whose `code` is `repo_not_found` for both endpoints, and SHALL write nothing to the database.
8. IF a `CacheStoreError` occurs while serving either endpoint, THEN THE API_App SHALL return HTTP 500 with an Error_Envelope whose `code` is `storage_error`, and the previously persisted Study_Mode SHALL remain unchanged.

### Requirement 14: Socratic Start and Submit Endpoints

**User Story:** As a learner, I want to answer code-grounded questions and receive a graded verdict, so that mastery is earned and persisted.

#### Acceptance Criteria

1. WHEN a client sends `POST /api/repos/{repo_id}/socratic/start` with a `target_id` WHILE Study_Mode is on, THE API_App SHALL return HTTP 200 with a `SocraticCheck` of 1 or 2 questions from the Mastery_Engine, SHALL make no LLM_Router call, and SHALL change no Mastery_Record.
2. THE API_App SHALL return `expected_concepts` as an empty list in every question of the `socratic/start` response and SHALL include no answer, hint, or grading rubric in the response.
3. THE API_App SHALL run no countdown on the server and SHALL accept `socratic/submit` at any time after `socratic/start`, including more than 60 seconds after it.
4. WHEN a client sends `POST /api/repos/{repo_id}/socratic/submit` with `target_id` and a list of `SocraticAnswerItem` WHILE Study_Mode is on, THE API_App SHALL call the Mastery_Engine, return HTTP 200 with the `SocraticVerdict`, and persist the `new_state` and `next_review_at` the Mastery_Engine returns for the Target's Mastery_Record.
5. WHEN grading succeeds and the `SocraticVerdict` has `passed` false, THE API_App SHALL return HTTP 200 with a `SocraticVerdict` whose `new_state` and `next_review_at` equal the values of the Mastery_Record before the request, and SHALL never report `MASTERED` unless the Mastery_Record was already `MASTERED` before the request.
6. IF Study_Mode is off for the repository, THEN THE API_App SHALL return HTTP 409 with `code` `study_mode_disabled` for both Socratic endpoints, SHALL create no question, SHALL make no LLM_Router call, and SHALL change no Mastery_Record.
7. IF `repo_id` is not stored, THEN THE API_App SHALL return HTTP 404 with `code` `repo_not_found` for both Socratic endpoints, and this check SHALL take precedence over every other error check of this requirement.
8. IF the `target_id` is not a symbol id in the stored Snapshot of the repository, THEN THE API_App SHALL return HTTP 404 with `code` `unknown_target` for both Socratic endpoints and SHALL change no Mastery_Record.
9. IF the request body is not valid JSON, `target_id` is missing or is not a non-empty string, or the `answers` field of `socratic/submit` is missing or is not a list, THEN THE API_App SHALL return HTTP 422 with `code` `validation_error` and SHALL change no Mastery_Record.
10. IF the number of answers differs from the number of questions, an answer references an unknown or repeated `question_id`, an answer is empty or longer than 2,000 characters after trimming, or the Target `ast_hash` differs from the `ast_hash` the `question_id` values were derived from, THEN THE API_App SHALL return HTTP 422 with `code` `invalid_answers`, SHALL make no LLM_Router call, and SHALL change no Mastery_Record.
11. IF the grading LLM call fails, does not complete within 30 seconds, or returns output that fails `SocraticGrade` validation, THEN THE API_App SHALL return HTTP 503 with `code` `grading_unavailable`, SHALL change no Mastery_Record, and SHALL return a message that contains no provider error text, credential, or prompt text.
12. THE API_App SHALL NOT return a `SocraticVerdict` with `new_state` `MASTERED` and a non-null `next_review_at` for any response in which grading failed, its output was invalid, or `passed` is false.

### Requirement 15: Kiro Crew Webhook

**User Story:** As a Crew user, I want file-menu actions and Study Mode control to reach the shared engines, so that Crew behaves like every other surface.

#### Acceptance Criteria

1. THE Crew_Webhook SHALL accept `POST` requests whose JSON body is at most 1,048,576 bytes and names an `action` of `autopsy_file`, `explain_folder_architecture`, or `study_mode`, and SHALL validate the body with a Pydantic model. The required fields are `repo_id` and `path` for `autopsy_file`, `repo_id` and `path` for `explain_folder_architecture`, and `repo_id` and `enabled` (boolean) for `study_mode`. `path` is a string of 1 to 1,024 characters.
2. WHEN the action is `autopsy_file` and `path` names a file in the Snapshot, THE Crew_Webhook SHALL return HTTP 200 with the file's symbols sorted ascending by start line, at most 10, each with its L2 `ExplanationEnvelope` and `BlastRadius` obtained from the Dissection_Service. IF the file has more than 10 symbols, THEN THE Crew_Webhook SHALL return the 10 with the lowest start lines and SHALL include `truncated: true` in the response. IF the file has no symbols, THEN THE Crew_Webhook SHALL return an empty symbol list.
3. WHEN the action is `explain_folder_architecture` and `path` is a directory in the Snapshot or the repository root (the string `.`), THE Crew_Webhook SHALL return HTTP 200 with the L3 `ExplanationEnvelope` obtained from the Dissection_Service for that directory or for the repository root.
4. WHEN the action is `study_mode`, THE Crew_Webhook SHALL set Study_Mode to the `enabled` value through the Mastery_Engine and SHALL return HTTP 200 with the persisted Study_Mode value and the `ComprehensionVitals`. IF the Mastery_Engine write fails, THEN THE Crew_Webhook SHALL return an Error_Envelope with HTTP 500 and SHALL leave the previously persisted Study_Mode value unchanged.
5. WHERE the environment variable `KIRO_CREW_SECRET` is set to a non-empty value, THE Crew_Webhook SHALL authenticate every request before parsing the body, SHALL select exactly one signature scheme by the rule below, and SHALL compare every received signature value with its computed value using a constant-time comparison:
   - If the request has an `X-Kiro-Signature` header, THE Crew_Webhook SHALL accept the request only if the header value is `sha256=<hex>`, where `<hex>` is the 64-character lowercase hexadecimal HMAC-SHA256 of the raw request body keyed with the secret. THE Crew_Webhook SHALL NOT evaluate an `X-Crew-Proxy` header on that request, so that a valid `X-Crew-Proxy` header cannot rescue an invalid `X-Kiro-Signature` header.
   - If the request has no `X-Kiro-Signature` header and has an `X-Crew-Proxy` header, THE Crew_Webhook SHALL accept the request only if the header value is `<timestamp>:<hmac>`, where `<timestamp>` is a decimal Unix time in whole seconds, the absolute difference between `<timestamp>` and the Clock time is at most 60 seconds, and `<hmac>` is the 64-character lowercase hexadecimal HMAC-SHA256, keyed with the secret, of the string `<timestamp>:<method>:<path>:<body_hash>`. In that string `<method>` is the upper-case HTTP method, `<path>` is the request path followed by `?` and the raw query string when a query string is present, as the API_App receives them, and `<body_hash>` is the 64-character lowercase hexadecimal SHA-256 of the raw request body. This is the scheme documented for the Kiro Crew gateway (Observation 17).
6. WHILE `KIRO_CREW_SECRET` is set to a non-empty value, IF neither the `X-Kiro-Signature` header nor the `X-Crew-Proxy` header is present, or the header selected by criterion 5 occurs more than once, is malformed, does not match its computed value, or (for `X-Crew-Proxy`) carries a timestamp more than 60 seconds from the Clock time, or the Clock raises an error or returns a value that is not a timezone-aware UTC time, THEN THE Crew_Webhook SHALL return an Error_Envelope with HTTP 401 and `code` `invalid_signature`, SHALL run no action, and SHALL change no stored data.
7. WHILE `KIRO_CREW_SECRET` is unset or empty, THE Crew_Webhook SHALL accept requests without a signature and SHALL verify neither signature header, so that local development works.
8. THE Crew_Webhook SHALL NOT log the secret, the value of the `X-Kiro-Signature` header, the value of the `X-Crew-Proxy` header, any computed signature, or the signed string of criterion 5, and SHALL NOT include any of them in a response.
9. IF `path` is absolute, contains a `..` segment, contains a backslash, or does not name a file (for `autopsy_file`) or a directory or the repository root (for `explain_folder_architecture`) in the Snapshot, THEN THE Crew_Webhook SHALL return an Error_Envelope with HTTP 404 and `code` `unknown_target`, SHALL read no file, and SHALL change no Mastery_Record.
10. IF the body is not valid JSON, exceeds 1,048,576 bytes, names an unknown `action`, omits a required field, or has a field of the wrong type, THEN THE Crew_Webhook SHALL return an Error_Envelope with HTTP 422 and `code` `validation_error`, SHALL run no action, and SHALL change no stored data.
11. IF `repo_id` is not stored, THEN THE Crew_Webhook SHALL return an Error_Envelope with HTTP 404 and `code` `repo_not_found`, SHALL run no action, and SHALL change no stored data.
12. THE Crew_Webhook SHALL call the same Dissection_Service, Mastery_Engine, and Analysis_Pipeline functions the other routes call, and SHALL contain no duplicate analysis or mastery logic.
13. IF the Dissection_Service raises an error or the LLM_Router is unavailable while the Crew_Webhook serves `autopsy_file` or `explain_folder_architecture`, THEN THE Crew_Webhook SHALL return an Error_Envelope with a 5xx status, SHALL return no partial symbol list, and SHALL leave every Mastery_Record unchanged by that request.
14. THE Crew_Webhook SHALL serve every action from the stored Snapshot of the `repo_id`, SHALL start no ingestion, and SHALL return the same results whether the Local_Ingest_Setting is true or false.

### Requirement 16: FastMCP Server

**User Story:** As an agent user, I want five MCP tools backed by the shared engines, so that Kiro can dissect code and read mastery without a second implementation.

#### Acceptance Criteria

1. THE MCP_Server SHALL be implemented in `backend/mcp_server/server.py` with the server class of the installed `mcp` SDK (`MCPServer` in `mcp` 2.x) and SHALL isolate that import in exactly one import statement, so that an SDK rename changes one line.
2. THE `backend/pyproject.toml` dependency constraint for `mcp` SHALL admit the SDK version the MCP_Server targets (2.3.0 or later within the 2.x series) and SHALL exclude versions in which that server class does not exist.
3. THE MCP_Server SHALL expose exactly five tools: `dissect_symbol(repo_path, target_id, lens="L2_FLOW")`, `trace_blast_radius(repo_path, target_id, max_depth=3)`, `analyze_folder_architecture(repo_path)`, `check_spec_drift(repo_path)`, and `get_comprehension_vitals(repo_path)`.
4. THE MCP_Server SHALL return a Tool_Result from every tool, with `ok` set to `true` on success and to `false` on failure, so that `json.dumps` succeeds on the result.
5. THE MCP_Server SHALL implement each tool as a thin wrapper that calls the shared engines (Analysis_Pipeline, Dissection_Service, Graph_Engine, Topology_Profiler, Spec_Grounder, Mastery_Engine) and SHALL contain no duplicate analysis, scoring, or mastery logic.
6. WHEN `dissect_symbol` is called with a valid `repo_path`, `target_id`, and `lens`, THE MCP_Server SHALL return the `ExplanationEnvelope` and `BlastRadius` from the Dissection_Service in a success Tool_Result.
7. WHEN `trace_blast_radius` is called with a valid `repo_path`, `target_id`, and `max_depth`, THE MCP_Server SHALL return the `BlastRadius` from the Graph_Engine computed to the given `max_depth`.
8. WHEN `analyze_folder_architecture` is called with a valid `repo_path`, THE MCP_Server SHALL return the stored `TopologyProfile` if one exists for the current content, otherwise a `TopologyProfile` built through the Analysis_Pipeline, and SHALL make zero LLM_Router calls.
9. WHEN `check_spec_drift` is called with a valid `repo_path`, THE MCP_Server SHALL return the `ProvenanceReport` drift items and the `has_kiro_specs` value produced by the Spec_Grounder.
10. WHEN `get_comprehension_vitals` is called with a valid `repo_path` that has stored analysis, THE MCP_Server SHALL return the `ComprehensionVitals` from the Mastery_Engine unmodified, including `file_states`, and SHALL perform zero database writes.
11. WHEN `dissect_symbol`, `trace_blast_radius`, `analyze_folder_architecture`, or `check_spec_drift` is called for a directory that has no stored analysis or whose stored content hash differs from the current content, THE MCP_Server SHALL obtain current analysis through the Analysis_Pipeline, so that changed symbols become `STALE` or `UNAUDITED` under Requirement 3.
12. IF `get_comprehension_vitals` is called for a directory with no stored analysis, THEN THE MCP_Server SHALL return a failure Tool_Result with `code` `repo_not_analyzed`, SHALL run no analysis, and SHALL write nothing to the database.
13. IF `repo_path` is empty, longer than 4096 characters, malformed, missing, not a directory, or unreadable, THEN THE MCP_Server SHALL return a failure Tool_Result with `code` `invalid_repo_path`, SHALL NOT raise an uncaught exception, and SHALL write nothing to the database.
14. IF `target_id` is not a symbol id in the stored Snapshot, THEN THE MCP_Server SHALL return a failure Tool_Result with `code` `unknown_target` and SHALL change no Mastery_Record.
15. IF `lens` is not a lens value accepted by the Dissection_Service, THEN THE MCP_Server SHALL return a failure Tool_Result with `code` `invalid_lens` and SHALL change no Mastery_Record.
16. IF `max_depth` is not an integer from 0 to 20 inclusive, THEN THE MCP_Server SHALL return a failure Tool_Result with `code` `invalid_max_depth` and SHALL change no Mastery_Record.
17. THE MCP_Server SHALL include no credential, provider error text, stack trace, or server file-system path outside the requested `repo_path` in any Tool_Result.
18. THE MCP_Server SHALL write nothing to standard output other than MCP protocol messages, and SHALL write diagnostic logs only to standard error.
19. THE MCP_Server SHALL open the SQLite database at the path given by `STUPID_CODE_DB_PATH`, the same path as the API_App, so that Study_Mode and mastery state are shared between them.
20. WHERE `LLM_PROVIDER` is `mock`, THE MCP_Server SHALL run every tool with zero network calls.
21. THE MCP_Server SHALL accept an injected Cache_Store, LLM_Router, and Clock, so that tests can run each tool against a temporary database.
22. WHILE Study_Mode is on for the repository, WHEN `dissect_symbol` returns a success Tool_Result, THE MCP_Server SHALL record the mastery view event for the Target through the Dissection_Service under Requirement 3.
23. WHILE Study_Mode is off for the repository, WHEN `dissect_symbol` is called, THE MCP_Server SHALL change no Mastery_Record.
24. IF the LLM_Router fails or returns output that fails schema validation during `dissect_symbol`, THEN THE MCP_Server SHALL return a failure Tool_Result with `code` `llm_unavailable`, SHALL change no Mastery_Record, and SHALL leave previously stored analysis unchanged.
25. THE MCP_Server SHALL accept a local `repo_path` and analyze the repository through the Analysis_Pipeline whether the Local_Ingest_Setting is true or false, because the MCP_Server runs as a local stdio process and is not an HTTP endpoint.

### Requirement 17: Workspace MCP Configuration

**User Story:** As a Kiro IDE or CLI user, I want the MCP server registered in the workspace, so that the tools load without manual setup.

#### Acceptance Criteria

1. THE MCP_Config SHALL be the file `.kiro/settings/mcp.json` and SHALL parse without error as a single JSON document whose top-level value is an object.
2. THE MCP_Config SHALL define exactly one server entry under `mcpServers`, whose `command` is `.venv/bin/python` and whose `args` array contains the relative path `backend/mcp_server/server.py`.
3. THE MCP_Config SHALL use only workspace-relative paths, and no string value in the file SHALL begin with `/` or `~`, match a drive-letter prefix, contain `/Users/` or `/home/`, or contain a machine-specific user name.
4. THE MCP_Config SHALL start the server so that `backend.*` imports resolve from the workspace root, by a relative working directory, a relative `PYTHONPATH` entry, or an in-file path bootstrap that the design selects and verifies.
5. THE MCP_Config SHALL contain no API key or secret value, and SHALL set `LLM_PROVIDER` only WHERE the design needs it to default to `mock`, in which case the value SHALL be `mock`.
6. WHEN the command and arguments of the MCP_Config entry are run from the workspace root, THE MCP_Server SHALL answer an MCP `initialize` request within 10 seconds of process start, and SHALL answer a following `tools/list` request with exactly the five tool names `dissect_symbol`, `trace_blast_radius`, `analyze_folder_architecture`, `check_spec_drift`, and `get_comprehension_vitals`, and no other tool.
7. IF the file `.venv/bin/python` does not exist when the MCP_Config entry is run from the workspace root, THEN THE MCP_Server SHALL NOT start, and the launching process SHALL exit with a non-zero exit status and a message on standard error that names the missing `.venv/bin/python` path.

### Requirement 18: Kiro Power Package

**User Story:** As a Kiro user, I want a Power that bundles the MCP server and a skill, so that I can install Stupid Code in one step.

#### Acceptance Criteria

1. THE Power_Package SHALL contain `power/plugin.json`, `power/mcp.json`, and `power/skills/code-autopsy/SKILL.md`.
2. THE `power/plugin.json` file SHALL be valid JSON that conforms to the Agent Plugins 1.0.0 manifest fields documented at kiro.dev/docs/powers/create, with `name` (kebab-case, 1 to 64 characters), `version` (semantic version in `MAJOR.MINOR.PATCH` form), `description` (1 to 500 characters), `author` (object with a non-empty `name`), and `keywords` (array of 1 to 20 non-empty strings), and SHALL contain no field that the manifest reference does not define.
3. THE `power/plugin.json` file SHALL reference only files and directories that exist inside `power/`, and every referenced path SHALL be relative and contain no `..` segment.
4. THE `power/mcp.json` file SHALL be valid JSON, SHALL define exactly one server entry that runs `backend/mcp_server/server.py` with the command `.venv/bin/python` (the same command and script as the MCP_Config entry), and SHALL contain no absolute path, no home-directory path, and no secret value.
5. THE `power/skills/code-autopsy/SKILL.md` file SHALL begin with front matter that holds `name` equal to `code-autopsy` and a `description` of 1 to 500 characters that contains the words "Stupid Code", and SHALL be 200 lines or fewer.
6. THE `power/skills/code-autopsy/SKILL.md` file SHALL instruct the agent to identify the repository path and the target symbol, to use `dissect_symbol`, `trace_blast_radius`, `analyze_folder_architecture`, `check_spec_drift`, and `get_comprehension_vitals` by those exact names, and to ground every statement in tool output.
7. THE `power/skills/code-autopsy/SKILL.md` file SHALL instruct the agent, when a Tool_Result is missing or has `ok` equal to `false`, to tell the user which tool failed and its error `code`, and to avoid inventing code, symbols, lines, callers, callees, or specs.
8. THE `power/skills/code-autopsy/SKILL.md` file SHALL instruct the agent to read Study Mode from `get_comprehension_vitals`, to run no quiz while Study Mode is off, and to leave mastery decisions to the backend.
9. WHEN the command and arguments of the `power/mcp.json` entry are run from the workspace root, THE MCP_Server SHALL start and answer an MCP `initialize` request and a `tools/list` request that lists exactly the five tool names.
10. THE Power_Package SHALL contain no API key, no secret value, no absolute path, and no home-directory path in any of its files.

### Requirement 19: Kiro Crew App Package

**User Story:** As a Crew user, I want an app with file-tree actions, a Study Mode control, and two agents, so that Stupid Code works inside Crew.

#### Acceptance Criteria

1. THE Crew_Package SHALL contain `crew/app.json`, `crew/agents/autopsy-surgeon.md`, `crew/agents/socratic-examiner.md`, and `crew/skills/code-autopsy/SKILL.md`, each as a non-empty UTF-8 text file.
2. THE `crew/app.json` file SHALL be valid JSON that conforms to the Kiro Crew manifest reference (kiro.dev/docs/crew/apps/manifest), with a kebab-case `name` of 1 to 64 characters, a `version` in `MAJOR.MINOR.PATCH` form, a `displayName` of 1 to 60 characters, and a `description` of 1 to 280 characters, and SHALL contain no field that the reference does not define.
3. THE `crew/app.json` file SHALL declare exactly two `contributes.fileMenuItems` entries, labelled "Autopsy File" and "Explain Folder Architecture", each with an `endpoint` that targets the Crew_Webhook and a `surfaces` list that is non-empty and taken only from the values the reference defines.
4. THE `crew/app.json` file SHALL declare exactly one composer `contributes.sessionControls` entry, labelled "Study Mode", whose on and off values map to the Study_Mode boolean of the active repository.
5. THE `crew/app.json` file SHALL declare exactly the two custom agents `autopsy-surgeon` and `socratic-examiner` in the `agents` field.
6. WHERE the manifest reference requires agent definitions to be JSON files, THE Crew_Package SHALL provide `crew/agents/autopsy-surgeon.json` and `crew/agents/socratic-examiner.json` that each reference the matching Markdown agent file as their prompt source.
7. WHERE the manifest reference requires a session control to name an ESM `entryPoint`, THE Crew_Package SHALL provide that module as a single file of at most 100 lines that contains only the code the reference requires, and SHALL use `@kirocrew/app-sdk` only for capabilities the SDK documents.
8. THE Crew_Package SHALL declare in `app.json` only items whose files exist inside `crew/`, with relative paths that contain no `..` segment and no absolute path.
9. THE `crew/agents/autopsy-surgeon.md` file SHALL instruct the agent to dissect code with the MCP tools, to ground each claim in tool output, to invent no code or relationship, to read Study Mode from `get_comprehension_vitals`, and to run no quiz while Study Mode is off.
10. THE `crew/agents/socratic-examiner.md` file SHALL instruct the agent to ask 1 or 2 code-grounded questions, to grade through the backend's structured grading, to apply the 0.7 threshold only as reported by the backend, to reveal no expected answer before the user responds, and to declare mastery only after a passing backend verdict.
11. THE `crew/skills/code-autopsy/SKILL.md` file SHALL contain one titled section for each of: tool usage, file context, the three lenses, Study Mode, the Socratic workflow, mastery, evidence grounding, and handling of a missing tool or a failed backend, and SHALL use the same tool names, the same 0.7 Pass_Threshold, and the same Study Mode rules as the Power skill.
12. THE Crew_Package SHALL contain no Phase 4 web UI page, route, or React code.
13. IF a file named in criterion 1 or 6 is missing, or `crew/app.json` is not valid JSON, or `app.json` references a file that does not exist, THEN THE Test_Suite SHALL fail with an error that names the offending file or path.

### Requirement 20: Kiro Agent Hooks

**User Story:** As a maintainer, I want two hooks that verify engine edits and discourage blind acceptance of generated code, so that comprehension stays part of the workflow.

#### Acceptance Criteria

1. THE Hook_Files SHALL be `.kiro/hooks/verify-engines.json` and `.kiro/hooks/anti-vibe-coding.json`. Each SHALL be a valid UTF-8 JSON object in the v1 Kiro hook format, with exactly the top-level keys `version` (equal to `"v1"`) and `hooks` (an array of exactly one entry). Each entry SHALL hold only these keys: `name` (1 to 100 characters after trimming), `trigger` (one of `UserPromptSubmit`, `Stop`, `PreToolUse`, `PostToolUse`, `PreTaskExec`, `PostTaskExec`, `PostFileSave`, `PostFileCreate`, `PostFileDelete`, and `SessionStart`), an optional `matcher` (a non-empty string that compiles as a regular expression without error), and `action`. The `action` SHALL be exactly `{"type": "command", "command": <non-empty string>}` or `{"type": "agent", "prompt": <non-empty string>}`. No `.gitignore` rule SHALL ignore either Hook_File, as checked with `git check-ignore`. No file with the `.kiro.hook` extension SHALL exist anywhere in the repository for either hook.
2. THE Verify_Engines_Hook SHALL use the trigger `PostFileSave` and a `matcher` that matches a saved-file path naming a `.py` file directly inside `backend/engines/`. The matcher SHALL work on the path form the installed Kiro version passes to it and with the matching mode Kiro applies (search or full match), and the design SHALL verify both. Under that path form and matching mode, the matcher SHALL match `backend/engines/mastery.py` and `backend/engines/__init__.py`. It SHALL match none of `backend/engines/sub/helper.py`, `backend/engines/mastery.pyc`, `backend/engines/mastery.py.bak`, `backend/engines_old/mastery.py`, `backend/tests/unit/test_mastery_api_mcp.py`, `backend/api/main.py`, `README.md`, and `frontend/src/App.tsx`.
3. WHEN the Verify_Engines_Hook triggers, THE Verify_Engines_Hook SHALL run one `pytest` process per matched save, through a `command` action whose `command` string is exactly `.venv/bin/python -m pytest -q`, with the workspace root as the working directory.
4. THE Verify_Engines_Hook `command` string SHALL contain none of the characters or sequences `;`, `&`, `|`, `>`, `<`, a backtick, and `$(`, so that it runs no command other than the one in criterion 3. A run of the hook SHALL leave every Git-tracked file byte-identical to its content before the run.
5. IF the `.venv/bin/python -m pytest -q` command exits with a non-zero code or cannot start (for example, because `.venv/bin/python` does not exist), THEN THE Verify_Engines_Hook SHALL leave the saved file byte-identical to its content after the save, and the Kiro hook output of that run SHALL contain the output of the failing tests or the start error. The design SHALL record where the installed Kiro version shows `PostFileSave` command output, because the v1 format neither blocks on a `PostFileSave` exit code nor forwards its standard output to the agent session.
6. THE Anti_Vibe_Hook SHALL use the trigger `PostToolUse` and an `agent` action whose prompt runs in the Kiro session after each matched tool call. Its `matcher` SHALL match every Kiro agent tool name that creates or writes a file and no read-only tool name (a tool that reads files, lists directories, or searches). The design SHALL list, from the installed Kiro version, the exact write tool names as positive cases and at least three read-only tool names as negative cases, and the matcher SHALL match every positive case and no negative case.
7. WHEN the Anti_Vibe_Hook triggers, THE Anti_Vibe_Hook prompt SHALL instruct the agent to read `study_mode_enabled` by calling `get_comprehension_vitals` for the workspace repository. IF the value is false, the prompt SHALL instruct the agent to take no action, so that Autopsy Mode is never blocked. In this requirement, "take no action" means the agent sends the user no message about the file and calls no tool other than `get_comprehension_vitals`.
8. IF `get_comprehension_vitals` is unavailable, returns a Tool_Result with `ok` set to false, or returns no boolean `study_mode_enabled` value, THEN THE Anti_Vibe_Hook prompt SHALL instruct the agent to take no action, as defined in criterion 7, and to flag no file.
9. WHILE Study_Mode is on, WHEN the agent creates or writes a file whose content after the write has more than 25 lines, THE Anti_Vibe_Hook prompt SHALL instruct the agent to flag the file in a message to the user that names its repository-relative path and line count. The prompt SHALL also instruct the agent to call `dissect_symbol` on at least one symbol defined in that file before it treats the file as accepted. A line count is the number of lines after splitting the content on line breaks; blank lines count, and a final line break does not start an extra line.
10. THE Anti_Vibe_Hook prompt SHALL instruct the agent to flag a given file at most once within one Kiro session while that file's content is unchanged, to never flag a file of 25 lines or fewer, and to delete, revert, or modify no user code.
11. THE Hook_Files SHALL contain no API key, token, password, or other secret value, and no absolute or home-directory path. In this requirement, an absolute or home-directory path is any string that starts with `/` or `~`, or with a drive letter followed by `:\` or `:/`.
12. THE Anti_Vibe_Hook prompt SHALL contain the literal strings `get_comprehension_vitals`, `study_mode_enabled`, `dissect_symbol`, and `25`.

### Requirement 21: Unit Tests

**User Story:** As a maintainer, I want a small, offline, targeted unit suite, so that the new behavior is verified without bloat.

#### Acceptance Criteria

1. THE Test_Suite SHALL include the file `backend/tests/unit/test_mastery_api_mcp.py` containing between 20 and 25 test functions inclusive and fewer than 600 lines.
2. THE Test_Suite SHALL include unit tests that cover the Mastery_Engine behaviors below, each with at least one assertion on the resulting value or state:
   - Study_Mode returns `False` by default.
   - Study_Mode persists across a Cache_Store reopened on the same database file.
   - Mastery initialization sets every Target to `UNAUDITED` and creates no duplicate Mastery_Record when run twice.
   - A view event moves an `UNAUDITED` Target to `DISSECTED`.
   - A passing Socratic grade moves a Target to `MASTERED`.
   - A failing Socratic grade leaves the Mastery_Record unchanged.
   - A changed `ast_hash` moves a Target to `STALE`.
   - The Review_Schedule produces intervals of 1 day, 6 days, then `round(previous_interval * 2.5)` days on three consecutive passes.
   - Vitals report the per-state counts, `total_modules`, and `mastery_percentage`, and the same test asserts the `file_states` weakest-link value for at least one file whose symbols are in mixed states, without adding a test function.
   - `due_for_review` is ordered by `next_review_at` ascending, using a controlled Clock.
3. THE Test_Suite SHALL include unit tests that cover the Socratic workflow behaviors below:
   - A Socratic_Check contains 1 or 2 questions.
   - Each question has a `line_reference` that falls inside the line range of its Target.
   - A submitted answer is associated with its `question_id`.
   - A mock grader returns a structured `SocraticGrade`.
   - A score of 0.69 fails and a score of 0.70 passes against the Pass_Threshold.
   - An invalid grading response or a failed grading call grants no mastery and leaves the Mastery_Record unchanged.
4. THE Test_Suite SHALL include unit tests that call the API_App through FastAPI `TestClient` and cover each behavior below, with the git subprocess replaced by a test double:
   - Ingest validation: an invalid-input case returning status 400, a schema-invalid case returning status 422, a truncated-result case, and, inside the same ingest test function, a `path` request with the Local_Ingest_Setting false returning status 403 with `code` `local_ingest_disabled` and starting no ingestion.
   - List, snapshot, and explain reads.
   - A Study_Mode toggle.
   - Vitals read-only behavior: a vitals read leaves every Mastery_Record unchanged.
   - Socratic start and Socratic submit.
   - Error_Envelope shape on non-2xx responses.
   - GitHub rate limiting with a controlled Clock: a request over the limit is rejected, and a request after the window expires is accepted.
5. THE Test_Suite SHALL include unit tests that cover the Crew_Webhook behaviors below:
   - The file-menu `autopsy_file` action.
   - The `explain_folder_architecture` action.
   - Study_Mode control.
   - A request with a valid `X-Kiro-Signature` HMAC is accepted.
   - A request with a valid `X-Crew-Proxy` signature, whose timestamp is within 60 seconds of a controlled Clock, is accepted.
   - A request with an invalid `X-Kiro-Signature` or an invalid or stale `X-Crew-Proxy` signature, a request with both headers where `X-Kiro-Signature` is invalid and `X-Crew-Proxy` is valid, and a request with neither header are each rejected with an Error_Envelope that has HTTP 401 and `code` `invalid_signature`.
   - These signature cases run inside the existing signature test functions and add no test function to the count of Requirement 21 criterion 1.
   - A request made while the secret is unset is accepted, as defined in Requirement 15 criterion 7.
6. THE Test_Suite SHALL include unit tests that cover all five MCP tools, asserting for each tool:
   - A call with valid input returns a Tool_Result with `ok` equal to `true`, produced through the shared engines.
   - A call with invalid input returns a Tool_Result with `ok` equal to `false` and an `error` object.
   - The Tool_Result serializes with `json.dumps` without error.
7. THE Test_Suite SHALL include one test that asserts, for `.kiro/settings/mcp.json`, `power/plugin.json`, `power/mcp.json`, `crew/app.json`, and both Hook_Files, that:
   - Each file parses as valid JSON.
   - Every declared path exists and is relative.
   - No file contains an absolute path.
   - No file contains a non-empty literal value for a key named like a secret, token, API key, or password.
8. THE Test_Suite SHALL run with `LLM_PROVIDER=mock`, SHALL make no call to Gemini, Ollama, GitHub, or any other network service, SHALL read no real `.env` file, and SHALL use temporary repositories and temporary databases only.
9. THE Test_Suite SHALL preserve the root `pytest.ini` settings `testpaths = backend/tests`, `pythonpath = .`, and `asyncio_mode = auto`.
10. WHEN the new unit file runs alone, THE Test_Suite SHALL finish within 60 seconds with zero failures and zero errors.
11. WHEN the full Test_Suite runs, THE Test_Suite SHALL pass all Baseline_Count (770) existing tests and all new tests with zero failures and zero errors.

### Requirement 22: Property Tests

**User Story:** As a maintainer, I want exactly four bounded Hypothesis properties, so that the mastery invariants hold over generated input.

#### Acceptance Criteria

1. THE Test_Suite SHALL include `backend/tests/properties/test_mastery_properties.py` with exactly four Hypothesis property tests, each decorated with `@given`, and no other test function that uses Hypothesis.
2. THE first property SHALL generate sequences of 1 to 30 events drawn from `view`, `pass_check`, `fail_check`, and `ast_changed`, applied to one Mastery_Record that starts `UNAUDITED` with Study_Mode on, and SHALL assert after every event that the state is one of the four Mastery_State values, `interval_days` and `repetitions` are at least 0, no `fail_check` event changes a non-`MASTERED` state to `MASTERED`, and an event that the Mastery_Engine rejects with an invalid-transition or unknown-target error leaves the persisted Mastery_Record equal to its value before the event.
3. THE second property SHALL generate a count of 1 to 20 consecutive passing reviews applied to one fresh Mastery_Record with the initial `ease_factor` of 2.5, and SHALL assert after each pass that `repetitions` increased by exactly 1, `interval_days` is greater than or equal to its previous value, and `interval_days` equals 1 for the first pass, 6 for the second pass, and `round(previous_interval_days * ease_factor)` for each later pass. WHEN a pass would produce a `next_review_at` later than `9999-12-31T23:59:59Z` (with a Clock fixed at `2025-01-01T00:00:00Z` this is pass 17), THE second property SHALL assert that the Mastery_Engine raises the review-date-out-of-range error of Requirement 6 criterion 12 and that the Mastery_Record equals its value before that pass, and THE second property SHALL apply no later pass in that example.
4. THE third property SHALL generate sequences of 1 to 20 Study_Mode set operations with boolean values, applied to a repository that has at least 1 Mastery_Record and at least 1 cached `ExplanationEnvelope`, and SHALL assert that the number of Mastery_Records, every stored `ast_hash`, and every cached `ExplanationEnvelope` are equal to their values before the first operation, and that the Study_Mode value read after the sequence equals the last value set.
5. THE fourth property SHALL generate valid Snapshots with 1 to 10 symbols, store each in a temporary database, call each of the five MCP_Server tools with inputs that are valid for that Snapshot, and SHALL assert that `json.dumps` succeeds on every returned Tool_Result and that every Tool_Result contains the key `ok` with a boolean value.
6. THE property tests SHALL set `derandomize=True`, a `max_examples` value from 1 to 50 inclusive, and a per-example `deadline` of at most 500 ms, and SHALL add no `suppress_health_check` entry.
7. THE property tests SHALL set `LLM_PROVIDER=mock`, SHALL use a temporary or in-memory database and a controlled Clock, SHALL read no real `.env` file, and SHALL make no network call.
8. WHEN the new property file runs alone, THE Test_Suite SHALL finish within 60 seconds with all four tests passing.

### Requirement 23: Architecture, Security, and Error Handling

**User Story:** As a maintainer, I want the new code to follow the layering rules and fail safely, so that no surface weakens the guarantees of Phases 1 and 2.

#### Acceptance Criteria

1. THE Mastery_Engine, Analysis_Pipeline, and Dissection_Service SHALL import no `fastapi` module and no MCP_Server module, and the import graph among modules under `backend/engines/` SHALL contain 0 cycles, as checked by one assertion inside an existing unit test in the Test_Suite.
2. THE API_App, Crew_Webhook, and MCP_Server SHALL contain no mastery transition, scheduling, scoring, grading, or analysis logic and SHALL call the engines that own that logic: the Mastery_Engine owns transitions, the Pedagogy_Engine owns explanations, the Graph_Engine owns blast radius, the Spec_Grounder owns provenance and drift, the Topology_Profiler owns architecture, the LLM_Router owns structured generation, and the Cache_Store owns persistence.
3. THE Mastery_Engine SHALL read and write state only through the Cache_Store infrastructure and SHALL use exactly one database session per operation.
4. IF a Mastery_Engine operation fails after a write in its session, THEN THE Mastery_Engine SHALL roll back every write of that operation, and a following read SHALL return the values held before the operation began.
5. THE Cache_Store changes needed for Study_Mode, Mastery_Records, and the repository registry SHALL be additive, SHALL preserve every existing public method signature, and SHALL be recorded with a justification in the design.
6. THE new code SHALL NOT execute, import, or install any analyzed code, SHALL keep the ingestion guardrails, and SHALL clone GitHub repositories only through the Phase 1 Ingestion_Engine's shallow `git clone` with `--depth 30` and repository hooks disabled, which this spec leaves unchanged.
7. THE new code SHALL validate every external input (HTTP body, path parameter, MCP argument, webhook body, and LLM output) against a typed schema before any other use of the input.
8. THE new code SHALL NOT write to any log, and SHALL NOT include in any API, MCP, or webhook response, an API key, the value of `KIRO_CREW_SECRET`, a signature, an authorization header, prompt text, or the text of a raw provider exception.
9. IF an invalid repository, missing symbol, invalid lens, invalid answer, provider failure, malformed LLM output, database failure, invalid GitHub URL, exceeded rate limit, missing webhook secret, invalid signature, or MCP tool error occurs, THEN THE affected surface SHALL return an Error_Envelope (API_App and Crew_Webhook) or a failed Tool_Result (MCP_Server) that has a non-empty `code`, a `message` of 1 to 500 characters, and none of the values listed in criterion 8.
10. IF an error listed in criterion 9 occurs, THEN THE affected surface SHALL leave every Mastery_Record and every Study_Mode value unchanged, so that no mastery is granted and no state is advanced.
11. THE new Python code SHALL carry type annotations on all public functions and SHALL pass `ruff check` and `ruff format --check` with the repository configuration, each reporting 0 violations.
12. THE `.env.example` file SHALL gain exactly one line for each new setting (`KIRO_CREW_SECRET`, `STUPID_CODE_CORS_ORIGINS`, the two rate-limit settings, and `ALLOW_LOCAL_INGEST` with the value `true`), each with an empty or default value and no secret.
13. THE Hook_Files SHALL contain no command that deletes, reverts, or modifies a user source file, and a run of either hook SHALL leave the `git status` output of the repository unchanged.

### Requirement 24: Backward Compatibility and Definition of Done

**User Story:** As the project owner, I want proof that nothing regressed and every deliverable exists, so that Phase 3 can be accepted from evidence.

#### Acceptance Criteria

1. WHEN the full suite runs from the repository root with `LLM_PROVIDER=mock`, THE Test_Suite SHALL report 0 failed tests and 0 errors, SHALL report at least the 770 Baseline_Count tests as passing, and SHALL report exactly 4 new property tests as passing, with the final passed total equal to the Baseline_Count plus the new unit test count plus 4.
2. THE implementation report SHALL state the Baseline_Count measured by a pytest run before any change, the new unit test count, the new property test count, and the final passed total, each copied from the summary line of an actual pytest run.
3. THE implementation SHALL leave every Phase 1 and Phase 2 test file byte-identical to its state before this spec's changes, and SHALL record each change to a Phase 1 or Phase 2 source file (expected: `backend/domain/models.py` append, `backend/engines/cache_store.py` additive tables and methods, `backend/engines/llm_router.py` additive mock builder, `backend/api/main.py` router mounting, `backend/pyproject.toml` MCP constraint) with a justification in the design document.
4. WHEN `ruff check backend` and `ruff format --check backend` run from the repository root, THE commands SHALL each exit with code 0 and report 0 violations and 0 files needing reformatting.
5. THE implementation SHALL provide these deliverables, each present as a non-empty file or directory: the seven models and `SocraticGrade` in `backend/domain/models.py`; `backend/engines/mastery.py`; the Analysis_Pipeline and Dissection_Service modules; `backend/api/routes/repos.py`, `autopsy.py`, `mastery.py`, and `crew.py`; `backend/mcp_server/server.py`; `.kiro/settings/mcp.json`; the Power_Package; the Crew_Package; the two Hook_Files; and the two new test files.
6. WHEN verification runs, THE implementation SHALL parse each JSON manifest (`.kiro/settings/mcp.json`, `power/plugin.json`, `power/mcp.json`, `crew/app.json`, both Hook_Files) and confirm each parses without error, and SHALL list the MCP_Server tools and confirm the list contains exactly the five tool names defined in Requirement 16.
7. WHEN the integration check runs, THE implementation SHALL execute one scripted check that ingests a temporary repository through the API_App with the mock provider, reads the Study_Mode value through the API_App and through the MCP tools, and reports that both surfaces returned the same boolean value, with the script exiting with code 0 when the values match.
8. IF the two Study_Mode values in the integration check differ, or either surface returns an error, THEN THE integration script SHALL exit with a non-zero code and report which surface returned which value or error.
9. THE implementation report SHALL contain exactly ten lettered sections in this order: A spec artifacts, B implementation summary, C mastery behavior, D API summary, E MCP summary, F Kiro-native integrations, G test results with the actual numbers from criterion 2, H integration verification, I limitations, and J completion status of exactly one of COMPLETE, PARTIALLY COMPLETE, or BLOCKED.
10. IF any requirement of this spec is not met, THEN THE implementation report SHALL list each unmet requirement number with a one-sentence reason under section I and SHALL set section J to PARTIALLY COMPLETE or BLOCKED.
11. THE implementation SHALL add no Phase 4 work, no frontend code (no web UI page, React component, or static asset), and no deployment configuration (no container, CI pipeline, or hosting file).
