# Implementation Plan: 04-autopsy-ui

## Overview

This plan builds the Code Autopsy UI in `ui/` (React, TypeScript strict, Vite, Tailwind, `@xyflow/react`, `dagre`, Vitest, fast-check) in the layered order of the design: toolchain, then `api/`, then pure `core/` modules, then `state/` and `data/`, then components (shared, Command_Bar, Specimen_Rail, Canvas, Autopsy_Slab, Exorcism_Modal), then deep links, then verification and the report.

Ground rules for every task:

- TypeScript is the implementation language. All new files live under `ui/` or `.kiro/specs/04-autopsy-ui/`. No file under `backend/`, `power/`, `crew/`, `scripts/`, or `.kiro/specs/01-*` to `03-*` is touched, and no deployment configuration is added (Requirements 30.1, 30.2, 30.7).
- Only `ui/src/api/client.ts` calls `fetch`. No `dangerouslySetInnerHTML`. No absolute `http://` or `https://` URL in `ui/src` except the prefix `https://github.com/` (Requirements 1.9, 2.4, 29.10).
- The user asked for the full 18-case test plan from the design (Requirement 28.1 allows 12 to 18). Every test sub-task is therefore required and carries no `*` marker. Each property test implements exactly one Correctness Property with at least 100 runs and a fixed seed.
- Tests run offline with `fetch` mocked and fail on any unmatched request (Requirements 1.12, 28.2, 28.3).
- Commands run from `ui/` with `LLM_PROVIDER=mock`.

## Tasks

- [x] 1. Scaffold the `ui/` project
  - [x] 1.1 Create the Vite, TypeScript, and Tailwind project files
    - Create `ui/package.json` with scripts `dev` (`vite`), `build` (`tsc --noEmit && vite build`), `typecheck` (`tsc --noEmit`), `test` (`vitest run`)
    - Declare runtime dependencies `react`, `react-dom`, `@xyflow/react`, `dagre`, `lucide-react` and the dev dependencies listed in the design Toolchain Configuration, including `fast-check`
    - Create `ui/tsconfig.json` with `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, including `src` and `tests`
    - Create `ui/vite.config.ts` with the React plugin, dev proxy for `/api` and `/health` to `http://127.0.0.1:8000` with no `rewrite`, and the Vitest block (jsdom, setup file, no watch)
    - Create `ui/tailwind.config.ts` (full `theme.colors` replacement with CSS-variable tokens, `autopsy:` and `lab:` variants), `ui/postcss.config.js`, `ui/index.html` (with `#app-root` and `#modal-root`), `ui/.gitignore` for `node_modules/` and `dist/`
    - Run `npm install` to produce and commit-ready `ui/package-lock.json`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.10, 1.11, 30.8_

  - [x] 1.2 Create styles, entry point, and Vitest setup with helpers
    - Create `ui/src/styles/tokens.css` (single source of color tokens, including the one amber `stale` token) and `ui/src/styles/index.css` (Tailwind layers, Autopsy-only grid, shroud, fracture pulse, `prefers-reduced-motion` rules, focus indicator)
    - Create a minimal `ui/src/main.tsx` that restores the visual mode from `localStorage` inside `try/catch`, validates it, sets `document.documentElement.dataset.visualMode` before the first render, and mounts a placeholder `App.tsx`
    - Create `ui/tests/setup.ts` with jsdom stubs (`ResizeObserver`, `DOMMatrixReadOnly`, `matchMedia`, `scrollIntoView`, `navigator.clipboard`), `fc.configureGlobal({ numRuns: 100, seed: 20250101 })`, `jest-dom`, per-test reset of `localStorage` and URL, and a global `afterEach` that fails on unmatched fetch requests with `Unmatched request: <METHOD> <path>`
    - Create `ui/tests/helpers/mockFetch.ts` (routes, abort-aware, records calls and unmatched) and `ui/tests/helpers/deferred.ts`
    - Use system font stacks only, with no external host in the bundle
    - _Requirements: 1.9, 1.10, 1.12, 4.12, 4.13, 10.1, 10.3, 10.4, 10.6, 10.7, 10.10, 10.14, 28.2, 28.3, 28.4, 29.11_

