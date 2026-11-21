## Integration check (scripts/check_study_mode_parity.py)

Command: `LLM_PROVIDER=mock .venv/bin/python scripts/check_study_mode_parity.py` (run from workspace root)

Output:

```
[set True] API study_mode_enabled=True
[set True] MCP study_mode_enabled=True
[set False] API study_mode_enabled=False
[set False] MCP study_mode_enabled=False
PARITY OK
```

Exit code: 0

`git status --porcelain data`: empty (no ./data files left behind).

## Manifest validation and MCP tool list

Task 18.2 (Requirements 24.5, 24.6, 17.6, 18.9).

### JSON manifests (`.venv/bin/python -m json.tool`, run from workspace root)

```
OK .kiro/settings/mcp.json
OK power/plugin.json
OK power/mcp.json
OK crew/app.json
OK crew/agents/autopsy-surgeon.json
OK crew/agents/socratic-examiner.json
OK .kiro/hooks/verify-engines.json
OK .kiro/hooks/anti-vibe-coding.json
```

All 8 manifests parse without error.

### MCP tool list (real subprocess)

`mcp` stdio client (`StdioServerParameters`) launched with the command and args from `.kiro/settings/mcp.json` (`.venv/bin/python backend/mcp_server/server.py`), `LLM_PROVIDER=mock`, `STUPID_CODE_DB_PATH` set to a temp file. `list_tools()` returned:

```
['dissect_symbol', 'trace_blast_radius', 'analyze_folder_architecture', 'check_spec_drift', 'get_comprehension_vitals']
```

Exactly these five names, no others: EXACT.

### Requirement 24.5 deliverables (non-empty file or directory)

Present: `backend/domain/models.py`, `backend/engines/mastery.py`, `backend/engines/analysis_pipeline.py`, `backend/engines/dissection.py`, `backend/api/routes/repos.py`, `autopsy.py`, `mastery.py`, `crew.py`, `backend/mcp_server/server.py`, `.kiro/settings/mcp.json`, `power/`, `crew/`, both hook files, `backend/tests/properties/test_mastery_properties.py`, `backend/tests/unit/test_mastery_api_mcp.py`.

## Full suite and lint

- `LLM_PROVIDER=mock .venv/bin/python -m pytest -q`: 798 passed in 20.87s (0 failed, 0 errors; 770 baseline + 24 + 4)
- Skipped/xfail (`-rs -rx`): 0 skipped, 0 xfailed
- `pytest --collect-only -q`: 798 tests collected
- `backend/tests/unit/test_mastery_api_mcp.py`: 24 passed in 0.92s (24 `^def test_`, 599 lines)
- `backend/tests/properties/test_mastery_properties.py`: 4 passed in 2.36s (4 `@given`)
- `.venv/bin/ruff check backend scripts`: All checks passed!
- `.venv/bin/ruff format --check backend scripts`: 36 files already formatted
- pytest.ini unchanged (`git diff --stat pytest.ini` empty)

## Backward-compatibility review

Task 18.3. Review only; no source or test file was changed.

### 1. Hash comparison against phase12-hashes.txt

Changed (8): `.env.example`, `.gitignore`, `backend/api/main.py`, `backend/domain/models.py`, `backend/engines/cache_store.py`, `backend/engines/llm_router.py`, `backend/pyproject.toml`, `backend/tests/unit/test_ast_graph_engine.py`.

Unchanged: `pytest.ini`, `backend/tests/conftest.py`, `backend/tests/support.py`, every other Phase 1/2 test file (`test_health.py`, `test_spec_topology_pedagogy.py`, both property files, `properties/.gitkeep`), and the untouched engines `ingestion.py`, `ast_parser.py`, `dsa_scanner.py`, `graph_engine.py`, `spec_grounder.py`, `topology.py`, `pedagogy.py`.

The only changed test file is `test_ast_graph_engine.py` (+18 / -2). Its diff is one added comment line (`# Spec #03 adds these files (user-approved exception to Req 24.3)`) plus the parametrize entries for `backend/api` and `backend/mcp_server`. The `power`, `crew`, and `ui` entries are unchanged. This matches the exception recorded in baseline.md.

No `skip`/`xfail` line was added or removed in any test (`git diff -U0 backend/tests` has no such line). `test_spec_topology_pedagogy.py` and `test_ast_graph_engine.py` already contain skip/xfail text, but it is unchanged from the baseline and the full run reports 0 skipped and 0 xfailed.

