# Requirements Document

## Introduction

Spec #02 extends the completed Phase 1 foundation (Spec #01: domain models, ingestion, AST parser, graph engine, DSA scanner) with repository provenance, architecture topology, structured LLM access, caching, and a three-tier code pedagogy engine. It adds seven areas: extended domain models, a Kiro Spec and Git provenance grounder, a deterministic folder topology profiler, a provider-agnostic structured LLM router, an AST-hashed SQLite cache store, a pedagogy and counterfactual engine, and the unit and Hypothesis property tests that verify them.

Everything derivable from source, graph, specs, or Git metadata is computed deterministically. The LLM only phrases explanations from a minimal, grounded context slice. All LLM output is validated against Pydantic schemas before use or persistence. Analyzed repositories are untrusted: no analyzed code is executed or imported.

Layering follows `.kiro/steering/architecture.md`: `domain` depends on nothing in this project, `engines` use `domain`, and neither imports FastAPI, MCP, or frontend code.

LLM failure handling differs by tier. L2 degrades gracefully: when the LLM_Router fails, the Pedagogy_Engine returns a deterministic `L2FlowExplanation` that is not cached (Requirement 14 criterion 10). L1 and L3 have no deterministic fallback, so on LLM_Router failure the Pedagogy_Engine raises a `PedagogyError` (Requirement 13 criterion 7, Requirement 12 criterion 14).

### Phase 1 Preservation

All Phase 1 models, ingestion, AST parser, graph engine, DSA scanner, and their interfaces are preserved. `backend/domain/models.py` is extended by appending only. Any Phase 1 engine change must be minimal, backward-compatible, and justified in the design. No existing test is weakened, deleted, skipped, or marked xfail.

### Out of Scope

Spec #3, Active Mastery, FSRS, Study Mode watchers, MCP expansion, Kiro Power, Crew App, frontend and UI, hooks, API expansion, and deployment.

### Observations (reported, not silently resolved)

1. **Baseline test count.** A baseline run before this spec shows 745 passing tests, matching the stated count.
2. **No existing settings module.** The repository has no pydantic-settings class; `.env.example` defines `LLM_PROVIDER=mock`, `GEMINI_MODEL=gemini-2.5-flash`, `OLLAMA_BASE_URL=http://localhost:11434/v1`, `OLLAMA_MODEL=qwen3.5`, and `STUPID_CODE_DB_PATH=./data/stupid_code.db`. The design will introduce one small pydantic-settings class inside `llm_router.py` and `cache_store.py` consumers (kept out of `domain`) that honors these defaults. Please confirm placement.
3. **Pytest configuration precedence.** The root `pytest.ini` takes precedence over `backend/pyproject.toml`, so `asyncio_mode = auto` from pyproject does not apply at the repository root. Requirement 17 adds it to the root file.
4. **Git history and the offline rule.** `testing-rules.md` forbids external services. Git history tests run only against a temporary repository created in the test and never against an external repository.
5. **Pytest line-count targets.** The unit test file limit (under 600 lines) and test counts (about 20 to 25 unit tests, exactly four properties) are treated as hard constraints of Requirement 17.

## Glossary

- **Domain_Models**: The Pydantic v2 module `backend/domain/models.py`.
- **Spec_Grounder**: The module `backend/engines/spec_grounder.py`.
- **Topology_Profiler**: The module `backend/engines/topology.py`.
- **LLM_Router**: The module `backend/engines/llm_router.py`.
- **Cache_Store**: The module `backend/engines/cache_store.py`.
- **Pedagogy_Engine**: The module `backend/engines/pedagogy.py`.
- **Test_Suite**: The tests in `backend/tests/unit/test_spec_topology_pedagogy.py`, `backend/tests/properties/test_pedagogy_properties.py`, and all existing tests.
- **Pytest_Config**: The root `pytest.ini` file.
- **Repo_Root**: The resolved absolute directory of the analyzed repository, taken from `RepoGraphSnapshot.root_path`.
- **Relative_Path**: A POSIX-style path relative to Repo_Root as defined in Spec #01.
- **Snapshot**: A `RepoGraphSnapshot` from Spec #01.
- **Kiro_Spec_Document**: A file named `requirements.md`, `design.md`, or `tasks.md` in `.kiro/specs/<spec_name>/` of Repo_Root.
- **Steering_Document**: A Markdown file in `.kiro/steering/` of Repo_Root.
- **Spec_Section**: A Markdown heading and the text beneath it, up to the next heading of the same or higher level, within a Kiro_Spec_Document or Steering_Document.
- **Spec_Link**: A `SpecLink` associating a file path or symbol with a Spec_Section.
- **Defensible_Evidence**: A literal, checkable match between repository content and a Spec_Section, limited to: an exact Relative_Path mentioned in the section, an exact symbol qualname or name mentioned in a code span, or an exact module or component name mentioned in the section heading.
- **Core_Implementation_File**: A Snapshot file whose path is not under a directory segment named `tests`, `test`, `__tests__`, `docs`, or `examples`, is not named `__init__.py`, and whose analysis has at least one symbol.
- **Referenced_Task_Path**: A Relative_Path appearing inside inline code spans or list items of a `tasks.md` file that has a Supported_Extension or a known directory prefix, and that is not located inside a fenced code block.
- **Commit_Record**: A string `"<short_hash>|<subject>"` produced from Git history.
- **Directory_Role**: One of `domain`, `engines`, `api`, `ui`, `tests`, `config`, `infrastructure`, `services`, `entry_points`, `other`. The value `other` is the default role for a directory whose name and observed contents match no other role.
- **Grounder_Result**: The internal result object returned by the Spec_Grounder's discovery and parsing step. It is not part of `ProvenanceReport`. It carries the parsed Spec_Sections and the records of skipped files, each holding a relative path and a reason (unreadable, invalid encoding, or oversize).
- **Import_Edge**: A `GraphEdge` with `edge_type == "imports"`.
- **Cross_Folder_Import**: An Import_Edge whose source and target files have different parent directories and whose source and target are different files.
- **Topology_Pattern**: One of `Hexagonal / Clean Architecture`, `Layered MVC`, `Feature-Sliced`, `Modular Monolith`, `Flat / Script`.
- **Provider**: One of `mock`, `gemini`, `ollama`.
- **Response_Model**: A Pydantic model class passed to `generate_structured` as the required output schema.
- **Mock_Provider**: The deterministic, network-free Provider.
- **Lens**: A `PedagogyLens` value: `L1_SYNTAX`, `L2_FLOW`, or `L3_ARCHITECTURE`.
- **Target**: A symbol id (`<Relative_Path>::<Qualname>`) for L1 and L2, or a repository or directory identifier for L3.
- **Target_AST_Hash**: The `ast_hash` of the Target symbol, or for an L3 Target, the deterministic digest of the Topology_Profile and the sorted file `ast_hash` values of the files in scope.
- **Cache_Key**: The tuple `(repo_id, ast_hash, target_id, lens)`.
- **Context_Slice**: The minimal 1-hop grounded input given to the LLM_Router for one explanation, as defined in Requirement 12 criterion 4.
- **Explanation_Envelope**: An `ExplanationEnvelope` for exactly one Lens.

