/**
 * Runtime validators for Backend_API responses (Requirements 2.8, 2.11, 27.4, 27.5).
 *
 * Each validator takes parsed JSON (`unknown`) and returns the typed value, or
 * `null` when a required field is missing or has the wrong primitive type. It
 * never returns partial data. Only presence and primitive type of the fields the
 * UI reads are checked: extra fields are accepted, and enum-like fields accept
 * any string so a newer backend still renders as plain text.
 */

import type {
  BlastRadius,
  BoundaryMetrics,
  ComprehensionVitals,
  DriftItem,
  DSACard,
  DSASignal,
  ExecutionStep,
  ExplainResponse,
  ExplanationEnvelope,
  FileAnalysis,
  GraphEdge,
  HealthResponse,
  IngestResponse,
  IngestSummary,
  IngestWarning,
  L1Annotation,
  L1Explanation,
  L2Explanation,
  L3Alternative,
  L3Explanation,
  ProvenanceReport,
  RepoGraphSnapshot,
  RepoSummary,
  SnapshotResponse,
  SocraticCheck,
  SocraticQuestion,
  SocraticVerdict,
  SpecLink,
  StudyModeResponse,
  SymbolNode,
  TopologyProfile,
} from './types';

/** A validator returns the typed value or `null`. */
export type Validator<T> = (value: unknown) => T | null;

// -- primitive guards ---------------------------------------------------------------

type Rec = Record<string, unknown>;

function isRec(v: unknown): v is Rec {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}
const isStr = (v: unknown): v is string => typeof v === 'string';
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isBool = (v: unknown): v is boolean => typeof v === 'boolean';
const isNullableStr = (v: unknown): v is string | null => v === null || isStr(v);

function every<T>(v: unknown, test: (item: unknown) => boolean): v is T[] {
  return Array.isArray(v) && v.every(test);
}
const isStrArray = (v: unknown): v is string[] => every<string>(v, isStr);

function isRecordOf(v: unknown, test: (item: unknown) => boolean): v is Rec {
  return isRec(v) && Object.values(v).every(test);
}

/** Builds an array-of-T guard from an item guard. */
function arrayOf(guard: (v: unknown) => boolean): (v: unknown) => boolean {
  return (v) => Array.isArray(v) && v.every(guard);
}

/** Shape guard: each listed field must satisfy its check. */
function shape(checks: Record<string, (v: unknown) => boolean>): (v: unknown) => boolean {
  const entries = Object.entries(checks);
  return (v) => isRec(v) && entries.every(([key, check]) => key in v && check(v[key]));
}

/** Turns a guard into a Validator for type T. */
function validator<T>(guard: (v: unknown) => boolean): Validator<T> {
  return (value) => (guard(value) ? (value as T) : null);
}

// -- shared shapes ------------------------------------------------------------------

const isSymbolNode = shape({
  id: isStr,
  name: isStr,
  qualname: isStr,
  kind: isStr,
  file_path: isStr,
  start_line: isNum,
  end_line: isNum,
  signature: isStr,
  ast_hash: isStr,
  decorators: isStrArray,
  is_async: isBool,
  raw_calls: isStrArray,
}) as (v: unknown) => v is SymbolNode;

const isFileAnalysis = shape({
  file_path: isStr,
  language: isStr,
  loc: isNum,
  ast_hash: isStr,
  imports: isStrArray,
  exports: isStrArray,
  symbols: arrayOf(isSymbolNode),
  parse_errors: isStrArray,
}) as (v: unknown) => v is FileAnalysis;

const isGraphEdge = shape({
  source: isStr,
  target: isStr,
  edge_type: isStr,
}) as (v: unknown) => v is GraphEdge;

const isDsaSignal = shape({
  symbol_id: isStr,
  file_path: isStr,
  start_line: isNum,
  end_line: isNum,
  chapter: isStr,
  pattern_name: isStr,
  confidence: isNum,
  evidence: isStrArray,
}) as (v: unknown) => v is DSASignal;

const isSnapshot = shape({
  repo_id: isStr,
  root_path: isStr,
  files: arrayOf(isFileAnalysis),
  edges: arrayOf(isGraphEdge),
  vital_organs: isStrArray,
  cycles: arrayOf(isStrArray),
  dsa_signals: arrayOf(isDsaSignal),
}) as (v: unknown) => v is RepoGraphSnapshot;

const isSpecLink = shape({
  spec_name: isStr,
  source_file: isStr,
  section_title: isStr,
  excerpt: isStr,
  confidence: isNum,
}) as (v: unknown) => v is SpecLink;

const isDriftItem = shape({
  drift_type: isStr,
  target: isStr,
  details: isStr,
}) as (v: unknown) => v is DriftItem;

const isProvenance = shape({
  repo_id: isStr,
  has_kiro_specs: isBool,
  spec_links: (v) => isRecordOf(v, arrayOf(isSpecLink)),
  drift_items: arrayOf(isDriftItem),
  recent_commits: (v) => isRecordOf(v, isStrArray),
}) as (v: unknown) => v is ProvenanceReport;

const isBoundaryMetrics = shape({
  max_depth: isNum,
  cross_folder_import_ratio: isNum,
  domain_isolation_score: isNum,
  entry_point_count: isNum,
}) as (v: unknown) => v is BoundaryMetrics;

const isTopology = shape({
  repo_id: isStr,
  detected_pattern: isStr,
  confidence: isNum,
  directory_roles: (v) => isRecordOf(v, isStr),
  boundary_metrics: isBoundaryMetrics,
  evidence: isStrArray,
}) as (v: unknown) => v is TopologyProfile;