### 2. Per-file diff review

| File | numstat (+/-) | Result |
|---|---|---|
| `backend/domain/models.py` | 153 / 0 | Append only. 0 removed lines. |
| `backend/engines/llm_router.py` | 46 / 0 | Additions only (grader builder, registry entry, docstring). |
| `backend/engines/cache_store.py` | 268 / 1 | One removed line: `from sqlalchemy import Engine, UniqueConstraint, event`. Replaced by `from sqlalchemy import Engine, Integer, UniqueConstraint, event, type_coerce`. This is the expected sqlalchemy import widening. No other existing line was removed. |
| `backend/api/main.py` | 73 / 4 | Rewritten as `create_app` plus `app = create_app()`. The 4 removed lines are the old `app = FastAPI(...)` and the old `/health` decorator, signature, and return. `/health` keeps the same path, return type, and body `{"status": "ok", "service": "stupid-code"}`. Its function body is identical but it is now nested in `create_app`. |
| `backend/pyproject.toml` | 1 / 1 | Only `"mcp>=1.0"` changed to `"mcp>=2.3,<3"`. |
| `.env.example` | 5 / 0 | Exactly five appended lines, no secret value. |
| `.gitignore` | 1 / 0 | One appended line, `data/repos/`. It does not ignore `.kiro/` or the hook files. |

All match the design's Phase 1 and Phase 2 Change Log. `cache_store.py` keeps its existing public methods, and the `Integer` and `type_coerce` imports are used by the new additions. I did not diff the design's text for the `type_coerce` use. Nothing indicates it is unjustified.

### 3. Out-of-scope files

- No frontend or Phase 4 files were added. `ui/` holds only the pre-existing tracked `.gitkeep`. There is no `package.json`, `Dockerfile`, CI directory (`.github`), hosting config, `.tsx`, `.jsx`, `.css`, or `*.kiro.hook` file anywhere outside `.venv`.
- `crew/` and `power/` contain no `.py` file. The only JS file is `crew/ui/study-mode-control.mjs`, the required session control.
- The new `.py` files are all within the design's file list or the deviations below.

### 4. `git status --porcelain` grouped

Modified (8): `.env.example`, `.gitignore`, `backend/api/main.py`, `backend/domain/models.py`, `backend/engines/cache_store.py`, `backend/engines/llm_router.py`, `backend/pyproject.toml`, `backend/tests/unit/test_ast_graph_engine.py`.

New:
- Engines: `backend/engines/mastery.py`, `analysis_pipeline.py`, `dissection.py`.
- API: `backend/api/{settings,errors,rate_limit,crew_signature,services,schemas}.py`, `backend/api/routes/` (`repos`, `autopsy`, `mastery`, `crew`).
- MCP: `backend/mcp_server/server.py`, `.kiro/settings/`.
- Hooks: `.kiro/hooks/` (two files).
- Kiro packages: `power/{plugin.json,mcp.json,skills/}`, `crew/{app.json,agents/,skills/,ui/}`.
- Tests: `backend/tests/mastery_support.py`, `backend/tests/properties/test_mastery_properties.py`, `backend/tests/unit/test_mastery_api_mcp.py`.
- Script: `scripts/` (`check_study_mode_parity.py`).
- Spec directory: `.kiro/specs/03-mastery-and-kiro-native/`.

### 5. Deviations and notes

1. `backend/tests/mastery_support.py` is a shared helper module that the tasks specify (task 15.1). It is not a test file, but it is a new file under `backend/tests/`.
2. `scripts/check_study_mode_parity.py` is the integration script that task 17.1 specifies.
3. `backend/tests/unit/test_mastery_api_mcp.py` is 599 lines, one under the 600-line limit. It holds exactly 24 tests.
4. Property 4 only asserts that `json.dumps` succeeds and that `result["ok"]` exists and is a `bool`, as the task specifies. It does not check deeper result content.
5. `test_ast_graph_engine.py` edit is the approved Req 24.3 exception (see baseline.md).
6. The "Present" list in the manifest section named the wrong path for the unit test file. That path is now corrected to `backend/tests/unit/test_mastery_api_mcp.py`.

Conclusion: no unapproved change to a Phase 1/2 file was found, and no source problem to report.
