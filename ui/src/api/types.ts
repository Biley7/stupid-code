/**
 * Contract_Types: TypeScript mirror of the Backend_API contract (Spec #03).
 *
 * Verified against backend/domain/models.py, backend/api/schemas.py and
 * backend/api/routes/*.py. Field names, nullability and enum values match 1:1.
 * Enum-like fields use `Tolerant<...>` so an unknown string from a newer
 * backend still type-checks and renders as plain text (Requirement 27.5).
 */

/** Known literals for editor help, plus any other string. */
export type Tolerant<T extends string> = T | (string & {});

export type Lens = 'L1_SYNTAX' | 'L2_FLOW' | 'L3_ARCHITECTURE';
export type MasteryState = Tolerant<'UNAUDITED' | 'DISSECTED' | 'MASTERED' | 'STALE'>;

export type LanguageName = Tolerant<'python' | 'typescript' | 'javascript' | 'tsx' | 'java'>;
export type SymbolKind = Tolerant<'function' | 'method' | 'class' | 'interface' | 'component'>;
export type EdgeType = Tolerant<'imports' | 'calls'>;
export type DsaChapter = Tolerant<
  | 'Hash Tables'
  | 'Graphs & Trees'
  | 'Recursion & Dynamic Programming'
  | 'Sliding Window / Two Pointers'
  | 'Heaps & Priority Queues'
  | 'Sorting & Binary Search'
>;
export type TopologyPattern = Tolerant<
  | 'Hexagonal / Clean Architecture'
  | 'Layered MVC'
  | 'Feature-Sliced'
  | 'Modular Monolith'
  | 'Flat / Script'
>;
export type DirectoryRole = Tolerant<
  | 'domain'
  | 'engines'
  | 'api'
  | 'ui'
  | 'tests'
  | 'config'
  | 'infrastructure'
  | 'services'
  | 'entry_points'
  | 'other'
>;
export type DriftType = Tolerant<'UNSPECIFIED_CODE' | 'UNIMPLEMENTED_SPEC'>;
export type SpecSourceFile = Tolerant<'requirements.md' | 'design.md' | 'tasks.md'>;

// -- health, repositories -----------------------------------------------------------

export interface HealthResponse {
  status: string;
  service: string;
}

export interface RepoSummary {
  repo_id: string;
  file_count: number;
  symbol_count: number;
  study_mode_enabled: boolean;
}

// -- snapshot -----------------------------------------------------------------------

export interface SymbolNode {
  /** `file_path::qualname` */
  id: string;
  name: string;
  qualname: string;
  kind: SymbolKind;
  file_path: string;
  start_line: number;
  end_line: number;
  signature: string;
  ast_hash: string;
  decorators: string[];
  is_async: boolean;
  raw_calls: string[];
}

export interface FileAnalysis {
  file_path: string;
  language: LanguageName;
  loc: number;
  ast_hash: string;
  imports: string[];
  exports: string[];
  symbols: SymbolNode[];
  parse_errors: string[];
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_type: EdgeType;
}

export interface DSASignal {
  symbol_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  chapter: DsaChapter;
  pattern_name: string;
  confidence: number;
  evidence: string[];
}

export interface RepoGraphSnapshot {
  repo_id: string;
  /** Always "." over HTTP. */
  root_path: string;
  files: FileAnalysis[];
  edges: GraphEdge[];
  /** File paths or symbol ids. */
  vital_organs: string[];
  /** Each entry holds file paths or symbol ids. */
  cycles: string[][];
  dsa_signals: DSASignal[];
}

// -- provenance, topology -----------------------------------------------------------

export interface SpecLink {
  spec_name: string;
  source_file: SpecSourceFile;
  section_title: string;
  excerpt: string;
  confidence: number;
}

export interface DriftItem {
  drift_type: DriftType;
  target: string;
  details: string;
}

export interface ProvenanceReport {
  repo_id: string;
  has_kiro_specs: boolean;
  /** Keyed by file path. */
  spec_links: Record<string, SpecLink[]>;
  drift_items: DriftItem[];
  /** Keyed by file path; opaque `<short hash>|<subject>` strings, newest first. */
  recent_commits: Record<string, string[]>;
}

export interface BoundaryMetrics {
  max_depth: number;
  cross_folder_import_ratio: number;
  domain_isolation_score: number;
  entry_point_count: number;
}

export interface TopologyProfile {
  repo_id: string;
  detected_pattern: TopologyPattern;
  confidence: number;
  /** Keyed by directory path. */
  directory_roles: Record<string, DirectoryRole>;
  boundary_metrics: BoundaryMetrics;
  evidence: string[];
}

export interface SnapshotResponse {
  snapshot: RepoGraphSnapshot;
  provenance: ProvenanceReport;
  topology: TopologyProfile;
}

// -- ingest -------------------------------------------------------------------------

