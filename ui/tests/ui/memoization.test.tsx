import { act, render, screen, waitFor } from '@testing-library/react';
import type { Dispatch } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { FileAnalysis, SnapshotResponse, SymbolNode } from '../../src/api/types';
import { ApiProvider } from '../../src/api/context';
import { GraphView } from '../../src/components/canvas/GraphView';
import { FileTree } from '../../src/components/rail/FileTree';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { computeCounters, resetComputeCounters } from '../../src/core/counters';
import type { AppAction } from '../../src/state/appReducer';
import { StoreProvider, useAppDispatch, useDataState } from '../../src/state/store';
import { makeRepos, makeSnapshotResponse, makeVitals } from '../fixtures/builders';
import { installFetchMock, type FetchMock } from '../helpers/mockFetch';

// Record the props GraphView passes to ReactFlow; jsdom has no layout, so the DOM cannot show virtualization.
const flowProps = vi.hoisted(() => ({ calls: [] as Record<string, unknown>[] }));
vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  return {
    ...actual,
    ReactFlow: (props: Record<string, unknown>) => {
      flowProps.calls.push(props);
      return <div data-testid="flow" data-nodes={(props.nodes as unknown[]).length} />;
    },
  };
});

let mock: FetchMock | null = null;
afterEach(() => {
  mock?.restore();
  mock = null;
  flowProps.calls.length = 0;
});

const FILE_COUNT = 320;
const pathOf = (i: number) => `pkg${i % 8}/mod${i}.py`;

/** Deterministic 320-file snapshot with two symbols per file, a chain of imports, and one cycle. */
function bigSnapshot(): SnapshotResponse {
  const base = makeSnapshotResponse();
  const files: FileAnalysis[] = [];
  for (let i = 0; i < FILE_COUNT; i++) {
    const path = pathOf(i);
    const symbols: SymbolNode[] = [0, 1].map((k) => ({
      id: `${path}::fn${k}`,
      name: `fn${k}`,
      qualname: `fn${k}`,
      kind: 'function',
      file_path: path,
      start_line: 1 + k * 10,
      end_line: 9 + k * 10,
      signature: `def fn${k}()`,
      ast_hash: `h-${i}-${k}`,
      decorators: [],
      is_async: false,
      raw_calls: [],
    }));
    files.push({
      file_path: path,
      language: 'python',
      loc: 20,
      ast_hash: `h-${i}`,
      imports: [],
      exports: ['fn0', 'fn1'],
      symbols,
      parse_errors: [],
    });
  }
  const edges = files.slice(1).map((f, i) => ({
    source: files[i]!.file_path,
    target: f.file_path,
    edge_type: 'imports',
  }));
  edges.push({ source: pathOf(1), target: pathOf(0), edge_type: 'imports' });
  return {
    ...base,
    snapshot: {
      ...base.snapshot,
      files,
      edges,
      vital_organs: [],
      cycles: [[pathOf(0), pathOf(1)]],
      dsa_signals: [],
    },
    topology: { ...base.topology!, directory_roles: {} },
  } as SnapshotResponse;
}

let dispatch: Dispatch<AppAction> | null = null;
let vitalsReady = false;
function Driver() {
  dispatch = useAppDispatch();
  vitalsReady = useDataState().vitals.status === 'ready';
  return null;
}

describe('memoization with a 300+ node snapshot (test case 18)', () => {
  it('recomputes no memoized structure on selection changes and enables onlyRenderVisibleElements', async () => {
    const snapshot = bigSnapshot();
    const vitals = makeVitals({ file_states: { [pathOf(0)]: 'MASTERED', [pathOf(1)]: 'DISSECTED' } });
    mock = installFetchMock([
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
      { method: 'GET', path: '/api/repos/alpha/snapshot', respond: () => ({ json: snapshot }) },
      { method: 'GET', path: '/api/repos/alpha/vitals', respond: () => ({ json: vitals }) },
    ]);
    resetComputeCounters();
    flowProps.calls.length = 0;

    render(
      <ApiProvider>
        <StoreProvider>
          <DataLoader />
          <Driver />
          <FileTree />
          <GraphView />
        </StoreProvider>
      </ApiProvider>,
    );
    act(() => dispatch!({ type: 'repo-selected', repoId: 'alpha' }));

    await screen.findByRole('tree', { name: 'Repository file tree' });
    const flow = await screen.findByTestId('flow');
    expect(flow).toHaveAttribute('data-nodes', String(FILE_COUNT));
    await waitFor(() => expect(vitalsReady).toBe(true));
    // Let the vitals-driven mastery lookup settle before taking the baseline.
    await waitFor(() => expect(computeCounters.masteryLookup).toBeGreaterThan(0));
    await act(async () => {});

    const baseline = { ...computeCounters };
    expect(baseline.graph).toBe(1);
    expect(baseline.layout).toBe(1);
    expect(baseline.cycleSet).toBeGreaterThan(0);
    expect(baseline.fileTree).toBeGreaterThan(0);

    const file = (i: number) => ({ kind: 'file' as const, path: pathOf(i) });
    const sym = (i: number) => ({ kind: 'symbol' as const, id: `${pathOf(i)}::fn0`, filePath: pathOf(i) });
    for (const action of [
      { type: 'select-target', target: file(3) },
      { type: 'select-target', target: sym(5) },
      { type: 'select-target', target: file(0) },
      { type: 'select-target', target: file(250) },
      { type: 'node-cleared' },
      { type: 'select-target', target: file(1) },
      { type: 'visual-mode-set', value: 'Lab' },
      { type: 'select-target', target: file(7) },
    ] as AppAction[]) {
      act(() => dispatch!(action));
    }
    await act(async () => {});

    expect({ ...computeCounters }).toEqual(baseline);
    expect(flowProps.calls.length).toBeGreaterThan(1);
    expect(flowProps.calls.every((p) => p.onlyRenderVisibleElements === true)).toBe(true);
  });
});