- [x] 2. Contract types, validators, errors, and API_Client
  - [x] 2.1 Define Contract_Types in `ui/src/api/types.ts`
    - Mirror every request and response shape of the Verified Backend Contract field for field, including `ExplanationEnvelope` with one non-null tier, `SocraticVerdict.next_review_at: string | null`, `L3.spec_rationale: string | null`, and the nine operation types
    - Keep enum-like fields tolerant of unknown strings where the design requires it
    - _Requirements: 2.1, 2.2, 27.5_

  - [x] 2.2 Implement `api/errors.ts` and `api/config.ts`
    - Add `ApiHttpError` (status, nullable code, message, optional `retryAfterSeconds`), `ApiNetworkError`, `ApiMalformedError` (operation name), `ApiAbortError` as four distinct classes, and the fixed `GENERIC_HTTP_MESSAGE`
    - Add `normalizeBaseUrl` (remove one or more trailing slashes, empty means relative) and `buildUrl`
    - _Requirements: 1.7, 1.8, 2.9, 2.10, 2.12, 2.13, 2.14_

  - [x] 2.3 Implement runtime validators in `api/validate.ts`
    - Write one validator per response type that rejects a missing required field and tolerates unknown enum strings
    - Return typed values and never partial data
    - _Requirements: 2.8, 2.11, 27.4, 27.5_

  - [x] 2.4 Implement `api/client.ts` and `api/context.tsx`
    - Implement `createApiClient({ baseUrl? })` with exactly the nine operations, looking up `globalThis.fetch` at call time
    - Percent-encode `repo_id` as one segment, send only the endpoint's JSON keys with `Content-Type: application/json`, and send no body for `GET` operations
    - Follow the design's fixed order of checks: pre-aborted signal, fetch rejection (abort versus network), non-2xx envelope parsing, 429 `Retry-After` parsing, 2xx body validation, and the explain tier, lens, and target match check
    - Add `ApiProvider` and `useApi`
    - _Requirements: 1.7, 1.8, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 19.14_

  - [x] 2.5 Write the API error mapping property test (test case 2)
    - Create `ui/tests/unit/apiErrors.property.test.ts`
    - **Property 2: API_Client error and response mapping**
    - Cover error envelope, non-envelope body, empty body, non-JSON body, network failure, abort, `Retry-After` states, and assert no raw body, stack trace, or exception class name appears in any error
    - **Validates: Requirements 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 28.13**

  - [x] 2.6 Write the request construction property test (test case 3)
    - Create `ui/tests/unit/apiRequests.property.test.ts`
    - **Property 3: Request construction**
    - Generate base URLs with trailing slashes and `repo_id` values containing `/`, `?`, `#`, `%`, spaces, and Unicode, across all nine operations
    - **Validates: Requirements 1.7, 1.8, 2.5, 2.6, 2.7**

  - [x] 2.7 Create typed test fixtures and arbitraries
    - Create `ui/tests/fixtures/` builders (`makeRepos`, `makeSnapshotResponse`, `makeVitals`, `makeExplain`, `makeCheck`, `makeVerdict`) with no randomness and no clock reads
    - Include backend text containing `<b>`, `<script>`, and Markdown markers in at least one fixture
    - Create `ui/tests/fixtures/arbitraries.ts` with fast-check snapshot arbitraries
    - _Requirements: 28.1, 28.14_

