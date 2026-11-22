// Skeletal X-Ray graph (Requirements 15, 16, 10, 11, 29.7, 29.8).
// Reads the snapshot, vitals and cached explain data from the stores. Never calls
// the backend for blast radius; the snapshot retry reuses useSnapshot.reload.
import '@xyflow/react/dist/style.css';
import {
  MarkerType,
  ReactFlow,
  type Edge,
  type EdgeTypes,
  type NodeMouseHandler,
  type NodeTypes,
} from '@xyflow/react';
import { useCallback, useMemo, useRef, useState } from 'react';
import type { BlastRadius, FileAnalysis, Lens, RepoGraphSnapshot } from '../../api/types';
import { computeCounters } from '../../core/counters';
import { buildGraphModel, highlightFor, type GraphModel, type Highlight, type Layer } from '../../core/graph';
import { layoutGraph, NODE_HEIGHT, NODE_WIDTH, type LayoutResult } from '../../core/layout';
import {
  fileMasteryView,
  isShrouded,
  type MasteryPresentation,
  type VisualMode,
  type VitalsRemote,
} from '../../core/mastery';
import { presentError } from '../../core/present';
import { buildSnapshotIndex, resolveTarget } from '../../core/snapshotIndex';
import { useSnapshot } from '../../data/useSnapshot';
import { explainKey, type DataState } from '../../state/dataReducer';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';
import { CircularEdge, type CircularFlowEdge } from './CircularEdge';
import { FileNode, type GraphFlowNode, type GraphNodeData } from './FileNode';
import { SymbolNode } from './SymbolNode';

const VISIBLE_ONLY_THRESHOLD = 300;
const LAYERS: readonly { id: Layer; label: string }[] = [
  { id: 'files', label: 'Files' },
  { id: 'symbols', label: 'Symbols' },
];
const nodeTypes: NodeTypes = { file: FileNode, symbol: SymbolNode };
const edgeTypes: EdgeTypes = { circular: CircularEdge };

// Model and layout depend only on the snapshot and the layer (Requirements 15.7, 29.7).
interface LayerBuild {
  model: GraphModel;
  layout: LayoutResult;
}
const layerCache = new WeakMap<RepoGraphSnapshot, Partial<Record<Layer, LayerBuild>>>();
function layerBuild(snapshot: RepoGraphSnapshot, layer: Layer): LayerBuild {
  let perLayer = layerCache.get(snapshot);
  if (perLayer === undefined) {
    perLayer = {};
    layerCache.set(snapshot, perLayer);
  }
  let hit = perLayer[layer];
  if (hit === undefined) {
    const model = buildGraphModel(snapshot, layer);
    hit = { model, layout: layoutGraph(model) };
    perLayer[layer] = hit;
  }
  return hit;
}

/** File path to mastery presentation, rebuilt only when the vitals value changes. */
function buildMasteryLookup(files: readonly FileAnalysis[], vitals: VitalsRemote) {
  computeCounters.masteryLookup += 1;
  const lookup = new Map<string, MasteryPresentation>();
  for (const f of files) lookup.set(f.file_path, fileMasteryView(vitals, f.file_path));
  return lookup;
}

const BLAST_LENSES: readonly Lens[] = ['L2_FLOW', 'L1_SYNTAX', 'L3_ARCHITECTURE'];

/** Blast radius of the first ready explain entry for the selected symbol. */
function selectBlastRadius(
  data: DataState,
  repoId: string | null,
  symbol: string | null,
): BlastRadius | undefined {
  if (repoId === null || symbol === null) return undefined;
  for (const lens of BLAST_LENSES) {
    const entry = data.explain[explainKey(repoId, symbol, lens)];
    if (entry !== undefined && entry.status === 'ready') return entry.data.blast_radius;
  }
  return undefined;
}

function sameData(a: GraphNodeData, b: GraphNodeData): boolean {
  return (
    a.label === b.label &&
    a.kind === b.kind &&
    a.mastery === b.mastery &&
    a.fileLevel === b.fileLevel &&
    a.shroud === b.shroud &&
    a.selected === b.selected &&
    a.upstream === b.upstream &&
    a.downstream === b.downstream &&
    a.blast === b.blast &&
    a.dimmed === b.dimmed &&
    a.onSelect === b.onSelect &&
    a.onClear === b.onClear
  );
}

