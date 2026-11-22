# Implementation Report: 04-autopsy-ui

**Completion status: PARTIALLY COMPLETE**

## 1. Spec artifacts

- `.kiro/specs/04-autopsy-ui/requirements.md`
- `.kiro/specs/04-autopsy-ui/design.md`
- `.kiro/specs/04-autopsy-ui/tasks.md` (and `tasks.meta.json`)
- `.kiro/specs/04-autopsy-ui/implementation-report.md` (this file)

## 2. Frontend structure

All code is under `ui/` (React 18, TypeScript, Vite, Tailwind, `@xyflow/react`, `dagre`, Vitest, Testing Library).

- `ui/src/api/`: `client.ts`, `config.ts`, `context.tsx`, `errors.ts`, `types.ts`, `validate.ts`. Central contract-first client.
- `ui/src/core/`: pure logic (`counters`, `deepLink`, `exorcism`, `explainTarget`, `fileTree`, `graph`, `layout`, `mastery`, `present`, `snapshotIndex`).
- `ui/src/data/`: request hooks (`useRepos`, `useSnapshot`, `useExplain`, `useIngest`, `useVitals`, `useStudyMode`, `useSocratic`, `useLatest`, `useRetry`, `requests`, `requestScope`).
- `ui/src/state/`: `appReducer.ts`, `dataReducer.ts`, `store.tsx`.
- `ui/src/components/`: `shell/` (CommandBar, RepoSelector, IngestModal, StudyModeSwitch, VisualModeToggle, VitalsMeter, DeepLinkController, DataLoader, NoticeBar, Shell), `rail/` (SpecimenRail, FileTree, VitalOrgansList, DriftPanel), `canvas/` (Canvas, GraphView, TopologyView, FileNode, SymbolNode, CircularEdge), `slab/` (AutopsySlab, LensTabs, LensPanel, L1/L2/L3 panels, SlabMetadata, ExorcismAction), `exorcism/ExorcismModal.tsx`, `shared/`.
- `ui/src/styles/`: `index.css`, `tokens.css`.
- Config: `ui/package.json`, `ui/package-lock.json`, `ui/tsconfig.json`, `ui/vite.config.ts`, `ui/tailwind.config.ts`, `ui/postcss.config.js`, `ui/index.html`, `ui/.gitignore`.
- Tests: `ui/tests/ui/` (7 files), `ui/tests/unit/` (11 property files), plus `fixtures/`, `helpers/`, `setup.ts`.

Dev dependencies added beyond the base toolchain: `fast-check` and `@types/node`.

## 3. API contract verification

- Every request goes through the single client in `ui/src/api/client.ts` (the only `fetch` call site in `ui/src`). It uses `/api/repos`, `/api/repos/ingest` and the per-repository routes built by `repoPath`.
- Responses are validated by `ui/src/api/validate.ts` before use. Error envelopes, non-envelope bodies, non-JSON bodies and network failures map to fixed messages; `Retry-After` is read only when the header is readable (`parseRetryAfter`).
- No endpoint was invented. No backend change was proposed or made.
- CORS: no defect found. In dev, the Vite proxy makes requests same-origin. A cross-origin `VITE_API_BASE_URL` would need its origin in `STUPID_CODE_CORS_ORIGINS`, and `Retry-After` would then be unreadable (as the requirements already state).
- No CORS or API defect was reported, so there is no defect to list under Req 31.8.

### Recorded Contract Mismatches

