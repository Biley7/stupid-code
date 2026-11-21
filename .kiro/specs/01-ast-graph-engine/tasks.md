# Implementation Plan: 01-ast-graph-engine

## Overview

This plan implements Spec #01 in Python 3.14 (the language used by `design.md` and the existing backend). It builds in dependency order: test configuration and domain models, ingestion, parser, graph engine, DSA scanner, the four Hypothesis properties, then final verification.

Conventions used in every task:

- Implementation files are `pytest.ini`, `backend/domain/models.py`, `backend/engines/ingestion.py`, `backend/engines/ast_parser.py`, `backend/engines/graph_engine.py`, and `backend/engines/dsa_scanner.py`.
- Unit tests go only in `backend/tests/unit/test_ast_graph_engine.py` (call it the unit file). Property tests go only in `backend/tests/properties/test_ast_graph_properties.py` (call it the property file). No other test file is added (Req 6.3).
- "D1" to "D8" refer to the design decisions table in `design.md`.
- All tests are offline: no network, no real `.env`, `LLM_PROVIDER=mock`, and a recording double for `git_runner` (Req 6.1, 6.2).
- Scope: nothing is added under `backend/api`, `backend/mcp_server`, `power`, `crew`, or `ui`, and nothing from Specs #2 to #4 is implemented (Req 6.18).

## Tasks