- [x] 3. Pure core modules
  - [x] 3.1 Implement `core/mastery.ts`
    - Implement `presentMastery` (total over any input, six categories with distinct label and icon, four known states with distinct tokens, unknown input maps to `STATE UNKNOWN`), `fileMasteryView` (derived only from `file_states` and the `Remote` status), and the Shroud predicate (true only for `UNAUDITED` in `Autopsy` mode)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.7, 11.8, 15.11, 27.5, 27.9_

  - [x] 3.2 Write the mastery property test (test case 1)
    - Create `ui/tests/unit/mastery.property.test.ts`
    - **Property 1: Mastery presentation is total, distinct, and derived only from loaded file states**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.7, 11.8, 15.11, 27.5, 27.9, 28.9**

  - [x] 3.3 Implement `core/snapshotIndex.ts` and `core/fileTree.ts`
    - `snapshotIndex`: lookup maps for files, symbols, and directory keys, `classifyNode` (file, symbol, directory, null), and `resolveTarget` returning `null` for an absent id
    - `fileTree`: `buildFileTree` (folders before files, code-unit order, symbols by `start_line` then `id`, permutation-independent) and `flattenVisible` with an expanded set
    - _Requirements: 4.8, 4.9, 12.1, 12.2, 12.4, 12.8_

  - [x] 3.4 Write the file tree property test (test case 7)
    - Create `ui/tests/unit/fileTree.property.test.ts`
    - **Property 7: File tree structure and ordering**
    - **Validates: Requirements 12.1, 12.2, 12.4, 12.8**

  - [x] 3.5 Implement `core/graph.ts`
    - `buildGraphModel(snapshot, layer)` with files layer (`imports`) and symbols layer (`calls`), duplicate removal, circular edge marking from `snapshot.cycles`, and `highlightFor` returning one-hop upstream and downstream sets restricted to layer nodes
    - _Requirements: 15.3, 15.4, 15.5, 15.9, 16.2, 16.8_

  - [x] 3.6 Implement `core/layout.ts`
    - `layoutGraph` as a dagre wrapper that sorts nodes and edges before insertion, returns integer positions, and keeps every node box inside the reported width and height
    - _Requirements: 15.6, 15.8_

  - [x] 3.7 Write the graph model property test (test case 5)
    - Create `ui/tests/unit/graph.property.test.ts`
    - **Property 5: Graph model respects layers, cycles, and one-hop neighborhoods**
    - **Validates: Requirements 15.3, 15.4, 15.5, 15.9, 16.2, 16.8**

  - [x] 3.8 Write the layout property test (test case 4)
    - Create `ui/tests/unit/layout.property.test.ts`
    - **Property 4: Layout is deterministic and independent of input order**
    - **Validates: Requirements 15.6, 15.8**

  - [x] 3.9 Implement `core/explainTarget.ts`
    - `resolveExplainTarget` returning `ok`, `pick-symbol`, or `none`: symbol id for L1 and L2, directory key or `repoId` for L3, and never a file path
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7_

  - [x] 3.10 Write the explain target property test (test case 10)
    - Create `ui/tests/unit/explainTarget.property.test.ts`
    - **Property 10: Explain targets are never file paths**
    - **Validates: Requirements 19.3, 19.4, 19.5, 19.6, 19.7, 28.10**

  - [x] 3.11 Implement `core/deepLink.ts`
    - `parseDeepLink` (first occurrence, 4096-character limit, exact `graph` or `topology`), `resolveDeepLink` (exact case-sensitive repository match, ignore `file` without a repository), and `buildSearch` (preserves unrelated parameters, round-trips with `parseDeepLink`)
    - _Requirements: 26.1, 26.2, 26.4, 26.5, 26.6, 26.7, 26.8, 26.11, 26.12, 26.13_

  - [x] 3.12 Write the deep link property test (test case 8)
    - Create `ui/tests/unit/deepLink.property.test.ts`
    - **Property 8: Deep-link parsing, resolution, and URL building**
    - **Validates: Requirements 26.1, 26.2, 26.4, 26.5, 26.6, 26.7, 26.8, 26.11, 26.12, 26.13, 28.12**

  - [x] 3.13 Implement `core/exorcism.ts`
    - Pure transition function with phases including `submitting`, `verdict`, `expired`, `study_off`, and `read_only_off`, a 60-second `remaining` bounded between 0 and 60, `call_submit` emitted only for complete trimmed answers (1 to 2000 characters, one per `question_id`), expiry on zero with any blank answer, and the verdict stored as returned with pass or fail from `passed` only
    - _Requirements: 23.8, 23.10, 23.13, 23.14, 23.15, 24.1, 24.2, 24.4, 24.5, 24.7, 24.11, 24.12, 24.15_

  - [x] 3.14 Write the Exorcism state machine property test (test case 11)
    - Create `ui/tests/unit/exorcism.property.test.ts`
    - **Property 11: Exorcism state machine invariants**
    - **Validates: Requirements 23.8, 23.10, 23.13, 23.14, 23.15, 24.1, 24.2, 24.4, 24.5, 24.7, 24.11, 24.12, 24.15**

  - [x] 3.15 Implement `core/present.ts` and `core/counters.ts`
    - `presentError(error, context)` per the design mapping table (abort returns `null`, explain and socratic service-unavailable texts, `rate_limited` with seconds only when readable, `local_ingest_disabled`, network and malformed fixed texts)
    - `counters.ts` exposing recompute counters for graph, layout, cycle set, file tree, and mastery lookup, read by tests
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.10, 3.11, 3.13, 7.11, 7.12, 29.7, 29.12_