## Requirements

### Requirement 1: Extended Domain Models

**User Story:** As a developer, I want strict, serializable schemas for provenance, topology, and pedagogy, so that every new engine shares one validated data contract.

#### Acceptance Criteria

1. THE Domain_Models SHALL append the models `PedagogyLens`, `SpecLink`, `SpecDriftItem`, `ProvenanceReport`, `TopologyProfile`, `SyntaxAnnotation`, `L1SyntaxExplanation`, `FlowStep`, `DSACard`, `L2FlowExplanation`, `AlternativeArchitecture`, `L3ArchitectureExplanation`, and `ExplanationEnvelope` to `backend/domain/models.py` and add each of the 13 names to `__all__`.
2. THE Domain_Models SHALL define `PedagogyLens` as a string enum with exactly the values `L1_SYNTAX`, `L2_FLOW`, and `L3_ARCHITECTURE`.
3. THE Domain_Models SHALL define the `SpecLink.source_file` field as an enum of exactly `requirements.md`, `design.md`, and `tasks.md`, and the `SpecDriftItem.drift_type` field as an enum of exactly `UNSPECIFIED_CODE` and `UNIMPLEMENTED_SPEC`.
4. THE Domain_Models SHALL define the `TopologyProfile.detected_pattern` field as an enum of exactly the five Topology_Pattern values defined in the Glossary.
5. THE Domain_Models SHALL define the fields of each new model as listed in the Domain_Models field table of design.md, plus the single additive field `L2FlowExplanation.llm_content_available` (boolean, default true) required by Requirement 14 criterion 10, using frozen, extra-forbidding, strict Pydantic v2 configuration consistent with the Phase 1 models.
6. IF a model is constructed with a field not defined on that model, THEN THE Domain_Models SHALL reject the model with a validation error and create no model instance.
7. IF a field value of a new model is assigned after construction, THEN THE Domain_Models SHALL raise an error and leave the field value unchanged.
8. IF a `confidence` value, or a ratio or score in `boundary_metrics`, is below 0.0, is above 1.0, is NaN, or is infinite, THEN THE Domain_Models SHALL reject the model with a validation error identifying the offending field. Values of exactly 0.0 and 1.0 SHALL be accepted.
9. IF a `SyntaxAnnotation` has a `line_start` or `line_end` below 1, or a `line_end` below its `line_start`, or a `DSACard` has a `start_line` or `end_line` below 1, or an `end_line` below its `start_line`, or a `FlowStep` has a `step_number` below 1, THEN THE Domain_Models SHALL reject the model with a validation error identifying the offending field. A `line_end` equal to `line_start`, and an `end_line` equal to `start_line`, SHALL be accepted.
10. THE Domain_Models SHALL define `L3ArchitectureExplanation.spec_rationale` and the `l1`, `l2`, and `l3` fields of `ExplanationEnvelope` as nullable, with a default of `None`.
11. IF an `ExplanationEnvelope` has any tier populated other than the tier matching its `lens`, or has `None` in the tier matching its `lens`, THEN THE Domain_Models SHALL reject the model with a validation error. The mapping SHALL be `L1_SYNTAX` to `l1`, `L2_FLOW` to `l2`, and `L3_ARCHITECTURE` to `l3`.
12. THE Domain_Models SHALL import only the Python standard library and Pydantic.
13. FOR ALL valid new models, serializing with `model_dump_json` and parsing with `model_validate_json` SHALL produce a model equal to the original (round-trip property).
14. THE Domain_Models SHALL leave every Phase 1 model definition unchanged, so that the existing Phase 1 unit and property tests pass without modification.

### Requirement 2: Spec Discovery and Parsing

**User Story:** As a developer, I want Kiro specs and steering files read safely and deterministically, so that explanations can cite real project intent.

#### Acceptance Criteria

1. WHEN Repo_Root contains `.kiro/specs/<spec_name>/` directories, THE Spec_Grounder SHALL discover each Kiro_Spec_Document present in each directory and parse it into Spec_Sections.
2. WHEN Repo_Root contains `.kiro/steering/*.md` files, THE Spec_Grounder SHALL discover each Steering_Document directly in `.kiro/steering/` (not in subdirectories) and parse it into Spec_Sections.
3. IF a spec directory lacks one or more of the three Kiro_Spec_Documents, THEN THE Spec_Grounder SHALL process the documents that exist, omit the missing ones, and return no error for the missing documents.
4. IF Repo_Root has no `.kiro` directory, no `.kiro/specs` directory, or no `.kiro/steering` directory, THEN THE Spec_Grounder SHALL return a result with zero entries for each absent source and without raising an error.
5. THE Spec_Grounder SHALL report `has_kiro_specs` as true if and only if at least one Kiro_Spec_Document was found and parsed, and as false otherwise.
6. THE Spec_Grounder SHALL open files in read-only mode, SHALL create, modify, or delete zero files under Repo_Root, and SHALL process spec directory names and documents in ascending lexicographic order, so that two runs on identical input return identical output.
7. IF a spec or steering file cannot be read or cannot be decoded as UTF-8, THEN THE Spec_Grounder SHALL skip that file, continue with the remaining files, and record the skipped file's relative path and a reason (unreadable or invalid encoding) in the Grounder_Result.
8. IF a spec or steering file is larger than 512 KB (524,288 bytes), THEN THE Spec_Grounder SHALL skip that file, continue with the remaining files, and record the skipped file's relative path and the reason (oversize) in the Grounder_Result. A file of exactly 524,288 bytes SHALL be processed.

