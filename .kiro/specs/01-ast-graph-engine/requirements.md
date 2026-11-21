# Requirements Document

## Introduction

Spec #01 delivers the deterministic, offline, LLM-free static-analysis foundation of Stupid Code (Code Autopsy Edition). It covers six areas: test configuration and pure domain schemas, safe repository ingestion, a multi-language Tree-sitter parser with AST normalizer, a NetworkX dependency and call graph engine with blast-radius tracing, a structural DSA-in-the-Wild scanner, and the unit and Hypothesis property tests that verify them.

The supported languages are Python, TypeScript, JavaScript, TSX, and Java. All analysis is static. Analyzed repositories are treated as untrusted, and no repository code is ever executed or imported.

Layering follows `.kiro/steering/architecture.md`: `domain` depends on nothing in this project, `engines` use `domain`, and neither imports FastAPI, MCP, or frontend code.

### Out of Scope

Spec and Git provenance grounding, folder topology, counterfactual architecture, pedagogy, LLM routing, AST context slicing, SQLite caching, Study Mode, mastery, FSRS, Socratic flows, FastMCP tools, Kiro Power and Crew, hooks, API expansion, frontend and UI, deployment, and DSA categories beyond the six listed in Requirement 5. These belong to later specs and are not implemented here.

### Steering Observations (reported, not silently resolved)

