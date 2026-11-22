# Requirements Document

## Introduction

Spec #04 builds the Code Autopsy UI: the React and TypeScript frontend in `ui/` for Stupid Code (Code Autopsy Edition). It consumes the completed backend of Specs #01 to #03 (engines, ingestion, graph, provenance, topology, LLM router, pedagogy, mastery, REST API) without changing that backend. The UI is the Hosted Web App surface named in `product.md`. It adds no business logic that the backend already owns: mastery state, grading, explanations, blast radius, topology, and provenance all come from backend responses.

The UI has a top Command_Bar, a collapsible left Specimen_Rail, a center Canvas (Graph_View and Topology_View), a right Autopsy_Slab with three pedagogical lenses, and an Exorcism_Modal for Study Mode verification. It follows `design-system.md` (clinical X-ray identity, color only as system state) and `architecture.md` (static analysis only, structured outputs, no duplicated logic).

### Scope Lock

- No file under `backend/` (Phases 1 to 3), `power/`, `crew/`, `scripts/`, or `.kiro/specs/01-*` to `03-*` is modified, and no existing backend test is modified. All 798 existing backend tests keep passing.
- No new endpoint, backend feature, engine, deployment configuration, or product feature is added.
- If a real CORS or API contract defect blocks the frontend, the defect is reported with file, issue, and minimal proposed fix, and no change is made until the project owner approves it.

### Verified Backend Contract

Each item below was verified by reading the live code on the date of writing. The UI contract follows these items 1:1.

**Endpoints** (all JSON; `ui/` is the only consumer in this spec):

| Method and path | Request body | Success response |
|---|---|---|
| `GET /health` | none | `{"status": "ok", "service": "stupid-code"}` |
| `GET /api/repos` | none | `RepoSummary[]` sorted by `repo_id`: `repo_id`, `file_count`, `symbol_count`, `study_mode_enabled` |
| `POST /api/repos/ingest` | exactly one of `path` or `url` (non-blank string, at most 4096 characters); optional `max_files`, `max_total_bytes` (integers, 1 to the backend default ceiling) | `IngestResponse`: `repo_id`, `summary` (`file_count`, `symbol_count`, `edge_count`, `dsa_signal_count`), `provenance`, `topology`, `truncated`, `warnings[]` (`kind`, `path`, `detail`) |
| `GET /api/repos/{repo_id}/snapshot` | none | `SnapshotResponse`: `snapshot`, `provenance`, `topology` |
| `POST /api/repos/{repo_id}/explain` | `{target_id: string (1 to 500), lens: "L1_SYNTAX" or "L2_FLOW" or "L3_ARCHITECTURE"}`, no other keys | `ExplainResponse`: `envelope` (`ExplanationEnvelope`), `blast_radius` |
| `GET /api/repos/{repo_id}/vitals` | none | `ComprehensionVitals` |
| `POST /api/repos/{repo_id}/study-mode` | `{enabled: boolean}` (strict boolean) | `{repo_id, study_mode_enabled}` |
| `POST /api/repos/{repo_id}/socratic/start` | `{target_id: string}` | `SocraticCheck`: `repo_id`, `target_id`, `questions[1..2]` |
| `POST /api/repos/{repo_id}/socratic/submit` | `{target_id: string, answers: [{question_id, answer}]}` | `SocraticVerdict` |

**Snapshot shapes.** `RepoGraphSnapshot`: `repo_id`, `root_path` (always `"."` over HTTP), `files[]`, `edges[]`, `vital_organs[]`, `cycles[][]`, `dsa_signals[]`. `FileAnalysis`: `file_path`, `language` (`python`, `typescript`, `javascript`, `tsx`, `java`), `loc`, `ast_hash`, `imports[]`, `exports[]`, `symbols[]`, `parse_errors[]`. `SymbolNode`: `id` (`file_path::qualname`), `name`, `qualname`, `kind` (`function`, `method`, `class`, `interface`, `component`), `file_path`, `start_line`, `end_line`, `signature`, `ast_hash`, `decorators[]`, `is_async`, `raw_calls[]`. `GraphEdge`: `source`, `target`, `edge_type` (`imports` between file paths, `calls` between symbol ids). `vital_organs` and each entry of `cycles` hold node ids, which are file paths or symbol ids. `DSASignal`: `symbol_id`, `file_path`, `start_line`, `end_line`, `chapter`, `pattern_name`, `confidence`, `evidence[]`.

**Provenance shape.** `ProvenanceReport`: `repo_id`, `has_kiro_specs`, `spec_links` (object keyed by file path, values `SpecLink[]` with `spec_name`, `source_file`, `section_title`, `excerpt` of 1 to 300 characters, `confidence`), `drift_items[]` (`drift_type` of `UNSPECIFIED_CODE` or `UNIMPLEMENTED_SPEC`, `target`, `details`), `recent_commits` (object keyed by file path, values are opaque strings, newest first, at most 20 per file, produced as `<short hash>|<subject>` by a read-only `git log`). For `UNSPECIFIED_CODE` the `target` is a snapshot file path. For `UNIMPLEMENTED_SPEC` the `target` is a path referenced by a spec task that is not found in the snapshot.

**Topology shape.** `TopologyProfile`: `repo_id`, `detected_pattern` (`Hexagonal / Clean Architecture`, `Layered MVC`, `Feature-Sliced`, `Modular Monolith`, `Flat / Script`), `confidence` (0 to 1), `directory_roles` (object keyed by directory path, role one of `domain`, `engines`, `api`, `ui`, `tests`, `config`, `infrastructure`, `services`, `entry_points`, `other`), `boundary_metrics` (exactly `max_depth`, `cross_folder_import_ratio`, `domain_isolation_score`, `entry_point_count`; the two ratio and score values are 0 to 1), `evidence[]`.

**Explanation shapes.** `ExplanationEnvelope`: `repo_id`, `target_id`, `ast_hash`, `lens`, `cached`, and exactly one of `l1`, `l2`, `l3` (the other two are `null`). `L1`: `target_id`, `language`, `summary`, `annotations[]` (`line_start`, `line_end`, `construct`, `explanation`, `what_if_removed`), `key_takeaway`. `L2`: `target_id`, `execution_steps[]` (`step_number`, `location`, `action`, `data_transformation`), `upstream_callers[]`, `downstream_callees[]`, `side_effects[]`, `dsa_cards[]` (`chapter`, `pattern_name`, `start_line`, `end_line`, `why_used_here`, `time_complexity`, `space_complexity`), `llm_content_available` (false when the backend returned a degraded result). `L3`: `target_id`, `topology_pattern`, `why_this_folder_structure`, `structural_evidence[1..20]`, `alternatives[]` (`pattern_name`, `why_not_chosen`, `when_to_switch`), `spec_rationale` (string or `null`). `BlastRadius`: `target_id`, `upstream_callers[]`, `downstream_callees[]`, `impact_score` (0 to 1).

**Explain targets.** L1 and L2 accept only a snapshot symbol id. L3 accepts only the `repo_id` or a key of `topology.directory_roles`. A file path is not a valid explain target for any lens. The L3 blast radius is always empty with `impact_score` 0.

**Mastery shapes.** `MasteryState`: `UNAUDITED`, `DISSECTED`, `MASTERED`, `STALE`. `ComprehensionVitals`: `repo_id`, `study_mode_enabled`, `total_modules`, `unaudited_count`, `dissected_count`, `mastered_count`, `stale_count`, `mastery_percentage` (0 to 100), `due_for_review[]` (symbol ids), `file_states` (object keyed by file path, one `MasteryState` per file by the weakest-link rule). Mastery is stored per symbol only. A file with no tracked symbol has no key in `file_states`. The API exposes no per-symbol mastery state. `SocraticQuestion`: `question_id`, `target_id`, `prompt`, `line_reference`, `expected_concepts` (always `[]` in the start response). `SocraticVerdict`: `target_id`, `passed`, `score` (0 to 1), `feedback`, `new_state`, `next_review_at` (UTC string or `null`).

**Socratic rules.** `target_id` must be a snapshot symbol id. `socratic/start` and `socratic/submit` return 409 `study_mode_disabled` while Study Mode is off. A submit must hold exactly one answer per question, each `question_id` once, each answer 1 to 2000 characters after trimming. A blank, missing, duplicate, or foreign answer yields 422 `invalid_answers`; the contract has no representation for a missing answer. `passed` is `score >= 0.7`. A failed submit for a symbol that is already `MASTERED` returns `new_state` `MASTERED` with its existing `next_review_at` and `passed` false.

**Study Mode side effect.** While Study Mode is on, an L1 or L2 explain moves an `UNAUDITED` symbol to `DISSECTED`. L3 explain changes no mastery.

**Errors.** Every non-2xx response body is `{"error": {"code": string, "message": string}}`, the message is 1 to 500 characters, fixed, and free of stack traces. Codes seen on these routes: `malformed_request` (400), `validation_error` (422), `invalid_limit` (422), `local_ingest_disabled` (403), `rate_limited` (429 with a `Retry-After` header, GitHub `url` ingests only), `repo_not_found` (404), `unknown_target` (404), `source_unreadable` (409), `study_mode_disabled` (409), `invalid_answers` (422), `llm_unavailable` (503), `invalid_llm_output` (502), `grading_unavailable` (503), `storage_error` (500), `analysis_failed` (500), `no_supported_files` (422), `internal_error` (500), `not_found` (404), `method_not_allowed` (405), plus lower-case ingestion error kinds (400, 422, 500, 504). Unknown paths and methods use the same envelope.

**CORS.** The backend allows the origins in `STUPID_CODE_CORS_ORIGINS`, defaulting to `http://localhost:5173`, `http://localhost:3000`, `http://127.0.0.1:5173`, `http://127.0.0.1:3000`. It rejects the `*` wildcard, allows only `GET` and `POST`, allows the headers `Content-Type`, `X-Kiro-Signature`, `X-Crew-Proxy`, allows no credentials, and exposes no response headers beyond the browser defaults. The Vite dev proxy makes the dev server same-origin, so no CORS issue arises. A cross-origin `VITE_API_BASE_URL` needs its origin in `STUPID_CODE_CORS_ORIGINS`, and `Retry-After` is then unreadable. No CORS defect blocking the UI was found.

### Recorded Contract Mismatches

The requested UI features below do not match the live backend. Each is handled by a graceful-degradation requirement, and no API is invented.