### Requirement 3: Spec-to-Code Linking

**User Story:** As a developer, I want each file linked to the spec sections that describe it, so that I can see why the code exists.

#### Acceptance Criteria

1. WHEN a Snapshot file has Defensible_Evidence in a Spec_Section, THE Spec_Grounder SHALL create a Spec_Link containing the spec name, the exact source document, the section title, an excerpt taken verbatim from the section, and a confidence value that is a number from 0.0 to 1.0 inclusive.
2. THE Spec_Grounder SHALL key `ProvenanceReport.spec_links` by Relative_Path of Snapshot files, SHALL include a path only when it has at least one Spec_Link, and SHALL list no path that is absent from the Snapshot.
3. IF a Snapshot file has no Defensible_Evidence in a Spec_Section, THEN THE Spec_Grounder SHALL create no Spec_Link for that file and Spec_Section pair.
4. THE Spec_Grounder SHALL assign a confidence value strictly higher to an exact Relative_Path match than to a symbol name match, and strictly higher to a symbol name match than to a module or component name match in a heading.
5. THE Spec_Grounder SHALL limit each excerpt to at most 300 characters, taken as a contiguous substring of the section text; WHERE the section text is 300 characters or fewer, THE Spec_Grounder SHALL use the whole section text as the excerpt.
6. THE Spec_Grounder SHALL order the Spec_Links of each path by descending confidence, then by ascending spec name, then ascending source document, then ascending section title, using code point string comparison for the ascending keys.
7. IF a Spec_Link would originate from a Steering_Document, THEN THE Spec_Grounder SHALL omit that Spec_Link, because `SpecLink.source_file` does not admit steering documents.
8. WHEN a Spec_Link originates from a Kiro_Spec_Document, THE Spec_Grounder SHALL set `SpecLink.source_file` to the name of that Kiro_Spec_Document.

### Requirement 4: Spec Drift Detection

**User Story:** As a developer, I want conservative drift reports, so that I can find real mismatches between specs and code without noise.

#### Acceptance Criteria

1. WHEN a Core_Implementation_File has no Spec_Link and its Repo_Root-relative path (using `/` separators, compared case-sensitively) is not mentioned in any Kiro_Spec_Document, THE Spec_Grounder SHALL emit a `SpecDriftItem` with `drift_type` `UNSPECIFIED_CODE`, the Repo_Root-relative file path as `target`, and non-empty details.
2. WHEN a Referenced_Task_Path in a `tasks.md` does not exist in Repo_Root on disk, THE Spec_Grounder SHALL emit a `SpecDriftItem` with `drift_type` `UNIMPLEMENTED_SPEC`, the path as `target`, and details containing the name of the spec that contains the `tasks.md`.
3. THE Spec_Grounder SHALL ignore each of the following when collecting referenced paths: paths inside fenced code blocks; paths containing any placeholder marker (`<`, `>`, `{`, `}`, `*`, `...`, or `example`, with `example` matched case-insensitively); absolute paths; paths with a `..` segment; URLs; and bare names without a directory separator.
4. IF a referenced path matches more than one real file in Repo_Root by path suffix, THEN THE Spec_Grounder SHALL treat the reference as ambiguous and SHALL emit no `SpecDriftItem` for it.
5. WHILE `has_kiro_specs` is false, THE Spec_Grounder SHALL emit zero `SpecDriftItem` entries.
6. THE Spec_Grounder SHALL emit each `SpecDriftItem` at most once per `(drift_type, target)` pair, and SHALL order the emitted items ascending by `drift_type` and then ascending by `target`, using the same ordering on every run with identical input.
7. WHEN every Core_Implementation_File has a Spec_Link or is mentioned in a Kiro_Spec_Document, THE Spec_Grounder SHALL emit zero `UNSPECIFIED_CODE` items.
8. IF a Kiro_Spec_Document cannot be read or decoded, THEN THE Spec_Grounder SHALL skip that document, SHALL continue processing the remaining documents, and SHALL emit no `SpecDriftItem` derived from the skipped document.
9. IF Repo_Root contains zero Core_Implementation_Files, THEN THE Spec_Grounder SHALL emit zero `UNSPECIFIED_CODE` items and SHALL NOT raise an error.

### Requirement 5: Git History Association

**User Story:** As a developer, I want recent commit context per file, so that explanations can reference real change history.

#### Acceptance Criteria

1. WHEN Repo_Root contains a `.git` directory and Git is available, THE Spec_Grounder SHALL run `git log -n 20 --pretty=format:%h|%s --name-only` exactly once against Repo_Root using a subprocess argument list without a shell.
2. WHEN the Git command completes with exit status 0, THE Spec_Grounder SHALL associate each Commit_Record with every listed file path that is a Snapshot file and SHALL store the result in `ProvenanceReport.recent_commits` keyed by Relative_Path.
3. THE Spec_Grounder SHALL keep at most 20 commits in total and at most 20 Commit_Records per file, ordered from newest to oldest.
4. IF a listed file path is not a Snapshot file, THEN THE Spec_Grounder SHALL omit that path from `ProvenanceReport.recent_commits`.
5. WHEN the Git command exits with status 0 and outputs no commits, THE Spec_Grounder SHALL return an empty `recent_commits` without raising.
6. THE Spec_Grounder SHALL terminate the Git command if it runs longer than 10 seconds or produces more than 1,048,576 bytes of output.
7. IF Repo_Root has no `.git` directory, Git is not installed, the command times out, the output exceeds 1,048,576 bytes, or the command exits with a non-zero status, THEN THE Spec_Grounder SHALL return an empty `recent_commits` and continue without raising.
8. THE Spec_Grounder SHALL run only read-only Git commands, SHALL pass a minimal environment without secrets, and SHALL NOT store or log raw Git output beyond Commit_Records for Snapshot files.
9. THE Spec_Grounder SHALL NOT contact any remote repository.

