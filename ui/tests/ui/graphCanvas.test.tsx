import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Dispatch } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiProvider } from '../../src/api/context';
import { Canvas } from '../../src/components/canvas/Canvas';
import { FileTree } from '../../src/components/rail/FileTree';
import { VitalOrgansList } from '../../src/components/rail/VitalOrgansList';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { AutopsySlab } from '../../src/components/slab/AutopsySlab';
import type { AppAction } from '../../src/state/appReducer';
import { StoreProvider, useAppDispatch } from '../../src/state/store';
import { makeExplain, makeRepos, makeSnapshotResponse, makeVitals } from '../fixtures/builders';
import { installFetchMock, type FetchMock } from '../helpers/mockFetch';

// jsdom has no layout, so React Flow renders no nodes. The mock renders one element per node
// from the exact nodes, edges and handlers GraphView passes in, exposing the derived flags.
vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  return {
    ...actual,
    ReactFlow: (props: {
      nodes: { id: string; data: Record<string, unknown> }[];
      edges: unknown[];
      onNodeClick: (event: unknown, node: unknown) => void;
    }) => (
      <div data-testid="flow" data-nodes={props.nodes.length} data-edges={props.edges.length}>
        {props.nodes.map((n) => (
          <button
            key={n.id}
            type="button"
            data-testid={`node:${n.id}`}
            data-selected={String(n.data.selected)}
            data-upstream={String(n.data.upstream)}
            data-downstream={String(n.data.downstream)}
            data-blast={String(n.data.blast)}
            data-shroud={String(n.data.shroud)}
            onClick={(e) => props.onNodeClick(e, n)}
          >
            {String(n.data.label)}
          </button>
        ))}
      </div>
    ),
  };
});

let mock: FetchMock | null = null;
afterEach(() => {
  mock?.restore();
  mock = null;
});

let dispatch: Dispatch<AppAction> | null = null;
function Driver() {
  dispatch = useAppDispatch();
  return null;
}

const MODELS = 'backend/domain/models.py';
const GRAPH = 'backend/engines/graph.py';
const BUILD = `${GRAPH}::build`;