1. **Total-size guardrail.** `architecture.md` requires file-count, per-file-size, and total-repository-size limits plus time and resource guardrails. The request names only a per-file limit (512 KB) and a file-count limit (500). Requirement 2 adds a configurable total-bytes limit and the clone timeout so the spec satisfies the steering document. Please confirm or remove.
2. **Network versus offline suite.** `testing-rules.md` forbids external network services in tests, while Requirement 2 clones from GitHub. Requirement 6 therefore requires all clone tests to replace the git subprocess with a test double. No test may contact GitHub.
3. **Pytest configuration precedence.** `backend/pyproject.toml` already has `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and `addopts = "-ra"`. A root `pytest.ini` takes precedence when pytest runs from the repository root, so those two settings would not apply there. The requested minimal `pytest.ini` is kept as specified. Spec #01 tests are synchronous, so there is no functional impact now. The design must record the consequence for future async tests.
4. **Dependency on provider settings.** `testing-rules.md` requires `LLM_PROVIDER=mock` by default and no real `.env` reads. Spec #01 has no LLM or settings usage, so this holds trivially, and Requirement 6 states it explicitly.

No direct contradiction between the request and the steering documents was found. `design-system.md` and `product.md` impose no constraints on this backend-only spec beyond the DSA-in-the-Wild rule: patterns are reported only when evidence supports them.

## Glossary

- **Pytest_Config**: The root `pytest.ini` file.
- **Domain_Models**: The Pydantic v2 module `backend/domain/models.py`.
- **Ingestion_Engine**: The module `backend/engines/ingestion.py`.
- **AST_Parser**: The module `backend/engines/ast_parser.py`.
- **Graph_Engine**: The module `backend/engines/graph_engine.py`.
- **DSA_Scanner**: The module `backend/engines/dsa_scanner.py`.
- **Test_Suite**: The tests in `backend/tests/unit/test_ast_graph_engine.py`, `backend/tests/properties/test_ast_graph_properties.py`, and existing tests.
- **Repo_Root**: The resolved absolute directory under analysis. For a local analysis it is the validated input directory. For a remote analysis it is the clone directory.
- **Relative_Path**: A POSIX-style path relative to Repo_Root, with no leading slash and no `.` or `..` segments.
- **Supported_Extension**: One of `.py`, `.ts`, `.js`, `.tsx`, `.java`. These map to python, typescript, javascript, tsx, java respectively.
- **Managed_Workspace**: The directory `data/repos/` under the project root, the only location where clones are created.
- **Skipped_Directory**: A directory named `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build`, `__pycache__`, `.next`, `target`, or `.pytest_cache`.
- **Symbol**: A function, method, class, interface, or component represented by a SymbolNode.
- **Qualname**: The dotted name of a Symbol within its file, for example `Outer.inner_method`.
- **Symbol_Id**: The string `<Relative_Path>::<Qualname>`.
- **Normalized_AST_Hash**: The SHA-256 hex digest defined in Requirement 3, criteria 10 to 13.
- **Parse_Error**: A Tree-sitter ERROR or MISSING node reported in `FileAnalysis.parse_errors` with a 1-indexed line.
- **Raw_Call**: A callee identifier string extracted syntactically from a call expression in a Symbol body, with no semantic resolution.
- **Import_Edge**: A GraphEdge with `edge_type` `imports`, where source is the importing file path and target is the imported file path.
- **Call_Edge**: A GraphEdge with `edge_type` `calls`, where source is the caller Symbol_Id and target is the callee Symbol_Id.
- **Blast_Radius**: The BlastRadius model describing upstream callers and downstream callees of a target within a depth bound.
- **Vital_Organ**: A node ranked among the top-k nodes by the deterministic centrality ranking in Requirement 4.
- **DSA_Chapter**: One of the strings `Hash Tables`, `Graphs & Trees`, `Recursion & Dynamic Programming`, `Sliding Window / Two Pointers`, `Heaps & Priority Queues`, `Sorting & Binary Search`.
- **DSA_Signal**: A DSASignal produced by the DSA_Scanner for one function or method.
- **Evidence**: A concrete, non-empty structural observation, for example `while loop at lines 12-20 with variables left, right updated in body`.

## Requirements

### Requirement 1: Test Configuration and Pure Domain Schemas

**User Story:** As a developer, I want consistent test discovery and a pure, validated set of domain schemas, so that every engine shares one deterministic data contract.

#### Acceptance Criteria

1. THE Pytest_Config SHALL contain a `[pytest]` section with `testpaths = backend/tests` and `pythonpath = .` and no other settings.
2. WHEN `pytest` is run from the repository root with no arguments, THE Test_Suite SHALL be discovered from `backend/tests`.
3. WHEN `pytest backend` is run from the repository root, THE Test_Suite SHALL be discovered with the same set of test ids as the run in criterion 2.
4. THE Domain_Models SHALL import only the Python standard library and Pydantic v2.
5. THE Domain_Models SHALL define a `Language` string enum with exactly the serialized values `python`, `typescript`, `javascript`, `tsx`, `java`.
6. THE Domain_Models SHALL define a `SymbolKind` string enum with exactly the serialized values `function`, `method`, `class`, `interface`, `component`.
7. THE Domain_Models SHALL define an `EdgeType` string enum with exactly the serialized values `imports`, `calls`.
8. THE Domain_Models SHALL define `SymbolNode` with exactly the fields `id` (string), `name` (string), `qualname` (string), `kind` (`SymbolKind`), `file_path` (string), `start_line` (integer), `end_line` (integer), `signature` (string), `ast_hash` (string), `decorators` (list of strings), `is_async` (boolean), `raw_calls` (list of strings).
9. WHEN a SymbolNode is constructed, THE Domain_Models SHALL accept it only if `id` equals `file_path + "::" + qualname` exactly (case-sensitive, no normalization).
10. IF a SymbolNode is constructed with `start_line` below 1, or with `end_line` below `start_line`, THEN THE Domain_Models SHALL raise a validation error and SHALL NOT create the object.
11. IF a SymbolNode is constructed with a `file_path` that is not a Relative_Path, or with a `name` that differs from the last dot-separated segment of `qualname`, THEN THE Domain_Models SHALL raise a validation error and SHALL NOT create the object.
12. THE Domain_Models SHALL define a Relative_Path as a non-empty string of at most 4096 characters that uses `/` as its separator, does not start with `/`, does not start with a drive letter followed by `:`, contains no `\` character, and contains no `..` segment.
13. THE Domain_Models SHALL define `FileAnalysis` with exactly the fields `file_path` (Relative_Path), `language` (`Language`), `loc` (integer), `ast_hash` (string), `imports` (list of strings), `exports` (list of strings), `symbols` (list of SymbolNode), `parse_errors` (list of strings).
14. WHEN a FileAnalysis is constructed with a non-empty `parse_errors` list and a valid `symbols` list, THE Domain_Models SHALL accept it as a valid partial analysis and SHALL retain every entry of both lists unchanged and in order.
15. IF a FileAnalysis is constructed with `loc` below 0, or with any contained SymbolNode whose `file_path` differs from the FileAnalysis `file_path`, THEN THE Domain_Models SHALL raise a validation error and SHALL NOT create the object.
16. IF a FileAnalysis is constructed with two or more SymbolNodes that have the same Symbol_Id, THEN THE Domain_Models SHALL raise a validation error and SHALL NOT create the object.
17. THE Domain_Models SHALL define `GraphEdge` with exactly the fields `source` (string), `target` (string), `edge_type` (`EdgeType`).
18. THE Domain_Models SHALL define `BlastRadius` with exactly the fields `target_id` (string), `upstream_callers` (list of strings), `downstream_callees` (list of strings), `impact_score` (float).
19. IF a BlastRadius is constructed with `impact_score` below 0.0 or above 1.0, THEN THE Domain_Models SHALL raise a validation error. The values 0.0 and 1.0 SHALL be accepted.
20. THE Domain_Models SHALL define `DSASignal` with exactly the fields `symbol_id` (string), `file_path` (Relative_Path), `start_line` (integer), `end_line` (integer), `chapter` (DSA_Chapter), `pattern_name` (string), `confidence` (float), `evidence` (list of strings).
21. IF a DSASignal is constructed with `confidence` below 0.0 or above 1.0, THEN THE Domain_Models SHALL raise a validation error. The values 0.0 and 1.0 SHALL be accepted.
22. IF a DSASignal is constructed with an empty `evidence` list, or with any evidence string that is empty or contains only whitespace characters, THEN THE Domain_Models SHALL raise a validation error.
23. IF a DSASignal is constructed with a `chapter` value that is not a member of DSA_Chapter, THEN THE Domain_Models SHALL raise a validation error.
24. IF a DSASignal is constructed with `start_line` below 1, or with `end_line` below `start_line`, THEN THE Domain_Models SHALL raise a validation error.
25. THE Domain_Models SHALL define `RepoGraphSnapshot` with exactly the fields `repo_id` (string), `root_path` (string), `files` (list of FileAnalysis), `edges` (list of GraphEdge), `vital_organs` (ordered list of node id strings), `cycles` (list of lists of node id strings), `dsa_signals` (list of DSASignal).
26. THE Domain_Models SHALL contain no field intended to hold LLM output.
27. WHEN any domain model instance is serialized to JSON and validated again, THE Domain_Models SHALL produce an instance equal to the original, including list order and enum members.
28. WHEN any domain model is serialized, THE Domain_Models SHALL emit enum members as their string values, and two serializations of equal instances SHALL be byte-identical.
29. THE Domain_Models SHALL accept an empty list (length 0) for every list-typed field.
30. IF a required field is missing or has a value of the wrong type, THEN THE Domain_Models SHALL raise a validation error that identifies the offending field, and SHALL NOT create the object.

### Requirement 2: Safe Repository Ingestion

**User Story:** As a developer, I want to discover source files from a local directory or a public GitHub repository without running any repository code, so that untrusted code can be analyzed safely.

#### Acceptance Criteria

1. THE Ingestion_Engine SHALL expose one function that discovers supported source files from a local directory and one function that discovers them from a public GitHub HTTPS URL, and both SHALL return a list of Relative_Path strings that is sorted in ascending lexicographic order and contains no duplicates, together with a truncation indicator and a list of typed warnings.
2. THE Ingestion_Engine SHALL import no FastAPI, MCP, or frontend module.
3. THE Ingestion_Engine SHALL include only files whose extension, compared case-insensitively, is a Supported_Extension.
4. IF the local path is empty, consists only of whitespace, is malformed, does not exist, is not a directory, or is not readable by the current process, THEN THE Ingestion_Engine SHALL raise a typed ingestion error whose type identifies which of these causes applies and SHALL return no file list.
5. WHEN a local path is provided, THE Ingestion_Engine SHALL resolve it to an absolute real path (all symlinks resolved) and use that path as Repo_Root.
6. IF a discovered entry resolves, after symlink resolution, to a location outside Repo_Root, THEN THE Ingestion_Engine SHALL exclude that entry, record a typed warning naming its Relative_Path, and continue discovery.
7. WHEN discovery encounters a symlinked directory, THE Ingestion_Engine SHALL traverse it only if its resolved path lies inside Repo_Root and has not already been visited in the current discovery.
8. THE Ingestion_Engine SHALL skip every Skipped_Directory at any depth.
9. THE Ingestion_Engine SHALL skip every file larger than 512 KB (524288 bytes); a file of exactly 524288 bytes SHALL be included.
10. THE Ingestion_Engine SHALL skip every file whose first 8192 bytes contain a NUL byte (a file shorter than 8192 bytes is checked over its full length).
11. THE Ingestion_Engine SHALL accept a `max_files` parameter with default 500 and a `max_total_bytes` parameter with default 20971520 (20 MB), and SHALL raise a typed ingestion error if either value is not an integer of at least 1.
12. WHEN the number of qualifying files exceeds `max_files`, THE Ingestion_Engine SHALL return the first `max_files` Relative_Path values in sorted order and SHALL set the truncation indicator to true.
13. WHEN adding the next qualifying file in sorted order would make the cumulative size of returned files exceed `max_total_bytes`, THE Ingestion_Engine SHALL stop adding files, exclude that file and all later files, and SHALL set the truncation indicator to true.
14. WHEN the same repository content is discovered twice, THE Ingestion_Engine SHALL return byte-identical lists regardless of filesystem enumeration order.
15. IF a filesystem error occurs while reading a single entry below Repo_Root, THEN THE Ingestion_Engine SHALL skip that entry, record a typed warning containing the entry's Relative_Path and the error cause, and continue discovery.
16. IF a filesystem error occurs on Repo_Root itself, THEN THE Ingestion_Engine SHALL raise a typed ingestion error and SHALL return no file list.
17. THE Ingestion_Engine SHALL validate a GitHub URL in a step that is separate from, and runs before, destination-path construction.
18. WHEN a GitHub URL is validated, THE Ingestion_Engine SHALL accept only the form `https://github.com/<owner>/<repo>` with an optional trailing `.git` or `/`, and a total length of at most 2048 characters.
19. WHEN a GitHub URL is validated, THE Ingestion_Engine SHALL require `<owner>` to match `[A-Za-z0-9_.-]+` with length 1 to 39 characters, SHALL require `<repo>` to match `[A-Za-z0-9_.-]+` with length 1 to 100 characters, and SHALL reject the values `.` and `..` for either.
20. IF a GitHub URL uses a scheme other than `https`, has a host other than `github.com`, exceeds 2048 characters, or contains userinfo, a port, a query, a fragment, extra path segments, encoded separators, whitespace, or control characters, THEN THE Ingestion_Engine SHALL raise a typed ingestion error identifying the violated rule, without invoking git and without creating any directory.
21. WHEN a GitHub URL has been validated, THE Ingestion_Engine SHALL derive the destination directory from the parsed owner and repo values only, beneath the Managed_Workspace.
22. WHEN a destination directory is constructed, THE Ingestion_Engine SHALL verify that its resolved path is inside the Managed_Workspace before cloning, and IF it is not, THE Ingestion_Engine SHALL raise a typed ingestion error without invoking git.
23. WHEN a clone is performed, THE Ingestion_Engine SHALL run `git clone --depth 30 --single-branch` as a subprocess with an argument list, without a shell, with `--no-recurse-submodules`, with git hooks disabled, and with a timeout of 60 seconds.
24. THE Ingestion_Engine SHALL run no subprocess other than the git clone.
25. THE Ingestion_Engine SHALL run no build, install, or repository script, and SHALL NOT execute or import any repository file.
26. IF git exits with a non-zero status, is not installed, or runs longer than the 60-second timeout, THEN THE Ingestion_Engine SHALL terminate the git process, raise a typed ingestion error identifying which of these three causes applies, remove any partial clone directory, and SHALL NOT return a file list.
27. WHEN a clone directory for the same owner and repo already exists in the Managed_Workspace, THE Ingestion_Engine SHALL replace it with a fresh clone, performing removal only on a path verified to be inside the Managed_Workspace.
28. WHEN a clone succeeds, THE Ingestion_Engine SHALL apply criteria 3 to 14 to the clone directory as Repo_Root.
29. WHEN discovery on a valid Repo_Root finds no qualifying files, THE Ingestion_Engine SHALL return an empty list, no error, and a truncation indicator of false.
30. IF removal of an existing or partial clone directory fails, THEN THE Ingestion_Engine SHALL raise a typed ingestion error naming the failure and SHALL NOT return a file list.