### Requirement 6: Provenance Report Output

**User Story:** As a developer, I want one validated provenance report, so that downstream engines consume a single contract.

#### Acceptance Criteria

1. WHEN a Snapshot is analyzed, THE Spec_Grounder SHALL return a `ProvenanceReport` that passes `ProvenanceReport` model validation and contains exactly the fields `repo_id`, `has_kiro_specs`, `spec_links`, `drift_items`, and `recent_commits`.
2. WHEN a Snapshot is analyzed, THE Spec_Grounder SHALL set `repo_id` to the `repo_id` of the analyzed Snapshot and SHALL set `has_kiro_specs` to true if and only if at least one Kiro_Spec_Document was found and parsed (as defined in Requirement 2 criterion 5), otherwise false.
3. WHEN a Snapshot is analyzed, THE Spec_Grounder SHALL return `spec_links`, `drift_items`, and `recent_commits` as empty collections when there are no entries, and never null.
4. WHEN the same Repo_Root contents and the same Snapshot are analyzed two or more times, THE Spec_Grounder SHALL return `ProvenanceReport` values that are equal in every field, including the order of entries in `spec_links`, `drift_items`, and `recent_commits`.
5. IF the Snapshot has zero files, THEN THE Spec_Grounder SHALL return a valid `ProvenanceReport` with the Snapshot's `repo_id`, empty `spec_links`, empty `drift_items`, and empty `recent_commits`, and SHALL raise no error.
6. IF the report cannot be built because the Snapshot is invalid or the Repo_Root is unreadable, THEN THE Spec_Grounder SHALL raise an error that identifies the cause and SHALL return no partial `ProvenanceReport`.
7. THE Spec_Grounder SHALL make zero LLM calls while producing a `ProvenanceReport`.

### Requirement 7: Topology Classification

**User Story:** As a developer, I want the repository's architecture style classified from structure, so that I can understand how it is organized.

#### Acceptance Criteria

1. WHEN a Snapshot is analyzed, THE Topology_Profiler SHALL return a valid `TopologyProfile` computed using only the Snapshot paths, directory hierarchy, per-file symbol counts, and Import_Edges.
2. THE Topology_Profiler SHALL perform zero LLM calls, zero network calls, and zero file reads outside the Snapshot data.
3. WHEN a Snapshot with at least one file is analyzed, THE Topology_Profiler SHALL assign each Topology_Pattern a score between 0.0 and 1.0 inclusive, using at least two independent signals from directory naming, import direction between directories, and file distribution, and SHALL classify the repository as exactly one Topology_Pattern, the one with the highest score.
4. WHERE only a single signal supports a Topology_Pattern, THE Topology_Profiler SHALL cap that pattern's confidence at 0.5.
5. WHEN the top two Topology_Pattern scores differ by less than 0.1, THE Topology_Profiler SHALL cap the reported confidence at 0.6.
6. IF no Topology_Pattern has a score of at least 0.3, THEN THE Topology_Profiler SHALL classify the repository as `Flat / Script`.
7. THE Topology_Profiler SHALL report `confidence` as a number between 0.0 and 1.0 inclusive, and a Snapshot with a higher pattern score and the same number of supporting signals SHALL NOT receive a lower confidence.
8. FOR ALL equal Snapshots, THE Topology_Profiler SHALL return equal `TopologyProfile` values, independent of the order of files and edges.
9. IF the Snapshot has zero files, THEN THE Topology_Profiler SHALL return `Flat / Script` with confidence 0.0 and empty `directory_roles` and `evidence`, and SHALL NOT raise an error.
10. IF the Snapshot is malformed (for example, an Import_Edge references a path not present in the Snapshot files), THEN THE Topology_Profiler SHALL ignore the invalid edge, SHALL still return a valid `TopologyProfile`, and SHALL NOT raise an error.
11. IF two or more Topology_Patterns tie for the highest score, THEN THE Topology_Profiler SHALL select the tied pattern whose name sorts first alphabetically, so that the result is deterministic.

### Requirement 8: Directory Roles, Boundary Metrics, and Evidence

**User Story:** As a developer, I want measurable boundaries and cited evidence, so that topology claims are checkable.

#### Acceptance Criteria

1. THE Topology_Profiler SHALL assign `directory_roles` only to directories present in the Snapshot, mapping each directory path to exactly one Directory_Role value, based on directory name and on observed contents.
2. THE Topology_Profiler SHALL report `boundary_metrics` with exactly the keys `max_depth`, `cross_folder_import_ratio`, `domain_isolation_score`, and `entry_point_count`.
3. THE Topology_Profiler SHALL compute `max_depth` as the largest number of directory segments in any Snapshot file path, excluding the file name segment, and `entry_point_count` as the number of files classified as entry points, both reported as floats, and as 0.0 WHEN the Snapshot contains no files.
4. THE Topology_Profiler SHALL compute `cross_folder_import_ratio` as the number of Cross_Folder_Imports divided by the number of Import_Edges whose source and target are different files, and as 0.0 WHEN that denominator is zero.
5. THE Topology_Profiler SHALL compute `domain_isolation_score` as 1.0 minus the fraction of Import_Edges leaving files under a directory with role `domain` whose target is outside that directory, and as 1.0 WHEN no domain directory or no such edges exist.
6. THE Topology_Profiler SHALL ignore self-edges and edges whose source or target is not a Snapshot file when computing metrics.
7. FOR ALL Snapshots, THE Topology_Profiler SHALL return `cross_folder_import_ratio` and `domain_isolation_score` within 0.0 to 1.0 inclusive and SHALL NOT raise a division-by-zero error.
8. THE Topology_Profiler SHALL return `evidence` as a list of strings sorted in ascending lexicographic order by Unicode code point, each string at most 200 characters, each referencing an observed directory, file, or import relationship in the Snapshot.
9. IF a directory's name and observed contents match no defined Directory_Role, THEN THE Topology_Profiler SHALL assign that directory the default Directory_Role value defined in the Glossary, and SHALL NOT omit it from `directory_roles`.
10. IF the Snapshot contains no files, THEN THE Topology_Profiler SHALL return empty `directory_roles`, `boundary_metrics` with `max_depth` and `entry_point_count` of 0.0, `cross_folder_import_ratio` of 0.0, `domain_isolation_score` of 1.0, and an empty `evidence` list, and SHALL NOT raise an error.
11. WHEN the same Snapshot is profiled more than once, THE Topology_Profiler SHALL return identical `directory_roles`, `boundary_metrics`, and `evidence` on every run.