| # | Mismatch | Handling in the UI |
|---|---|---|
| 1 | No source text endpoint | No source code is shown. `SlabMetadata` shows line ranges, metadata and backend text only (file header comment: "no source code"). |
| 2 | No standalone blast-radius route | Blast radius is taken only from the explain response of a selected symbol (`selectBlastRadius` in `GraphView.tsx`). File nodes get none. |
| 3 | No per-symbol or per-file-record mastery | Mastery comes from `file_states` and aggregate counts. `core/mastery.ts` maps `NO TRACKED SYMBOLS` and `STATE UNKNOWN` for files without a state. |
| 4 | No ingestion progress stream | The ingest modal shows an in-flight state for the single blocking request and sends no second request. No percentage is shown. |
| 5 | Recent commits are opaque strings and may be absent | `SlabMetadata` looks up `recent_commits` per file path with an own-property check and falls back to an empty list. Strings are rendered as text. |
| 6 | Spec evidence is per file | `spec_links` is read per file path (`SlabMetadata`, `DriftPanel`). Drift items carry no links. `DriftPanel` handles a missing `has_kiro_specs` with Graceful_Degradation. |
| 7 | Missing Socratic answers have no representation | `ExorcismModal` trims answers and does not submit blanks. On timeout with blank answers it shows "nothing was submitted". |
| 8 | `expected_concepts` is empty in the start response | The Exorcism modal does not read or reveal `expected_concepts` (only a comment mentions it). No answer key is shown. |
| 9 | No `GET` for one repository | Repository detail comes from `GET /api/repos/{repo_id}/snapshot` (`useSnapshot`). |
| 10 | `ast_hash` exists only as stored values | `SlabMetadata` shows `ast_hash` exactly as returned (`HashRow`), with no normalization. |

### Open Decision

Autopsy Mode and Lab Mode were implemented as **two independent controls**: `VisualModeToggle` (visual only) and `StudyModeSwitch` (backend Study Mode). Neither changes the other. This follows the Spec #04 request, not the `design-system.md` mapping of Lab Mode to Study Mode ON. The project owner has not yet decided; changing it later affects only the control wiring.

## 4. UI implementation status per surface

Status is based on code presence and jsdom tests. No browser or visual check was done (see Limitations).

- **Command_Bar** (`shell/`): implemented. Repo selector, Ingest button and modal, Study Mode switch, Autopsy/Lab toggle, Vitals meter. Partial: Req 7.16 (see Limitations).
- **Specimen_Rail** (`rail/`): implemented. File tree, vital organs quick-jump, spec drift panel.
- **Canvas** (`canvas/`): implemented. Skeletal graph with memoized nodes, circular-edge marking, selection sync, blast radius for symbols, topology view. React Flow is mocked in tests.
- **Autopsy_Slab** (`slab/`): implemented. Metadata, lens tabs, L1, L2 (with DSA cards, section hidden when empty) and L3 (counterfactual matrix) panels, Exorcism action shown only while Study Mode is on.
- **Exorcism_Modal** (`exorcism/`): implemented. Start without an answer key, 60 s countdown, submit, verdicts, `study_mode_disabled` handling, refresh of vitals and graph styling after the verdict.

## 5. Test counts

Run now with `LLM_PROVIDER=mock npm test` in `ui/`:

- `Test Files  18 passed (18)`
- `Tests  18 passed (18)`
- 0 failed, 0 skipped. 11 property tests (`ui/tests/unit/*.property.test.ts`) and 7 UI test files (`ui/tests/ui/`).
- `fetch` is mocked everywhere. The `mockFetch` helper fails any unmatched request. Fake timers cover the 60 s countdown.
- Three consecutive reruns each reported `Test Files  18 passed (18)` and `Tests  18 passed (18)`.
- Req 28.1 requires 12 to 18 cases. The suite has 18.

## 6. Build verification actually executed

Run in `ui/` on this date:

| Command | Exit code | Summary lines |
|---|---|---|
| `LLM_PROVIDER=mock npm test` | 0 | `Test Files  18 passed (18)`, `Tests  18 passed (18)` |
| `npm run typecheck` (`tsc --noEmit`) | 0 | no errors printed |
| `npm run build` (`tsc --noEmit && vite build`) | 0 | `✓ 1991 modules transformed.`, `dist/assets/index-jGg_LKXk.js 527.91 kB │ gzip: 169.84 kB`, `✓ built in 1.03s`. It also prints a chunk-size warning (chunks over 500 kB). The warning does not fail the build. |

Backend suite: see section 7. No command required by Req 31.1 was left unrun.

## 7. Backend preservation

