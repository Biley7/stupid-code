import dagre from 'dagre';
import { computeCounters } from './counters';
import type { GraphModel } from './graph';

export const NODE_WIDTH = 180;
export const NODE_HEIGHT = 44;

export interface LayoutResult {
  /** Top-left integer coordinates per node id. */
  positions: ReadonlyMap<string, { x: number; y: number }>;
  width: number;
  height: number;
}

/** UTF-16 code-unit order, independent of locale. */
function cmp(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

const cache = new WeakMap<GraphModel, LayoutResult>();

/**
 * Deterministic dagre layout. Nodes and edges are sorted before insertion so the
 * result does not depend on input order. Never reads the DOM. Memoized per model.
 */
export function layoutGraph(model: GraphModel): LayoutResult {
  const hit = cache.get(model);
  if (hit !== undefined) return hit;
  computeCounters.layout += 1;

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 72, marginx: 16, marginy: 16 });
  g.setDefaultEdgeLabel(() => ({}));

  const ids = model.nodes.map((n) => n.id).sort(cmp);
  for (const id of ids) g.setNode(id, { width: NODE_WIDTH, height: NODE_HEIGHT });

  const edges = model.edges
    .map((e) => ({ source: e.source, target: e.target }))
    .sort((a, b) => cmp(a.source, b.source) || cmp(a.target, b.target));
  for (const e of edges) g.setEdge(e.source, e.target);

  dagre.layout(g);

  const positions = new Map<string, { x: number; y: number }>();
  let maxRight = 0;
  let maxBottom = 0;
  for (const id of ids) {
    const n = g.node(id);
    const x = Math.max(0, Math.round(n.x - NODE_WIDTH / 2));
    const y = Math.max(0, Math.round(n.y - NODE_HEIGHT / 2));
    positions.set(id, { x, y });
    maxRight = Math.max(maxRight, x + NODE_WIDTH);
    maxBottom = Math.max(maxBottom, y + NODE_HEIGHT);
  }

  const graphLabel = g.graph();
  const width = Math.ceil(Math.max(graphLabel.width ?? 0, maxRight));
  const height = Math.ceil(Math.max(graphLabel.height ?? 0, maxBottom));

  const result: LayoutResult = { positions, width, height };
  cache.set(model, result);
  return result;
}