1. **No source text endpoint.** No route returns file or symbol source. The UI shows line ranges, signatures, and backend text, and never shows source code.
2. **No standalone blast-radius route.** `BlastRadius` returns only inside the explain response and only for symbols. File nodes have no backend blast radius.
3. **No per-symbol or per-file-record mastery.** Only `file_states` (per file, weakest-link) and aggregate counts exist. Files with no tracked symbol have no state.
4. **No ingestion progress stream.** Ingest is one blocking request. Progress is an indeterminate in-flight state.
5. **Recent commits are opaque strings** and may be absent for any file or for the whole repository.
6. **Spec evidence is per file.** `spec_links` is keyed by file path and drift items carry no spec links.
7. **Missing Socratic answers have no contract representation.** The UI cannot submit a blank answer.
8. **`expected_concepts` is empty** in the start response, so no answer key is available to reveal.
9. **No `GET` for one repository.** Repository detail comes from `GET /api/repos/{repo_id}/snapshot`.
10. **`ast_hash` exists only as stored values.** The UI displays the value as the backend returns it and applies no normalization of its own.

### Open Decision for the Project Owner

`design-system.md` states that the Autopsy Mode and Lab Mode toggle maps to Study Mode OFF and ON. The Spec #04 request defines Autopsy and Lab as a visual-only toggle, separate from the Study Mode switch. These requirements follow the request: two independent controls. Requirement 10 and Requirement 9 isolate the two so that a later decision changes only the control wiring.

## Glossary

- **Autopsy_UI**: The React and TypeScript application in `ui/`.
- **Backend_API**: The FastAPI application of Spec #03, reached through the Vite dev proxy or `VITE_API_BASE_URL`.
- **API_Client**: The single TypeScript module through which every Autopsy_UI view calls the Backend_API.
- **Contract_Types**: The TypeScript types in `ui/` that mirror the Verified Backend Contract field for field.
- **App_Store**: The single shared client state holding the selected repository, selected file, selected symbol, selected graph node, active view, active lens, Study Mode, and visual mode.
- **Command_Bar**: The top region holding the Repo_Selector, the Ingest button, the Vitals_Meter, the Study_Mode_Switch, and the Visual_Mode_Toggle.
- **Repo_Selector**: The Command_Bar control listing repositories from `GET /api/repos`.
- **Ingest_Modal**: The dialog that submits `POST /api/repos/ingest`.
- **Vitals_Meter**: The Command_Bar display of `ComprehensionVitals`.
- **Study_Mode_Switch**: The Command_Bar switch bound to `POST /api/repos/{repo_id}/study-mode`.
- **Visual_Mode_Toggle**: The Command_Bar toggle between `Autopsy` and `Lab` visual modes.
- **Specimen_Rail**: The collapsible left panel holding the File_Tree, Vital_Organs_List, and Drift_Panel.
- **File_Tree**: The folder and file tree built from `snapshot.files`.
- **Vital_Organs_List**: The quick-jump list built from `snapshot.vital_organs`.
- **Drift_Panel**: The panel built from `provenance.drift_items` and `provenance.spec_links`.
- **Canvas**: The center region holding exactly one active view, Graph_View or Topology_View.
- **Graph_View**: The @xyflow/react skeletal X-ray graph of `snapshot.edges`.
- **Topology_View**: The folder topology blueprint built from `TopologyProfile`.
- **Autopsy_Slab**: The right drawer for the selected file or symbol.
- **Lens**: One of `L1_SYNTAX`, `L2_FLOW`, `L3_ARCHITECTURE`.
- **Exorcism_Modal**: The dialog for a Socratic check in Study Mode.
- **Mastery_Indicator**: The visual and textual marker of a `MasteryState` on a node, tree row, or count.
- **Shroud**: The haunted overlay on a node whose mastery state is `UNAUDITED` in Autopsy visual mode.
- **Unaudited_Fallback**: The neutral marker for a file that has no key in `file_states`.
- **Selection_Sync**: The rule that File_Tree, Graph_View, Vital_Organs_List, Drift_Panel, and Autopsy_Slab all read the one selection in the App_Store.
- **Deep_Link**: A URL whose query holds `repo_id`, `file`, and `view` parameters.
- **Test_Suite**: The Vitest and React Testing Library tests in `ui/`.
- **Drift_Entry**: One element of `provenance.drift_items`, with `drift_type`, `target`, and `details`.
- **Lens_Panel**: The Autopsy_Slab region that shows the content of the active Lens.
- **Explain_Target**: The `target_id` sent in an explain request: a symbol id for `L1_SYNTAX` and `L2_FLOW`, and the `repo_id` or a key of `directory_roles` for `L3_ARCHITECTURE`.
- **Explain_Cache**: The session-scoped store of successful explain responses keyed by `repo_id`, Explain_Target, and Lens.
- **Blast_Radius_Chip**: A text chip in the Autopsy_Slab that shows one id of `blast_radius.upstream_callers` or `blast_radius.downstream_callees` with its direction.
- **DSA_Card**: The display of one `dsa_cards` entry in the `DSA-in-the-Wild` section.
- **Counterfactual_Tradeoff_Matrix**: The table in the L3 Lens_Panel that compares `topology_pattern` with `alternatives`.
- **Backend_Suite**: The existing backend pytest suite of Specs #01 to #03.
- **Graceful_Degradation**: The behavior of showing a naming text or omitting an element, and generating no substitute value, when the Backend_API provides no data for it.
- **Implementer**: The person or agent that carries out the implementation of this spec.

## Requirements

### Requirement 1: Frontend Project and Toolchain

**User Story:** As a developer, I want a reproducible Vite project in `ui/`, so that I can run, build, and test the Autopsy_UI with standard commands.

#### Acceptance Criteria

1. THE `ui/package.json` SHALL declare React, TypeScript, Vite, Tailwind CSS, `@xyflow/react`, `dagre`, `lucide-react`, Vitest, and `@testing-library/react` as dependencies or devDependencies.
2. THE `ui/package.json` SHALL define the npm scripts `dev`, `build`, `test`, and `typecheck`.
3. WHEN `npm test` runs, THE Test_Suite SHALL execute once without watch mode and SHALL exit.
4. THE Autopsy_UI SHALL enable TypeScript strict mode.
5. IF the TypeScript compiler finds a type error, THEN `npm run typecheck` and `npm run build` SHALL each exit with a non-zero code.
6. THE Vite dev server SHALL proxy `/api/*` and `/health` to `http://127.0.0.1:8000`, forwarding the request path unchanged.
7. WHERE `VITE_API_BASE_URL` is set to a non-empty value, THE API_Client SHALL remove one or more trailing `/` characters from the value and SHALL prefix every request path with the result.
8. WHILE `VITE_API_BASE_URL` is unset or empty, THE API_Client SHALL send requests to relative paths.
9. THE Autopsy_UI SHALL contain no absolute `http://` or `https://` URL in `ui/src`, except the validation prefix `https://github.com/`.
10. THE Autopsy_UI build output SHALL reference no external host, and fonts and assets SHALL load from the local bundle.
11. THE `ui/` directory SHALL contain a committed package lockfile.
12. THE Test_Suite SHALL send no request to the Backend_API or to any external host.

### Requirement 2: Centralized Contract-First API Client

**User Story:** As a developer, I want one typed API client that mirrors the backend 1:1, so that no view guesses a field or endpoint.

#### Acceptance Criteria

1. THE Contract_Types SHALL define every request and response shape of the Verified Backend Contract with the same field names, enum values, optionality, and nullability.
2. THE Contract_Types SHALL type `ExplanationEnvelope` with exactly one non-null tier among `l1`, `l2`, and `l3`, `SocraticVerdict.next_review_at` as `string | null`, and `L3.spec_rationale` as `string | null`.
3. THE API_Client SHALL expose exactly nine operations: `getHealth`, `listRepos`, `ingestRepo`, `getSnapshot`, `explain`, `getVitals`, `setStudyMode`, `startSocratic`, and `submitSocratic`.
4. THE API_Client SHALL be the only module that calls `fetch` or `XMLHttpRequest`.
5. THE API_Client SHALL send each JSON request body with `Content-Type: application/json` and only the keys listed for that endpoint: `target_id` and `lens` for explain, exactly one of `path` or `url` for ingest.
6. THE API_Client SHALL send no body for `getHealth`, `listRepos`, `getSnapshot`, and `getVitals`.
7. THE API_Client SHALL percent-encode `repo_id` as one path segment.
8. WHEN a response has a 2xx status and a valid body, THE API_Client SHALL return the body typed as the matching Contract_Type.
9. WHEN a response has a non-2xx status and a body of the form `{"error": {"code", "message"}}`, THE API_Client SHALL raise an HTTP error carrying the status, the `code`, and the `message`, and SHALL pass an unknown `code` through unchanged.
10. IF a response has a non-2xx status and a body that is not the error envelope, is empty, or is not JSON, THEN THE API_Client SHALL raise an HTTP error with the status and a fixed generic message, and SHALL include no raw body in the error.
11. IF a 2xx response body is empty, is not valid JSON, lacks a required field, or is an explain response whose populated tier does not match the requested lens, THEN THE API_Client SHALL raise a malformed-response error carrying the operation name and no partial data.
12. IF the request fails before an HTTP response arrives, THEN THE API_Client SHALL raise a network error distinct from an HTTP error.
13. WHEN a 429 response carries a `Retry-After` header that is a readable non-negative integer, THE API_Client SHALL include the value in the raised error, and SHALL raise the error without the value for any other header state.
14. WHEN a request is aborted through an `AbortSignal`, THE API_Client SHALL raise an abort error of a type distinct from the HTTP, network, and malformed-response errors, and SHALL send no request WHEN the signal is already aborted.
15. THE API_Client SHALL add no error envelope, retry policy, or response cache beyond the Verified Backend Contract.

### Requirement 3: Consistent Loading, Empty, and Error States

**User Story:** As a user, I want every panel to show clear loading, empty, and failure states, so that I always know what the system is doing.

#### Acceptance Criteria