interface GraphCanvasProps {
  snapshot: RepoGraphSnapshot;
  layer: Layer;
  model: GraphModel;
  layout: LayoutResult;
  mastery: ReadonlyMap<string, MasteryPresentation>;
  highlight: Highlight;
  visualMode: VisualMode;
  onSelect: (id: string) => void;
  onClear: () => void;
}

function GraphCanvas({
  layer,
  model,
  layout,
  mastery,
  highlight,
  visualMode,
  onSelect,
  onClear,
}: GraphCanvasProps) {
  // Previous data objects, reused when no derived field changed (Requirement 29.8).
  const dataCache = useRef(new Map<string, GraphNodeData>());
  const hasSelection = highlight.selected !== null;
  const unknown = useMemo(() => fileMasteryView({ status: 'idle' }, ''), []);

  const nodes = useMemo<GraphFlowNode[]>(() => {
    const previous = dataCache.current;
    const next = new Map<string, GraphNodeData>();
    const out = model.nodes.map((n): GraphFlowNode => {
      const m = mastery.get(n.filePath) ?? unknown;
      const isSelected = highlight.selected === n.id;
      const up = highlight.upstream.has(n.id);
      const down = highlight.downstream.has(n.id);
      const blast = highlight.blast.has(n.id);
      const fresh: GraphNodeData = {
        id: n.id,
        label: n.label,
        kind: n.kind,
        mastery: m,
        fileLevel: layer === 'symbols',
        shroud: isShrouded(m, visualMode),
        selected: isSelected,
        upstream: up,
        downstream: down,
        blast,
        dimmed: hasSelection && !isSelected && !up && !down && !blast,
        onSelect,
        onClear,
      };
      const old = previous.get(n.id);
      const data = old !== undefined && sameData(old, fresh) ? old : fresh;
      next.set(n.id, data);
      return {
        id: n.id,
        type: layer === 'files' ? 'file' : 'symbol',
        position: layout.positions.get(n.id) ?? { x: 0, y: 0 },
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        data,
        draggable: false,
        connectable: false,
        focusable: false,
      };
    });
    dataCache.current = next;
    return out;
  }, [model, layout, mastery, unknown, highlight, visualMode, layer, hasSelection, onSelect, onClear]);

  const edges = useMemo<(Edge | CircularFlowEdge)[]>(
    () =>
      model.edges.map((e) => {
        const incident = highlight.selected === e.source || highlight.selected === e.target;
        const dimmed = hasSelection && !incident;
        const marker = { type: MarkerType.ArrowClosed, width: 14, height: 14 };
        if (e.circular) {
          return {
            id: e.id,
            source: e.source,
            target: e.target,
            type: 'circular',
            data: { dimmed },
            markerEnd: { ...marker, color: 'var(--color-crimson)' },
            focusable: false,
          } satisfies CircularFlowEdge;
        }
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: 'smoothstep',
          markerEnd: { ...marker, color: incident ? 'var(--color-bone)' : 'var(--color-muted)' },
          style: {
            stroke: incident ? 'var(--color-bone)' : 'var(--color-muted)',
            strokeWidth: incident ? 1.5 : 1,
            opacity: dimmed ? 0.35 : 1,
          },
          focusable: false,
        } satisfies Edge;
      }),
    [model, highlight.selected, hasSelection],
  );

  const onNodeClick = useCallback<NodeMouseHandler>((_event, node) => onSelect(node.id), [onSelect]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onNodeClick}
      onPaneClick={onClear}
      nodesDraggable={false}
      nodesConnectable={false}
      nodesFocusable={false}
      edgesFocusable={false}
      elementsSelectable={false}
      onlyRenderVisibleElements={model.nodes.length > VISIBLE_ONLY_THRESHOLD}
      minZoom={0.05}
      fitView
      style={{ background: 'transparent' }}
    />
  );
}