### Requirement 9: Structured LLM Router Interface and Configuration

**User Story:** As a developer, I want one typed entry point for structured LLM output, so that engines never handle raw provider text.

#### Acceptance Criteria

1. THE LLM_Router SHALL expose `async generate_structured(system_prompt: str, user_prompt: str, response_model: type[T]) -> T`, where `T` is a Pydantic model type.
2. THE LLM_Router SHALL select the Provider from the `LLM_PROVIDER` setting, accepting only the case-sensitive values `mock`, `gemini`, and `ollama`, with default `mock` when the setting is unset.
3. THE LLM_Router SHALL read `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `OLLAMA_BASE_URL`, and `OLLAMA_MODEL` through pydantic-settings, using the defaults in `.env.example` (`GEMINI_MODEL=gemini-2.5-flash`, `OLLAMA_BASE_URL=http://localhost:11434/v1`, `OLLAMA_MODEL=qwen3.5`) when a setting is unset.
4. IF `LLM_PROVIDER` is not one of the accepted values, THEN THE LLM_Router SHALL raise a configuration error naming `mock`, `gemini`, and `ollama` as the accepted values and SHALL NOT make any Provider call.
5. IF the selected Provider is `gemini` and `GEMINI_API_KEY` is empty or contains only whitespace, THEN THE LLM_Router SHALL raise a configuration error indicating the missing key before any network call and SHALL NOT include the key value in the error.
6. WHEN a Provider returns output that passes validation, THE LLM_Router SHALL return an instance of `response_model` and SHALL NOT return raw provider text.
7. IF a Provider returns output that fails validation after the attempts allowed by Requirement 10 (2 attempts for `ollama`, 1 attempt for `gemini`), or a connection error, timeout, or provider error occurs, THEN THE LLM_Router SHALL raise an `LLMRouterError` that contains the provider name and one failure category (validation, connection, timeout, or provider) and omits API keys, authorization headers, and prompt text.
8. THE LLM_Router SHALL NOT write API keys, authorization headers, or prompt text to any log record at any log level.
9. THE LLM_Router SHALL contain all Provider-specific code, and callers SHALL be able to call `generate_structured` without importing any Provider SDK.
10. WHERE `LLM_PROVIDER` is `mock`, THE LLM_Router SHALL NOT import any Provider SDK and SHALL NOT open any network connection.
11. WHERE `LLM_PROVIDER` is `gemini` or `ollama`, THE LLM_Router SHALL import the Provider SDK on the first call to that Provider and not at module import time.

### Requirement 10: Mock, Gemini, and Ollama Providers

**User Story:** As a developer, I want a deterministic mock and two real providers behind the same interface, so that tests run offline and production can use either model host.

#### Acceptance Criteria

1. WHEN the Mock_Provider receives the same prompts and Response_Model in two or more calls, THE LLM_Router SHALL return outputs that are equal field-by-field in every call.
2. THE Mock_Provider SHALL return a schema-valid instance for `L1SyntaxExplanation`, `L2FlowExplanation`, and `L3ArchitectureExplanation`, deriving its field values from the grounded Context_Slice in the user prompt and using no randomness, clock, or network.
3. IF the Mock_Provider receives a Response_Model other than `L1SyntaxExplanation`, `L2FlowExplanation`, or `L3ArchitectureExplanation`, THEN THE LLM_Router SHALL raise an `LLMRouterError` identifying the unsupported Response_Model and SHALL make no network call.
4. WHEN the Provider is `gemini`, THE LLM_Router SHALL call `client.models.generate_content` of the `google-genai` SDK with `response_mime_type` set to `application/json` and `response_schema` set to the Response_Model, using the `GEMINI_MODEL` setting, and SHALL validate the returned JSON against the Response_Model.
5. WHEN the Provider is `ollama`, THE LLM_Router SHALL call `openai.AsyncOpenAI` with `base_url` from `OLLAMA_BASE_URL` and `api_key` set to `ollama`, using the `OLLAMA_MODEL` setting and a JSON-schema instruction derived from the Response_Model, and SHALL validate the returned JSON against the Response_Model.
6. IF an `ollama` response fails JSON parsing or validation, THEN THE LLM_Router SHALL retry the call exactly once with the same prompts and, IF the retry also fails, THEN THE LLM_Router SHALL raise an `LLMRouterError` indicating that parsing or validation failed after one retry.
7. IF a `gemini` response fails JSON parsing or validation, THEN THE LLM_Router SHALL raise an `LLMRouterError` indicating that parsing or validation failed, and SHALL make exactly one call to the Provider.
8. THE LLM_Router SHALL apply a request timeout of 60 seconds to each Provider call, and each retry under criterion 6 SHALL have its own 60-second timeout.
9. IF a Provider call exceeds the 60-second timeout or fails with a connection or SDK error, THEN THE LLM_Router SHALL raise an `LLMRouterError` indicating a timeout or Provider failure, and SHALL NOT return a partial or unvalidated result.
10. IF the `GEMINI_MODEL`, `OLLAMA_MODEL`, or `OLLAMA_BASE_URL` setting required by the selected Provider is absent or an empty string, THEN THE LLM_Router SHALL raise an `LLMRouterError` naming the missing setting before making any Provider call.

### Requirement 11: SQLite Cache Store

**User Story:** As a developer, I want analysis and explanations persisted by AST hash, so that unchanged code is never re-explained.