- [x] 4. Checkpoint - Ensure core and API tests pass
  - Run `npm test`, `npm run typecheck`, and `npm run build` in `ui/` with `LLM_PROVIDER=mock`. Ensure all pass, ask the user if questions arise.

- [x] 5. State stores and data hooks
  - [x] 5.1 Implement `state/appReducer.ts`
    - Exactly eight state values with the initial state of Requirement 4.2 and the actions `repo-selected`, `select-target`, `select-directory`, `node-cleared`, `layer-changed`, `view-set`, `lens-set`, `study-mode-set`, `visual-mode-set`
    - Return the same state reference when the action changes nothing, and apply each selection update atomically
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 4.9, 4.10, 9.14, 10.5, 17.5, 17.9, 19.2_

  - [x] 5.2 Write the app reducer property test (test case 6)
    - Create `ui/tests/unit/appReducer.property.test.ts`
    - **Property 6: Selection updates are atomic, validated, and idempotent**
    - **Validates: Requirements 4.4, 4.6, 4.7, 4.8, 4.9, 4.10, 9.14, 10.5, 17.9, 19.2**

  - [x] 5.3 Implement `state/dataReducer.ts`
    - `Remote<T>` states, `DataState` keyed to one `repoId`, per-resource sequence numbers, `resource-start`, `resource-success`, `resource-failure`, and `repo-selected` actions
    - Ignore any result whose `repoId` or `seq` is stale, and clear snapshot, vitals, and explain data on a repository change
    - Support the `replace` and `keep` vitals refresh modes with the `refreshFailed` flag
    - _Requirements: 4.4, 4.14, 8.9, 8.10, 8.11, 19.15, 25.7, 25.9, 25.10_

  - [x] 5.4 Write the data guards property test (test case 9)
    - Create `ui/tests/unit/dataGuards.property.test.ts`
    - **Property 9: Stale responses never change data state**
    - **Validates: Requirements 4.4, 4.14, 8.9, 8.10, 25.9, 25.10**

  - [x] 5.5 Implement `state/store.tsx` and `data/requestScope.ts`
    - Providers, hooks, and selectors for both stores; one effect that persists only `visualMode` to `localStorage` inside `try/catch` and updates `data-visual-mode` synchronously; Study Mode never stored in browser storage
    - Per-repository `AbortController` scope that aborts previous-repository requests on repository change
    - _Requirements: 4.3, 4.5, 4.11, 4.12, 4.13, 10.1, 10.3, 10.4_

  - [x] 5.6 Implement the data-loading hooks
    - `useRepos`, `useSnapshot`, `useVitals`, `useExplain` (Explain_Cache keyed by repo, target, and lens, no caching of failures), `useStudyMode` (pending state, value restored on failure, list entry patched on success), `useIngest` (single in-flight request), `useSocratic`, `useRetry` (health check first after a network error, `rate_limited` countdown gating)
    - Study Mode is set only from the vitals response and the study-mode POST response
    - _Requirements: 3.1, 3.7, 3.8, 3.9, 3.12, 4.5, 4.11, 6.1, 6.5, 7.4, 8.9, 8.10, 9.1, 9.7, 19.8, 19.9, 19.10, 19.15_

- [x] 6. Shared components
  - [x] 6.1 Implement `StateBlock`, `PlainText`, `LiveRegion`, and `MasteryBadge`
    - `StateBlock` with `loading`, `empty`, and `error` variants (retry, optional health note, `retryAfterSeconds` gating) and live-region roles; no color-only state
    - `PlainText` renders a text node with `white-space: pre-wrap`; `MasteryBadge` renders icon, label text, and token from `presentMastery`
    - _Requirements: 3.1, 3.2, 3.3, 3.6, 3.15, 3.16, 11.9, 29.3, 29.9, 29.10_

  - [x] 6.2 Implement `Modal`, `ErrorBoundary`, and `Tabs`
    - `Modal` through a portal to `#modal-root` with focus move, focus trap, `inert` on `#app-root`, focus return to the opener or Command_Bar heading, and Escape ignored while `blockClose` is true
    - `ErrorBoundary` with a fixed message and a reset action that re-renders from the stores without reload
    - Accessible `Tabs` with keyboard support
    - _Requirements: 3.14, 29.1, 29.4, 29.5, 29.6_