export function GraphView() {
  const data = useDataState();
  const { repoId, symbol, node, visualMode } = useAppState();
  const dispatch = useAppDispatch();
  const { snapshot, reload } = useSnapshot({ autoload: false });
  const [layer, setLayer] = useState<Layer>('files');

  const snap = snapshot.status === 'ready' ? snapshot.data.snapshot : null;
  const vitals = data.vitals;

  const build = useMemo(() => (snap === null ? null : layerBuild(snap, layer)), [snap, layer]);
  const mastery = useMemo(
    () => (snap === null ? new Map<string, MasteryPresentation>() : buildMasteryLookup(snap.files, vitals)),
    [snap, vitals],
  );
  const index = useMemo(() => (snap === null ? null : buildSnapshotIndex(snap)), [snap]);

  const blast = selectBlastRadius(data, repoId, symbol);
  const selectedId = build !== null && node !== null ? node : null;
  const highlight = useMemo(
    () =>
      build === null
        ? highlightFor({ nodes: [], edges: [], circularEdgeIds: new Set(), outgoing: new Map(), incoming: new Map() }, null)
        : highlightFor(build.model, selectedId, selectedId !== null && selectedId === symbol ? blast : undefined),
    [build, selectedId, symbol, blast],
  );

  const onSelect = useCallback(
    (id: string) => {
      if (index === null) return;
      const target = resolveTarget(index, id);
      if (target !== null) dispatch({ type: 'select-target', target });
    },
    [index, dispatch],
  );
  const onClear = useCallback(() => dispatch({ type: 'node-cleared' }), [dispatch]);

  const changeLayer = (next: Layer) => {
    if (next === layer || snap === null) return;
    const nextBuild = layerBuild(snap, next);
    const keep = node !== null && nextBuild.model.nodes.some((n) => n.id === node);
    setLayer(next);
    dispatch({ type: 'layer-changed', keepNode: keep });
  };

  if (repoId === null) return <StateBlock variant="empty" label="No repository selected." />;
  if (snapshot.status === 'idle' || snapshot.status === 'loading') {
    return <StateBlock variant="loading" label="Loading graph…" />;
  }
  if (snapshot.status === 'error') {
    const presented = presentError(snapshot.error, 'generic');
    if (presented === null) return null;
    return (
      <StateBlock
        variant="error"
        message={presented.message}
        onRetry={() => void reload()}
        retryAfterSeconds={presented.retryAfterSeconds}
      />
    );
  }
  if (build === null) return null;

  const layerLabel = layer === 'files' ? 'Files' : 'Symbols';
  const inCount = selectedId === null ? 0 : (build.model.incoming.get(selectedId)?.length ?? 0);
  const outCount = selectedId === null ? 0 : (build.model.outgoing.get(selectedId)?.length ?? 0);
  const textAlternative =
    selectedId === null
      ? 'Nothing is selected.'
      : `Selected ${selectedId}. Incoming edges: ${inCount}. Outgoing edges: ${outCount}.` +
        (inCount === 0 && outCount === 0 ? ' No upstream or downstream nodes.' : '');

  return (
    <section aria-label="Dependency graph" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-3 border-b border-hairline bg-surface px-2 py-1">
        <div role="group" aria-label="Graph layer" className="flex gap-1">
          {LAYERS.map((l) => (
            <button
              key={l.id}
              type="button"
              aria-pressed={layer === l.id}
              onClick={() => changeLayer(l.id)}
              className={`border px-2 py-0.5 font-mono text-xs ${
                layer === l.id ? 'border-bone text-bone' : 'border-hairline text-muted'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        {highlight.selected !== null ? (
          <p className="m-0 font-mono text-xs text-muted">
            {highlight.source === 'blast_radius'
              ? 'blast radius from blast-radius result'
              : 'highlighting derived from snapshot'}
            {highlight.source === 'blast_radius' && highlight.impactScore !== null
              ? ` | impact_score ${highlight.impactScore} (from blast-radius result)`
              : ''}
          </p>
        ) : null}
      </div>
      <p role="status" className="sr-only">
        <PlainText text={textAlternative} />
      </p>
      {build.model.nodes.length === 0 ? (
        <StateBlock variant="empty" label={`The ${layerLabel} layer has no nodes.`} />
      ) : (
        <div className="canvas-grid min-h-0 flex-1" data-layer={layer}>
          <GraphCanvas
            key={`${layer}`}
            snapshot={snap as RepoGraphSnapshot}
            layer={layer}
            model={build.model}
            layout={build.layout}
            mastery={mastery}
            highlight={highlight}
            visualMode={visualMode}
            onSelect={onSelect}
            onClear={onClear}
          />
        </div>
      )}
    </section>
  );
}