#### Acceptance Criteria

1. WHERE `STUPID_CODE_DB_PATH` is set to a non-empty value, THE Cache_Store SHALL use that value as the database location, and WHERE it is unset or empty, THE Cache_Store SHALL use `./data/stupid_code.db`.
2. WHERE the database location is `:memory:`, THE Cache_Store SHALL use an in-memory database that is discarded when the Cache_Store is closed.
3. WHEN the database location is a file path and its parent directory does not exist, THE Cache_Store SHALL create the parent directory, including intermediate directories, and SHALL enable SQLite WAL journal mode.
4. THE Cache_Store SHALL define its tables with SQLModel and SHALL persist Snapshot JSON, `ProvenanceReport` JSON, `TopologyProfile` JSON, and `ExplanationEnvelope` JSON.
5. WHEN an object is written under a Cache_Key `(repo_id, ast_hash, target_id, lens)` that already has a row, THE Cache_Store SHALL replace that row, so that exactly one row exists per Cache_Key and the subsequent read returns the most recently written object.
6. THE Cache_Store SHALL enforce a unique constraint on the Cache_Key `(repo_id, ast_hash, target_id, lens)`.
7. WHEN a stored object is read, THE Cache_Store SHALL validate it with the corresponding Domain_Models class and SHALL return an object equal to the one stored.
8. WHEN a read finds no row for the requested Cache_Key, THE Cache_Store SHALL return a miss indication and SHALL NOT raise an error.
9. IF a stored row fails Domain_Models validation, THEN THE Cache_Store SHALL treat the row as a miss, delete that row, and SHALL NOT return its content.
10. THE Cache_Store SHALL use one session per operation, SHALL commit when the operation succeeds, and SHALL roll back all changes made by the operation when it fails.
11. IF a database error occurs, including a locked, unwritable, corrupt, or unreachable database, or a failure to create the parent directory, THEN THE Cache_Store SHALL raise a `CacheStoreError`, SHALL leave previously committed rows unchanged, and SHALL NOT return unrelated or stale content.
12. THE Cache_Store SHALL write only to the configured database location and its SQLite journal files.
13. THE Cache_Store SHALL keep lenses isolated, so that an entry for one Lens is never returned for another Lens with the same repo_id, ast_hash, and target_id.

### Requirement 12: Pedagogy Context Slicing and Cache-First Flow

**User Story:** As a developer, I want explanations built from a small grounded slice and cached by AST hash, so that results are cheap, relevant, and reproducible.

#### Acceptance Criteria

1. THE Pedagogy_Engine SHALL expose `async explain_target(repo_id, target_id, lens: PedagogyLens, force_refresh: bool = False) -> ExplanationEnvelope`.
2. WHEN `explain_target` is called, THE Pedagogy_Engine SHALL load the Snapshot, `ProvenanceReport`, and `TopologyProfile` for `repo_id` from the Cache_Store before building the Context_Slice.
3. IF `target_id` does not name a Snapshot symbol for L1 or L2, THEN THE Pedagogy_Engine SHALL raise a `PedagogyError` indicating the target is unknown, SHALL NOT call the LLM_Router, and SHALL NOT create or modify any Cache_Store entry.
4. THE Pedagogy_Engine SHALL build a Context_Slice containing exactly these items: the Target source text, signature and metadata; the signatures of direct callers and direct callees only (call depth 1, no transitive callers or callees); matching Spec_Links; DSASignals whose `symbol_id` equals the Target; the `TopologyProfile`; and `ProvenanceReport` entries for the Target file.
5. THE Pedagogy_Engine SHALL obtain direct callers and callees from the Phase 1 Graph_Engine and SHALL NOT reimplement call resolution.
6. THE Pedagogy_Engine SHALL read Target source text only from the Snapshot file under Repo_Root, and SHALL NOT include the content of any file other than the Target file in the Context_Slice.
7. WHEN `force_refresh` is false and the Cache_Store holds an entry for the Cache_Key, THE Pedagogy_Engine SHALL return that entry with `cached` set to true, SHALL make 0 calls to the LLM_Router, and SHALL NOT modify the stored entry.
8. WHEN `force_refresh` is true or the Cache_Store has no entry for the Cache_Key, THE Pedagogy_Engine SHALL call the LLM_Router exactly once, validate the result, replace any existing entry for the Cache_Key with the validated Explanation_Envelope with `cached` false, and return it.
9. WHEN the Target_AST_Hash differs from the hash of a stored entry for the same repo_id, target_id, and lens, THE Pedagogy_Engine SHALL treat the lookup as a miss, call the LLM_Router exactly once, and persist the fresh Explanation_Envelope under the new Target_AST_Hash.
10. THE Pedagogy_Engine SHALL populate only the tier matching the requested Lens in the Explanation_Envelope, and SHALL leave the tiers for all other Lenses empty.
11. THE Pedagogy_Engine SHALL NOT execute analyzed code.
12. FOR ALL equal Context_Slice inputs, THE Pedagogy_Engine SHALL build Context_Slices that are equal in content and in element order.
13. IF the Snapshot, `ProvenanceReport`, or `TopologyProfile` for `repo_id` is absent from the Cache_Store, THEN THE Pedagogy_Engine SHALL raise a `PedagogyError` naming each missing item, SHALL NOT call the LLM_Router, and SHALL NOT create or modify any Cache_Store entry.
14. IF the LLM_Router call raises an error or returns a result that fails Explanation_Envelope validation, THEN THE Pedagogy_Engine SHALL raise a `PedagogyError` indicating the failure cause, SHALL NOT persist the result, and SHALL leave any existing Cache_Store entry for the Cache_Key unchanged. (Exception: L2 degrades per Requirement 14 criterion 10.)
15. IF the Target source file is missing or unreadable under Repo_Root, THEN THE Pedagogy_Engine SHALL raise a `PedagogyError` naming the file, SHALL NOT call the LLM_Router, and SHALL NOT create or modify any Cache_Store entry.

### Requirement 13: L1 Syntax Explanation

**User Story:** As a learner, I want line-by-line grounded syntax explanations, so that I understand exactly what the code constructs do.