- [x] 7. Command_Bar
  - [x] 7.1 Implement the application shell, `DataLoader`, and `NoticeBar`
    - `App.tsx` with `ApiProvider`, store providers, and `Shell` with landmark regions in the order Command_Bar, Specimen_Rail, Canvas, Autopsy_Slab and a `ModalRoot`
    - `DataLoader` loads repos on mount and snapshot and vitals when the selected repository changes; no snapshot request while no repository is selected
    - `NoticeBar` with dismissible notices
    - _Requirements: 3.1, 5.1, 5.5, 5.6, 5.7, 5.8, 5.10, 6.1, 26.2_

  - [x] 7.2 Implement `RepoSelector`
    - List entries in backend order with `repo_id`, `file_count`, `symbol_count`; loading, empty (with Ingest action), and error states with one request per retry
    - Selecting the current repository sends no request; refresh keeps or clears the selection as required; `repo_id` rendered as plain monospace text with the full value in a tooltip and accessible name
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.10, 6.11, 6.12, 6.13_

  - [x] 7.3 Implement `IngestModal`
    - Opens with `GitHub URL` preselected, source choice keeps text and clears messages, trimmed input, validation for blank, over 4096 characters, and missing `https://github.com/` prefix with no request
    - Sends exactly one of `url` or `path` and no limit keys; blocks double submit and Escape while in flight; shows the summary and warnings on success, refreshes the repository list, and selects the new repository; maps `rate_limited` (seconds only when readable) and `local_ingest_disabled`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 29.6_

  - [x] 7.4 Implement `VitalsMeter`, `StudyModeSwitch`, `VisualModeToggle`, and `CommandBar`
    - `VitalsMeter` shows counts and percentage verbatim with a live region, an empty state for `total_modules` 0, and an error state with retry
    - `StudyModeSwitch` as `role="switch"` with pending state (`aria-busy`, previous value shown), restore and error on failure, and `study_mode_disabled` handling
    - `VisualModeToggle` with `aria-pressed` and visible text, dispatching only `visual-mode-set`, independent of Study Mode
    - Assemble `CommandBar` in tab order and wire it into `Shell`
    - _Requirements: 5.1, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12, 9.13, 9.14, 10.1, 10.2, 10.5, 10.13_

  - [x] 7.5 Write the repository list test (test case 12)
    - Create `ui/tests/ui/repos.test.tsx` covering list loading, empty, error with retry, selection, and plain-text rendering of an HTML-tag `repo_id`
    - Deep-link cases are added in task 12.2
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.12, 28.5, 28.14_

  - [x] 7.6 Write the ingest test (test case 13)
    - Create `ui/tests/ui/ingest.test.tsx` covering blank input, wrong GitHub prefix with no request, success with list refresh and selection, `rate_limited` with `Retry-After`, `local_ingest_disabled`, and in-flight double submit
    - _Requirements: 7.4, 7.5, 7.6, 7.8, 7.9, 7.11, 7.12, 28.6_

  - [x] 7.7 Write the vitals and Study Mode test (test case 14)
    - Create `ui/tests/ui/vitalsStudy.test.tsx` covering vitals values and empty state, Study Mode pending state with `aria-busy` and previous value, failure restoring the value with an error, and the Exorcism action hidden while Study Mode is off
    - _Requirements: 8.1, 8.2, 8.3, 9.4, 9.5, 9.7, 23.1, 28.7_

- [x] 8. Specimen_Rail
  - [x] 8.1 Implement `FileTree`
    - `tree` role with roving tabindex, folders then files then symbols from `core/fileTree`, mastery badges via `fileMasteryView` including the Unaudited_Fallback, windowing above 1,000 rows, selection through `select-target`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 11.4, 27.9_

  - [x] 8.2 Implement `VitalOrgansList`
    - Keep backend order, classify each id as `FILE`, `SYMBOL`, or `UNRESOLVED`, select only resolvable ids, and show an empty state when there are none
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 4.9_

  - [x] 8.3 Implement `DriftPanel`
    - List `drift_items` with filter and empty state, treat an absent `UNIMPLEMENTED_SPEC` target as non-selectable, show spec links for the selected file, and handle a missing `has_kiro_specs` state with Graceful_Degradation
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 4.9, 27.6_

  - [x] 8.4 Implement `SpecimenRail` and wire it into `Shell`
    - Collapse button with accessible label and `aria-expanded`; collapsed content is unmounted so controls leave the tab order; selection kept and no request sent while collapsed; freed width goes to the Canvas
    - Show loading and error states for the snapshot request
    - _Requirements: 5.2, 5.3, 5.4, 5.6, 5.7, 5.8, 3.1_