1. WHILE a request is in flight, THE Autopsy_UI SHALL show a loading state with a text label only in the region that depends on the request, and every other region SHALL stay interactive.
2. WHEN a request returns a valid result whose primary collection is empty (repositories, `snapshot.files`, `vital_organs`, `edges`, `drift_items`, or `total_modules` of 0), THE Autopsy_UI SHALL show an empty state that names what is absent, with no error styling and no retry action.
3. WHEN a request fails with an HTTP error, THE Autopsy_UI SHALL show the envelope `message`.
4. WHEN a request fails with a network error, THE Autopsy_UI SHALL show a fixed connectivity message.
5. WHEN a request fails with a malformed-response error or a non-envelope HTTP error, THE Autopsy_UI SHALL show a fixed generic message.
6. THE Autopsy_UI SHALL show no stack trace, raw response body, exception class name, or bare status code as the only error text.
7. WHEN the user activates retry in an error state, THE Autopsy_UI SHALL re-send the failed request once per activation.
8. WHEN the user activates retry after a network error, THE Autopsy_UI SHALL first call `GET /health` once and SHALL report in text whether the Backend_API answered `{"status": "ok", "service": "stupid-code"}`.
9. IF the health call fails or returns any other result, THEN THE Autopsy_UI SHALL keep the error state and the retry action.
10. IF an explain request fails with `llm_unavailable` or `invalid_llm_output`, THEN THE Autopsy_UI SHALL state that the explanation service is unavailable and SHALL produce no explanation.
11. IF a Socratic request fails with `llm_unavailable`, `invalid_llm_output`, or `grading_unavailable`, THEN THE Autopsy_UI SHALL state that the grading service is unavailable, SHALL make no mastery change, and SHALL keep the Exorcism_Modal inputs and the selection unchanged.
12. IF the error `code` is `rate_limited` and `Retry-After` is readable, THEN THE Autopsy_UI SHALL show the retry action only after that many seconds have elapsed.
13. WHEN a request is aborted or its response is discarded, THE Autopsy_UI SHALL show no error.
14. THE Autopsy_UI SHALL wrap the Canvas and the Autopsy_Slab each in an error boundary that shows a fixed message and a reset action, and the reset action SHALL re-render the region from the App_Store without a page reload.
15. THE Autopsy_UI SHALL use one shared component set for the loading, empty, and error states.
16. THE Autopsy_UI SHALL announce each loading, empty, and error state through a live region and SHALL NOT convey the state by color alone.

### Requirement 4: Shared State

**User Story:** As a user, I want every panel to agree on what is selected, so that I never see conflicting views.

#### Acceptance Criteria

1. THE App_Store SHALL hold exactly these eight values: selected `repo_id` (`string | null`), selected file path (`string | null`), selected symbol id (`string | null`), selected graph node id (`string | null`), active view (`graph | topology`), active Lens (`L1_SYNTAX | L2_FLOW | L3_ARCHITECTURE`), Study Mode (`true | false | unknown`), and visual mode (`Autopsy | Lab`).
2. THE App_Store SHALL start with no selection, view `graph`, Lens `L1_SYNTAX`, Study Mode `unknown`, and the visual mode restored under Requirement 10.
3. THE App_Store SHALL hold each value once, and no component SHALL keep a copy that can diverge.
4. WHEN the selected repository changes, THE App_Store SHALL clear the selected file, symbol, and graph node, SHALL set Study Mode to `unknown`, SHALL discard cached snapshot, vitals, provenance, and Explain_Cache data of the previous repository, and SHALL keep the active view, the active Lens, and the visual mode.
5. WHEN the selected repository changes, THE Autopsy_UI SHALL abort the in-flight requests of the previous repository through their `AbortSignal`.
6. THE App_Store SHALL apply each selection update atomically, so that no render shows a mix of old and new selection values.
7. WHEN a file is selected as a target, THE App_Store SHALL set the selected file and the selected graph node to that file and SHALL clear the selected symbol.
8. WHEN a symbol is selected as a target, THE App_Store SHALL set the selected symbol and the selected graph node to that symbol and SHALL set the selected file to the `file_path` found in the snapshot.
9. IF a selection target is not in the snapshot, including an `UNIMPLEMENTED_SPEC` target that is absent, THEN THE App_Store SHALL leave the selection unchanged.
10. WHEN the selected target equals the current selection, THE App_Store SHALL perform no update.
11. THE App_Store SHALL derive Study Mode only from Backend_API responses and SHALL NOT store Study Mode in browser storage.
12. THE App_Store SHALL persist only the visual mode, in `localStorage`.
13. IF the stored visual mode is invalid, missing, or unreadable, THEN THE App_Store SHALL use `Autopsy` and SHALL show no error.
14. WHEN a response arrives for a repository that is no longer selected, THE Autopsy_UI SHALL discard the response.

### Requirement 5: Application Layout

**User Story:** As a user, I want a dense forensic workstation layout, so that I can inspect code without leaving the screen.

#### Acceptance Criteria

1. THE Autopsy_UI SHALL render the Command_Bar across the full width at the top, the Specimen_Rail on the left, the Canvas in the center, and the Autopsy_Slab on the right, with no overlap among them.
2. THE Specimen_Rail SHALL provide a collapse button whose accessible label states the action and whose expanded state is exposed to assistive technology.
3. WHEN the Specimen_Rail is collapsed, THE Autopsy_UI SHALL keep the selection, send no request, remove the rail controls from the tab order, and show none of their content.
4. WHILE the Specimen_Rail is collapsed, THE Autopsy_UI SHALL give the freed width to the Canvas.
5. WHILE no repository is selected, THE Canvas SHALL show an empty state that directs the user to select or ingest a repository, and THE Autopsy_UI SHALL send no snapshot request.
6. WHEN a repository is selected, THE Autopsy_UI SHALL send `GET /api/repos/{repo_id}/snapshot` and SHALL show a loading state in the Specimen_Rail and in the Canvas until the response arrives.
7. IF the snapshot request fails, THEN THE Autopsy_UI SHALL show an error state with a retry action, SHALL show no data of a previous repository, and SHALL keep the Command_Bar operable.
8. WHEN `snapshot.files` is empty, THE Specimen_Rail and the Canvas SHALL show an empty state.
9. WHILE no file, symbol, or directory is selected, THE Autopsy_Slab SHALL show an empty state and THE Autopsy_UI SHALL send no explain request.
10. THE Autopsy_UI SHALL use the tab order Command_Bar, Specimen_Rail, Canvas, Autopsy_Slab, with a visible focus indicator of at least 3:1 contrast.

### Requirement 6: Repository Selector

**User Story:** As a user, I want to pick from the repositories the backend knows, so that I never see fake data.

#### Acceptance Criteria

1. WHEN the Autopsy_UI loads, THE Repo_Selector SHALL send one `GET /api/repos` request and SHALL list each returned entry in the backend order with `repo_id`, `file_count`, and `symbol_count`.
2. WHILE the list request is in flight, THE Repo_Selector SHALL show a loading state and SHALL block repository selection.
3. WHEN the list is empty, THE Repo_Selector SHALL show an empty state with the Ingest action and no selected repository.
4. IF the list request fails or returns a malformed response, THEN THE Repo_Selector SHALL show an error state with a retry action, SHALL list no repository, and SHALL leave the selection unchanged.
5. WHEN the user activates retry, THE Repo_Selector SHALL send one list request.
6. WHEN the user selects a repository, THE App_Store SHALL set the selected `repo_id` to the returned value verbatim and SHALL apply the repository change of Requirement 4 criterion 4.
7. WHEN the user selects the repository that is already selected, THE Repo_Selector SHALL send no new request and SHALL change no state.
8. THE Repo_Selector SHALL list no repository that the Backend_API did not return, including a repository named by a Deep_Link, by browser storage, or by a failed ingest.
9. WHEN a Deep_Link names a `repo_id`, THE Autopsy_UI SHALL select it only IF the list contains it, and otherwise SHALL show the notice of Requirement 26 criterion 2.
10. WHEN the list is refreshed and the selected repository is absent, THE App_Store SHALL clear the selected repository and THE Canvas SHALL show the empty state of Requirement 5 criterion 5.
11. WHEN the list is refreshed and the selected repository is present, THE Repo_Selector SHALL keep the selection and show the refreshed counts.
12. THE Repo_Selector SHALL render `repo_id` as plain monospace text, visually truncated, with the full value (up to 500 characters) available in a tooltip and to assistive technology.
13. THE Repo_Selector SHALL be operable by keyboard, SHALL carry an accessible name, and SHALL indicate the selected entry.

### Requirement 7: Ingest Modal

**User Story:** As a user, I want to ingest a public GitHub repository or a local path, so that I can analyze new code.

#### Acceptance Criteria

1. WHEN the user activates the Ingest button, THE Autopsy_UI SHALL open the Ingest_Modal with `GitHub URL` preselected, an empty input, focus moved inside, a focus trap, an accessible title, and a close control.
2. THE Ingest_Modal SHALL offer a two-way source choice between `GitHub URL` and `Local path` with one text input.
3. WHEN the user changes the source choice, THE Ingest_Modal SHALL keep the entered text and clear all validation and error messages.
4. WHEN the user submits, THE Ingest_Modal SHALL send exactly one of `url` or `path` according to the source choice, trimmed, and no other key, including no `max_files` and no `max_total_bytes`.
5. IF the input is blank after trimming or longer than 4096 characters, THEN THE Ingest_Modal SHALL show a validation message that names the input and SHALL send no request.
6. IF the source choice is `GitHub URL` and the trimmed input does not start with the case-sensitive prefix `https://github.com/`, THEN THE Ingest_Modal SHALL show a validation message and SHALL send no request.
7. WHILE the ingest request is in flight, THE Ingest_Modal SHALL show an indeterminate progress state, disable the submit control, and send no second request on a click or the Enter key.
8. WHEN the ingest request succeeds, THE Ingest_Modal SHALL show `repo_id`, the four `summary` counts, `truncated` as `Yes` or `No`, and every `warnings` entry in order with `kind`, `path`, and `detail`, or a statement that no warnings were returned.
9. WHEN the ingest request succeeds, THE Autopsy_UI SHALL refresh `GET /api/repos`, SHALL select the returned `repo_id` only IF the user has not selected another repository since the submit, and SHALL load its snapshot and vitals.
10. IF the ingest request fails with an error envelope, THEN THE Ingest_Modal SHALL show the `message`, keep the input, re-enable submit, and leave the selection and the repository list unchanged.
11. IF the error `code` is `rate_limited`, THEN THE Ingest_Modal SHALL state that GitHub ingestion is rate limited and SHALL show the `Retry-After` seconds only WHEN the value was readable.
12. IF the error `code` is `local_ingest_disabled`, THEN THE Ingest_Modal SHALL state that local path ingestion is disabled on this server.
13. IF the ingest request fails with a non-envelope response or a network error, THEN THE Ingest_Modal SHALL show a generic could-not-be-reached message and keep the input.
14. IF a follow-up refresh (list, snapshot, or vitals) fails after a successful ingest, THEN THE Ingest_Modal SHALL keep the success summary, show the error, and offer a retry that repeats only the failed follow-ups.
15. WHEN the user closes the Ingest_Modal through the close control or the Escape key, THE Autopsy_UI SHALL return focus to the Ingest button.
16. WHEN the user closes the Ingest_Modal while the request is in flight, THE Autopsy_UI SHALL dismiss only the display, SHALL NOT abort the request, and SHALL still apply the selection of criterion 9 on success.
17. THE Ingest_Modal SHALL create no repository entry in the UI before the Backend_API confirms the ingest.