export interface IngestLimits {
  max_files?: number;
  max_total_bytes?: number;
}

/** Exactly one of `path` or `url`. */
export type IngestRequest =
  | ({ path: string; url?: never } & IngestLimits)
  | ({ url: string; path?: never } & IngestLimits);

export interface IngestSummary {
  file_count: number;
  symbol_count: number;
  edge_count: number;
  dsa_signal_count: number;
}

export interface IngestWarning {
  kind: string;
  path: string;
  detail: string;
}

export interface IngestResponse {
  repo_id: string;
  summary: IngestSummary;
  provenance: ProvenanceReport;
  topology: TopologyProfile;
  truncated: boolean;
  warnings: IngestWarning[];
}

// -- explain ------------------------------------------------------------------------

export interface ExplainRequest {
  target_id: string;
  lens: Lens;
}

export interface L1Annotation {
  line_start: number;
  line_end: number;
  construct: string;
  explanation: string;
  what_if_removed: string;
}

export interface L1Explanation {
  target_id: string;
  language: LanguageName;
  summary: string;
  annotations: L1Annotation[];
  key_takeaway: string;
}

export interface ExecutionStep {
  step_number: number;
  location: string;
  action: string;
  data_transformation: string;
}

export interface DSACard {
  chapter: DsaChapter;
  pattern_name: string;
  start_line: number;
  end_line: number;
  why_used_here: string;
  time_complexity: string;
  space_complexity: string;
}

export interface L2Explanation {
  target_id: string;
  execution_steps: ExecutionStep[];
  upstream_callers: string[];
  downstream_callees: string[];
  side_effects: string[];
  dsa_cards: DSACard[];
  /** False when the backend returned a degraded result. */
  llm_content_available: boolean;
}

export interface L3Alternative {
  pattern_name: TopologyPattern;
  why_not_chosen: string;
  when_to_switch: string;
}

export interface L3Explanation {
  target_id: string;
  topology_pattern: TopologyPattern;
  why_this_folder_structure: string;
  /** 1 to 20 entries. */
  structural_evidence: string[];
  alternatives: L3Alternative[];
  spec_rationale: string | null;
}

interface EnvelopeBase {
  repo_id: string;
  target_id: string;
  ast_hash: string;
  cached: boolean;
}

/**
 * Exactly the tier matching `lens` is non-null; the other two are null.
 * The backend always serializes all three keys.
 */
export type ExplanationEnvelope =
  | (EnvelopeBase & {
      lens: 'L1_SYNTAX';
      l1: L1Explanation;
      l2: null;
      l3: null;
    })
  | (EnvelopeBase & {
      lens: 'L2_FLOW';
      l1: null;
      l2: L2Explanation;
      l3: null;
    })
  | (EnvelopeBase & {
      lens: 'L3_ARCHITECTURE';
      l1: null;
      l2: null;
      l3: L3Explanation;
    });

export interface BlastRadius {
  target_id: string;
  upstream_callers: string[];
  downstream_callees: string[];
  /** 0 to 1. */
  impact_score: number;
}

export interface ExplainResponse {
  envelope: ExplanationEnvelope;
  blast_radius: BlastRadius;
}

// -- vitals, study mode, socratic ---------------------------------------------------

export interface ComprehensionVitals {
  repo_id: string;
  study_mode_enabled: boolean;
  total_modules: number;
  unaudited_count: number;
  dissected_count: number;
  mastered_count: number;
  stale_count: number;
  /** 0 to 100. */
  mastery_percentage: number;
  /** Symbol ids. */
  due_for_review: string[];
  /** Keyed by file path; a file with no tracked symbol has no key. */
  file_states: Record<string, MasteryState>;
}

export interface StudyModeRequest {
  enabled: boolean;
}

export interface StudyModeResponse {
  repo_id: string;
  study_mode_enabled: boolean;
}

export interface SocraticStartRequest {
  target_id: string;
}

export interface SocraticQuestion {
  question_id: string;
  target_id: string;
  prompt: string;
  line_reference: string;
  /** Always `[]` in the start response. */
  expected_concepts: string[];
}

export interface SocraticCheck {
  repo_id: string;
  target_id: string;
  /** 1 to 2 questions. */
  questions: SocraticQuestion[];
}

export interface SocraticAnswer {
  question_id: string;
  answer: string;
}

export interface SocraticSubmitRequest {
  target_id: string;
  answers: SocraticAnswer[];
}

export interface SocraticVerdict {
  target_id: string;
  passed: boolean;
  /** 0 to 1. */
  score: number;
  feedback: string;
  new_state: MasteryState;
  /** UTC `YYYY-MM-DDTHH:MM:SSZ` or null. */
  next_review_at: string | null;
}

// -- errors -------------------------------------------------------------------------

export interface ApiErrorBody {
  code: string;
  message: string;
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}
