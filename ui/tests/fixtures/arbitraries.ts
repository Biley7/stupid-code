import fc from 'fast-check';
import type {
  FileAnalysis,
  GraphEdge,
  SnapshotResponse,
  SymbolNode,
} from '../../src/api/types';

const word = fc.stringMatching(/^[a-z][a-z0-9_]{0,7}$/);
const text = fc.string({ maxLength: 30 });

const language = fc.constantFrom('python', 'typescript', 'javascript', 'tsx', 'java', 'cobol');
const kind = fc.constantFrom('function', 'method', 'class', 'interface', 'component', 'macro');
const edgeType = fc.constantFrom('imports', 'calls', 'inherits');
const role = fc.constantFrom('domain', 'engines', 'api', 'ui', 'tests', 'other', 'mystery');
const pattern = fc.constantFrom(
  'Hexagonal / Clean Architecture',
  'Layered MVC',
  'Feature-Sliced',
  'Modular Monolith',
  'Flat / Script',
  'Unknown Pattern',
);
const mastery = fc.constantFrom('UNAUDITED', 'DISSECTED', 'MASTERED', 'STALE', 'MYSTERY');

const symbolFor = (filePath: string): fc.Arbitrary<SymbolNode> =>
  fc
    .record({
      qualname: word,
      kind,
      start: fc.integer({ min: 1, max: 200 }),
      len: fc.integer({ min: 0, max: 50 }),
      signature: text,
      is_async: fc.boolean(),
      decorators: fc.array(word, { maxLength: 2 }),
    })
    .map(({ qualname, start, len, ...rest }) => ({
      id: `${filePath}::${qualname}`,
      name: qualname,
      qualname,
      file_path: filePath,
      start_line: start,
      end_line: start + len,
      ast_hash: `h-${filePath}-${qualname}`,
      raw_calls: [],
      ...rest,
    }));

const fileFor = (filePath: string): fc.Arbitrary<FileAnalysis> =>
  fc
    .record({
      language,
      loc: fc.nat({ max: 5000 }),
      symbols: fc.uniqueArray(symbolFor(filePath), { selector: (s) => s.id, maxLength: 4 }),
      parse_errors: fc.array(text, { maxLength: 2 }),
    })
    .map((f) => ({
      file_path: filePath,
      ast_hash: `h-${filePath}`,
      imports: [],
      exports: f.symbols.map((s) => s.name),
      ...f,
    }));

/**
 * Snapshot responses with unique file paths and symbol ids. Edges, vital organs and cycles only
 * reference nodes that exist. Enum-like fields include unknown strings (Requirement 27.5).
 */
export const snapshotResponseArb: fc.Arbitrary<SnapshotResponse> = fc
  .uniqueArray(fc.tuple(fc.array(word, { minLength: 0, maxLength: 2 }), word), {
    selector: ([dirs, name]) => [...dirs, name].join('/'),
    maxLength: 8,
  })
  .map((parts) => parts.map(([dirs, name]) => [...dirs, `${name}.py`].join('/')))
  .chain((paths) =>
    fc.tuple(...paths.map(fileFor)).chain((files) => {
      const nodeIds = files.flatMap((f) => [f.file_path, ...f.symbols.map((s) => s.id)]);
      const node = nodeIds.length > 0 ? fc.constantFrom(...nodeIds) : null;
      const edges: fc.Arbitrary<GraphEdge[]> = node
        ? fc.array(fc.record({ source: node, target: node, edge_type: edgeType }), { maxLength: 12 })
        : fc.constant([]);
      const nodeList = node ? fc.array(node, { maxLength: 4 }) : fc.constant([] as string[]);
      const dirs = [...new Set(paths.map((p) => p.split('/').slice(0, -1).join('/')))];
      return fc.record({
        edges,
        vital_organs: nodeList,
        cycles: node ? fc.array(fc.array(node, { minLength: 2, maxLength: 3 }), { maxLength: 2 }) : fc.constant([]),
        pattern,
        confidence: fc.double({ min: 0, max: 1, noNaN: true }),
        roles: fc.array(role, { minLength: dirs.length, maxLength: dirs.length }),
        has_kiro_specs: fc.boolean(),
        evidence: fc.array(text, { maxLength: 3 }),
        states: fc.array(mastery, { minLength: files.length, maxLength: files.length }),
      }).map((r): SnapshotResponse => {
        const repo_id = 'arb';
        return {
          snapshot: {
            repo_id,
            root_path: '.',
            files,
            edges: r.edges,
            vital_organs: r.vital_organs,
            cycles: r.cycles,
            dsa_signals: [],
          },
          provenance: {
            repo_id,
            has_kiro_specs: r.has_kiro_specs,
            spec_links: {},
            drift_items: [],
            recent_commits: {},
          },
          topology: {
            repo_id,
            detected_pattern: r.pattern,
            confidence: r.confidence,
            directory_roles: Object.fromEntries(dirs.map((d, i) => [d, r.roles[i] ?? 'other'])),
            boundary_metrics: {
              max_depth: 3,
              cross_folder_import_ratio: 0,
              domain_isolation_score: 1,
              entry_point_count: 0,
            },
            evidence: r.evidence,
          },
        };
      });
    }),
  );

/** Per-file mastery states aligned with a snapshot's files. Some files have no tracked symbols and no key. */
export const fileStatesArb = (files: readonly FileAnalysis[]) =>
  fc
    .array(fc.option(mastery, { nil: undefined }), { minLength: files.length, maxLength: files.length })
    .map((states) => {
      const out: Record<string, string> = {};
      files.forEach((f, i) => {
        const s = states[i];
        if (s !== undefined) out[f.file_path] = s;
      });
      return out;
    });
