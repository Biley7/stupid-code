import type {
  ComprehensionVitals,
  ExplainResponse,
  FileAnalysis,
  Lens,
  RepoSummary,
  SnapshotResponse,
  SocraticCheck,
  SocraticVerdict,
  SymbolNode,
} from '../../src/api/types';
import { deepMerge, type DeepPartial } from './deepMerge';

export type { DeepPartial } from './deepMerge';

/** Backend text with HTML and Markdown markers, to prove plain-text rendering (Requirement 28.14). */
export const HOSTILE_TEXT = '<b>bold</b> <script>alert(1)</script> **strong** `code` [link](http://x) # heading';

export function makeRepos(): RepoSummary[] {
  return [
    { repo_id: 'alpha', file_count: 2, symbol_count: 3, study_mode_enabled: false },
    { repo_id: 'beta/with space', file_count: 0, symbol_count: 0, study_mode_enabled: true },
  ];
}

function symbol(file: string, qualname: string, kind: string, start: number, end: number): SymbolNode {
  return {
    id: `${file}::${qualname}`,
    name: qualname.split('.').pop() ?? qualname,
    qualname,
    kind,
    file_path: file,
    start_line: start,
    end_line: end,
    signature: `def ${qualname}()`,
    ast_hash: `hash-${file}-${qualname}`,
    decorators: [],
    is_async: false,
    raw_calls: [],
  };
}

function file(path: string, symbols: SymbolNode[], loc: number): FileAnalysis {
  return {
    file_path: path,
    language: 'python',
    loc,
    ast_hash: `hash-${path}`,
    imports: [],
    exports: symbols.map((s) => s.name),
    symbols,
    parse_errors: [],
  };
}

export function makeSnapshotResponse(overrides?: DeepPartial<SnapshotResponse>): SnapshotResponse {
  const base: SnapshotResponse = {
    snapshot: {
      repo_id: 'alpha',
      root_path: '.',
      files: [
        file('backend/domain/models.py', [symbol('backend/domain/models.py', 'Model', 'class', 1, 20)], 20),
        file(
          'backend/engines/graph.py',
          [
            symbol('backend/engines/graph.py', 'build', 'function', 3, 30),
            symbol('backend/engines/graph.py', 'Graph.walk', 'method', 32, 50),
          ],
          50,
        ),
      ],
      edges: [
        { source: 'backend/engines/graph.py', target: 'backend/domain/models.py', edge_type: 'imports' },
        {
          source: 'backend/engines/graph.py::build',
          target: 'backend/domain/models.py::Model',
          edge_type: 'calls',
        },
      ],
      vital_organs: ['backend/domain/models.py'],
      cycles: [],
      dsa_signals: [
        {
          symbol_id: 'backend/engines/graph.py::Graph.walk',
          file_path: 'backend/engines/graph.py',
          start_line: 32,
          end_line: 50,
          chapter: 'Graphs & Trees',
          pattern_name: 'Breadth-first search',
          confidence: 0.8,
          evidence: ['uses collections.deque', 'visited set'],
        },
      ],
    },
    provenance: {
      repo_id: 'alpha',
      has_kiro_specs: true,
      spec_links: {
        'backend/engines/graph.py': [
          {
            spec_name: '01-core',
            source_file: 'design.md',
            section_title: 'Graph engine',
            excerpt: 'The graph engine builds edges.',
            confidence: 0.7,
          },
        ],
      },
      drift_items: [
        { drift_type: 'UNSPECIFIED_CODE', target: 'backend/engines/graph.py', details: 'No spec mentions this file.' },
      ],
      recent_commits: { 'backend/engines/graph.py': ['abc1234|Add graph engine'] },
    },
    topology: {
      repo_id: 'alpha',
      detected_pattern: 'Hexagonal / Clean Architecture',
      confidence: 0.9,
      directory_roles: { 'backend/domain': 'domain', 'backend/engines': 'engines' },
      boundary_metrics: {
        max_depth: 3,
        cross_folder_import_ratio: 0.25,
        domain_isolation_score: 1,
        entry_point_count: 1,
      },
      evidence: ['domain imports nothing from engines'],
    },
  };
  return deepMerge(base, overrides);
}