### Requirement 8: Comprehension Vitals Meter

**User Story:** As a user, I want a live mastery summary, so that I can see how much of the codebase I have verified.

#### Acceptance Criteria

1. WHEN a repository is selected, THE Vitals_Meter SHALL send one `GET /api/repos/{repo_id}/vitals` request with no body.
2. WHILE no repository is selected, THE Vitals_Meter SHALL show an idle state and THE Autopsy_UI SHALL send no vitals request.
3. WHEN `total_modules` is greater than 0, THE Vitals_Meter SHALL show `mastery_percentage`, `unaudited_count`, `dissected_count`, `mastered_count`, and `stale_count` verbatim from the response, labelled by the mapping of Requirement 11, plus `total_modules` labelled as total tracked symbols, and SHALL recompute none of them.
4. WHILE the vitals request is in flight, THE Vitals_Meter SHALL show a loading state and SHALL show no value of a previous repository.
5. WHEN `total_modules` is 0, THE Vitals_Meter SHALL show an empty state, and SHALL show no percentage and no zero count as progress.
6. IF the vitals request fails, THEN THE Vitals_Meter SHALL show the error `message` or the fixed fallback message with a retry action, and SHALL show no earlier value.
7. WHEN the user activates retry, THE Vitals_Meter SHALL send one vitals request.
8. WHEN a Study Mode change succeeds, WHEN an L1 or L2 explain succeeds while Study Mode is on, or WHEN a Socratic verdict arrives, THE Autopsy_UI SHALL refresh the vitals within 500 ms, and an L3 explain SHALL NOT trigger a refresh.
9. WHEN a vitals response arrives for a repository that is not selected, THE Autopsy_UI SHALL discard the response.
10. WHEN vitals requests overlap, THE Vitals_Meter SHALL show only the response of the latest request.
11. IF a refresh fails, THEN THE Vitals_Meter SHALL replace the earlier values with the error state.
12. THE Vitals_Meter SHALL NOT display `due_for_review` or `file_states` entries.
13. THE Vitals_Meter SHALL expose its values as text with a polite live region and SHALL NOT convey them by color alone.

### Requirement 9: Study Mode Switch

**User Story:** As a user, I want to turn Study Mode on and off, so that I can choose between fast exploration and verified learning.

#### Acceptance Criteria

1. THE Study_Mode_Switch SHALL show the `study_mode_enabled` value that the Backend_API returned for the selected repository.
2. WHILE no repository is selected or Study Mode is `unknown`, THE Study_Mode_Switch SHALL be disabled with `aria-disabled` and SHALL show neither state as a backend value.
3. WHEN the user toggles the Study_Mode_Switch, THE Autopsy_UI SHALL send exactly one `POST /api/repos/{repo_id}/study-mode` with `{"enabled": <negation of the displayed value>}`.
4. WHILE the study-mode request is in flight, THE Study_Mode_Switch SHALL set `aria-busy`, SHALL keep showing the previous value, and SHALL ignore further toggles.
5. WHEN the request succeeds, THE Study_Mode_Switch SHALL show the response value, THE App_Store SHALL store it, THE Repo_Selector entry SHALL be updated, and THE Autopsy_UI SHALL refresh the vitals.
6. IF the request fails, THEN THE Study_Mode_Switch SHALL keep the previous value, SHALL show the envelope `message` or the connectivity message, SHALL show no success indication, and SHALL offer a retry.
7. IF the vitals refresh fails after a successful study-mode request, THEN THE Study_Mode_Switch SHALL keep the new value and THE Vitals_Meter SHALL show its error state.
8. WHEN the selected repository changes while the request is in flight, THE Autopsy_UI SHALL discard the response and show no error.
9. WHILE Study Mode is on, THE Autopsy_UI SHALL show a persistent text label `Study Mode ON` and the Exorcism action.
10. WHILE Study Mode is off, THE Autopsy_UI SHALL hide the Exorcism action and SHALL show no quiz and no Socratic prompt.
11. WHEN Study Mode turns off while the Exorcism_Modal is open, THE Autopsy_UI SHALL close the modal, discard unsent answers, and send no submit request.
12. IF a `socratic/start` or `socratic/submit` request fails with `study_mode_disabled`, THEN THE Autopsy_UI SHALL treat Study Mode as off, hide the Exorcism action, and refresh the vitals.
13. THE Study_Mode_Switch SHALL expose `role="switch"`, an accessible name, its checked state, and operation by the Space key.
14. THE Study_Mode_Switch and THE Visual_Mode_Toggle SHALL NOT change each other.

### Requirement 10: Visual Mode Toggle and Design System

**User Story:** As a user, I want an Autopsy and a Lab visual mode, so that I can choose between a forensic overlay and a distraction-free darkroom.

#### Acceptance Criteria

1. WHEN the user activates the Visual_Mode_Toggle, THE Autopsy_UI SHALL apply the new visual mode within 100 ms, with no page reload and no network request.
2. THE Visual_Mode_Toggle SHALL default to `Autopsy` when no valid stored value exists.
3. WHEN the user changes the visual mode, THE Autopsy_UI SHALL store the value in `localStorage` and SHALL restore it before the first Canvas render on the next load.
4. IF the stored value is invalid or `localStorage` throws, THEN THE Autopsy_UI SHALL use `Autopsy` or keep the in-memory value and SHALL show no error.
5. THE Visual_Mode_Toggle SHALL change presentation only, and SHALL leave the selection, active view, active Lens, Study Mode, and data unchanged.
6. THE Autopsy_UI SHALL reference colors only through named tokens: obsidian `#09090B`, elevated surface `#111113`, bone-white `#F4F4F5`, muted zinc `#A1A1AA`, hairline border `#27272A`, crimson `#DC2626`, secondary red `#EF4444`, emerald `#10B981`, and one amber token.
7. THE Autopsy_UI SHALL use the amber token only for `STALE`.
8. THE Autopsy_UI SHALL use crimson and red only for circular dependencies, spec drift, blast-radius risk, `UNAUDITED`, failed verification, and critical diagnostics.
9. THE Autopsy_UI SHALL use emerald only for `MASTERED`, passed verification, and other verified states.
10. THE Autopsy_UI SHALL use a sans-serif face for interface text and a monospace face for code, identifiers, paths, hashes, and diagnostic output.
11. THE Autopsy_UI SHALL contain no purple gradient, no glow or bloom (a blurred halo in a state color), no ghost, no pumpkin, and no decoration that maps to no engineering state.
12. WHILE the visual mode is `Autopsy`, THE Autopsy_UI SHALL show a coordinate grid on the Canvas, the Shroud with a static layer on `UNAUDITED` nodes, and a crimson fracture with a pulse on circular edges.
13. WHILE the visual mode is `Lab`, THE Autopsy_UI SHALL omit the grid, the static layer, and the pulse, and SHALL keep every marker, text, icon, and state color.
14. WHEN the operating system reports `prefers-reduced-motion: reduce`, THE Autopsy_UI SHALL disable the pulse and every other animation in both visual modes and SHALL keep the non-animated markers.
15. THE grid and THE Shroud SHALL be non-interactive, and node labels SHALL have a contrast of at least 4.5:1 against their background.
16. THE Visual_Mode_Toggle SHALL expose an accessible name, its pressed state, a visible text label of the current mode, keyboard operation, and a visible focus indicator.

### Requirement 11: Mastery State Presentation

**User Story:** As a user, I want each mastery state to be unmistakable without relying on color, so that every user can read the state.

#### Acceptance Criteria

1. THE Autopsy_UI SHALL render each Mastery_Indicator with a text label, a distinct icon, and a color for each of `UNAUDITED` (crimson), `DISSECTED` (bone-white or zinc), `MASTERED` (emerald), `STALE` (amber), `NO TRACKED SYMBOLS` (neutral zinc), and `STATE UNKNOWN` (neutral zinc).
2. THE label of a Mastery_Indicator for a `MasteryState` SHALL equal the `MasteryState` value.
3. WHEN a file path has no key in `file_states` after a successful vitals response, THE Autopsy_UI SHALL show `NO TRACKED SYMBOLS` in neutral zinc and SHALL NOT show crimson, emerald, or amber for that file.
4. WHILE the vitals request is loading, has failed, or has not been sent, THE Autopsy_UI SHALL show `STATE UNKNOWN` in neutral zinc for every file and SHALL NOT infer a state from a previous repository or a discarded response.
5. THE Autopsy_UI SHALL derive each per-file Mastery_Indicator only from `file_states`, and not from counts, `due_for_review`, or an explain response.
6. WHEN a symbol is selected, THE Autopsy_UI SHALL show the Mastery_Indicator of its file with the text `File-level state` and SHALL show no per-symbol state.
7. THE Autopsy_UI SHALL contain one pure mapping module from state to label, icon, and color token, used by every component, and THE Test_Suite SHALL verify that each state has a distinct label, icon, and color token.
8. IF a `file_states` value is not a known `MasteryState`, THEN THE Autopsy_UI SHALL show `STATE UNKNOWN` and SHALL NOT crash.
9. THE Autopsy_UI SHALL expose each Mastery_Indicator label as text to assistive technology.
10. WHEN one vitals response arrives, THE Autopsy_UI SHALL update every region that shows a Mastery_Indicator at once.
11. WHILE the visual mode is `Lab`, THE Autopsy_UI SHALL keep the label, icon, and color of each Mastery_Indicator and SHALL omit only the Shroud and the static layer.

### Requirement 12: Specimen Rail File Tree

**User Story:** As a user, I want a file tree from the real snapshot, so that I can navigate the repository.

#### Acceptance Criteria