### Requirement 3: Tree-sitter Parser and AST Normalizer

**User Story:** As a developer, I want each source file converted into a deterministic structured analysis, so that graph and pattern engines work from real syntax rather than text guesses.

#### Acceptance Criteria

1. THE AST_Parser SHALL parse files using the `tree-sitter` and `tree-sitter-language-pack` packages, with the grammars python, typescript, javascript, tsx, and java.
2. WHEN a file with a Supported_Extension is parsed, THE AST_Parser SHALL return exactly one `FileAnalysis` from `backend/domain/models.py` for that file, including when the file has syntax errors.
3. THE AST_Parser SHALL import no FastAPI, MCP, or frontend module and SHALL NOT execute or import any analyzed source.
4. THE AST_Parser SHALL derive Symbols, imports, exports, decorators, async status, and Raw_Call values from Tree-sitter nodes, using regular expressions only for minor string handling that does not decide whether a construct is a Symbol, import, export, decorator, async function, or call.
5. IF a file extension is not a Supported_Extension, THEN THE AST_Parser SHALL raise a typed unsupported-language error that identifies the rejected extension, and SHALL return no FileAnalysis.
6. THE AST_Parser SHALL set `FileAnalysis.language` from the file extension and `FileAnalysis.loc` to the count of lines in the decoded source containing at least one non-whitespace character, where lines are separated by `\n`, `\r\n`, or `\r`, and a comment-only line counts as a line.
7. WHEN a file is empty (zero bytes), THE AST_Parser SHALL return a FileAnalysis with `loc` 0, empty `symbols`, empty `parse_errors`, and an `ast_hash` that is a 64-character lowercase hexadecimal string.
8. THE AST_Parser SHALL use 1-indexed lines for every Symbol start and end line and every Parse_Error line.
9. WHEN the same source and path are parsed twice, THE AST_Parser SHALL return FileAnalysis objects that are equal in every field, including the order of `symbols`, `imports`, `exports`, `raw_calls`, and `parse_errors`.
10. THE AST_Parser SHALL expose `compute_normalized_ast_hash` returning the SHA-256 digest of a normalized serialization of the syntax tree, as a 64-character lowercase hexadecimal string.
11. THE normalized serialization SHALL be produced by a pre-order traversal that omits every comment node, omits all whitespace and positional information, and emits for each remaining node its grammar type, and for each leaf node its exact token text, with explicit delimiters for child boundaries such that two different tree shapes cannot produce the same serialization.
12. WHEN two sources differ only in whitespace, blank lines, comments, or indentation that does not change the syntax tree, THE AST_Parser SHALL produce equal Normalized_AST_Hash values.
13. WHEN two sources differ in an operator, an identifier, a literal, or the syntactic structure (including Python indentation that changes block membership), THE AST_Parser SHALL produce different Normalized_AST_Hash values.
14. THE AST_Parser SHALL use no random value, wall-clock time, or process-specific value in the hash input.
15. WHEN a file defines a top-level function, THE AST_Parser SHALL emit a Symbol of kind `function` with Qualname equal to its name.
16. WHEN a function is defined directly inside a class body, THE AST_Parser SHALL emit a Symbol of kind `method` with Qualname `<ClassQualname>.<name>`.
17. WHEN a class is defined, THE AST_Parser SHALL emit a Symbol of kind `class`.
18. WHERE the language is typescript, tsx, or java, THE AST_Parser SHALL emit a Symbol of kind `interface` for each interface declaration.
19. WHERE the language is tsx or javascript, THE AST_Parser SHALL emit a Symbol of kind `component` for a function or class whose name starts with an uppercase letter A-Z and whose body contains at least one JSX element, self-closing JSX element, or JSX fragment.
20. WHEN a function or class is nested inside another function, THE AST_Parser SHALL use a Qualname that includes the enclosing Symbol names, outermost first, separated by dots.
21. IF two Symbols in one file would receive the same Qualname, THEN THE AST_Parser SHALL keep the first Symbol in source order unchanged and append `@<start_line>` to the Qualname of each later Symbol, so that no Symbol_Id repeats within the file.
22. THE AST_Parser SHALL set each Symbol's `start_line` and `end_line` to the first and last lines of its declaration node, including decorators or annotations attached to it.
23. THE AST_Parser SHALL set each Symbol's `signature` to the declaration text up to but excluding the body, with each run of whitespace characters collapsed to one space and leading and trailing whitespace removed, including name, parameters, return type, and modifiers when present in the source.
24. WHEN the source declares no return type or parameter type, THE AST_Parser SHALL omit it from the signature and SHALL NOT infer a type.
25. THE AST_Parser SHALL set each Symbol's `ast_hash` to the Normalized_AST_Hash of that Symbol's declaration node.
26. WHEN a Symbol has Python decorators, Java annotations, or TypeScript or JavaScript decorators, THE AST_Parser SHALL list each as its source text in source order, and SHALL list none otherwise.
27. WHEN a Python function is declared with `async def`, or a TypeScript, JavaScript, or TSX function or method has an `async` modifier in the syntax tree, THE AST_Parser SHALL set `is_async` true, and SHALL set it false otherwise. Java Symbols SHALL have `is_async` false.
28. THE AST_Parser SHALL populate `raw_calls` for each function and method with the callee text of each call expression in its body, in source order of first occurrence, with later duplicates of identical callee text removed, where the callee text is the identifier or the dotted or member-access chain as written.
29. THE AST_Parser SHALL treat nested function bodies as belonging to the nested Symbol and not to the enclosing Symbol for `raw_calls`.
30. THE AST_Parser SHALL record imports as normalized module specifiers: for Python the dotted module path with leading dots preserved for relative imports, for TypeScript, JavaScript, and TSX the string literal source (without quotes) of each import statement and of each re-export `from` clause, and for Java the fully qualified imported name.
31. THE AST_Parser SHALL record exports only where the syntax is explicit: Python `__all__` list entries that are string literals, TypeScript, JavaScript, and TSX `export` declarations, export clauses, and default exports, and Java public top-level type declarations, and SHALL record no export for any other construct.
32. THE AST_Parser SHALL return `imports` and `exports` as lists sorted in ascending code-point order of the strings, with duplicates removed.
33. IF a source contains syntax errors, THEN THE AST_Parser SHALL return a FileAnalysis with at least one `parse_errors` entry, each entry including a 1-indexed line within 1 to the number of lines in the source, and SHALL retain every Symbol whose declaration node contains no Tree-sitter error or missing node.
34. IF a source contains syntax errors, THEN THE AST_Parser SHALL still return line numbers within 1 to the number of lines in the source and an `ast_hash` that is a 64-character lowercase hexadecimal string.
35. IF Tree-sitter fails to load a grammar or raises an unexpected exception, THEN THE AST_Parser SHALL raise a typed internal parser error distinct from Parse_Error, SHALL NOT report it in `parse_errors`, and SHALL return no partial FileAnalysis.
36. IF the source cannot be decoded as UTF-8, THEN THE AST_Parser SHALL replace each undecodable byte sequence with the U+FFFD replacement character, SHALL compute `loc`, Symbols, and hashes from the decoded text, and SHALL produce an identical FileAnalysis on every repeated parse of the same bytes.