- [x] 9. Canvas
  - [x] 9.1 Implement `GraphView` with `FileNode`, `SymbolNode`, and `CircularEdge`
    - `@xyflow/react` graph from `buildGraphModel` and `layoutGraph` with explicit node sizes, `React.memo` nodes, files and symbols layer switch, `onlyRenderVisibleElements` above 300 nodes, text alternative, keyboard-focusable nodes
    - Shroud for `UNAUDITED` nodes in Autopsy mode, mastery text and icon on nodes, dashed crimson circular edges with a `CIRCULAR` marker, neutral one-hop `UPSTREAM` and `DOWNSTREAM` markers, crimson `BLAST` markers only for ids from an explain `blast_radius`
    - Memoize graph model, layout, cycle set, and mastery lookup per snapshot or vitals value using `core/counters`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.10, 15.11, 15.12, 15.19, 15.20, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 29.7, 29.8_

  - [x] 9.2 Implement `TopologyView`
    - Show `detected_pattern`, `confidence`, the four `boundary_metrics`, `directory_roles` rows in sorted order, and `evidence`, all as plain text
    - Selecting a directory dispatches `select-directory`, keeps file and symbol, and switches the Lens to L3
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9_

  - [x] 9.3 Implement `Canvas` and wire it into `Shell`
    - View `tablist` for Graph and Topology with exactly one active view, per-region `ErrorBoundary`, empty states for no repository, no files, and no edges, and selection kept across view switches
    - _Requirements: 3.14, 5.5, 5.6, 5.7, 5.8, 15.12, 17.9_

  - [x] 9.4 Write the graph and Canvas test (test case 15)
    - Create `ui/tests/ui/graphCanvas.test.tsx` covering graph rendering from the snapshot, a node click updating tree, slab, and vital organs together (Selection_Sync), symbol blast radius from an L2 response, `derived from snapshot` for a file, Topology switch keeping selection, vital organ `UNRESOLVED` and order, and sorted topology rows
    - Assert Autopsy-only decoration through class names and `data-visual-mode`
    - _Requirements: 13.1, 13.3, 15.1, 15.9, 16.1, 16.2, 16.5, 16.6, 17.1, 17.9, 28.8, 10.13_

  - [x] 9.5 Write the memoization test (test case 18)
    - Create `ui/tests/ui/memoization.test.tsx` with a snapshot of 300 or more nodes
    - Read `computeCounters`, change the selection several times, and assert the counters for graph, layout, cycle set, file tree, and mastery lookup are unchanged; assert `onlyRenderVisibleElements` is enabled above 300 nodes
    - _Requirements: 15.7, 15.19, 29.7, 29.8, 29.12_