1. THE File_Tree SHALL build its folders and files from the `/`-separated segments of `file_path` values of `snapshot.files` and SHALL create no row for a path segment that no `file_path` contains.
2. THE File_Tree SHALL list folders before files and sort each group in ascending code-unit order, independent of the input order.
3. WHEN the user activates a folder row, THE File_Tree SHALL toggle the folder, SHALL expose `aria-expanded`, and SHALL change no selection.
4. WHEN the File_Tree first renders, THE File_Tree SHALL show every folder collapsed except the ancestors of the selected file.
5. WHEN the user selects a file row, THE App_Store SHALL select the file as defined in Requirement 4 criterion 7.
6. THE File_Tree SHALL show the `language` value of each file verbatim in a badge.
7. THE File_Tree SHALL show the Mastery_Indicator of each file as defined in Requirement 11.
8. WHERE a file has symbols, THE File_Tree SHALL list them as child rows labelled with `qualname` and `kind`, sorted by `start_line` and then by `id`.
9. WHEN the user selects a symbol row, THE App_Store SHALL select the symbol as defined in Requirement 4 criterion 8.
10. THE File_Tree SHALL show no Mastery_Indicator on a symbol row.
11. WHEN a file has a non-empty `parse_errors` list, THE File_Tree SHALL label the row `PARSE ERRORS` and the row SHALL stay selectable.
12. WHEN `snapshot.files` is empty, THE File_Tree SHALL show an empty state.
13. WHILE the snapshot is loading or has failed, THE File_Tree SHALL show the loading or error state of Requirement 3.
14. WHEN the selection changes from any source, THE File_Tree SHALL mark the selected row `aria-selected`, expand its ancestors, and scroll the row into view.
15. THE File_Tree SHALL use the roles `tree`, `treeitem`, and `group`, and an accessible name.
16. THE File_Tree SHALL use a roving `tabindex` and SHALL support the ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Home, and End keys.
17. WHEN the File_Tree holds more than 1,000 rows, THE File_Tree SHALL move focus within 100 ms of a key press.
18. THE File_Tree SHALL render all backend text as plain text.

### Requirement 13: Vital Organs Quick-Jump

**User Story:** As a user, I want to jump to the most central nodes, so that I can start with the code that matters most.

#### Acceptance Criteria

1. THE Vital_Organs_List SHALL list every entry of `snapshot.vital_organs` in the backend order, with no re-sorting, no deduplication, and no dropped entry.
2. WHEN a vital organ id equals a snapshot file path, THE Vital_Organs_List SHALL label the entry `FILE` with an icon.
3. WHEN a vital organ id equals a snapshot symbol id, THE Vital_Organs_List SHALL label the entry `SYMBOL` and show its `qualname` and `file_path`.
4. WHEN a vital organ id equals neither, THE Vital_Organs_List SHALL label the entry `UNRESOLVED`, set `aria-disabled`, and change no store value on activation.
5. WHEN the user selects a `FILE` entry, THE App_Store SHALL select the file as defined in Requirement 12 criterion 5.
6. WHEN the user selects a `SYMBOL` entry, THE App_Store SHALL select the symbol as defined in Requirement 12 criterion 9.
7. WHEN `snapshot.vital_organs` is empty, THE Vital_Organs_List SHALL show an empty state stating that the backend reported no vital organs.
8. WHEN an entry is selected while the Graph_View is the active view and the node exists in the current layer, THE Graph_View SHALL center the viewport on the node.
9. WHEN an entry is selected while the Graph_View is active and the node is absent from the current layer, THE Graph_View SHALL leave the viewport unchanged and THE App_Store SHALL keep the selection.
10. WHEN an entry is selected while the Topology_View is active, THE App_Store SHALL update the selection without switching the view, and THE Graph_View SHALL center on the node at its next activation.
11. WHEN the repository or the snapshot changes, THE Vital_Organs_List SHALL rebuild from the new snapshot.
12. THE Vital_Organs_List SHALL render each entry as a keyboard-focusable button operable by Enter and Space, with an accessible list name, and SHALL mark the selected entry with `aria-current` and a non-color marker.
13. THE Vital_Organs_List SHALL render plain text and SHALL show no rank or score that the backend did not return.

### Requirement 14: Spec Drift and Provenance Panel

**User Story:** As a user, I want to see where code and specs disagree, so that I can find unspecified code and unimplemented spec items.

#### Acceptance Criteria

1. THE Drift_Panel SHALL list every Drift_Entry in the backend order.
2. THE Drift_Panel SHALL show `drift_type`, `target`, and `details` of each Drift_Entry as plain text, with `target` untruncated.
3. THE Drift_Panel SHALL provide a filter with the options `All`, `UNSPECIFIED_CODE`, and `UNIMPLEMENTED_SPEC`, default `All`, and SHALL show the count of each option, where a count of 0 is allowed.
4. WHEN the filtered list is empty, THE Drift_Panel SHALL show `No entries of this type`.
5. WHEN the selected repository changes, THE Drift_Panel SHALL reset the filter to `All`.
6. THE Drift_Panel SHALL style each Drift_Entry in crimson and SHALL show the `drift_type` as text.
7. WHEN the user selects a Drift_Entry whose `target` equals a snapshot `file_path` by exact, case-sensitive comparison, THE App_Store SHALL select that file.
8. WHEN a Drift_Entry `target` equals no snapshot `file_path`, THE Drift_Panel SHALL show the entry as non-navigable with the label `NOT IN SNAPSHOT` and SHALL change no selection or highlight on activation.
9. WHEN a Drift_Entry is selected and the Graph_View is active and the target node exists, THE Graph_View SHALL highlight the target node.
10. WHERE the selected file has spec links, THE Drift_Panel SHALL show each link's `spec_name`, `source_file`, `section_title`, and `excerpt` as plain text exactly as returned and in the backend order, with no HTML or Markdown interpretation.
11. WHEN the selected file has no spec links and `has_kiro_specs` is true, THE Drift_Panel SHALL show `No spec links for this file`.
12. WHEN `has_kiro_specs` is false, THE Drift_Panel SHALL state that the repository has no `.kiro/specs/` documents and SHALL show no drift or evidence placeholder.
13. WHEN `has_kiro_specs` is true and `drift_items` is empty, THE Drift_Panel SHALL state that no drift was detected and SHALL show all filter counts as 0.
14. THE Drift_Panel SHALL show nothing that the Backend_API did not return and SHALL compute no drift locally.
15. WHILE the provenance data is loading or has failed, THE Drift_Panel SHALL show the loading or error state of Requirement 3.
16. THE Drift_Panel SHALL be keyboard operable, with accessible names that include the `drift_type` and the `target`.
17. THE Drift_Panel SHALL NOT show recent commits, because the Autopsy_Slab shows them under Requirement 18.

### Requirement 15: Skeletal X-Ray Graph

**User Story:** As a user, I want a graph of the real dependency structure, so that I can see how the code connects.

#### Acceptance Criteria

1. THE Canvas SHALL provide a view switch between `Graph` and `Topology` with `tablist` semantics, and the active view SHALL be held in the App_Store.
2. THE Graph_View SHALL render with `@xyflow/react`.
3. THE Graph_View SHALL offer a layer switch with default `Files` (one node per `file_path`, only `imports` edges) and `Symbols` (one node per symbol `id`, only `calls` edges).
4. THE Graph_View SHALL build nodes and edges only from `snapshot.files` and `snapshot.edges`.
5. WHEN an edge has an endpoint that is not a node of the active layer, THE Graph_View SHALL omit the edge and SHALL create no node for the endpoint.
6. THE Graph_View SHALL compute node positions with a deterministic layered layout independent of the input order of nodes and edges.
7. THE Graph_View SHALL memoize the layout per snapshot and layer, and SHALL NOT recompute it on a selection change.
8. THE Graph_View SHALL render a node with no edge as an isolated node inside the layout bounds.
9. THE Graph_View SHALL treat an edge as circular WHEN both endpoints are in the same entry of `snapshot.cycles`, in both layers, and SHALL render a circular edge with crimson fracture styling and the text marker `CIRCULAR`, and every other edge as non-circular.
10. THE Graph_View SHALL style each file node by its Mastery_Indicator of Requirement 11, including the `NO TRACKED SYMBOLS` and `STATE UNKNOWN` fallbacks.
11. WHILE the visual mode is `Autopsy`, THE Graph_View SHALL draw the Shroud only on nodes whose indicator is `UNAUDITED`, and SHALL NOT draw it on fallback or unknown-state nodes.
12. WHEN the state of a file changes from `UNAUDITED` to `MASTERED`, THE Graph_View SHALL remove the Shroud and show the emerald `MASTERED` indicator.
13. WHILE the `Symbols` layer is active, THE Graph_View SHALL style each symbol node with the Mastery_Indicator of its file and label it as file-level.
14. WHILE the snapshot is loading, THE Graph_View SHALL show a loading state.
15. WHEN the active layer has no nodes, THE Graph_View SHALL show an empty state that names the layer.
16. IF the snapshot request fails, THEN THE Graph_View SHALL show an error state with a retry action and no stale node.
17. THE Graph_View SHALL contain no hardcoded node or edge in production code.
18. THE Graph_View SHALL provide an accessible text alternative that lists the selected node id with its incoming and outgoing edge counts, or states that nothing is selected.
19. WHEN the active layer holds more than 300 nodes, THE Graph_View SHALL enable the `@xyflow/react` `onlyRenderVisibleElements` option.
20. WHEN the user switches the layer, THE App_Store SHALL keep the selected graph node only IF it exists in the new layer, and otherwise SHALL clear the selected graph node and leave the selected file unchanged.

### Requirement 16: Graph Selection and Blast Radius

**User Story:** As a user, I want to select a node and see what it affects, so that I can judge the impact of a change.

#### Acceptance Criteria