- Tracked files under `backend/`, `power/`, `crew/`, `scripts/` and `.kiro/specs/01-*` to `03-*`: no change (`git diff HEAD` over those paths is empty).
- The only modified tracked file in the repository is `.kiro/settings/mcp.json`, an intentional local edit made by the project owner before this work. It is outside the Autopsy_UI scope and was not touched by this work.
- Everything else is untracked and new: `.kiro/specs/04-autopsy-ui/` and `ui/` files. The root `.gitignore` was not modified. `ui/.gitignore` ignores `node_modules/` and `dist/` (confirmed with `git check-ignore`). No other repository-root file was added.
- No deployment configuration (container file, CI workflow, hosting manifest, infrastructure code) was added.
- `ui/package-lock.json` exists and is untracked. It must be committed.
- Backend suite results, stated separately:
  - **Working tree:** `1 failed, 797 passed`. The single failure is `backend/tests/unit/test_mastery_api_mcp.py::test_manifests_hooks_and_launch_config`. It fails because the owner's local `.kiro/settings/mcp.json` edit introduces absolute `/Users/...` paths. The working tree does **not** show 798 passed.
  - **Committed tree:** `git archive HEAD` exported to a temporary directory, with `PYTHONPATH` taking precedence and offline `LLM_PROVIDER=mock`: `798 passed in 23.03s`.
  - This result comes from the earlier verification and was not re-run for this report.

## 8. Limitations, deviations and decisions

1. **Vitals refresh modes.** The vitals refresh keeps the earlier values in some refresh paths and replaces them in others. Req 8.11 requires an error state to replace earlier values on a failed refresh. Check this against the design before relying on it.
2. **L3 explain target.** The L3 target is sent only when a valid selection exists. `resolveExplainTarget` returns no target otherwise. A file path is never sent as an explain target.
3. **Ingest modal close (Req 7.16).** The modal blocks closing while the request is in flight. The requirement asks to dismiss only the display and still apply the selection on success. `useIngest` aborts on unmount (`controller.current?.abort()`), so the modal cannot be hidden safely without a change. Req 7.16 is therefore only partly met.
4. **Toggle POST and `study_mode_disabled`.** `StudyModeSwitch` has no special handling of a `study_mode_disabled` code on the toggle request and shows a generic message. Handling of that code for `socratic/start` and `socratic/submit` is implemented (`useSocratic.ts`, `core/exorcism.ts`).
5. **Ingest follow-up error text.** In the ingest modal the follow-up error shows the fixed network message, not the specific error `message`.
6. **Dependencies.** `fast-check` and `@types/node` were added as dev dependencies.
7. **Colors.** An amber token `#F59E0B` was added to the design tokens, in addition to the colors in `design-system.md`.
8. **Bundle size.** The build warns about a 527.91 kB chunk. It is a warning only, and no code splitting was added.
9. **No browser or visual verification.** Only jsdom was used. React Flow is mocked in the tests. Layout, contrast (Req 29.2), focus behavior in a real browser and the reduced-motion CSS were not measured or viewed. Reduced motion exists as a `@media (prefers-reduced-motion: reduce)` rule in `index.css`.
10. **Task citations.** The requirement citations in `tasks.md` for tasks 8 to 27 were treated as non-authoritative. Requirements were taken from `requirements.md`.
11. **Formatting.** Prettier was not run. Step bodies inside merged `it` blocks are indented one level shallow.
12. **Safety checks.** No `dangerouslySetInnerHTML` appears in `ui/src` (grep found none).

### Unmet or partially met requirements

- **Req 7.16:** partially met. Close is blocked during the in-flight request, and `useIngest` aborts on unmount (item 3).
- **Req 30.3 and 31.2:** not met in the working tree. The Backend_Suite shows `1 failed, 797 passed` there because of the owner's `mcp.json` edit. Against the committed tree it shows `798 passed`.
- **Req 30.4:** the diff outside `ui/`, `.kiro/specs/04-*` is `.kiro/settings/mcp.json`. It is the owner's pre-existing edit and not part of this work.
- **Req 29.2 (contrast) and the visual parts of Req 29 and 10:** not verified in a browser. They are unconfirmed, not known to fail.
- **Req 8.11:** unconfirmed (item 1).
- **Req 7.14:** the follow-up error is shown as a fixed message instead of the specific error (item 5).

## 9. Completion status

**PARTIALLY COMPLETE.** `npm test`, `npm run typecheck` and `npm run build` all exit 0. The working-tree Backend_Suite shows 797 passed and 1 failed, only because of the owner's local `.kiro/settings/mcp.json` edit. The committed tree passes 798. Req 7.16 is partly met, and no browser check was done.