- [x] 10. Autopsy_Slab
  - [x] 10.1 Implement `SlabMetadata` and `LensTabs`
    - Metadata for the selected file or symbol (path, language, `loc`, `ast_hash` verbatim, line range, signature, copy action with `Copy failed` fallback, commit history list or `No commit history available for this file`, spec links, `File-level blast radius is not provided by the backend`, Unaudited_Fallback for files without a `file_states` key)
    - `LensTabs` as an accessible tablist for the three Lenses with keyboard support
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 27.1, 27.2, 27.5, 27.7, 27.9, 11.4_

  - [x] 10.2 Implement `L1Panel`
    - Summary, annotations with `line_start`, `line_end`, `construct`, `explanation`, hide an empty `what_if_removed`, and `key_takeaway`, all as plain text with no source code shown
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 27.1, 29.10_

  - [x] 10.3 Implement `L2Panel` with DSA cards and Blast_Radius_Chips
    - Execution steps, upstream callers, downstream callees, side effects, a degraded-result notice when `llm_content_available` is false, a `DSA-in-the-Wild` section of `DSA_Card`s that is hidden when `dsa_cards` is empty, and Blast_Radius_Chips with direction text
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 16.3, 16.4, 27.8_

  - [x] 10.4 Implement `L3Panel` with the Counterfactual_Tradeoff_Matrix
    - `topology_pattern`, `why_this_folder_structure`, `structural_evidence`, a matrix comparing the actual pattern (row marked `Selected`) with `alternatives`, `spec_rationale` when present, and an L3 blast radius with `impact_score` 0 not presented as low impact
    - Show an `unknown_target` error with retry while other Lenses stay usable
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 27.8_

  - [x] 10.5 Implement `LensPanel` and `AutopsySlab` and wire them into `Shell`
    - `LensPanel` resolves the target with `resolveExplainTarget`, sends an explain request only when a valid target exists, renders `pick-symbol` guidance for a file selection with L1 or L2, and owns loading, error, and retry states with the explain-specific messages and no cache of failures
    - `AutopsySlab` landmark with an empty state when nothing is selected, an `ErrorBoundary`, and the `ExorcismAction` and Exorcism modal mount point
    - _Requirements: 3.10, 5.9, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 19.9, 19.10, 19.11, 19.12, 19.13, 19.14, 19.15_

  - [x] 10.6 Write the lens test (test case 16)
    - Create `ui/tests/ui/lenses.test.tsx` covering Lens tabs and keyboard use, L1 callouts with an empty `what_if_removed` hidden, L2 flow, DSA cards present and the section hidden when empty, the degraded notice, the L3 matrix with a `Selected` row, error with retry and no cache of failures, a file path never sent as `target_id`, and HTML in backend text shown as text
    - _Requirements: 19.1, 19.3, 19.4, 19.9, 20.1, 20.5, 21.1, 21.5, 21.6, 22.1, 22.4, 28.10, 28.14_

- [x] 11. Exorcism modal and post-verdict refresh
  - [x] 11.1 Implement `ExorcismAction` and `ExorcismModal`
    - Show the action only for a selected symbol while Study Mode is on; start sends only `target_id`; render one or two questions with `line_reference`, with no answer key or `expected_concepts` revealed
    - Drive the modal from `core/exorcism`: 60-second countdown, per-question answer inputs limited to 2000 characters, submit only for complete answers, double-submit guard, read-only state when Study Mode turns off, `study_mode_disabled` and `invalid_answers` handling with answers kept, and grading-unavailable handling
    - Render pass and fail verdicts from `passed`, with `score`, `feedback`, `new_state`, `next_review_at`, a failed `MASTERED` case, and a `New check` action
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7, 23.8, 23.9, 23.10, 23.11, 23.12, 23.13, 23.14, 23.15, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8, 24.9, 24.10, 24.11, 24.12, 24.13, 24.14, 24.15, 3.11, 27.10_

  - [x] 11.2 Implement the post-verification refresh
    - After a verdict, refresh vitals in `keep` mode and update file tree badges, graph Shroud and mastery styling, and the Vitals_Meter from the refreshed `file_states`; no client-side mastery computation
    - Show an out-of-date notice with retry when the refresh fails, keeping the previous values; ignore refresh results for a repository that is no longer selected; clear the Shroud without animation under reduced motion
    - After an explain in Study Mode, refresh vitals in `keep` mode
    - _Requirements: 19.15, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8, 25.9, 25.10, 29.11_

  - [x] 11.3 Write the Exorcism test (test case 17)
    - Create `ui/tests/ui/exorcism.test.tsx` using fake timers
    - Cover start sending only `target_id`, no answer key shown, the 60-second countdown, blank-at-zero expiry, submit, pass and fail verdicts, vitals refresh turning the Shroud and tree badge to `MASTERED`, and `New check` returning `study_mode_disabled` showing the Study Mode off state
    - _Requirements: 23.1, 23.4, 23.8, 23.9, 23.11, 24.1, 24.5, 24.6, 25.1, 25.2, 28.4, 28.11_

- [x] 12. Deep links and URL sync
  - [x] 12.1 Implement `DeepLinkController` and wire it into `Shell`
    - On load, parse `repo_id`, `file`, `view` and resolve against the loaded repository list and snapshot; select only listed repositories and snapshot files; show notices for an unknown repository, an unknown file, and an unsupported view without selecting anything invalid
    - Keep the URL in sync through `history.replaceState` with `buildSearch`, preserving unrelated parameters, with no extra requests
    - _Requirements: 6.8, 6.9, 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8, 26.9, 26.10, 26.11, 26.12, 26.13_

  - [x] 12.2 Extend the repository test with Deep_Link cases (test case 12)
    - Update `ui/tests/ui/repos.test.tsx` to cover Deep_Links for `repo_id`, `file`, and `view`, an unknown repository, an unknown file, and an unsupported view
    - _Requirements: 26.2, 26.5, 26.7, 28.12_

