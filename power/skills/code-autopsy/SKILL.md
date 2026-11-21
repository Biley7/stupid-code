---
name: code-autopsy
description: Perform a grounded Stupid Code autopsy of a local repository. Explain symbols under the L1, L2, or L3 lens, trace blast radius, profile folder architecture, check spec drift, and read Study Mode comprehension vitals through the stupid-code MCP server.
---

# Code Autopsy (Stupid Code)

Use the `stupid-code` MCP server to explain real code from real analysis. The backend parses the repository, builds the call graph, and decides mastery. Your job is to call the tools, report what they return, and say nothing the tools did not return.

## When to use

- The user asks what a function, method, class, or file does, or how it fits into the system.
- The user asks what breaks if a symbol changes (callers, callees, impact).
- The user asks how a repository or folder is organized.
- The user asks whether the code still matches its `.kiro/specs` documents.
- The user asks about their comprehension progress, Study Mode, or due reviews.

## Inputs

Identify both inputs before calling a tool. Ask the user when either is unclear.

1. **Repository path** (`repo_path`): a readable local directory, 1 to 4,096 characters. Use the workspace root unless the user names another directory.
2. **Target symbol** (`target_id`): a Snapshot symbol id of the form `<relative/path.py>::<qualname>`, for example `pkg/mod.py::Parser.parse`. For the L3 lens the target may also be the `repo_id` or a directory path.

If you do not know the exact id, do not guess one. Ask the user, or use ids that appear in earlier tool output (for example `upstream_callers`, `downstream_callees`, or `file_states` keys for the file).

## Tools

Call these tools by these exact names. Each returns a Tool_Result object.

| Tool | Arguments | Success payload |
| --- | --- | --- |
| `dissect_symbol` | `repo_path`, `target_id`, `lens` (default `L2_FLOW`) | `repo_id`, `envelope`, `blast_radius` |
| `trace_blast_radius` | `repo_path`, `target_id`, `max_depth` (integer 0 to 20, default 3) | `repo_id`, `blast_radius` |
| `analyze_folder_architecture` | `repo_path` | `repo_id`, `topology` |
| `check_spec_drift` | `repo_path` | `repo_id`, `has_kiro_specs`, `drift_items` |
| `get_comprehension_vitals` | `repo_path` | `repo_id`, `vitals` |

Notes:

- The first four tools analyze the repository on first use and reuse the stored analysis while the files are unchanged.
- `get_comprehension_vitals` runs no analysis and writes nothing. It fails with `repo_not_analyzed` until another tool has analyzed the repository.
- `analyze_folder_architecture` and `check_spec_drift` make no LLM call.
- `blast_radius` holds `target_id`, `upstream_callers`, `downstream_callees`, and `impact_score`.
- `envelope` holds `repo_id`, `target_id`, `ast_hash`, `lens`, `cached`, and the lens section `l1`, `l2`, or `l3`.
- `topology` holds `detected_pattern`, `confidence`, `directory_roles`, `boundary_metrics`, and `evidence`.
- Each item of `drift_items` holds `drift_type`, `target`, and `details`.

## Lenses

- `L1_SYNTAX`: what the code literally does, line by line. Use for "what does this do".
- `L2_FLOW`: how data and control move through the symbol and its direct neighbors. Use for "how does this work" and as the default.
- `L3_ARCHITECTURE`: where the code sits in the system and which boundaries it touches. Use for "why is this here" and for folders.

Pick the lens that matches the question. Do not combine lens sections into claims that no section makes.

## Evidence rule

Ground every statement in tool output.

- Cite the file path, line range, symbol id, or field name each statement comes from.
- Quote only code that appears in a Tool_Result.
- Never invent code, symbols, line numbers, callers, callees, specs, drift items, or architecture patterns.
- An empty list means none were found. Say so; do not fill the gap from general knowledge.
- If the user asks something the tools cannot answer, say the tools do not cover it.
- When `has_kiro_specs` is false, say the repository has no `.kiro` specs instead of describing any.

## Failures

Every Tool_Result has a boolean `ok`.

- Success: `{"ok": true, ...payload}`.
- Failure: `{"ok": false, "error": {"code": "<code>", "message": "<text>"}}`.

When a Tool_Result is missing, or `ok` is `false`:

1. Tell the user which tool failed and its `error.code` (and the `error.message`).
2. Stop that line of analysis. Do not fill in the missing result from memory or guesswork.
3. Suggest the fix that matches the code, then let the user decide.

| `error.code` | Meaning and next step |
| --- | --- |
| `invalid_repo_path` | `repo_path` is not a readable directory. Ask for a correct path. |
| `no_supported_files` | No readable supported source files. Confirm the path. |
| `repo_not_analyzed` | No stored analysis. Run another tool on the repository first. |
| `unknown_target` | `target_id` is not in the Snapshot. Ask for the exact id. |
| `invalid_lens` | Use `L1_SYNTAX`, `L2_FLOW`, or `L3_ARCHITECTURE`. |
| `invalid_max_depth` | Use an integer from 0 to 20. |
| `llm_unavailable` | The explanation model failed. Retry later; do not write your own explanation. |
| `source_unreadable` | The target file cannot be read. |
| `storage_error` | The cache database failed. |
| `analysis_failed` | Repository analysis failed. |
| `internal_error` | Unexpected server error. Report it as is. |

## Study Mode

Study Mode is a per-repository flag stored by the backend.

1. Read it from `get_comprehension_vitals`: the value is `vitals.study_mode_enabled`.
2. When `study_mode_enabled` is `false`, the tool fails, or the value is not a boolean, run no quiz and ask no comprehension question. Explain code normally.
3. When it is `true`, `dissect_symbol` with `L1_SYNTAX` or `L2_FLOW` records a view, and you may offer a Socratic check.
4. Do not toggle Study Mode on your own. The user turns it on or off (REST `POST /api/repos/{repo_id}/study-mode` with `{"enabled": true}` or `false`).

### Socratic checks

No MCP tool grades answers. Grading goes through the backend REST API:

- `POST /api/repos/{repo_id}/socratic/start` with `{"target_id": "<id>"}` returns the questions. Each has `question_id`, `prompt`, and `line_reference`.
- `POST /api/repos/{repo_id}/socratic/submit` with `{"target_id": "<id>", "answers": [{"question_id": "<id>", "answer": "<text>"}]}` returns a verdict: `passed`, `score`, `feedback`, `new_state`, and `next_review_at`.

Rules:

- Show each question with its `line_reference`. Do not reveal or hint at expected answers before the user answers.
- Submit the user's own words. Do not rewrite, improve, or answer for them.
- Report the verdict exactly as returned. If the call fails, report the error code and grant nothing.

## Mastery

The backend decides mastery. You never do.

- States are `UNAUDITED`, `DISSECTED`, `MASTERED`, and `STALE`. Report them from `vitals` or a verdict only.
- A symbol is mastered only when a submit verdict says `passed: true`. The backend applies the 0.7 pass threshold.
- Do not declare, predict, or promise mastery, and do not compute your own score.
- Report `mastery_percentage`, the state counts, `due_for_review`, and `file_states` as returned.