- [x] 1. Test configuration and domain models
  - [x] 1.1 Create `pytest.ini` and confirm dependencies
    - Create `/pytest.ini` containing exactly a `[pytest]` section with `testpaths = backend/tests` and `pythonpath = .`, and no other settings.
    - Check `backend/pyproject.toml` declares `tree-sitter`, `tree-sitter-language-pack`, `networkx`, `pydantic>=2`, `pytest`, `hypothesis`, and `ruff`. Add only the missing ones. Do not add SciPy or NumPy (D1).
    - Do not change any other setting in `backend/pyproject.toml`.
    - _Requirements: 1.1, 1.2, 1.3_
    - _Design: "pytest.ini consequences"; D1_
    - Verified by: smoke test in 11.1 and the root run in 11.2.

  - [x] 1.2 Implement `backend/domain/models.py`
    - Implement `Language`, `SymbolKind`, `EdgeType` string enums and the `DSAChapter` literal with the exact members from the design.
    - Implement the `RelativePath` validated type (1 to 4096 chars, no leading `/`, no drive prefix, no `\`, no `.` or `..` segment; D3).
    - Implement `SymbolNode`, `FileAnalysis`, `GraphEdge`, `BlastRadius`, `DSASignal`, `RepoGraphSnapshot` with `ConfigDict(frozen=True, extra="forbid")`, strict scalar types, fields in the declared order, and the cross-field validators (id equals `file_path + "::" + qualname`; `name` equals last qualname segment after stripping one `@\d+` suffix (D2); line ordering; unique symbol ids; foreign `file_path`; bounds on `impact_score` and `confidence`; non-blank evidence).
    - Import only `re`, `enum`, `typing`, and `pydantic`. Add no field for LLM output.
    - Confirm `model_validate_json(model_dump_json())` round-trips under strict types.
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20, 1.21, 1.22, 1.23, 1.24, 1.25, 1.26, 1.27, 1.28, 1.29, 1.30_
    - _Design: "Domain_Models"; "Data Models"; D2, D3_
    - Verified by: unit tests in 1.3.

  - [x] 1.3 Write unit tests for the domain models
    - Create the unit file with the offline autouse fixture (blocks `socket.socket.connect`, `subprocess.run`, `subprocess.Popen`; sets `LLM_PROVIDER=mock`).
    - Add tests: enum values, valid construction of each model, required fields, wrong types naming the field, line validity (0 and 1, end below start), `impact_score` and `confidence` bounds (-0.0001, 0.0, 1.0, 1.0001), unknown chapter, blank evidence, id mismatch, name versus last segment including `@12`, duplicate symbol ids, foreign `file_path`, negative `loc`, enum serialization, JSON round trip, byte-identical dumps, empty lists, partial analysis retaining both lists.
    - _Requirements: 1.5, 1.6, 1.7, 1.9, 1.10, 1.11, 1.14, 1.15, 1.16, 1.19, 1.21, 1.22, 1.23, 1.24, 1.27, 1.28, 1.29, 1.30, 6.1, 6.4_

- [x] 2. Ingestion engine
  - [x] 2.1 Implement ingestion types and URL validation in `backend/engines/ingestion.py`
    - Define `IngestionErrorKind`, `IngestionError(kind, message, detail)`, `WarningKind`, `IngestionWarning`, `GitHubRepoRef`, `DiscoveryResult`, and the `GitRunner` alias (D4).
    - Implement `validate_github_url` as a pure function that applies the rules in the design's order and rebuilds `clone_url` from owner and repo. Each rejection rule raises its own `kind`.
    - Implement `build_clone_destination(ref, workspace)` with real-path containment inside the Managed_Workspace (`data/repos` default).
    - Import no FastAPI, MCP, or frontend module.
    - _Requirements: 2.2, 2.17, 2.18, 2.19, 2.20, 2.21, 2.22_
    - _Design: "Ingestion_Engine"; "GitHub discovery" steps 1 and 2; "Safety boundaries"; D4_
    - Verified by: unit tests in 2.4.

  - [x] 2.2 Implement `discover_local`
    - Validate `max_files` and `max_total_bytes` (int, not bool, at least 1) and the path (empty, NUL, missing, not a directory, unreadable).
    - Resolve the real path as Repo_Root. Walk iteratively with `os.scandir`, sorted by name, with a visited-directory set.
    - Apply Skipped_Directory, extension (case-insensitive), 524288-byte size, 8192-byte NUL probe, symlink-escape warning, and per-entry `ENTRY_UNREADABLE` warning rules. A root `scandir` failure raises `ROOT_FILESYSTEM_ERROR`.
    - Sort qualifying files, then apply `max_files` and `max_total_bytes` truncation in the design's order. Return sorted, duplicate-free `DiscoveryResult` with sorted warnings. An empty result is not an error.
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 2.29_
    - _Design: "Local discovery"; D4_
    - Verified by: unit tests in 2.5.

  - [x] 2.3 Implement `discover_github`
    - Run `validate_github_url`, then `build_clone_destination`, then containment-checked removal of an existing destination (`CLEANUP_FAILED` on failure) and `mkdir(parents=True, exist_ok=True)`.
    - Call `git_runner` once with the exact argv, `shell=False`, `timeout=60`, `capture_output=True`, `stdin=subprocess.DEVNULL`, `check=False`, and an env copy with `GIT_TERMINAL_PROMPT=0`. Argv includes `-c core.hooksPath=<os.devnull>`, `--depth 30`, `--single-branch`, `--no-recurse-submodules`, and a `--` guard.
    - Map `FileNotFoundError`, `TimeoutExpired`, and non-zero exit to `GIT_NOT_INSTALLED`, `GIT_TIMEOUT`, `GIT_FAILED` (first 500 chars of stderr in `detail`), removing any partial clone first. On success run the local walk on the clone.
    - Run no subprocess other than the single git clone.
    - _Requirements: 2.21, 2.22, 2.23, 2.24, 2.25, 2.26, 2.27, 2.28, 2.30_
    - _Design: "GitHub discovery" steps 2 to 6; "Safety boundaries"_
    - Verified by: unit tests in 2.6.

  - [x] 2.4 Write unit tests for URL validation and destination containment
    - Accept table (plain, `.git`, trailing `/`, length limits for owner 39 and repo 100). Reject table with one case per rule: scheme, host, over 2048 chars, userinfo, port, query, fragment, extra path segment, `%2f` and `%5c` in any case, whitespace, control characters, `.` and `..` owner or repo, bad characters. Assert the `kind` for each and that the runner double and filesystem are untouched.
    - Destination containment: a destination resolving outside the workspace (for example via a symlinked workspace entry) raises `DESTINATION_OUTSIDE_WORKSPACE` without calling the runner.
    - _Requirements: 2.17, 2.18, 2.19, 2.20, 2.21, 2.22, 6.2, 6.5_

  - [x] 2.5 Write unit tests for local discovery
    - Using `tmp_path`: Skipped_Directory at any depth, extension case-insensitivity, binary skip, 524287 / 524288 / 524289 byte files, `max_files` truncation, `max_total_bytes` truncation, sorted duplicate-free output, repeat-run equality, symlink escape warning, symlink loop, unreadable entry warning, invalid and unreadable paths, bad limits, empty repository.
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16, 2.29, 6.5_

  - [x] 2.6 Write unit tests for cloning with a test double
    - A recording `git_runner` double asserts exact argv and kwargs (no shell, timeout 60, hooks disabled, no submodules, `--` guard, single call).
    - Cover non-zero exit, missing git, timeout, partial-clone removal, replacement of an existing clone, removal failure (`CLEANUP_FAILED`), and a successful clone followed by discovery on the clone directory. Use a temporary workspace. Assert no real network or subprocess call happens.
    - _Requirements: 2.22, 2.23, 2.24, 2.26, 2.27, 2.28, 2.30, 6.2, 6.5_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. AST parser
  - [x] 4.1 Implement parser common mechanics and the normalized hash in `backend/engines/ast_parser.py`
    - Define `ParsedFile` (frozen dataclass: `analysis`, `source`, `root`, `symbol_nodes`), `ParserError`, `UnsupportedLanguageError(extension)`, `ParserInternalError`.
    - Implement `language_for_path` (case-insensitive extension map), UTF-8 replacement decoding and re-encoding, a lazily cached `Parser` per language, wrapping of grammar or parse exceptions in `ParserInternalError`, `loc` counting (`\r\n|\n|\r`), 1-indexed lines, and the `parse_errors` walk (ERROR and missing nodes, no descent into ERROR, clamped line numbers).
    - Implement `compute_normalized_ast_hash` as an iterative pre-order serialization (comments skipped, length-prefixed leaf text, missing marker, SHA-256 hex). Use explicit stacks or `TreeCursor`, never recursion.
    - Implement `parse_source` and `parse_file` returning one `FileAnalysis` (with `imports`, `exports`, and `symbols` empty until later tasks fill them). Import no FastAPI, MCP, or frontend module.
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.34, 3.35, 3.36_
    - _Design: "Decoding and common mechanics"; "Normalized AST hash algorithm"_
    - Verified by: unit tests in 4.6 and Properties 1 and 2 in 10.1 and 10.2.

  - [x] 4.2 Implement the shared symbol walk and Python extraction
    - Implement the pre-order scope walk with enclosing-name stack for qualnames, `method` versus `function` by nearest enclosing class, nested qualnames, and the post-walk collision suffix `@<start_line>` (including nested prefixes). Set `id = file_path + "::" + qualname`.
    - Implement `raw_calls` collection (explicit stack, not descending into nested Symbol declarations, source-order first occurrences) and `symbol_nodes`.
    - Implement Python rules: `function_definition`, `class_definition`, `decorated_definition` decorators and line range, `async`, signature extraction, call callee rules, imports (including relative imports, D6), and `__all__` exports. Sort and deduplicate `imports` and `exports`.
    - Set Symbol `ast_hash` from the declaration node (the `decorated_definition` when present).
    - _Requirements: 3.4, 3.15, 3.16, 3.17, 3.20, 3.21, 3.22, 3.23, 3.24, 3.25, 3.26, 3.27, 3.28, 3.29, 3.30, 3.31, 3.32_
    - _Design: "Per-language node types: Python"; "Scope and qualnames"; "raw_calls"; D6_
    - Verified by: unit tests in 4.7.

  - [x] 4.3 Implement TypeScript, JavaScript, and TSX extraction
    - Add the TS/JS/TSX rules: function declarations, arrow and function-expression variable declarators, `method_definition`, classes, `interface_declaration` (TS and TSX), decorators (export-statement, class, and preceding-sibling forms, with the line range starting at the first decorator), `async`, call callee rules, import and re-export sources, export statements (named, default, `*`), and `component` detection (JS and TSX, uppercase name, JSX descendant, never methods).
    - Keep signatures without inferred types, ending at `=>` for arrow functions.
    - _Requirements: 3.15, 3.16, 3.17, 3.18, 3.19, 3.22, 3.23, 3.24, 3.26, 3.27, 3.28, 3.30, 3.31_
    - _Design: "Per-language node types: TypeScript, JavaScript, TSX"; research finding 2_
    - Verified by: unit tests in 4.8.

  - [x] 4.4 Implement Java extraction
    - Add the Java rules: `class_declaration`, `enum_declaration` and `record_declaration` as kind `class` (D7), `interface_declaration`, `method_declaration` and `constructor_declaration` as `method`, annotations from `modifiers`, bodiless method signatures, `method_invocation` callee rules, `import_declaration` text (static removed), public top-level type exports, and `is_async` always false.
    - _Requirements: 3.15, 3.16, 3.17, 3.18, 3.22, 3.23, 3.26, 3.27, 3.28, 3.30, 3.31_
    - _Design: "Per-language node types: Java"; D7_
    - Verified by: unit tests in 4.9.

  - [x] 4.5 Implement syntax-error recovery across languages
    - Keep a Symbol only when its declaration node has no error or missing node, and still emit all other Symbols. Ensure erroneous input yields at least one `parse_errors` entry with a line within 1 to the line count, a valid 64-hex `ast_hash`, and no exception for syntax errors.
    - Confirm a grammar-load or Tree-sitter exception raises `ParserInternalError`, is never added to `parse_errors`, and returns no partial `FileAnalysis`.
    - _Requirements: 3.33, 3.34, 3.35_
    - _Design: "Decoding and common mechanics" items 4, 7, 8; "Error Handling"_
    - Verified by: unit tests in 4.10.

  - [x] 4.6 Write unit tests for parser basics and hashing
    - Unsupported extension error carrying the extension, empty file (loc 0, 64-hex hash, no symbols or errors), non-UTF-8 bytes (replacement, repeatable result), `loc` with comment-only and blank lines and `\r` endings, repeat-parse equality, injected parser failure raising `ParserInternalError`.
    - Hash tests: identical source equal; whitespace-only, blank-line-only, and comment-only changes equal; operator change, identifier change, literal change, and structural change (including Python indentation that changes block membership) each differ.
    - _Requirements: 3.5, 3.6, 3.7, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.35, 3.36, 6.7_

  - [x] 4.7 Write unit tests for Python parsing
    - Fixture asserting language, symbols, qualnames, kinds, signatures, line ranges with decorators, imports (absolute and relative), `__all__` exports, `raw_calls` (order, duplicates, nested function ownership), decorators, `async def`, LOC, hash shape, nested qualnames, and `@<line>` collision suffixes. Assert that component and interface kinds do not appear.
    - _Requirements: 3.15, 3.16, 3.17, 3.20, 3.21, 3.22, 3.23, 3.24, 3.26, 3.27, 3.28, 3.29, 3.30, 3.31, 3.32, 6.6_

  - [x] 4.8 Write unit tests for TypeScript, JavaScript, and TSX parsing
    - One fixture per language covering symbols and kinds (function, arrow declarator, method, class, interface for TS and TSX, component for JS and TSX and not for methods), signatures, line ranges, decorators in all three placements, `async`, calls, imports and re-exports, exports (named, default, `*`), LOC, hash, and syntax-error recovery. Assert that interfaces are absent in JavaScript.
    - _Requirements: 3.15, 3.16, 3.17, 3.18, 3.19, 3.22, 3.23, 3.24, 3.26, 3.27, 3.28, 3.30, 3.31, 6.6_

  - [x] 4.9 Write unit tests for Java parsing
    - Fixture covering classes, enums and records as `class`, interfaces, methods and constructors, annotations, bodiless method signatures, calls, imports (plain, wildcard, static), public top-level exports, `is_async` false, LOC, hash, and syntax-error recovery. Assert absence of decorators other than annotations and of `component`.
    - _Requirements: 3.15, 3.16, 3.17, 3.18, 3.22, 3.23, 3.26, 3.27, 3.28, 3.30, 3.31, 6.6_

  - [x] 4.10 Write unit tests for syntax-error recovery
    - For each of the five languages, a source with a syntax error in one function and valid sibling functions: at least one `parse_errors` entry, line within range, valid sibling Symbols retained, erroneous Symbol dropped, 64-hex hash. Include a missing-node case.
    - _Requirements: 3.33, 3.34, 6.6_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Graph engine
  - [x] 6.1 Implement `build_graph` with import resolution in `backend/engines/graph_engine.py`
    - Define `GraphEngineError`, `InvalidArgumentError`, `MissingTargetError(target_id)`, `InvalidInputError`, `ConvergenceError`.
    - Implement `build_graph`: reject duplicate `file_path`, sort inputs, add file nodes then symbol nodes with the documented attributes, and return an empty `DiGraph` for empty input.
    - Implement import resolution per the design table (Python relative with dot arithmetic, Python absolute and Java suffix match with ambiguity giving no edge (D8), TS/JS/TSX relative with extension and `index` candidate order, bare specifiers unresolved). No self-import edges, deduplicated edges, every edge gets `edge_type`.
    - Import only `domain` and `networkx`, and no FastAPI, MCP, or frontend module.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.15, 4.35, 4.37_
    - _Design: "Graph construction"; "Import resolution"; D8_
    - Verified by: unit tests in 6.7.

  - [x] 6.2 Implement call resolution
    - Build `by_file_name`, `by_file_qualname`, and `imported_files` indexes. Apply the three ordered rules: `self.`/`this.` same-class method only, same-file name or qualname with exactly one candidate, then imported-file candidates with exactly one candidate overall (D5, D6). Zero or multiple candidates create no edge. Self-recursion creates a self-loop. Edges are insertion-ordered by the sorted traversal so input permutation gives an identical graph.
    - _Requirements: 4.10, 4.11, 4.12, 4.13, 4.14, 4.15_
    - _Design: "Call resolution"; D5, D6_
    - Verified by: unit tests in 6.8.

  - [x] 6.3 Implement `compute_vital_organs` with pure-Python PageRank
    - Validate `top_k` first (int, not bool, non-negative, else `InvalidArgumentError`, graph unmodified). Implement the fixed-order power iteration (alpha 0.85, tolerance 1e-10, at most 500 iterations, uniform dangling mass, `ConvergenceError` on failure) (D1).
    - Min-max normalize PageRank, in-degree, and out-degree (constant vector gives 0.0), score `0.5/0.25/0.25`, round to 12 decimals, sort by `(-score, node_id)`, and return the first `top_k`.
    - _Requirements: 4.16, 4.17, 4.18, 4.19, 4.20_
    - _Design: "Vital-organs scoring"; D1_
    - Verified by: unit tests in 6.9.

  - [x] 6.4 Implement `detect_cycles`
    - Use `nx.strongly_connected_components`; keep components with more than one node or a self-loop; return sorted node lists in a lexicographically sorted list. Read-only on the graph. Empty and acyclic graphs return `[]`.
    - _Requirements: 4.21, 4.22, 4.23, 4.24, 4.25_
    - _Design: "Cycle detection"_
    - Verified by: unit tests in 6.10 and Property 3 in 10.3.

  - [x] 6.5 Implement `trace_blast_radius`
    - Validate `max_depth` (int, not bool, at least 0, else `InvalidArgumentError`), then target presence (`MissingTargetError`). Run level-by-level BFS over `calls` edges only, upstream on predecessors and downstream on successors, with a visited set seeded with the target. Sort and deduplicate results, exclude the target.
    - Compute `impact_score = 0.0` when there are no Symbol nodes, else `min(1.0, max(0.0, (2*u + d) / (3*S)))`. Depth 0 returns empty lists and 0.0.
    - _Requirements: 4.26, 4.27, 4.28, 4.29, 4.30, 4.31, 4.32, 4.33, 4.34_
    - _Design: "Blast radius" including the `impact_score` bounds argument_
    - Verified by: unit tests in 6.11 and Property 4 in 10.4.

  - [x] 6.6 Implement `build_snapshot`
    - Call `build_graph`, `compute_vital_organs` (default `top_k`), and `detect_cycles`. Sort files by `file_path`, edges by `(source, target, edge_type.value)`, and DSA signals by the full tuple in the design. Return a `RepoGraphSnapshot`.
    - _Requirements: 4.36, 4.37_
    - _Design: "Snapshot assembly"_
    - Verified by: unit tests in 6.12.

  - [x] 6.7 Write unit tests for graph construction and import edges
    - Build `FileAnalysis` inputs directly. Cover import edges per language rule, relative dot arithmetic including going above the root, extension and `index` order, unresolved and external imports, ambiguous absolute imports, no self-import, edge direction, node attributes, permutation invariance, duplicate file path error, and empty input.
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.15, 4.35, 4.37, 6.8_

  - [x] 6.8 Write unit tests for call edges
    - Same-file call, imported-file call, `self.`/`this.` same-class resolution and no fallback when the class lacks the method, ambiguous call (two candidates), unresolved call, self-recursion self-loop, and caller-to-callee direction.
    - _Requirements: 4.4, 4.10, 4.11, 4.12, 4.13, 4.14, 6.8_

  - [x] 6.9 Write unit tests for vital organs
    - Hand-computed small graph checking score arithmetic, equal-score tie-break by node id, constant-component normalization, empty graph, `top_k` 0, `top_k` larger than the node count, and negative `top_k` leaving the graph unmodified.
    - _Requirements: 4.16, 4.17, 4.18, 4.19, 4.20, 6.8_

  - [x] 6.10 Write unit tests for cycle detection
    - Simple cycle, self-loop, multiple components, acyclic graph, empty graph, lexicographic result order, and a seeded 10,000-node, 50,000-edge graph that finishes within 5 seconds.
    - _Requirements: 4.21, 4.22, 4.23, 4.24, 6.8_

  - [x] 6.11 Write unit tests for blast radius
    - Exact upstream and downstream lists on a small graph, depth limits, depth 0, a cycle through the target, target excluded, sorted and duplicate-free output, only `calls` edges followed, missing target, negative depth, `impact_score` bounds, zero-symbol graph, monotonicity in the upstream count on a table of inputs, and repeat-query equality.
    - _Requirements: 4.26, 4.27, 4.28, 4.29, 4.30, 4.31, 4.32, 4.33, 4.34, 6.8_

  - [x] 6.12 Write unit tests for snapshot assembly
    - Ordering of files, edges, and DSA signals (ties broken by the remaining fields), `vital_organs` and `cycles` content, empty input, and JSON round trip of the snapshot.
    - _Requirements: 4.36, 4.37, 1.25, 1.27_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. DSA scanner
  - [x] 8.1 Implement scanner scaffolding in `backend/engines/dsa_scanner.py`
    - Define `ScanResult`, `SkippedFile`, `SkipReason`, and the public `scan_parsed`, `scan_file`, `scan_many`. Scan only `function` and `method` Symbols whose declaration node has no error, over a body that excludes nested Symbol declarations.
    - Implement shared predicates (`in_loop`, `collections`, `self_call`, `conditional`), the evidence formatter (construct plus line or line range inside the Symbol range, at most 10 items, at most 200 characters with the line reference kept), the module-level confidence table (non-decreasing in `k`, two decimals), dedupe per `(symbol_id, chapter, pattern_name)`, and the total sort order. Unsupported extensions return zero signals and one skipped entry. Files with no functions return zero signals.
    - Import no FastAPI, MCP, frontend, or LLM module. Use no regular expression to decide a pattern.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.21, 5.22, 5.24, 5.25, 5.26_
    - _Design: "DSA scanner: Scope and general mechanics, Shared predicates, Confidence table"_
    - Verified by: unit tests in 8.14 and 8.15.

  - [x] 8.2 Implement Hash Tables rules
    - Add `hash-table lookup`, `frequency counting`, and `de-duplication` with the required and optional evidence kinds per language (Python dict/set/Counter, JS and TS `Map`/`Set`, Java `HashMap` family). A literal that is only returned produces nothing.
    - _Requirements: 5.5, 5.6, 5.7, 5.19, 5.20, 5.23_
    - _Design: Rule table Hash Tables rows; "Counting updates by language"; "Language applicability"_
    - Verified by: unit tests in 8.3.

  - [x] 8.3 Write positive and negative fixtures for Hash Tables
    - Positive: lookup in a loop, frequency counting, de-duplication, each in Python, one TS or JS, and one Java case. Assert chapter, pattern name, evidence line numbers inside the Symbol range, and confidence from the table.
    - Negative look-alikes (required): a function that only builds or returns a dict, map, or set literal produces zero Hash Tables signals. A failing negative reports the fixture name and the signal.
    - _Requirements: 5.6, 5.7, 5.21, 6.9, 6.10_

  - [x] 8.4 Implement Graphs & Trees rules
    - Add `queue-based traversal` (`popleft`, `pop(0)`, `shift`, Java `poll`), `stack-based traversal` with visited, and `recursive node traversal` (child-access names) with the evidence kinds from the design.
    - _Requirements: 5.5, 5.8, 5.9, 5.19, 5.20, 5.23_
    - _Design: Rule table Graphs & Trees rows_
    - Verified by: unit tests in 8.5.

  - [x] 8.5 Write positive and negative fixtures for Graphs & Trees
    - Positive: BFS with `deque.popleft` and visited, stack DFS with visited, recursive tree walk over `left` and `right`, plus a JS or Java variant.
    - Negative look-alikes (required): nested loops over plain sequences produce zero signals.
    - _Requirements: 5.8, 5.9, 5.21, 6.9, 6.10_

  - [x] 8.6 Implement Recursion & Dynamic Programming rules
    - Add `direct recursion`, decorator `memoization` (Python `lru_cache` and `cache` forms), and manual `memoization` (lookup before the first self-call, store after it, same name). When both memoization rows match keep the higher confidence and merge evidence.
    - _Requirements: 5.5, 5.10, 5.11, 5.12, 5.19, 5.20, 5.23_
    - _Design: Rule table Recursion rows; memoization note under "Confidence table"_
    - Verified by: unit tests in 8.7.

  - [x] 8.7 Write positive and negative fixtures for Recursion & DP
    - Positive: a recursive factorial (direct recursion), an `@lru_cache` function, a manual memo dict function, and a JS or Java recursive case.
    - Negative look-alikes (required): a function that calls other functions repeatedly but never itself produces zero signals. Assert direct recursion and memoization pattern names differ.
    - _Requirements: 5.10, 5.11, 5.12, 5.21, 6.9, 6.10_

  - [x] 8.8 Implement Heaps & Priority Queues rules
    - Add `heapq operations` (Python, `heapq.<fn>` or bare name with a `heapq` import) and `priority queue usage` (`PriorityQueue`, `MinHeap` family, put-like and get-like calls on the created name).
    - _Requirements: 5.5, 5.13, 5.14, 5.19, 5.20, 5.23_
    - _Design: Rule table Heaps rows_
    - Verified by: unit tests in 8.9.

  - [x] 8.9 Write positive and negative fixtures for Heaps & PQ
    - Positive: `heappush` and `heappop`, `queue.PriorityQueue` put and get, Java `PriorityQueue` `offer` and `poll`.
    - Negative look-alikes (required): a module that imports `heapq` or `queue` but whose function calls no heap or priority-queue operation produces zero signals.
    - _Requirements: 5.13, 5.14, 5.21, 6.9, 6.10_

  - [x] 8.10 Implement Sorting & Binary Search rules
    - Add `bisect usage` (Python), `binary search` (midpoint forms plus a boundary narrowing under a comparison inside the loop), and `custom sort key` (key or comparator function passed to a sort call).
    - _Requirements: 5.5, 5.15, 5.16, 5.19, 5.20, 5.23_
    - _Design: Rule table Sorting rows_
    - Verified by: unit tests in 8.11.

  - [x] 8.11 Write positive and negative fixtures for Sorting & Binary Search
    - Positive: `bisect.bisect_left`, a classic binary search loop, `sorted(..., key=lambda ...)`, and a JS or Java binary search.
    - Negative look-alikes (required): a midpoint computed without a narrowing assignment under a comparison produces zero signals.
    - _Requirements: 5.15, 5.16, 5.21, 6.9, 6.10_

  - [x] 8.12 Implement Sliding Window / Two Pointers rules
    - Add `two pointers` with the three required evidence kinds (pointer init at opposite ends or shared start, conditional move, both used as indices of the same sequence) and the optional loop-condition kind. Confidence uses `k=3` and `k=4`.
    - _Requirements: 5.5, 5.17, 5.18, 5.19, 5.20, 5.23_
    - _Design: Rule table Two Pointers row; Confidence table note_
    - Verified by: unit tests in 8.13.

  - [x] 8.13 Write positive and negative fixtures for Two Pointers
    - Positive: opposite-end pointers moved under a condition, and a window pair indexing one sequence, in Python and one other language.
    - Negative look-alikes (required): a loop with two variables not both used as indices or not both updated produces zero signals.
    - _Requirements: 5.17, 5.18, 5.21, 6.9, 6.10_

  - [x] 8.14 Write negative fixtures for non-pattern code
    - Required negative fixtures for CRUD operations, API routing, configuration loading, plain loops, and simple transforms (at least Python plus one other language). Each must produce zero signals, and a failure message names the fixture and the unexpected signal.
    - _Requirements: 5.19, 6.9, 6.10_

  - [x] 8.15 Write unit tests for scanner behavior
    - Evidence bounds (1 to 10 items, each at most 200 characters, lines inside the Symbol range), chapter restricted to the six values, confidence values match the table and are non-decreasing in `k`, sorted output with no duplicate per symbol, chapter, and pattern, a file with parse errors still scanning its valid Symbols, an unsupported language reported as skipped, a file with no functions yielding zero signals, nested functions scanned as their own Symbols, and repeat-run equality.
    - _Requirements: 5.3, 5.4, 5.5, 5.21, 5.22, 5.24, 5.25, 5.26_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Hypothesis property tests
  - [x] 10.1 Write property test for AST hash invariance
    - Create the property file with the offline autouse fixture and a shared Hypothesis profile (`derandomize=True`, `max_examples` at least 100, no `deadline` override, no `suppress_health_check`).
    - Build the Python snippet model and renderer (identifier pool excluding keywords, integer literals, `+ - * // %`, comparisons, assignment, `return`, `if`/`else`, `while`) with a style record (indent 2, 4, or 8, operator spacing, blank lines, comment placement). Always add at least one comment so the text differs, and assert that.
    - **Property 1: AST hash is invariant under formatting and comment changes**
    - **Validates: Requirements 3.10, 3.11, 3.12, 6.11**
    - Tag: `Feature: 01-ast-graph-engine, Property 1`.
    - _Design: "Generators for the four properties"; Property 1_

  - [x] 10.2 Write property test for AST hash sensitivity
    - Replace one operator or one identifier use with a different valid one from the same class, re-render in the same style, assert zero `parse_errors`, and assert both the file hash and the enclosing Symbol hash differ.
    - **Property 2: AST hash changes when an operator or identifier changes**
    - **Validates: Requirements 3.13, 6.12**
    - Tag: `Feature: 01-ast-graph-engine, Property 2`.
    - _Design: Property 2_

  - [x] 10.3 Write property test for cycle detection and graph integrity
    - Generate digraphs of 0 to 40 nodes in the shapes listed in the design (empty, sparse, dense, only self-loops, closed chains, disjoint components) with `imports` or `calls` edge types. Compare `detect_cycles` against an independent self-reachability oracle, check sorted output and mutual-reachability classes, check every edge endpoint is a node, and compare against a rebuild with permuted node and edge order.
    - **Property 3: Cycle detection terminates, is correct, and is independent of insertion order**
    - **Validates: Requirements 4.3, 4.21, 4.22, 4.24, 4.25, 6.13**
    - Tag: `Feature: 01-ast-graph-engine, Property 3`.
    - _Design: Property 3_

  - [x] 10.4 Write property test for blast-radius monotonicity
    - Generate call graphs that plant a 1 to 4 caller chain into the target in at least half of draws, with `max_depth` from 0 to 5. Add a `calls` edge from a node outside the upstream set (and not the target) to a node inside it or to the target (use `assume` only when no candidate exists). Assert the new upstream set is a superset, sorted, duplicate-free, and excludes the target.
    - Add a companion plain pytest in the property file that samples the strategy under the same derandomized settings and asserts at least 30% of draws have a non-empty upstream set.
    - **Property 4: Adding a caller edge never shrinks the upstream set**
    - **Validates: Requirements 4.26, 4.27, 4.28, 4.29, 6.14**
    - Tag: `Feature: 01-ast-graph-engine, Property 4`.
    - _Design: Property 4_

- [x] 11. Final verification
  - [x] 11.1 Write smoke tests for configuration, layering, and scope
    - In the unit file: parse `pytest.ini` and assert only `testpaths` and `pythonpath`. Assert, by reading module imports with `ast`, that `domain` imports only stdlib and Pydantic, and that no engine imports FastAPI, MCP, or frontend modules, and `dsa_scanner` and `graph_engine` import no LLM module. Assert `ingestion.py` contains no subprocess use other than the `git_runner` default. Assert no new `.py` file exists under `backend/api` beyond `main.py`, and none under `backend/mcp_server`, `power`, `crew`, or `ui`.
    - _Requirements: 1.1, 1.4, 2.2, 2.24, 3.3, 4.2, 5.2, 6.18_

  - [x] 11.2 Run full pytest and ruff, and fix failures
    - Run `pytest` from the repository root and confirm 0 failures and 0 errors, including `backend/tests/unit/test_health.py`.
    - Run `pytest --collect-only -q` from the root and `pytest backend --collect-only -q`, normalize each id to absolute file path plus the part after `::`, and compare the two sets (Req 1.3, per the design's id-normalization note).
    - Run `ruff check backend` and fix every violation in Spec #01 files.
    - _Requirements: 1.2, 1.3, 6.16, 6.17_
    - _Design: "pytest.ini consequences"; "Smoke checks"_

  - [x] 11.3 Run determinism, offline, and safety checks
    - Run the full suite twice and confirm identical results (derandomized Hypothesis, no clock or randomness in outputs).
    - Run the suite with network access unavailable if the environment permits, and confirm no test needs a key, a real `.env`, or GitHub.
    - Grep the six implementation files for `shell=True`, `eval`, `exec`, `import_module`, `os.system`, and `random`, and confirm none applies to analyzed content. Confirm `git status` shows changes only in the Spec #01 files, `pytest.ini`, and `backend/pyproject.toml` if dependencies were added.
    - _Requirements: 6.1, 6.2, 6.15, 6.18, 2.24, 2.25, 3.3, 5.2_
    - _Design: "Determinism rules"; "Safety boundaries"_

- [x] 12. Final checkpoint - Ensure all tests pass and report honestly
  - Ensure all tests pass, ask the user if questions arise.
  - Report to the user, in the reply and not in a new file: what passed, what was not run, and any criterion that is unmet or only partly met. Include the design deviations in effect (D1 to D8), the root-versus-`pytest backend` id-string difference, the skipped optional tests if any, and known limitations (lone `\r` line numbers, call matching by file rather than imported name).

## Notes

- No task is optional. Every unit test, smoke test, property test, and DSA fixture task is required, per `testing-rules.md` and Requirement 6.
- Test work includes the unit tests, the smoke tests, the four Hypothesis property tests (10.1 to 10.4), and every DSA fixture task (8.3, 8.5, 8.7, 8.9, 8.11, 8.13, 8.14). The positive fixtures share a task with the negative look-alikes for the same chapter.
- Each implementation task names the test task that verifies it, and each test task lists the requirements it covers.
- Checkpoints (3, 5, 7, 9, 12) ensure incremental validation.
- This workflow only creates the plan. No code has been written.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1", "4.1", "6.1"] },
    { "id": 3, "tasks": ["2.2", "2.4", "4.2", "6.2"] },
    { "id": 4, "tasks": ["2.3", "2.5", "4.3", "6.3"] },
    { "id": 5, "tasks": ["2.6", "4.4", "6.4"] },
    { "id": 6, "tasks": ["4.5", "4.6", "6.5"] },
    { "id": 7, "tasks": ["4.7", "6.6", "8.1", "10.1"] },
    { "id": 8, "tasks": ["4.8", "8.2", "10.2"] },
    { "id": 9, "tasks": ["4.9", "8.4", "10.3"] },
    { "id": 10, "tasks": ["4.10", "8.6", "10.4"] },
    { "id": 11, "tasks": ["6.7", "8.8"] },
    { "id": 12, "tasks": ["6.8", "8.10"] },
    { "id": 13, "tasks": ["6.9", "8.12"] },
    { "id": 14, "tasks": ["6.10"] },
    { "id": 15, "tasks": ["6.11"] },
    { "id": 16, "tasks": ["6.12"] },
    { "id": 17, "tasks": ["8.3"] },
    { "id": 18, "tasks": ["8.5"] },
    { "id": 19, "tasks": ["8.7"] },
    { "id": 20, "tasks": ["8.9"] },
    { "id": 21, "tasks": ["8.11"] },
    { "id": 22, "tasks": ["8.13"] },
    { "id": 23, "tasks": ["8.14"] },
    { "id": 24, "tasks": ["8.15"] },
    { "id": 25, "tasks": ["11.1"] },
    { "id": 26, "tasks": ["11.2"] },
    { "id": 27, "tasks": ["11.3"] }
  ]
}
```