### Requirement 4: NetworkX Dependency and Call Graph Engine

**User Story:** As a developer, I want a dependency and call graph with centrality, cycle, and blast-radius queries, so that I can see which code matters most and what a change affects.

#### Acceptance Criteria

1. THE Graph_Engine SHALL build a `networkx.DiGraph` from a list of FileAnalysis objects, with one node per file (attribute `node_type="file"`) identified by Relative_Path and one node per Symbol (attribute `node_type="symbol"`) identified by Symbol_Id.
2. THE Graph_Engine SHALL import no FastAPI, MCP, or frontend module and SHALL NOT execute analyzed code.
3. THE Graph_Engine SHALL give every edge an `edge_type` attribute equal to `imports` or `calls`.
4. THE Graph_Engine SHALL direct every Import_Edge from the importing file to the imported file and every Call_Edge from the caller Symbol to the callee Symbol.
5. WHEN a Python import is relative, THE Graph_Engine SHALL resolve it against the importing file's directory, moving up one directory for each leading dot after the first, and SHALL create an Import_Edge only if the resulting path is a file in the analyzed file set.
6. WHEN a Python absolute import, or a Java fully qualified import, matches the dotted path of a file within the analyzed file set, THE Graph_Engine SHALL resolve it to that file.
7. WHEN a TypeScript, JavaScript, or TSX import specifier begins with `./` or `../`, THE Graph_Engine SHALL resolve it against the importing file's directory, trying the exact path, the Supported_Extensions, and an `index` file in a directory, in that order, and SHALL use the first match.
8. IF an import cannot be resolved to a file in the analyzed file set, THEN THE Graph_Engine SHALL create no edge for it, including imports of external packages, and SHALL continue building the remaining graph without raising an error.
9. THE Graph_Engine SHALL create no self-import edge from a file to itself.
10. WHEN a Raw_Call matches exactly one Symbol defined in the same file by simple name or Qualname, THE Graph_Engine SHALL create a Call_Edge to it.
11. WHEN a Raw_Call uses a name that the caller's file imports from a resolved file, and that file defines exactly one Symbol with that name, THE Graph_Engine SHALL create a Call_Edge to it.
12. WHEN a Raw_Call of the form `self.<name>` or `this.<name>` occurs in a method, THE Graph_Engine SHALL resolve it only to a method named `<name>` in the same class, and SHALL create no Call_Edge if the class has no such method.
13. IF a Raw_Call matches zero Symbols or more than one candidate Symbol, THEN THE Graph_Engine SHALL create no Call_Edge for it.
14. WHEN a caller invokes itself directly, THE Graph_Engine SHALL create a self-loop Call_Edge.
15. THE Graph_Engine SHALL produce an identical graph (same nodes, edges, attributes, and insertion order) for any permutation of the input FileAnalysis list.
16. THE Graph_Engine SHALL expose `compute_vital_organs(graph, top_k=10)` returning an ordered list of node ids, highest score first.
17. WHEN `compute_vital_organs` ranks nodes, THE Graph_Engine SHALL compute each score as 0.5 × normalized PageRank + 0.25 × normalized in-degree + 0.25 × normalized out-degree, where each component is min-max normalized to the range 0.0 to 1.0, and a component whose values are all equal normalizes to 0.0 for every node.
18. WHEN two nodes have equal scores, THE Graph_Engine SHALL order them by node id ascending.
19. THE Graph_Engine SHALL return at most `top_k` ids from `compute_vital_organs`, and SHALL return an empty list for an empty graph or `top_k` of 0.
20. IF `top_k` is negative, THEN THE Graph_Engine SHALL raise a typed invalid-argument error and SHALL leave the graph unmodified.
21. THE Graph_Engine SHALL expose `detect_cycles(graph)` returning a list of cycles, each a list of node ids.
22. WHEN `detect_cycles` runs, THE Graph_Engine SHALL report each strongly connected component with more than one node, or with a self-loop, as one cycle containing its sorted node ids, and SHALL sort the result list lexicographically by node-id list.
23. WHEN `detect_cycles` runs on any finite digraph, including dense graphs, disconnected graphs, and graphs with self-loops, THE Graph_Engine SHALL terminate and return its result within 5 seconds for a graph of up to 10,000 nodes and 50,000 edges.
24. WHEN `detect_cycles` runs on an acyclic graph or an empty graph, THE Graph_Engine SHALL return an empty list.
25. THE Graph_Engine SHALL return identical `detect_cycles` output for graphs with the same nodes and edges regardless of insertion order.
26. THE Graph_Engine SHALL expose `trace_blast_radius(graph, target_id, max_depth=3)` returning a BlastRadius.
27. WHEN `trace_blast_radius` runs, THE Graph_Engine SHALL compute `upstream_callers` by reverse breadth-first traversal and `downstream_callees` by forward breadth-first traversal, each limited to `max_depth` edges and following `calls` edges only.
28. THE Graph_Engine SHALL exclude the target from both lists, contain no duplicates, and sort each list by node id ascending.
29. WHILE a cycle includes the target or any traversed node, THE Graph_Engine SHALL visit each node at most once and terminate.
30. WHEN `max_depth` is 0, THE Graph_Engine SHALL return empty `upstream_callers` and `downstream_callees` and an `impact_score` of 0.0.
31. IF `max_depth` is negative, THEN THE Graph_Engine SHALL raise a typed invalid-argument error and SHALL NOT return a BlastRadius.
32. IF `target_id` is not a node in the graph, THEN THE Graph_Engine SHALL raise a typed missing-target error and SHALL NOT return a BlastRadius.
33. THE Graph_Engine SHALL compute `impact_score` as a deterministic function of only the graph structure: the count of upstream callers within the depth bound, the count of downstream callees within the depth bound, and the total count of Symbol nodes, with the formula documented in the design, bounded to 0.0 through 1.0 inclusive, equal to 0.0 when the graph has no Symbol nodes, and non-decreasing as `upstream_callers` grows with other inputs held fixed.
34. WHEN the same graph is queried twice with the same arguments, THE Graph_Engine SHALL return equal BlastRadius objects.
35. IF the input to graph construction contains two FileAnalysis objects with the same `file_path`, THEN THE Graph_Engine SHALL raise a typed invalid-input error and SHALL NOT return a graph.
36. WHEN assembling a `RepoGraphSnapshot` from FileAnalysis objects and DSA_Signal values, THE Graph_Engine SHALL populate `files`, `edges`, `vital_organs`, `cycles`, and `dsa_signals`, with `files` sorted by Relative_Path ascending, `edges` sorted by source id, then target id, then `edge_type` ascending, `vital_organs` in the order from criteria 16 to 18, `cycles` in the order from criterion 22, and `dsa_signals` sorted by file path ascending with ties ordered by their remaining fields ascending.
37. WHEN graph construction receives an empty list of FileAnalysis objects, THE Graph_Engine SHALL return a `networkx.DiGraph` with 0 nodes and 0 edges.

