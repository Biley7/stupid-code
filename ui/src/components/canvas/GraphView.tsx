// Skeletal X-Ray graph (Requirements 15, 16, 10, 11, 29.7, 29.8).
// Reads the snapshot, vitals and cached explain data from the stores. Never calls
// the backend for blast radius; the snapshot retry reuses useSnapshot.reload.
import '@xyflow/react/dist/style.css';
import {
  Controls,
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
import {
  buildGraphModel,
  highlightFor,
  scopeModelToFile,
  type GraphModel,
  type Highlight,
  type Layer,
  type ScopedModel,
} from '../../core/graph';
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

// The full model depends only on the snapshot and the layer (Requirements 15.7, 29.7).
// Layout runs on the model that is displayed: the whole Files graph, or the scoped
// Symbols graph, so a repository with thousands of symbols is never laid out at once.
const modelCache = new WeakMap<RepoGraphSnapshot, Partial<Record<Layer, GraphModel>>>();
function layerModel(snapshot: RepoGraphSnapshot, layer: Layer): GraphModel {
  let perLayer = modelCache.get(snapshot);
  if (perLayer === undefined) {
    perLayer = {};
    modelCache.set(snapshot, perLayer);
  }
  let hit = perLayer[layer];
  if (hit === undefined) {
    hit = buildGraphModel(snapshot, layer);
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

  const autopsy = visualMode === 'Autopsy';
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
        // Blast Radius edges of the selected node are lit; unrelated edges recede.
        const lit = incident ? (autopsy ? 'var(--color-signal)' : 'var(--color-bone)') : 'var(--color-muted)';
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: 'smoothstep',
          markerEnd: { ...marker, color: lit },
          style: {
            stroke: lit,
            strokeWidth: incident ? 2 : 1,
            opacity: dimmed ? (autopsy ? 0.12 : 0.35) : 1,
          },
          zIndex: incident ? 10 : 0,
          focusable: false,
        } satisfies Edge;
      }),
    [model, highlight.selected, hasSelection, autopsy],
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
      fitViewOptions={{ padding: 0.2, maxZoom: 1.25 }}
      style={{ background: 'transparent' }}
    >
      <Controls showInteractive={false} position="bottom-left" fitViewOptions={{ padding: 0.2, maxZoom: 1.25 }} />
    </ReactFlow>
  );
}

const EMPTY_MODEL: GraphModel = {
  nodes: [],
  edges: [],
  circularEdgeIds: new Set(),
  outgoing: new Map(),
  incoming: new Map(),
};
const NO_IDS: readonly string[] = [];

/** Keeps the previous scope object while the kept node ids are unchanged, so layout stays memoized. */
function useStableScope(next: ScopedModel | null): ScopedModel | null {
  const ref = useRef<ScopedModel | null>(null);
  const prev = ref.current;
  if (
    prev !== null &&
    next !== null &&
    prev.total === next.total &&
    prev.truncated === next.truncated &&
    prev.model.nodes.length === next.model.nodes.length &&
    prev.model.edges.length === next.model.edges.length &&
    prev.model.nodes.every((n, i) => n.id === next.model.nodes[i]?.id)
  ) {
    return prev;
  }
  ref.current = next;
  return next;
}