1. WHEN the user clicks a node, THE App_Store SHALL set the selected graph node and Selection_Sync SHALL select the matching file or symbol.
2. WHEN a node is selected, THE Graph_View SHALL highlight the node, its one-hop upstream nodes (sources of edges into the node), and its one-hop downstream nodes (targets of edges from the node) from the edges of the active layer, and SHALL dim every other node and edge.
3. WHEN the selected node is a symbol and an explain response for it exists in the session, THE Graph_View SHALL mark the ids of `blast_radius.upstream_callers` and `blast_radius.downstream_callees` as the blast radius and SHALL show `impact_score` as text labelled `from blast-radius result`.
4. WHEN the selected node is a symbol with no explain response, THE Graph_View SHALL use the `calls` edges of the snapshot, label the highlighting `derived from snapshot`, and show no `impact_score`.
5. WHEN the selected node is a file, THE Graph_View SHALL use the `imports` edges of the snapshot, label the highlighting `derived from snapshot`, and show no `impact_score`.
6. THE Graph_View SHALL style blast-radius members in crimson with a text marker and SHALL NOT use emerald for them.
7. WHEN the user clicks the Canvas background, THE App_Store SHALL clear the selected graph node, and THE Graph_View SHALL remove the dimming, the blast-radius styling, and the score text.
8. WHEN a blast-radius id is not a node of the active layer, THE Graph_View SHALL skip the id and SHALL create no node.
9. THE Graph_View SHALL make nodes focusable, SHALL select a focused node on Enter or Space, and SHALL clear the selection on Escape.
10. WHEN the selected node has no neighbors, THE Graph_View SHALL keep it highlighted and its text alternative SHALL state `No upstream or downstream nodes`.
11. WHEN the layer or the repository changes, THE Graph_View SHALL clear the node selection and styling unless the id exists in the new layer.
12. WHEN the selected symbol changes, THE Graph_View SHALL discard the blast radius of the symbol that is no longer selected.
13. THE Graph_View SHALL NOT call the Backend_API itself, and SHALL use a blast radius only from an explain response that the Autopsy_Slab requested.

### Requirement 17: Folder Topology Blueprint

**User Story:** As a user, I want a blueprint of how the folders are organized, so that I can read the architecture at a glance.

#### Acceptance Criteria

1. THE Topology_View SHALL display `detected_pattern` as returned, including `Flat / Script`, and display `confidence` as a rounded whole percentage.
2. THE Topology_View SHALL list each key of `directory_roles` once with its role in monospace, sorted by code point, and SHALL show an unknown role value as plain text.
3. THE Topology_View SHALL display `domain_isolation_score` and `cross_folder_import_ratio` with two decimals and `max_depth` and `entry_point_count` as integers, each labelled with its key name.
4. THE Topology_View SHALL list every `evidence` entry in order as plain text.
5. WHEN the user selects a directory row, THE Autopsy_UI SHALL set the Autopsy_Slab target to that directory, switch the active Lens to `L3_ARCHITECTURE`, and mark the row selected.
6. THE Topology_View directory rows SHALL offer only `L3_ARCHITECTURE` and no `L1_SYNTAX` or `L2_FLOW`.
7. IF `directory_roles` or `evidence` is empty, THEN THE Topology_View SHALL show an empty state for that section and SHALL still show the other sections.
8. THE Topology_View SHALL show no classification, role, or metric that the Backend_API did not return.
9. WHEN the user switches between Graph_View and Topology_View, THE App_Store SHALL keep the selected file and symbol.
10. WHILE the snapshot is loading or has failed, THE Topology_View SHALL show the loading or error state of Requirement 3.

### Requirement 18: Autopsy Slab Metadata

**User Story:** As a user, I want the facts about the selected file or symbol in one drawer, so that I can ground every explanation.

#### Acceptance Criteria

1. WHEN a file is selected, THE Autopsy_Slab SHALL display the path, `language`, `loc`, `ast_hash`, and the file-level Mastery_Indicator from `file_states` only (`NO TRACKED SYMBOLS` or `STATE UNKNOWN` as defined in Requirement 11).
2. WHEN a symbol is selected, THE Autopsy_Slab SHALL display `qualname`, `kind`, `signature`, `start_line` to `end_line`, `ast_hash`, its file path, and the file-level Mastery_Indicator labelled as file-level, with no per-symbol state.
3. THE Autopsy_Slab SHALL display each `ast_hash` verbatim in monospace with a copy control, and IF the clipboard write fails, THEN THE Autopsy_Slab SHALL show a copy-failed message and keep the text selectable.
4. WHEN an explain response for the current target exists, THE Autopsy_Slab SHALL display `envelope.ast_hash` and a `cached` or `fresh` label, and OTHERWISE SHALL omit both with no placeholder.
5. WHERE `provenance.recent_commits` has entries for the selected file, THE Autopsy_Slab SHALL list at most 20 as plain text, newest first, showing the text before the first `|` as the hash and the rest as the subject, and a string without `|` as one text.
6. WHEN the selected file has no commits, THE Autopsy_Slab SHALL state that no commit history is available.
7. WHERE the selected file has spec links, THE Autopsy_Slab SHALL list the excerpts as defined in Requirement 14 criterion 10.
8. WHEN a directory is selected under `L3_ARCHITECTURE`, THE Autopsy_Slab SHALL show its path and role and no file-only field.
9. WHEN nothing is selected, or the selection is not in the snapshot, THE Autopsy_Slab SHALL show an empty state with no stale metadata.
10. THE Autopsy_Slab SHALL NOT display source code.
11. THE Autopsy_Slab SHALL be a labelled landmark region.

### Requirement 19: Lens Navigation and Explain Requests

**User Story:** As a user, I want three lenses on the same target, so that I can read syntax, flow, and architecture separately.

#### Acceptance Criteria

1. THE Autopsy_Slab SHALL provide tabs `L1_SYNTAX`, `L2_FLOW`, and `L3_ARCHITECTURE` with `tablist`, `tab`, `aria-selected`, and `aria-controls`, operated by the arrow keys with wrap, Home, and End, and the active Lens SHALL be held in the App_Store.
2. WHEN the user changes the active Lens, THE App_Store SHALL keep the selection.
3. WHEN the Lens is `L1_SYNTAX` or `L2_FLOW` and a symbol is selected, THE Autopsy_UI SHALL send one explain request with only `target_id` (the symbol id) and `lens`.
4. WHEN the Lens is `L3_ARCHITECTURE` and a directory that is a key of `directory_roles` is selected, THE Autopsy_UI SHALL send it as `target_id`.
5. WHEN the Lens is `L3_ARCHITECTURE` and no directory is selected, THE Autopsy_UI SHALL send the `repo_id` as `target_id`, even if a file or symbol is selected.
6. WHEN the Lens is `L1_SYNTAX` or `L2_FLOW` and only a file is selected, THE Lens_Panel SHALL list the symbols of the file and send no request, and IF the file has no symbols, THEN THE Lens_Panel SHALL state that the file has no explainable symbols.
7. WHEN no valid Explain_Target exists, THE Autopsy_Slab SHALL show its empty state and send no request.
8. THE Autopsy_UI SHALL keep at most one in-flight explain request per `repo_id`, Explain_Target, and Lens.
9. WHILE an explain request is in flight, THE Lens_Panel SHALL show a loading state.
10. IF an explain request fails or returns a malformed response, THEN THE Lens_Panel SHALL show the envelope `message` or a fixed local message with a retry action, SHALL keep the other tabs usable, and SHALL NOT store the failed result in the Explain_Cache.
11. WHEN an explain request succeeds, THE Autopsy_UI SHALL store it in the Explain_Cache for the session and SHALL send no repeat request for that key unless the user activates retry or refresh.
12. WHEN the user activates retry or refresh, THE Autopsy_UI SHALL discard the cache entry and send exactly one request.
13. WHEN the repository, symbol, directory, or Lens changes while a request is in flight, THE Autopsy_UI SHALL abort the stale request and discard its response.
14. IF a response has an `envelope.lens` or `envelope.target_id` that differs from the request, or a null tier for the Lens, THEN THE Autopsy_UI SHALL treat it as malformed and render nothing from it.
15. WHILE Study Mode is on, WHEN a non-cached L1 or L2 explain succeeds, THE Autopsy_UI SHALL send one vitals refresh, and IF the refresh fails, THEN THE Autopsy_UI SHALL keep the previous vitals and the explanation.
16. WHEN a request is served from the Explain_Cache, THE Autopsy_UI SHALL send no explain request and no vitals request.
17. THE Autopsy_UI SHALL contain no hardcoded explanation text.

### Requirement 20: L1 Syntax Lens

**User Story:** As a user, I want the exact syntax explained with line references, so that I can learn what each construct does.

#### Acceptance Criteria

1. WHEN an L1 envelope arrives, THE Lens_Panel SHALL show `summary`, `language`, and `key_takeaway`, each with a label.
2. THE Lens_Panel SHALL list `annotations` in the backend order, each with its line range (a single number WHEN `line_start` equals `line_end`), `construct`, and `explanation`, as a semantic list readable by assistive technology.
3. THE Lens_Panel SHALL show `what_if_removed` in a callout labelled `What breaks if removed?`.
4. WHEN `what_if_removed` is empty or whitespace, THE Lens_Panel SHALL render no callout and no placeholder for that annotation.
5. WHEN `annotations` is empty, THE Lens_Panel SHALL show the summary and the key takeaway and state that no annotations were returned.
6. THE Lens_Panel SHALL display out-of-range or reversed line numbers exactly as returned.
7. IF `l1.target_id` differs from the requested target, THEN THE Autopsy_UI SHALL treat the response as malformed as defined in Requirement 19 criterion 14.
8. THE Lens_Panel SHALL render all backend text as plain text with line breaks preserved and with no HTML or Markdown interpretation.

### Requirement 21: L2 Flow Lens and DSA-in-the-Wild

**User Story:** As a user, I want the execution and data flow of a symbol, so that I can follow how data moves.

#### Acceptance Criteria

1. WHEN an L2 envelope arrives, THE Lens_Panel SHALL list `execution_steps` in ascending `step_number`, keeping the backend order for equal numbers, each with `location`, `action`, and `data_transformation`.
2. THE Lens_Panel SHALL show `upstream_callers`, `downstream_callees`, and `side_effects` as labelled sections in the backend order and SHALL omit a section WHEN its list is empty.
3. THE Lens_Panel SHALL show each id of `blast_radius.upstream_callers` and `blast_radius.downstream_callees` as a Blast_Radius_Chip labelled by direction, with `impact_score` as text with two decimals.
4. WHEN a Blast_Radius_Chip id equals a snapshot symbol id, THE Lens_Panel SHALL render the chip as a keyboard-focusable control that selects that symbol through the App_Store, and OTHERWISE SHALL render it as non-interactive text.
5. WHERE `dsa_cards` is non-empty, THE Lens_Panel SHALL show a `DSA-in-the-Wild` section with one DSA_Card per entry in the backend order, each showing `chapter`, `pattern_name`, `start_line` to `end_line`, `why_used_here`, `time_complexity`, and `space_complexity`.
6. WHEN `dsa_cards` is empty, THE Lens_Panel SHALL omit the `DSA-in-the-Wild` section, its heading, and any placeholder.
7. THE Lens_Panel SHALL NOT derive a DSA_Card from `snapshot.dsa_signals`.
8. WHEN `llm_content_available` is false, THE Lens_Panel SHALL show a notice that generated flow content is unavailable and SHALL still show every deterministic field, including the blast radius and `dsa_cards`.
9. WHEN every list and the blast radius of an L2 envelope are empty, THE Lens_Panel SHALL show a single empty state, plus the notice of criterion 8 WHEN the result is degraded.
10. THE Lens_Panel SHALL render all backend text as plain text.