### Requirement 5: DSA-in-the-Wild Structural Scanner

**User Story:** As a developer, I want data structure and algorithm patterns identified from actual code structure with evidence, so that explanations are grounded and never forced onto code that has no meaningful pattern.

#### Acceptance Criteria

1. THE DSA_Scanner SHALL inspect Tree-sitter syntax trees of functions and methods and SHALL NOT rely on regular-expression matching alone to detect any pattern.
2. THE DSA_Scanner SHALL import no FastAPI, MCP, frontend, or LLM module, and SHALL use no random value.
3. THE DSA_Scanner SHALL emit each DSA_Signal for exactly one function or method, with `symbol_id`, `file_path`, `start_line`, `end_line`, `chapter`, `pattern_name`, `confidence`, and Evidence containing 1 to 10 items, each a non-empty string of at most 200 characters.
4. THE DSA_Scanner SHALL restrict `chapter` to exactly these strings: `Hash Tables`, `Graphs & Trees`, `Recursion & Dynamic Programming`, `Sliding Window / Two Pointers`, `Heaps & Priority Queues`, `Sorting & Binary Search`.
5. THE DSA_Scanner SHALL assign `confidence` as a number from 0.00 to 1.00 inclusive, with two decimal places, taken from a fixed rule table keyed by pattern and by the count of independent evidence items, so that equal inputs always yield equal confidence and a higher evidence count never yields a lower confidence for the same pattern.
6. WHEN a function builds a dictionary, map, or set and tests membership in it or reads from it inside a loop, or accumulates frequency counts in it, or uses it to remove duplicates, THE DSA_Scanner SHALL emit a `Hash Tables` signal.
7. IF a function only declares or returns a dict, map, or set literal without membership, lookup, counting, or de-duplication use, THEN THE DSA_Scanner SHALL emit no Hash Tables signal.
8. WHEN a function traverses an adjacency structure using a queue or stack with a visited collection, or uses `deque` with `popleft`, or `pop(0)` on a work list, or recursively visits children or neighbors of a node, THE DSA_Scanner SHALL emit a `Graphs & Trees` signal.
9. IF a function contains only nested loops over plain sequences without adjacency, queue or stack, visited, or recursive node-visit structure, THEN THE DSA_Scanner SHALL emit no Graphs & Trees signal.
10. WHEN a function contains a call to itself by its own name, THE DSA_Scanner SHALL emit a `Recursion & Dynamic Programming` signal with pattern name identifying direct recursion.
11. WHEN a function is decorated with `lru_cache` or `cache`, or looks up a memo collection before a recursive call and stores the result after it, THE DSA_Scanner SHALL emit a `Recursion & Dynamic Programming` signal with a pattern name identifying memoization, distinct from the direct-recursion pattern name.
12. IF a function calls another function with a different name more than once and contains no call to itself, THEN THE DSA_Scanner SHALL emit no Recursion & Dynamic Programming signal.
13. WHEN a function calls `heapq` push or pop operations, or uses a `PriorityQueue` or `PriorityQueue`-equivalent put and get operations, THE DSA_Scanner SHALL emit a `Heaps & Priority Queues` signal.
14. IF a module imports `heapq` or `queue` and the function does not call a heap or priority-queue operation, THEN THE DSA_Scanner SHALL emit no Heaps & Priority Queues signal for that function.
15. WHEN a function calls `bisect` functions, or contains a loop that computes a midpoint of two index variables with `// 2` or an equivalent integer division or shift and narrows one boundary variable based on a comparison, or defines a custom sort comparator or key function passed to a sort call, THE DSA_Scanner SHALL emit a `Sorting & Binary Search` signal.
16. IF a function computes a midpoint but contains no comparison that adjusts a boundary variable inside a loop, THEN THE DSA_Scanner SHALL emit no binary-search signal for that function.
17. WHEN a function contains a loop in which two index variables are initialized to opposite ends or to a shared start, and at least one of them is moved by an increment or decrement conditionally in the loop body, and both are used to index the same sequence, THE DSA_Scanner SHALL emit a `Sliding Window / Two Pointers` signal.
18. IF a function contains a loop with two variables that are not both used as indices and not both updated by the loop body, THEN THE DSA_Scanner SHALL emit no Sliding Window / Two Pointers signal.
19. WHEN a function contains CRUD operations, configuration loading, API routing, simple transforms, boilerplate, ordinary loops, or basic business logic without the structures in criteria 6 to 17, THE DSA_Scanner SHALL return zero signals for that function.
20. IF a function does not contain at least one of the constructs listed in the trigger of the criterion for a pattern (criteria 6, 8, 10, 11, 13, 15, 17), THEN THE DSA_Scanner SHALL return no signal for that pattern for that function.
21. THE DSA_Scanner SHALL build each Evidence item only from observed syntax nodes, and each item SHALL contain the construct name and the 1-based line number or line range of that construct, within the `start_line` to `end_line` range of the signal's function.
22. THE DSA_Scanner SHALL return signals sorted by `file_path`, `start_line`, `chapter`, then `pattern_name`, in ascending order, with no duplicate signal for the same symbol, chapter, and pattern.
23. WHERE the language is python, THE DSA_Scanner SHALL apply every rule in criteria 6 to 18, and WHERE the language is typescript, javascript, tsx, or java, THE DSA_Scanner SHALL apply the rules whose constructs exist in that grammar, and SHALL emit no signal based on a construct absent from that grammar.
24. IF a file has Parse_Error entries, THEN THE DSA_Scanner SHALL scan only Symbols whose declaration contains no error node, and SHALL still scan those Symbols and return their signals without raising an exception.
25. IF the language of a file is not python, typescript, javascript, tsx, or java, THEN THE DSA_Scanner SHALL return zero signals for that file and SHALL report the file as skipped with an indication that the language is unsupported.
26. IF a file contains no function or method Symbols, THEN THE DSA_Scanner SHALL return zero signals for that file without raising an exception.