- [x] 13. Checkpoint - Ensure the full UI test suite passes
  - Run `npm test`, `npm run typecheck`, and `npm run build` in `ui/` with `LLM_PROVIDER=mock`. Ensure all pass, the suite has 18 cases and 0 skipped, and ask the user if questions arise.

- [x] 14. Final verification and report
  - [x] 14.1 Run the smoke checks and the final UI commands
    - Search `ui/src` for absolute `http://` or `https://` URLs other than `https://github.com/`, for `dangerouslySetInnerHTML`, and for `fetch(` outside `api/client.ts`; fix any finding
    - Confirm `ui/package-lock.json` exists and that `ui/node_modules/` and `ui/dist/` are ignored
    - Run `npm test`, `npm run build`, and `npm run typecheck` in `ui/` with `LLM_PROVIDER=mock`, and record each exit code and summary line actually produced; run `npm test` three times to confirm identical results
    - _Requirements: 1.5, 1.9, 1.10, 1.11, 2.4, 28.4, 28.15, 29.10, 30.8, 31.1, 31.2_

  - [x] 14.2 Verify backend preservation
    - Run `git status` and `git diff --stat` against the pre-work commit and confirm no path outside `ui/` and `.kiro/specs/04-*`, listing any required repository-root file such as `.gitignore`
    - Run the backend pytest suite with `LLM_PROVIDER=mock` and no network, and confirm 798 passed, 0 failed, 0 errors, 0 skipped
    - Make no backend change; if a real CORS or API defect blocks the UI, record file, issue, reason, and minimal proposed fix instead
    - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7, 30.9, 31.2_

  - [x] 14.3 Write `implementation-report.md`
    - Create `.kiro/specs/04-autopsy-ui/implementation-report.md` with the sections: spec artifacts; frontend structure; API contract verification; UI implementation status per surface (Command_Bar, Specimen_Rail, Canvas, Autopsy_Slab, Exorcism_Modal); test counts; build verification actually executed; backend preservation; limitations; completion status
    - Record the ten Recorded Contract Mismatches by number with their handling, state that the Open Decision was implemented as two independent controls, list any unmet requirement by number, and name any command not run
    - State the completion status as exactly one of `COMPLETE`, `PARTIALLY COMPLETE`, or `BLOCKED`, based only on recorded evidence
    - _Requirements: 31.3, 31.4, 31.5, 31.6, 31.7, 31.8, 31.9_

## Notes

- All test sub-tasks are required because the project owner asked for the full 12 to 18 case plan; 18 cases are planned (11 property, 7 example). Cases 12 is written in 7.5 and extended in 12.2.
- Each property test cites its design property and the requirements it validates.
- Checkpoints 4 and 13 run `npm test`, `npm run typecheck`, and `npm run build`.
- Task 14 never edits `backend/`. The workflow ends when `implementation-report.md` is written; deployment is out of scope.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.7", "3.1", "3.3", "3.11", "3.13"] },
    { "id": 3, "tasks": ["2.3", "3.2", "3.4", "3.5", "3.9", "3.12", "3.14", "3.15"] },
    { "id": 4, "tasks": ["2.4", "3.6", "3.7", "3.10", "5.1", "5.3"] },
    { "id": 5, "tasks": ["2.5", "2.6", "3.8", "5.2", "5.4", "5.5", "6.1", "6.2"] },
    { "id": 6, "tasks": ["5.6"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9.1", "9.2", "10.1", "10.2", "10.3", "10.4", "11.1"] },
    { "id": 8, "tasks": ["7.4", "11.2"] },
    { "id": 9, "tasks": ["7.5", "7.6", "7.7", "8.4"] },
    { "id": 10, "tasks": ["9.3"] },
    { "id": 11, "tasks": ["9.5", "10.5"] },
    { "id": 12, "tasks": ["9.4", "10.6", "11.3", "12.1"] },
    { "id": 13, "tasks": ["12.2"] },
    { "id": 14, "tasks": ["14.1", "14.2"] },
    { "id": 15, "tasks": ["14.3"] }
  ]
}
```