#### Acceptance Criteria

1. WHEN the Lens is `L1_SYNTAX`, THE Pedagogy_Engine SHALL return an `L1SyntaxExplanation` whose `target_id` equals the requested Target and whose `language` equals the language of the Target file.
2. THE Pedagogy_Engine SHALL require each `SyntaxAnnotation` to have integer `line_start` and `line_end` values such that `line_start` ≤ `line_end` and both lie within the inclusive line range of the Target symbol.
3. THE Pedagogy_Engine SHALL require each `SyntaxAnnotation` to contain a `construct`, `explanation`, and `what_if_removed`, each with 1 to 2,000 characters after trimming leading and trailing whitespace.
4. IF the LLM_Router output contains an annotation whose line range is outside the Target symbol's line range, whose `line_start` is greater than `line_end`, or whose `construct` text does not occur as a substring of the Target source lines from `line_start` to `line_end`, THEN THE Pedagogy_Engine SHALL reject the entire output with a `PedagogyError` identifying the offending annotation index, SHALL NOT persist any part of it, and SHALL NOT return an `L1SyntaxExplanation`.
5. THE Pedagogy_Engine SHALL instruct the LLM_Router to explain what each construct is, what it does, why it matters, and what happens if it is removed.
6. IF the LLM_Router output contains zero annotations or cannot be parsed into an `L1SyntaxExplanation`, THEN THE Pedagogy_Engine SHALL reject the output with a `PedagogyError` and SHALL NOT persist it.
7. IF the LLM_Router fails to return a response within 30 seconds or returns an error, THEN THE Pedagogy_Engine SHALL return a `PedagogyError` indicating the Router failure and SHALL NOT persist any explanation.

### Requirement 14: L2 Flow Explanation and DSA Cards

**User Story:** As a learner, I want grounded execution flow and real algorithm patterns, so that I see how data moves and where known techniques appear.

#### Acceptance Criteria

1. WHEN the Lens is `L2_FLOW`, THE Pedagogy_Engine SHALL return an `L2FlowExplanation` whose `upstream_callers` and `downstream_callees` equal the Graph_Engine direct callers and callees of the Target, each listed once and sorted ascending by symbol identifier.
2. WHEN the Pedagogy_Engine returns an `L2FlowExplanation`, THE Pedagogy_Engine SHALL set `execution_steps` so that `step_number` values are consecutive integers starting at 1 with no gaps or duplicates, and SHALL set `execution_steps` to an empty list if the Target has no executable statements.
3. WHEN the Pedagogy_Engine builds `dsa_cards`, THE Pedagogy_Engine SHALL create one DSACard for each DSASignal whose `symbol_id` equals the Target, copying `chapter`, `pattern_name`, `start_line`, and `end_line` unchanged from the signal.
4. WHEN the Pedagogy_Engine derives complexity for a DSACard, THE Pedagogy_Engine SHALL set `time_complexity` and `space_complexity` from a fixed deterministic table keyed by `(chapter, pattern_name)`, and SHALL set both fields to the exact text `not determined` for a pair absent from the table.
5. WHEN the LLM_Router returns `why_used_here` for a DSACard, THE Pedagogy_Engine SHALL accept it only if it is non-empty, at most 500 characters, and references at least one element of the signal evidence, and SHALL otherwise set `why_used_here` to an empty string.
6. IF the LLM_Router proposes a DSACard not backed by a DSASignal of the Target, THEN THE Pedagogy_Engine SHALL discard that DSACard and leave `dsa_cards` unchanged.
7. IF the Target has zero DSASignals, THEN THE Pedagogy_Engine SHALL return `dsa_cards` equal to an empty list.
8. THE Pedagogy_Engine SHALL NOT include DSASignals of any other symbol in the `dsa_cards` of the Target.
9. IF the LLM_Router proposes `upstream_callers` or `downstream_callees`, THEN THE Pedagogy_Engine SHALL replace them with the deterministic values from criterion 1.
10. IF the LLM_Router fails or does not respond within 30 seconds, THEN THE Pedagogy_Engine SHALL still return the `L2FlowExplanation` with deterministic `upstream_callers`, `downstream_callees`, and `dsa_cards`, set `why_used_here` to an empty string for every DSACard, and set `llm_content_available` to false as the indicator that LLM-generated content is unavailable (a degraded result is not persisted to the cache).

### Requirement 15: L3 Architecture Explanation and Counterfactuals

**User Story:** As a learner, I want the repository's architecture explained with grounded alternatives, so that I understand the tradeoffs of this structure.

#### Acceptance Criteria

1. WHEN the Lens is `L3_ARCHITECTURE`, THE Pedagogy_Engine SHALL return an `L3ArchitectureExplanation` whose `topology_pattern` equals the `detected_pattern` of the stored `TopologyProfile`.
2. WHEN the Pedagogy_Engine builds an `L3ArchitectureExplanation`, THE Pedagogy_Engine SHALL set `structural_evidence` to a list of 1 to 20 entries, each derived from a `TopologyProfile.evidence` item or from a file path that exists in the Snapshot.
3. WHEN the Pedagogy_Engine builds an `L3ArchitectureExplanation`, THE Pedagogy_Engine SHALL return between 1 and 3 `AlternativeArchitecture` items, each with a `pattern_name` that is a Topology_Pattern other than the detected pattern, a `why_not_chosen` of 1 to 1,000 non-whitespace-only characters, and a `when_to_switch` of 1 to 1,000 non-whitespace-only characters.
4. WHEN the Pedagogy_Engine builds the Context_Slice for L3, THE Pedagogy_Engine SHALL include the directory roles, boundary metrics, drift items, and Spec_Links from the stored reports.
5. WHEN at least one Spec_Link exists in the `ProvenanceReport`, THE Pedagogy_Engine SHALL set `spec_rationale` to text of 1 to 2,000 characters that quotes or paraphrases at least one of those Spec_Link excerpts.
6. IF the `ProvenanceReport` contains no Spec_Link, THEN THE Pedagogy_Engine SHALL set `spec_rationale` to null.
7. IF the LLM_Router output names a path in `structural_evidence` that is not present in the Snapshot or in the `TopologyProfile`, THEN THE Pedagogy_Engine SHALL reject that output with a `PedagogyError` identifying the unknown path, SHALL NOT persist it, and SHALL leave previously stored explanations unchanged.
8. IF the `TopologyProfile` confidence is below 0.5, THEN THE Pedagogy_Engine SHALL include in `why_this_folder_structure` a statement that names the confidence value to two decimal places and indicates the pattern detection is low confidence.
9. IF the `TopologyProfile` or `ProvenanceReport` is not stored for the Snapshot, THEN THE Pedagogy_Engine SHALL return a `PedagogyError` naming the missing report and SHALL NOT call the LLM_Router.