describe('graph and canvas (test case 15)', () => {
  it('renders the graph and keeps tree, slab, vital organs and topology in sync', async () => {
    const snapshot = makeSnapshotResponse({
      snapshot: { vital_organs: [MODELS, 'ghost/missing.py', BUILD] },
    });
    // Insertion order is deliberately unsorted; the view must sort rows.
    snapshot.topology!.directory_roles = { 'z/last': 'api', 'backend/engines': 'engines', 'backend/domain': 'domain' };
    // graph.py is UNAUDITED, so it carries the Autopsy-only shroud.
    const vitals = makeVitals();
    vitals.file_states = { [MODELS]: 'MASTERED', [GRAPH]: 'UNAUDITED' };

    mock = installFetchMock([
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
      { method: 'GET', path: '/api/repos/alpha/snapshot', respond: () => ({ json: snapshot }) },
      { method: 'GET', path: '/api/repos/alpha/vitals', respond: () => ({ json: vitals }) },
      {
        method: 'POST',
        path: '/api/repos/alpha/explain',
        body: (b) => (b as { lens: string }).lens === 'L1_SYNTAX',
        respond: () => ({ json: makeExplain('L1_SYNTAX', undefined, BUILD) }),
      },
      {
        method: 'POST',
        path: '/api/repos/alpha/explain',
        body: (b) => (b as { lens: string }).lens === 'L2_FLOW',
        respond: () => ({ json: makeExplain('L2_FLOW', undefined, BUILD) }),
      },
    ]);

    render(
      <ApiProvider>
        <StoreProvider>
          <DataLoader />
          <Driver />
          <FileTree />
          <VitalOrgansList />
          <Canvas />
          <AutopsySlab />
        </StoreProvider>
      </ApiProvider>,
    );
    act(() => dispatch!({ type: 'repo-selected', repoId: 'alpha' }));

    // Graph rendered from the snapshot: two file nodes, one imports edge.
    const flow = await screen.findByTestId('flow');
    expect(flow).toHaveAttribute('data-nodes', '2');
    expect(flow).toHaveAttribute('data-edges', '1');
    const tree = await screen.findByRole('tree', { name: 'Repository file tree' });
    await waitFor(() => expect(screen.getByTestId(`node:${GRAPH}`)).toHaveAttribute('data-shroud', 'true'));

    // Vital organs: backend order, FILE / UNRESOLVED / SYMBOL.
    const organs = within(screen.getByRole('list', { name: 'Vital organs' })).getAllByRole('button');
    expect(organs.map((b) => b.textContent?.match(/FILE|UNRESOLVED|SYMBOL/)?.[0])).toEqual([
      'FILE',
      'UNRESOLVED',
      'SYMBOL',
    ]);
    expect(organs[1]).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('main', { name: 'Canvas' })).toHaveClass('canvas-grid');

    // Autopsy-only decoration: attribute, shroud flag, and CSS selectors gated on Autopsy.
    expect(document.documentElement.dataset.visualMode).toBe('autopsy');
    expect(screen.getByTestId(`node:${MODELS}`)).toHaveAttribute('data-shroud', 'false');
    act(() => dispatch!({ type: 'visual-mode-set', value: 'Lab' }));
    expect(document.documentElement.dataset.visualMode).toBe('lab');
    expect(screen.getByTestId(`node:${GRAPH}`)).toHaveAttribute('data-shroud', 'false');
    act(() => dispatch!({ type: 'visual-mode-set', value: 'Autopsy' }));
    expect(screen.getByTestId(`node:${GRAPH}`)).toHaveAttribute('data-shroud', 'true');
    const css = readFileSync(resolve(__dirname, '../../src/styles/index.css'), 'utf8');
    expect(css).toMatch(/\[data-visual-mode='autopsy'\] \.canvas-grid/);
    expect(css).toMatch(/\[data-visual-mode='autopsy'\] \.node-unaudited/);
    expect(css).not.toMatch(/\[data-visual-mode='lab'\]/);

    // Node click: tree, slab and vital organs move together (Selection_Sync).
    fireEvent.click(screen.getByTestId(`node:${MODELS}`));
    await waitFor(() => expect(screen.getByTestId(`node:${MODELS}`)).toHaveAttribute('data-selected', 'true'));
    expect(within(tree).getByRole('treeitem', { name: /models\.py/ })).toHaveAttribute('aria-selected', 'true');
    expect(organs[0]).toHaveAttribute('aria-current', 'true');
    const slab = screen.getByRole('complementary', { name: 'Autopsy slab' });
    expect(within(slab).getByText(MODELS)).toBeInTheDocument();
    expect(within(slab).getByLabelText('File metadata')).toBeInTheDocument();
    // Neighbours come from snapshot edges and the graph says so (a file has no blast radius).
    expect(screen.getByText(/highlighting derived from snapshot/)).toBeInTheDocument();
    expect(screen.getByTestId(`node:${GRAPH}`)).toHaveAttribute('data-upstream', 'true');
    expect(within(slab).getByText(/File-level blast radius is not provided/)).toBeInTheDocument();

    // Symbol with an L2 response: blast radius highlight comes from the explain result.
    fireEvent.click(organs[2]!);
    fireEvent.click(screen.getByRole('button', { name: 'Symbols' }));
    fireEvent.click(within(slab).getByRole('tab', { name: 'L2_FLOW' }));
    await within(slab).findByRole('heading', { name: 'Blast radius' });
    await waitFor(() => expect(screen.getByText(/blast radius from blast-radius result/)).toBeInTheDocument());
    expect(screen.getByText(/impact_score 0\.5/)).toBeInTheDocument();
    expect(screen.getByTestId(`node:${BUILD}`)).toHaveAttribute('data-selected', 'true');
    expect(screen.getByTestId(`node:${MODELS}::Model`)).toHaveAttribute('data-blast', 'true');
    expect(organs[2]).toHaveAttribute('aria-current', 'true');

    // Topology switch keeps the selection; rows are sorted.
    fireEvent.click(screen.getByRole('tab', { name: 'Topology' }));
    const dirs = await screen.findByRole('region', { name: 'Directory roles' }).catch(() =>
      screen.findByLabelText('Directory roles'),
    );
    const rows = within(dirs).getAllByRole('button').map((b) => b.textContent);
    expect(rows).toEqual(['backend/domaindomain', 'backend/enginesengines', 'z/lastapi']);
    expect(screen.queryByTestId('flow')).not.toBeInTheDocument();
    expect(within(tree).getByRole('treeitem', { name: /build/, selected: true })).toBeInTheDocument();
    expect(organs[2]).toHaveAttribute('aria-current', 'true');
    expect(within(slab).getByText(BUILD.split('::')[1]!, { selector: 'span' })).toBeInTheDocument();
  });
});
