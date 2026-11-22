import type { BlastRadius, RepoGraphSnapshot } from '../api/types';
import { computeCounters } from './counters';

export type Layer = 'files' | 'symbols';

export interface GraphNodeModel {
  id: string;
  layer: Layer;
  label: string;
  filePath: string;
  kind?: string;
}

export interface GraphEdgeModel {
  id: string;
  source: string;
  target: string;
  edgeType: string;
  circular: boolean;
}

export interface GraphModel {
  nodes: GraphNodeModel[];
  edges: GraphEdgeModel[];
  circularEdgeIds: ReadonlySet<string>;
  outgoing: ReadonlyMap<string, readonly string[]>;
  incoming: ReadonlyMap<string, readonly string[]>;
}

export interface Highlight {
  selected: string | null;
  upstream: ReadonlySet<string>;
  downstream: ReadonlySet<string>;
  blast: ReadonlySet<string>;
  source: 'blast_radius' | 'derived' | 'none';
  impactScore: number | null;
}

const LAYER_EDGE_TYPE: Record<Layer, string> = { files: 'imports', symbols: 'calls' };

/** UTF-16 code-unit order, independent of locale. */
function cmp(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function edgeId(source: string, target: string, edgeType: string): string {
  return JSON.stringify([source, target, edgeType]);
}

function baseName(path: string): string {
  const i = path.lastIndexOf('/');
  return i === -1 ? path : path.slice(i + 1);
}

export function buildGraphModel(snapshot: RepoGraphSnapshot, layer: Layer): GraphModel {
  computeCounters.graph += 1;
  const nodeMap = new Map<string, GraphNodeModel>();
  if (layer === 'files') {
    for (const f of snapshot.files) {
      if (nodeMap.has(f.file_path)) continue;
      nodeMap.set(f.file_path, {
        id: f.file_path,
        layer,
        label: baseName(f.file_path),
        filePath: f.file_path,
      });
    }
  } else {
    for (const f of snapshot.files) {
      for (const s of f.symbols) {
        if (nodeMap.has(s.id)) continue;
        nodeMap.set(s.id, {
          id: s.id,
          layer,
          label: s.qualname,
          filePath: s.file_path,
          kind: s.kind,
        });
      }
    }
  }
  const nodes = [...nodeMap.values()].sort((a, b) => cmp(a.id, b.id));

  // Cycle membership: node id -> indices of cycle entries containing it.
  computeCounters.cycleSet += 1;
  const cycleIndex = new Map<string, number[]>();
  snapshot.cycles.forEach((entry, i) => {
    for (const id of entry) {
      const list = cycleIndex.get(id);
      if (list === undefined) cycleIndex.set(id, [i]);
      else if (list[list.length - 1] !== i) list.push(i);
    }
  });
  const sharesCycle = (a: string, b: string): boolean => {
    const la = cycleIndex.get(a);
    const lb = cycleIndex.get(b);
    if (la === undefined || lb === undefined) return false;
    return la.some((i) => lb.includes(i));
  };

  const wanted = LAYER_EDGE_TYPE[layer];
  const edgeMap = new Map<string, GraphEdgeModel>();
  for (const e of snapshot.edges) {
    if (e.edge_type !== wanted) continue;
    if (!nodeMap.has(e.source) || !nodeMap.has(e.target)) continue;
    const id = edgeId(e.source, e.target, e.edge_type);
    if (edgeMap.has(id)) continue;
    edgeMap.set(id, {
      id,
      source: e.source,
      target: e.target,
      edgeType: e.edge_type,
      circular: sharesCycle(e.source, e.target),
    });
  }
  const edges = [...edgeMap.values()].sort(
    (a, b) => cmp(a.source, b.source) || cmp(a.target, b.target) || cmp(a.edgeType, b.edgeType),
  );

  const circularEdgeIds = new Set<string>();
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  for (const e of edges) {
    if (e.circular) circularEdgeIds.add(e.id);
    const out = outgoing.get(e.source);
    if (out === undefined) outgoing.set(e.source, [e.target]);
    else out.push(e.target);
    const inc = incoming.get(e.target);
    if (inc === undefined) incoming.set(e.target, [e.source]);
    else inc.push(e.source);
  }

  return { nodes, edges, circularEdgeIds, outgoing, incoming };
}

const EMPTY_SET: ReadonlySet<string> = new Set<string>();

/**
 * One-hop neighbourhood of the selected node, plus blast-radius ids when an explain
 * result is supplied. Ids that are not nodes of the layer are skipped.
 */
export function highlightFor(
  model: GraphModel,
  selectedId: string | null,
  blast?: BlastRadius,
): Highlight {
  if (selectedId === null || !model.nodes.some((n) => n.id === selectedId)) {
    return {
      selected: null,
      upstream: EMPTY_SET,
      downstream: EMPTY_SET,
      blast: EMPTY_SET,
      source: 'none',
      impactScore: null,
    };
  }
  const upstream = new Set(model.incoming.get(selectedId) ?? []);
  const downstream = new Set(model.outgoing.get(selectedId) ?? []);

  if (blast === undefined) {
    return {
      selected: selectedId,
      upstream,
      downstream,
      blast: EMPTY_SET,
      source: 'derived',
      impactScore: null,
    };
  }
  const nodeIds = new Set(model.nodes.map((n) => n.id));
  const blastIds = new Set<string>();
  for (const id of [...blast.upstream_callers, ...blast.downstream_callees]) {
    if (nodeIds.has(id)) blastIds.add(id);
  }
  return {
    selected: selectedId,
    upstream,
    downstream,
    blast: blastIds,
    source: 'blast_radius',
    impactScore: blast.impact_score,
  };
}