### Requirement 22: L3 Architecture Lens and Counterfactual Tradeoff Matrix

**User Story:** As a user, I want to understand why the folder structure exists and what the alternatives would cost, so that I can judge architectural choices.

#### Acceptance Criteria

1. WHEN an L3 envelope arrives, THE Lens_Panel SHALL show `topology_pattern`, `why_this_folder_structure`, and every `structural_evidence` entry in order.
2. WHERE `spec_rationale` is non-null, THE Lens_Panel SHALL show it under a `Spec rationale` heading, and WHEN it is `null`, THE Lens_Panel SHALL omit the section.
3. WHERE `alternatives` is non-empty, THE Lens_Panel SHALL show a Counterfactual_Tradeoff_Matrix with the columns `Pattern`, `Why not selected`, and `When to switch`, one row per alternative in the backend order, and one row marked `Selected` by text for `topology_pattern`.
4. THE `Selected` row SHALL show a non-color `not applicable` marker in the other cells and SHALL borrow no text from `why_this_folder_structure`.
5. WHEN an alternative equals `topology_pattern`, THE Counterfactual_Tradeoff_Matrix SHALL still give it its own row.
6. WHEN `alternatives` is empty, THE Lens_Panel SHALL omit the Counterfactual_Tradeoff_Matrix and state that no alternatives were returned.
7. THE Lens_Panel SHALL fill the Counterfactual_Tradeoff_Matrix only from `alternatives` and `topology_pattern`.
8. THE Counterfactual_Tradeoff_Matrix SHALL be a semantic table that stays readable at 320 px width.
9. THE Lens_Panel SHALL render plain text, and for L3 SHALL show no Blast_Radius_Chip, no `impact_score`, and no mastery-change indication.
10. IF an L3 request fails with `unknown_target`, THEN THE Lens_Panel SHALL show the `message` with a retry action and keep the L1 and L2 tabs usable.

### Requirement 23: Exorcism Check Start

**User Story:** As a learner in Study Mode, I want a timed Socratic check on a symbol, so that I can prove I understand it.

#### Acceptance Criteria

1. WHILE Study Mode is on and a symbol is selected, THE Autopsy_Slab SHALL show the `Exorcism Check` action visible and enabled.
2. WHILE Study Mode is on and only a file is selected, THE Autopsy_Slab SHALL disable the action and show text that a symbol must be selected.
3. WHILE Study Mode is off, THE Autopsy_Slab SHALL NOT render the action.
4. WHEN the user activates the action, THE Autopsy_UI SHALL open the Exorcism_Modal and send exactly one `POST /api/repos/{repo_id}/socratic/start` with only `target_id`.
5. WHILE the start request is in flight, THE Exorcism_Modal SHALL show a loading state and ignore re-activation of the action.
6. THE Exorcism_Modal SHALL have a focus trap, an accessible title naming the symbol, a close control, and Escape handling, and SHALL return focus to the action on close.
7. WHEN a valid start response arrives, THE Exorcism_Modal SHALL show one text input per question (one or two), labelled by its `prompt` with its `line_reference`, with a limit of 2000 characters.
8. IF the start response holds zero or more than two questions, THEN THE Exorcism_Modal SHALL show an error with a retry action and start no countdown.
9. THE Exorcism_Modal SHALL show no `expected_concepts` value and no answer key.
10. WHEN a valid start response arrives, THE Exorcism_Modal SHALL start one 60-second countdown in the frontend, shown as text in whole seconds, and SHALL send no timer value to the Backend_API.
11. IF the start request fails with `study_mode_disabled`, THEN THE Exorcism_Modal SHALL state that Study Mode is off, show no quiz, and offer no retry.
12. IF the start request fails with `unknown_target`, `source_unreadable`, `llm_unavailable`, `invalid_llm_output`, `repo_not_found`, `internal_error`, or a network error, THEN THE Exorcism_Modal SHALL show the message with a retry action and start no countdown.
13. WHEN the countdown reaches 0 and every answer is non-blank after trimming, THE Exorcism_Modal SHALL submit the answers as entered under Requirement 24.
14. WHEN the countdown reaches 0 and an answer is blank after trimming, THE Exorcism_Modal SHALL lock the inputs, state that time expired, send no submit request, and offer a restart through `socratic/start`.
15. THE Exorcism_Modal SHALL fabricate no answer.
16. WHEN the user closes the Exorcism_Modal before submitting, THE Autopsy_UI SHALL stop the countdown, send no request, and change no mastery display.
17. WHEN the repository or the selected symbol changes while the Exorcism_Modal is open, THE Autopsy_UI SHALL close the modal and discard a pending start response.

### Requirement 24: Exorcism Submission and Verdict

**User Story:** As a learner, I want my answers graded by the backend and the real verdict shown, so that mastery reflects verified understanding.

#### Acceptance Criteria

1. WHEN the user submits, THE Exorcism_Modal SHALL send `POST /api/repos/{repo_id}/socratic/submit` with `target_id` and exactly one trimmed answer per question, each `question_id` from the start response used once.
2. IF an answer is blank or longer than 2000 characters after trimming, THEN THE Exorcism_Modal SHALL show a validation message naming the questions, send no request, and keep the answers.
3. THE Exorcism_Modal SHALL show a live character count `<count> / 2000` of the trimmed answer per input.
4. WHILE the submit request is in flight, THE Exorcism_Modal SHALL show a loading state, disable the submit control and the inputs, and send no duplicate submit.
5. WHEN the response arrives, THE Exorcism_Modal SHALL show `score` as a rounded percentage, `PASSED` or `FAILED` derived only from `passed`, `feedback`, `new_state` with its Mastery_Indicator, and a `next_review_at` row only WHEN the value is non-null.
6. WHEN `passed` is true, THE Exorcism_Modal SHALL style the verdict in emerald.
7. WHEN `passed` is false, THE Exorcism_Modal SHALL style the verdict in crimson based on `passed` and not on `new_state`, and SHALL show `new_state` exactly as returned, including `MASTERED`, with its `next_review_at`.
8. WHEN `new_state` is `STALE`, THE Exorcism_Modal SHALL show the amber `STALE` indicator.
9. THE Exorcism_Modal SHALL compute no grade, score, pass result, or mastery state of its own.
10. IF the submit fails with `invalid_answers`, THEN THE Exorcism_Modal SHALL show the message, keep the answers, and re-enable submit.
11. IF the submit fails with `study_mode_disabled`, THEN THE Exorcism_Modal SHALL state that Study Mode is off, keep the answers read-only, allow no resubmit, and make no mastery change.
12. IF the submit fails with `grading_unavailable`, THEN THE Exorcism_Modal SHALL state that grading is unavailable, make no mastery change, keep the answers, and allow resubmission.
13. IF the submit fails with any other error or a network error, THEN THE Exorcism_Modal SHALL show the message, keep the answers, and allow resubmission.
14. IF the submit fails, THEN THE Autopsy_UI SHALL show no verdict, change no mastery display, and send no vitals refresh.
15. WHEN a verdict is displayed, THE Exorcism_Modal SHALL stop the countdown, make the inputs read-only, and disable submit.
16. WHEN a verdict is displayed, THE Exorcism_Modal SHALL offer a close control and a `New check` action that calls `socratic/start` again and discards the verdict and the previous answers.

### Requirement 25: Post-Verification Refresh

**User Story:** As a learner, I want the whole interface to reflect my new mastery immediately, so that the haunted shroud lifts without a reload.

#### Acceptance Criteria

1. WHEN a verdict (passed or not) is displayed, THE Autopsy_UI SHALL send one `GET /api/repos/{repo_id}/vitals` request for the repository of the checked symbol.
2. WHEN the vitals response arrives, THE Autopsy_UI SHALL replace the Vitals_Meter, `file_states`, and every Mastery_Indicator from that response only, and never from `new_state`.
3. WHEN the refreshed `file_states` marks the containing file `MASTERED`, THE Graph_View and the File_Tree SHALL show the emerald indicator and remove the Shroud.
4. WHEN the refreshed state is `UNAUDITED`, `DISSECTED`, or `STALE`, THE Autopsy_UI SHALL show that state, and SHALL show the Shroud only for `UNAUDITED` in `Autopsy` visual mode as defined in Requirement 15 criterion 11.
5. WHEN the containing file has no key in the refreshed `file_states`, THE Autopsy_UI SHALL show the Unaudited_Fallback.
6. THE Autopsy_UI SHALL complete the refresh without a page reload and SHALL keep the selection, view, Lens, Study Mode, and visual mode unchanged.
7. IF the refresh fails, THEN THE Autopsy_UI SHALL keep the verdict and the previous display, show an out-of-date notice with a retry action, and edit no state locally.
8. WHEN the user activates retry, THE Autopsy_UI SHALL send one new vitals request and apply the rules of this requirement.
9. WHEN the repository changes before the response arrives, THE Autopsy_UI SHALL discard the response.
10. WHEN refreshes overlap, THE Autopsy_UI SHALL apply only the most recent response.

### Requirement 26: Kiro Crew Deep Links

**User Story:** As a Kiro Crew user, I want a link to open the UI on a specific repository, file, and view, so that I can jump straight to the evidence.

#### Acceptance Criteria