### Requirement 16: Engineering Rules and Phase 1 Compatibility

**User Story:** As a maintainer, I want the new code to respect the architecture and existing contracts, so that Phase 1 remains stable.

#### Acceptance Criteria

1. THE Spec_Grounder, Topology_Profiler, Cache_Store, LLM_Router, and Pedagogy_Engine SHALL NOT contain an `import fastapi` or `from fastapi import ...` statement, directly or through a module of this spec.
2. THE Domain_Models SHALL NOT contain an import statement that references any module under `backend/engines`.
3. THE Spec_Grounder, Topology_Profiler, and Pedagogy_Engine SHALL obtain graph, AST, and DSA data by calling the Phase 1 Graph_Engine, AST_Parser, and DSA_Scanner, and SHALL NOT contain their own source-parsing, graph-construction, or DSA-pattern-detection logic.
4. THE modules of this spec SHALL have an import graph that contains zero cycles, as verified by an automated test that fails when one cycle is found. (Verified by a lightweight check within the existing unit-test budget, not an extra test file.)
5. WHERE a Phase 1 engine requires a change, THE change SHALL leave all existing public function signatures and return types unchanged, SHALL be recorded with a justification in the design document, and the existing Phase 1 tests SHALL pass with zero modifications to those test files.
6. WHEN the Spec_Grounder, Topology_Profiler, context slicing, DSA card mapping, Mock_Provider, or Cache_Key construction is run twice on identical input, THE component SHALL produce byte-identical serialized output, and any collection whose order carries no meaning SHALL be sorted by a stable key.
7. IF the data required for a spec section, excerpt, path, symbol, line number, caller, callee, DSA pattern, complexity value, architecture evidence item, or commit is not present in the Phase 1 results, the repository, or the loaded spec files, THEN THE new engines SHALL omit that item or mark it as unavailable, and SHALL NOT generate a substitute value.
8. WHEN a new engine performs a file write, THE new engine SHALL write only to the configured database location or the project-managed storage directory, and SHALL NOT create or modify any file elsewhere, including the source repository being analyzed.
9. WHEN `ruff check` and `ruff format --check` are run with the repository configuration over the new code, THE commands SHALL each exit with code 0 and report zero violations.

### Requirement 17: Test Suite

**User Story:** As a maintainer, I want a small, targeted, offline test suite, so that the new behavior is verified without bloat.

#### Acceptance Criteria

1. THE Pytest_Config SHALL contain the existing settings `testpaths = backend/tests` and `pythonpath = .` and SHALL add `asyncio_mode = auto`.
2. THE Test_Suite SHALL include `backend/tests/unit/test_spec_topology_pedagogy.py` containing between 20 and 25 test functions (inclusive) and fewer than 600 lines.
3. THE Test_Suite SHALL include `backend/tests/properties/test_pedagogy_properties.py` containing exactly four Hypothesis property tests.
4. THE unit tests SHALL exercise each of the following areas with at least one test per listed item (a single test may cover several items):
   - Domain models: valid construction, invalid construction rejected, and nullable fields set to null.
   - Spec discovery: missing spec files, grounded links, `UNSPECIFIED_CODE`, `UNIMPLEMENTED_SPEC`, git history association, and a directory with no `.git`.
   - Topology: a hexagonal fixture, a flat fixture, determinism across two runs on identical input, roles, metrics, metric bounds, and an empty graph.
   - Router: mock output, response validation, provider selection, and handling of an invalid response.
   - Cache: miss, hit, miss after an `ast_hash` change, lens isolation, serialization round trip, and the `:memory:` location.
   - Pedagogy: L1, L2, and L3 explanations, DSA cards built from real signals, DSA cards from empty signals, a cache hit that makes zero LLM calls, and force refresh that makes a new LLM call.
5. THE property tests SHALL verify the following:
   1. Two `explain_target` calls with the same Cache_Key return a first result generated by the LLM and a second result with `cached` true, with at most one LLM call in total.
   2. A different `ast_hash` produces a cache miss with `cached` false and a freshly generated result that differs from the previously cached result.
   3. A Target with zero relevant DSASignals returns an empty `dsa_cards` list that contains no card derived from another symbol's signals.
   4. `cross_folder_import_ratio` and `domain_isolation_score` are each within 0.0 to 1.0 inclusive for generated layouts, including empty layouts, isolated-node layouts, self-edge layouts, and layouts with no import edges.
6. THE Test_Suite SHALL use a deterministic mock LLM that returns identical output for identical input, and SHALL make no call to Gemini, Ollama, the internet, or any external repository.
7. THE Test_Suite SHALL NOT read a real `.env` file, and SHALL set `LLM_PROVIDER=mock` as the default for every test that does not explicitly set another value.
8. WHEN the full suite runs from the repository root, THE Test_Suite SHALL report zero failures and zero errors across all 745 existing tests plus the new tests, with no existing test weakened, deleted, skipped, or marked xfail.
9. THE Test_Suite SHALL run Git history tests only against a temporary repository created by the test, and SHALL configure each property test with `max_examples` of at most 100 and a per-example deadline of at most 500 ms.
10. IF a test attempts an outbound network connection or reads a path outside the repository and its own temporary directory, THEN THE Test_Suite SHALL fail that test with an error identifying the attempted access.
11. WHEN the new unit and property test files run on their own, THE Test_Suite SHALL complete within 60 seconds.