export function GraphView() {
  const data = useDataState();
  const { repoId, file, symbol, node, visualMode } = useAppState();
  const dispatch = useAppDispatch();
  const { snapshot, reload } = useSnapshot({ autoload: false });
  const [layer, setLayer] = useState<Layer>('files');
  const snap = snapshot.status === 'ready' ? snapshot.data.snapshot : null;
  const vitals = data.vitals;
  const fullModel = useMemo(() => (snap === null ? null : layerModel(snap, layer)), [snap, layer]);
  const mastery = useMemo(
    () => (snap === null ? new Map<string, MasteryPresentation>() : buildMasteryLookup(snap.files, vitals)),
    [snap, vitals],
  );
  const index = useMemo(() => (snap === null ? null : buildSnapshotIndex(snap)), [snap]);
  const blast = selectBlastRadius(data, repoId, symbol);
  // Symbols layer: only the selected file's symbols and their 1-hop neighbours are drawn.
  const blastIds = useMemo(
    () => (blast === undefined ? NO_IDS : [...blast.upstream_callers, ...blast.downstream_callees]),
    [blast],
  );
  const scopedNext = useMemo(
    () =>
      layer === 'symbols' && fullModel !== null && file !== null
        ? scopeModelToFile(fullModel, file, blastIds)
        : null,
    [layer, fullModel, file, blastIds],
  );
  const scoped = useStableScope(scopedNext);
  const needsFile = layer === 'symbols' && file === null;
  const model: GraphModel | null =
    fullModel === null ? null : layer === 'symbols' ? (scoped?.model ?? EMPTY_MODEL) : fullModel;
  const layout = useMemo(() => (model === null ? null : layoutGraph(model)), [model]);
  const selectedId = model !== null && node !== null ? node : null;
  const highlight = useMemo(
    () =>
      model === null
        ? highlightFor(EMPTY_MODEL, null)
        : highlightFor(model, selectedId, selectedId !== null && selectedId === symbol ? blast : undefined),
    [model, selectedId, symbol, blast],
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
    const nextModel = layerModel(snap, next);
    const keep = node !== null && nextModel.nodes.some((n) => n.id === node);
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
  if (fullModel === null || model === null || layout === null) return null;
  const layerLabel = layer === 'files' ? 'Files' : 'Symbols';
  const inCount = selectedId === null ? 0 : (model.incoming.get(selectedId)?.length ?? 0);
  const outCount = selectedId === null ? 0 : (model.outgoing.get(selectedId)?.length ?? 0);
  const textAlternative =
    selectedId === null
      ? 'Nothing is selected.'
      : `Selected ${selectedId}. Incoming edges: ${inCount}. Outgoing edges: ${outCount}.` +
        (inCount === 0 && outCount === 0 ? ' No upstream or downstream nodes.' : '');
  const number = new Intl.NumberFormat('en-US');
  // Remount (and so refit the viewport) when the repository, layer, or scoped file changes.
  const canvasKey = `${repoId}|${layer}|${layer === 'symbols' ? (file ?? '') : ''}`;
  return (
    <section aria-label="Dependency graph" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-hairline bg-surface px-2 py-1">
        <div role="group" aria-label="Graph layer" className="flex gap-1">
          {LAYERS.map((l) => (
            <button
              key={l.id}
              type="button"
              aria-pressed={layer === l.id}
              onClick={() => changeLayer(l.id)}
              className={`border px-2.5 py-0.5 text-xs font-medium ${
                layer === l.id ? 'border-bone bg-obsidian text-bone' : 'border-hairline text-muted hover:text-bone'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        {layer === 'symbols' && scoped !== null ? (
          <span
            data-testid="scope-badge"
            title="The Symbols graph shows the selected file's symbols and their direct callers and callees."
            className="border border-hairline px-1.5 py-0.5 text-[11px] tabular-nums text-muted"
          >
            Scoped: {number.format(scoped.shown)} of {number.format(scoped.total)} symbols
            {scoped.truncated ? ' (capped)' : ''}
          </span>
        ) : null}
        {highlight.selected !== null ? (
          <p className="m-0 min-w-0 text-xs text-muted">
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
      {needsFile ? (
        <StateBlock
          variant="empty"
          label={`Select a file to scope the Symbols graph (${number.format(fullModel.nodes.length)} symbols in this repository).`}
        />
      ) : model.nodes.length === 0 ? (
        <StateBlock variant="empty" label={`The ${layerLabel} layer has no nodes.`} />
      ) : (
        <div className="canvas-grid min-h-0 flex-1" data-layer={layer}>
          <GraphCanvas
            key={canvasKey}
            layer={layer}
            model={model}
            layout={layout}
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