export function makeVitals(overrides?: DeepPartial<ComprehensionVitals>): ComprehensionVitals {
  const base: ComprehensionVitals = {
    repo_id: 'alpha',
    study_mode_enabled: false,
    total_modules: 4,
    unaudited_count: 1,
    dissected_count: 1,
    mastered_count: 1,
    stale_count: 1,
    mastery_percentage: 25,
    due_for_review: ['backend/engines/graph.py::build'],
    file_states: {
      'backend/domain/models.py': 'MASTERED',
      'backend/engines/graph.py': 'DISSECTED',
    },
  };
  return deepMerge(base, overrides);
}

type TierOverrides<L extends Lens> = L extends 'L1_SYNTAX'
  ? DeepPartial<Extract<ExplainResponse['envelope'], { lens: 'L1_SYNTAX' }>['l1']>
  : L extends 'L2_FLOW'
    ? DeepPartial<Extract<ExplainResponse['envelope'], { lens: 'L2_FLOW' }>['l2']>
    : DeepPartial<Extract<ExplainResponse['envelope'], { lens: 'L3_ARCHITECTURE' }>['l3']>;

/** Builds an ExplainResponse whose envelope has only the tier matching `lens` non-null. */
export function makeExplain<L extends Lens>(
  lens: L,
  overrides?: TierOverrides<L>,
  target = 'backend/engines/graph.py::build',
): ExplainResponse {
  const common = { repo_id: 'alpha', target_id: target, ast_hash: 'hash-build', cached: false };
  const blast_radius = {
    target_id: target,
    upstream_callers: ['backend/api/routes.py::handler'],
    downstream_callees: ['backend/domain/models.py::Model'],
    impact_score: 0.5,
  };
  if (lens === 'L1_SYNTAX') {
    const l1 = deepMerge(
      {
        target_id: target,
        language: 'python',
        summary: HOSTILE_TEXT,
        annotations: [
          {
            line_start: 3,
            line_end: 5,
            construct: 'function definition',
            explanation: 'Defines build.',
            what_if_removed: 'Nothing could build the graph.',
          },
        ],
        key_takeaway: 'build is the entry point.',
      },
      overrides as never,
    );
    return { envelope: { ...common, lens: 'L1_SYNTAX', l1, l2: null, l3: null }, blast_radius };
  }
  if (lens === 'L2_FLOW') {
    const l2 = deepMerge(
      {
        target_id: target,
        execution_steps: [
          { step_number: 1, location: 'line 4', action: 'Create the graph', data_transformation: 'files to nodes' },
        ],
        upstream_callers: ['backend/api/routes.py::handler'],
        downstream_callees: ['backend/domain/models.py::Model'],
        side_effects: [],
        dsa_cards: [],
        llm_content_available: true,
      },
      overrides as never,
    );
    return { envelope: { ...common, lens: 'L2_FLOW', l1: null, l2, l3: null }, blast_radius };
  }
  const l3 = deepMerge(
    {
      target_id: target,
      topology_pattern: 'Hexagonal / Clean Architecture',
      why_this_folder_structure: 'Domain is separated from engines.',
      structural_evidence: ['backend/domain has no outward imports'],
      alternatives: [
        { pattern_name: 'Layered MVC', why_not_chosen: 'No views.', when_to_switch: 'If a UI is added.' },
      ],
      spec_rationale: null,
    },
    overrides as never,
  );
  return { envelope: { ...common, lens: 'L3_ARCHITECTURE', l1: null, l2: null, l3 }, blast_radius };
}

export function makeCheck(overrides?: DeepPartial<SocraticCheck>): SocraticCheck {
  const target = 'backend/engines/graph.py::build';
  const base: SocraticCheck = {
    repo_id: 'alpha',
    target_id: target,
    questions: [
      {
        question_id: 'q1',
        target_id: target,
        prompt: 'What does line 4 return?',
        line_reference: 'L4',
        expected_concepts: [],
      },
      {
        question_id: 'q2',
        target_id: target,
        prompt: 'Why is the set used?',
        line_reference: 'L7-L9',
        expected_concepts: [],
      },
    ],
  };
  return deepMerge(base, overrides);
}

export function makeVerdict(overrides?: DeepPartial<SocraticVerdict>): SocraticVerdict {
  const base: SocraticVerdict = {
    target_id: 'backend/engines/graph.py::build',
    passed: true,
    score: 0.9,
    feedback: 'Correct.',
    new_state: 'MASTERED',
    next_review_at: '2025-01-01T00:00:00Z',
  };
  return deepMerge(base, overrides);
}