1. WHEN the query holds a `repo_id` that equals a `repo_id` returned by `GET /api/repos`, THE Autopsy_UI SHALL select that repository and load its snapshot.
2. IF `repo_id` equals no returned `repo_id`, THEN THE Autopsy_UI SHALL select no repository, ignore `file`, show a dismissible not-found notice, and stay operable.
3. IF `GET /api/repos` fails while `repo_id` is present, THEN THE Autopsy_UI SHALL show the error state of Requirement 3 and no not-found notice.
4. WHEN the snapshot holds a file whose `file_path` equals `file`, THE Autopsy_UI SHALL select it, open the Autopsy_Slab on it, and make it visible in the File_Tree.
5. IF `file` equals no snapshot `file_path`, THEN THE Autopsy_UI SHALL keep the repository, select no file, and show a dismissible notice.
6. IF `file` is present without `repo_id`, THEN THE Autopsy_UI SHALL ignore it silently.
7. WHEN `view` is exactly `graph` or `topology`, THE Autopsy_UI SHALL open that view, and for any other value SHALL use `graph` with no notice.
8. WHEN the repository, file, or view in the App_Store changes, THE Autopsy_UI SHALL update the URL with `history.replaceState`, with `repo_id` only while a repository is selected, `file` only while a file is selected, and `view` always, and SHALL add no history entry.
9. WHEN the query holds none of the three parameters, THE Autopsy_UI SHALL start normally with no notice.
10. THE Autopsy_UI SHALL send no request for a Deep_Link beyond the normal repository, snapshot, vitals, and provenance loading, and SHALL issue no explain, Socratic, study-mode, or ingest request.
11. THE Autopsy_UI SHALL treat the values as untrusted, match them by exact case-sensitive equality, and render them as plain text.
12. WHEN a parameter occurs more than once, THE Autopsy_UI SHALL use its first occurrence.
13. WHEN a value is longer than 4096 characters, THE Autopsy_UI SHALL match it against nothing.

### Requirement 27: Graceful Degradation for Unsupported Features

**User Story:** As a user, I want the UI to say plainly what the backend does not provide, so that I never see fabricated data.

#### Acceptance Criteria

1. WHEN an element depends on data the Backend_API does not provide (per-symbol mastery, file blast radius, source code, ingestion progress percentage, spec links for a drift item), THE Autopsy_UI SHALL show text that names the missing item or omit the element, and SHALL generate no substitute value.
2. THE Autopsy_UI SHALL contain no hardcoded mock repository, file, symbol, mastery state, explanation, question, or verdict in any production module.
3. THE Autopsy_UI SHALL keep test fixtures only under test directories and exclude them from the production build.
4. IF a required field is missing in a 2xx response, THEN THE API_Client SHALL raise a malformed-response error, THE Autopsy_UI SHALL show the generic message of Requirement 3 criterion 5, and previously displayed valid data SHALL stay.
5. WHEN a `MasteryState`, `edge_type`, `kind`, `language`, `drift_type`, directory role, or `detected_pattern` value is unknown, THE Autopsy_UI SHALL show it as plain text with a neutral style, with no crimson and no emerald, and SHALL NOT crash.
6. WHEN the selected file has no commit history, THE Autopsy_Slab SHALL show `No commit history available for this file`.
7. WHEN a file is selected, THE Autopsy_Slab SHALL show `File-level blast radius is not provided by the backend` in place of an impact value and SHALL compute no impact value, while the neighbor highlighting of Requirement 16 criterion 5 stays labelled as derived.
8. WHEN an L3 blast radius is empty with `impact_score` 0, THE Autopsy_Slab SHALL NOT present it as low impact.
9. WHEN a file has no `file_states` key, THE Autopsy_UI SHALL show the Unaudited_Fallback and no `MasteryState`.

### Requirement 28: Test Suite

**User Story:** As a developer, I want a small deterministic test suite with no network, so that I can verify the UI on any machine.

#### Acceptance Criteria

1. THE Test_Suite SHALL use Vitest and `@testing-library/react` and SHALL contain 12 to 18 test cases, and one case MAY cover several criteria of one flow.
2. THE Test_Suite SHALL mock `fetch`, and WHEN a request matches no mock, THE Test_Suite SHALL fail the test with a message naming the method and path.
3. THE Test_Suite SHALL run offline, with no backend, LLM, credential, or `.env` file.
4. THE Test_Suite SHALL give the same result on three consecutive runs, SHALL read no wall-clock time, and SHALL use fake timers for the 60-second Exorcism countdown.
5. THE Test_Suite SHALL cover repository list loading, empty, and selection.
6. THE Test_Suite SHALL cover ingest validation (blank input, wrong GitHub prefix), ingest success with list refresh, and ingest errors `rate_limited` with `Retry-After` and `local_ingest_disabled`.
7. THE Test_Suite SHALL cover vitals display, and the Study Mode pending state and a failure that restores the previous value and shows an error.
8. THE Test_Suite SHALL cover graph rendering, node selection with Selection_Sync, the blast radius for a symbol, and the switch to the Topology_View.
9. THE Test_Suite SHALL cover the pure mastery mapping for `UNAUDITED`, `DISSECTED`, `MASTERED`, `STALE`, `NO TRACKED SYMBOLS`, and `STATE UNKNOWN`.
10. THE Test_Suite SHALL cover Lens selection, L1 callouts, L2 flow, DSA_Cards present and the section hidden when empty, the L3 matrix, and that a file path is never sent as an explain target.
11. THE Test_Suite SHALL cover Socratic start with no answer key, `study_mode_disabled`, submit, pass and fail verdicts, and the refresh of vitals and graph styling after completion.
12. THE Test_Suite SHALL cover Deep_Links for `repo_id`, `file`, `view`, an unknown repository, an unknown file, and an unsupported view.
13. THE Test_Suite SHALL cover API_Client error mapping for an error envelope, a non-envelope body, a non-JSON body, and a network failure, with none leaking a stack trace or raw body.
14. THE Test_Suite SHALL assert that backend text containing an HTML tag renders as plain text.
15. THE Test_Suite SHALL run through one `ui` command that exits non-zero on failure.

### Requirement 29: Quality, Accessibility, and Performance

**User Story:** As a user, I want a fast and accessible interface, so that I can work comfortably with large repositories.

#### Acceptance Criteria

1. THE Autopsy_UI SHALL give every icon-only button, tab, switch, toggle, tree, graph region, and dialog an accessible name.
2. THE Autopsy_UI SHALL meet a contrast of at least 4.5:1 for normal text and 3:1 for large text, non-text markers, and focus indicators in both visual modes.
3. THE Autopsy_UI SHALL pair every color-coded state with text or a named icon.
4. WHEN a modal closes, THE Autopsy_UI SHALL return focus to the opener, or to the Command_Bar region heading if the opener no longer exists.
5. WHILE a modal is open, THE Autopsy_UI SHALL trap focus in the modal and make the background inert.
6. WHEN the user presses Escape, THE Autopsy_UI SHALL close the modal, except WHILE its submit or ingest request is in flight, when the key SHALL be ignored and the entered values kept.
7. THE Autopsy_UI SHALL memoize the file tree, node and edge lists, layout, cycle edge set, and mastery lookup per snapshot or vitals value.
8. THE Autopsy_UI SHALL wrap graph node components in `React.memo`, so that a selection change re-renders only nodes whose highlight changed.
9. THE Autopsy_UI SHALL use the same loading, empty, and error pattern in every region.
10. THE Autopsy_UI SHALL render backend text as text nodes and SHALL use no `dangerouslySetInnerHTML`.
11. WHEN `prefers-reduced-motion: reduce` is set, THE Autopsy_UI SHALL disable animated transitions, including the Shroud clearing animation, and show the final state immediately.
12. THE Test_Suite SHALL include a deterministic test with 300 or more nodes that verifies through a recompute counter or spy that a selection change recomputes no memoized structure.

### Requirement 30: Backend Preservation and Scope Control

**User Story:** As the project owner, I want the frontend delivered without touching the backend, so that Phases 1 to 3 stay stable.

#### Acceptance Criteria

1. THE Autopsy_UI work SHALL modify no file under `backend/`, `power/`, `crew/`, `scripts/`, or `.kiro/specs/01-*` to `03-*`, and no existing backend test.
2. THE Autopsy_UI work SHALL add no endpoint, engine, backend feature, product feature, or file under `backend/`.
3. WHEN the Backend_Suite runs with `LLM_PROVIDER=mock` and no network, THE Backend_Suite SHALL report 798 passed, 0 failed, 0 errors, and 0 skipped.
4. THE diff against the pre-work commit SHALL show no path outside `ui/`, `.kiro/specs/04-*`, and required repository-root files such as `.gitignore`, and THE implementation report SHALL list each such root file.
5. IF a real CORS or API defect blocks the Autopsy_UI, THEN THE Implementer SHALL report the file, the issue, the reason, and a minimal proposed fix, SHALL make no backend change without written approval of the project owner, and THE Autopsy_UI SHALL keep working through Graceful_Degradation.
6. WHEN a feature has no backend route or field, THE Autopsy_UI SHALL apply Graceful_Degradation, call no route absent from the Verified Backend Contract, and compute no backend-owned value.
7. THE Autopsy_UI work SHALL add no deployment configuration (container file, CI workflow, hosting manifest, or infrastructure-as-code).
8. THE repository SHALL keep `ui/node_modules/` and `ui/dist/` untracked.
9. THE Test_Suite SHALL leave `backend/`, `power/`, `crew/`, and `scripts/` unmodified.

### Requirement 31: Definition of Done and Final Report

**User Story:** As the project owner, I want an evidence-based completion report, so that I can trust the delivery status.

#### Acceptance Criteria

1. WHEN the implementation ends, THE Implementer SHALL run `npm test`, `npm run build`, and `npm run typecheck` in `ui/` with `LLM_PROVIDER=mock`, and SHALL record the exit code and the summary lines actually produced for each.
2. THE Implementer SHALL declare completion only WHEN `npm run build` exits 0, `npm run typecheck` reports 0 errors, the Test_Suite reports 0 failed and 0 skipped with every API call mocked, and the Backend_Suite reports 798 passed, 0 failed, 0 errors, and 0 skipped.
3. THE Implementer SHALL write `.kiro/specs/04-autopsy-ui/implementation-report.md` with the sections: spec artifacts; frontend structure; API contract verification; UI implementation status per surface (Command_Bar, Specimen_Rail, Canvas, Autopsy_Slab, Exorcism_Modal); test counts; build verification actually executed; backend preservation; limitations; completion status.
4. THE implementation report SHALL state the completion status as exactly one of `COMPLETE`, `PARTIALLY COMPLETE`, or `BLOCKED`.
5. IF a requirement is unmet, THEN THE implementation report SHALL list it by number with the reason and SHALL NOT state `COMPLETE`.
6. THE implementation report SHALL record each of the ten Recorded Contract Mismatches by number with its handling.
7. IF a command was not run or did not finish, THEN THE implementation report SHALL name the command with the reason, SHALL record no output summary for it, and SHALL state `PARTIALLY COMPLETE` or `BLOCKED`.
8. IF a CORS or API defect was reported and not approved, THEN THE implementation report SHALL list its file, issue, reason, and proposed fix, and SHALL state `BLOCKED` WHERE the defect prevents a requirement.
9. THE implementation report SHALL state that the Open Decision was implemented as two independent controls.