const isRepoSummary = shape({
  repo_id: isStr,
  file_count: isNum,
  symbol_count: isNum,
  study_mode_enabled: isBool,
}) as (v: unknown) => v is RepoSummary;

const isIngestSummary = shape({
  file_count: isNum,
  symbol_count: isNum,
  edge_count: isNum,
  dsa_signal_count: isNum,
}) as (v: unknown) => v is IngestSummary;

const isIngestWarning = shape({
  kind: isStr,
  path: isStr,
  detail: isStr,
}) as (v: unknown) => v is IngestWarning;

// -- explain tiers ------------------------------------------------------------------

const isL1Annotation = shape({
  line_start: isNum,
  line_end: isNum,
  construct: isStr,
  explanation: isStr,
  what_if_removed: isStr,
}) as (v: unknown) => v is L1Annotation;

const isL1 = shape({
  target_id: isStr,
  language: isStr,
  summary: isStr,
  annotations: arrayOf(isL1Annotation),
  key_takeaway: isStr,
}) as (v: unknown) => v is L1Explanation;

const isExecutionStep = shape({
  step_number: isNum,
  location: isStr,
  action: isStr,
  data_transformation: isStr,
}) as (v: unknown) => v is ExecutionStep;

const isDsaCard = shape({
  chapter: isStr,
  pattern_name: isStr,
  start_line: isNum,
  end_line: isNum,
  why_used_here: isStr,
  time_complexity: isStr,
  space_complexity: isStr,
}) as (v: unknown) => v is DSACard;

const isL2 = shape({
  target_id: isStr,
  execution_steps: arrayOf(isExecutionStep),
  upstream_callers: isStrArray,
  downstream_callees: isStrArray,
  side_effects: isStrArray,
  dsa_cards: arrayOf(isDsaCard),
  llm_content_available: isBool,
}) as (v: unknown) => v is L2Explanation;

const isL3Alternative = shape({
  pattern_name: isStr,
  why_not_chosen: isStr,
  when_to_switch: isStr,
}) as (v: unknown) => v is L3Alternative;

const isL3 = shape({
  target_id: isStr,
  topology_pattern: isStr,
  why_this_folder_structure: isStr,
  structural_evidence: isStrArray,
  alternatives: arrayOf(isL3Alternative),
  spec_rationale: isNullableStr,
}) as (v: unknown) => v is L3Explanation;

const isBlastRadius = shape({
  target_id: isStr,
  upstream_callers: isStrArray,
  downstream_callees: isStrArray,
  impact_score: isNum,
}) as (v: unknown) => v is BlastRadius;

/** Envelope: the tier named by `lens` is valid, the other two are exactly null. */
function isEnvelope(v: unknown): v is ExplanationEnvelope {
  if (!isRec(v)) return false;
  if (!isStr(v.repo_id) || !isStr(v.target_id) || !isStr(v.ast_hash) || !isBool(v.cached)) {
    return false;
  }
  const tiers = { L1_SYNTAX: 'l1', L2_FLOW: 'l2', L3_ARCHITECTURE: 'l3' } as const;
  const guards = { l1: isL1, l2: isL2, l3: isL3 } as const;
  if (!isStr(v.lens) || !Object.prototype.hasOwnProperty.call(tiers, v.lens)) return false;
  const active = tiers[v.lens as keyof typeof tiers];
  return (['l1', 'l2', 'l3'] as const).every((key) =>
    key === active ? guards[key](v[key]) : v[key] === null,
  );
}

// -- socratic, vitals ---------------------------------------------------------------

const isSocraticQuestion = shape({
  question_id: isStr,
  target_id: isStr,
  prompt: isStr,
  line_reference: isStr,
  expected_concepts: isStrArray,
}) as (v: unknown) => v is SocraticQuestion;

const isVitals = shape({
  repo_id: isStr,
  study_mode_enabled: isBool,
  total_modules: isNum,
  unaudited_count: isNum,
  dissected_count: isNum,
  mastered_count: isNum,
  stale_count: isNum,
  mastery_percentage: isNum,
  due_for_review: isStrArray,
  file_states: (v) => isRecordOf(v, isStr),
}) as (v: unknown) => v is ComprehensionVitals;

// -- exported validators, one per response type ------------------------------------

export const validateHealth: Validator<HealthResponse> = validator(
  shape({ status: isStr, service: isStr }),
);

export const validateRepoList: Validator<RepoSummary[]> = validator(arrayOf(isRepoSummary));

export const validateIngestResponse: Validator<IngestResponse> = validator(
  shape({
    repo_id: isStr,
    summary: isIngestSummary,
    provenance: isProvenance,
    topology: isTopology,
    truncated: isBool,
    warnings: arrayOf(isIngestWarning),
  }),
);

export const validateSnapshotResponse: Validator<SnapshotResponse> = validator(
  shape({ snapshot: isSnapshot, provenance: isProvenance, topology: isTopology }),
);

export const validateExplainResponse: Validator<ExplainResponse> = validator(
  shape({ envelope: isEnvelope, blast_radius: isBlastRadius }),
);

export const validateVitals: Validator<ComprehensionVitals> = validator(isVitals);

export const validateStudyModeResponse: Validator<StudyModeResponse> = validator(
  shape({ repo_id: isStr, study_mode_enabled: isBool }),
);

export const validateSocraticCheck: Validator<SocraticCheck> = validator(
  shape({
    repo_id: isStr,
    target_id: isStr,
    questions: arrayOf(isSocraticQuestion),
  }),
);

export const validateSocraticVerdict: Validator<SocraticVerdict> = validator(
  shape({
    target_id: isStr,
    passed: isBool,
    score: isNum,
    feedback: isStr,
    new_state: isStr,
    next_review_at: isNullableStr,
  }),
);