### Requirement 6: Test Suite and Verification

**User Story:** As a maintainer, I want exhaustive deterministic unit tests and Hypothesis property tests, so that every behavior above is verified offline and false positives are caught.

#### Acceptance Criteria

1. WHILE the Test_Suite is running, THE Test_Suite SHALL make 0 network connections, require no API key, read no real `.env` file, make 0 live LLM calls, and use `LLM_PROVIDER` value `mock` wherever settings are consulted.
2. WHILE a clone-related test is running, THE Test_Suite SHALL replace the git subprocess with a test double and SHALL make 0 requests to GitHub.
3. THE Test_Suite SHALL place unit tests in `backend/tests/unit/test_ast_graph_engine.py` and property tests in `backend/tests/properties/test_ast_graph_properties.py`.
4. THE Test_Suite SHALL include at least one unit test for each of these Domain_Models behaviors: enum values, valid construction, required fields, wrong types, line validity, impact-score bounds, confidence bounds, enum serialization, round-trip, empty collections, and partial analysis.
5. THE Test_Suite SHALL include at least one unit test, using temporary directories, for each of these ingestion behaviors: URL validation accept cases, URL validation reject cases, destination containment, clone command arguments, clone failure handling, clone timeout handling, skipped directories, binary file skipping, oversize file skipping, file-count truncation, total-size truncation, symlink escape, sorted relative output, and invalid local paths.
6. THE Test_Suite SHALL include for each of Python, TypeScript, JavaScript, TSX, and Java at least one AST_Parser unit test that asserts language, symbols, qualnames, signatures, line ranges, imports, exports, Raw_Call values, decorators and annotations, async status, LOC, AST hash, and syntax-error recovery, where a behavior does not apply to a language the test asserts its absence.
7. THE Test_Suite SHALL include unit tests asserting that identical source gives equal AST hashes, that formatting-only changes and comment-only changes give equal AST hashes, and that an operator change, an identifier change, and a structural change each give a different AST hash.
8. THE Test_Suite SHALL include at least one unit test for each of these Graph_Engine behaviors: Import_Edge creation, Call_Edge creation, edge direction, local import resolution, call resolution, ambiguous call handling, unresolved call handling, vital organs ranking, tie-breaking, empty graphs, cycles, self-loops, blast-radius accuracy, depth limits, and missing targets.
9. THE Test_Suite SHALL include for each of the six DSA_Chapter values at least one positive fixture that produces a signal and at least one negative look-alike fixture that produces no signal, plus at least one negative fixture each for CRUD, routing, config, plain loops, and simple transforms.
10. IF any negative DSA fixture produces a signal, THEN THE Test_Suite SHALL report a test failure identifying the fixture and the signal.
11. THE Test_Suite SHALL include a Hypothesis property test of AST hash idempotency, in which generated valid Python function snippets receive whitespace, blank-line, formatting, and `#` comment changes, the transformed source differs textually from the original in at least one generated case, and the AST hash stays equal in every case.
12. THE Test_Suite SHALL include a Hypothesis property test of AST hash sensitivity, in which an operator or identifier in a generated valid Python snippet is changed to a different valid operator or identifier, the changed source parses with 0 syntax errors, and the AST hash differs in every case.
13. THE Test_Suite SHALL include a Hypothesis property test of graph integrity and cycle termination over generated digraphs including empty, disconnected, dense, self-loop, and multi-cycle graphs, asserting that `detect_cycles` terminates, returns the same result under node and edge reordering, returns cycles whose members are all nodes of the graph, and that every edge references existing nodes.
14. THE Test_Suite SHALL include a Hypothesis property test of blast-radius monotonicity, in which a new edge is added from a node outside the existing upstream set to a node inside the upstream set or to the target, and `upstream_callers` after the mutation is a superset of `upstream_callers` before, where the generator produces a target with at least one upstream path in at least 30 percent of generated cases.
15. THE Test_Suite SHALL configure every Hypothesis test with `derandomize=True` or a recorded fixed seed, and SHALL set no `deadline` override and no `suppress_health_check` entry that exists only to make a test pass.
16. WHEN `pytest` is run from the repository root, THE Test_Suite SHALL pass with 0 failures and 0 errors, including the existing health test.
17. WHEN `ruff check` is run on `backend`, THE Spec #01 files SHALL produce 0 violations.
18. THE Spec #01 implementation SHALL contain no code from Specs #2 to #4 and SHALL add 0 modules to `api`, `mcp_server`, `power`, `crew`, or `ui`.
