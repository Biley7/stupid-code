import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ApiProvider } from '../../src/api/context';
import type { Lens } from '../../src/api/types';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { NoticeProvider } from '../../src/components/shell/NoticeBar';
import { AutopsySlab } from '../../src/components/slab/AutopsySlab';
import { StoreProvider, useAppDispatch } from '../../src/state/store';
import type { AppAction } from '../../src/state/appReducer';
import {
  HOSTILE_TEXT,
  makeExplain,
  makeRepos,
  makeSnapshotResponse,
  makeVitals,
} from '../fixtures/builders';
import { installFetchMock, type FetchMock, type Route } from '../helpers/mockFetch';

let mock: FetchMock | null = null;
afterEach(() => {
  mock?.restore();
  mock = null;
});

const FILE = 'backend/engines/graph.py';
const SYMBOL = `${FILE}::build`;
const WALK = `${FILE}::Graph.walk`;

let dispatch: ((a: AppAction) => void) | null = null;
function Capture() {
  const d = useAppDispatch();
  dispatch = d;
  return null;
}

const explainBody = (lens: Lens) => (b: unknown) =>
  typeof b === 'object' && b !== null && (b as { lens?: unknown }).lens === lens;

describe('Autopsy_Slab lenses', () => {
  it('renders tabs, L1, L2, L3, errors, and target handling from backend explain data', async () => {
    const dsaCard = {
      chapter: 'Graphs & Trees',
      pattern_name: 'Breadth-first search',
      why_used_here: 'Walks nodes level by level.',
      start_line: 4,
      end_line: 9,
      time_complexity: 'O(V+E)',
      space_complexity: 'O(V)',
    };
    let l3Attempts = 0;
    const requested: { target_id: string; lens: string }[] = [];
    const record = (r: Route): Route => ({
      ...r,
      respond: () => r.respond(),
    });
    const routes: Route[] = [
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
      { method: 'GET', path: '/api/repos/alpha/snapshot', respond: () => ({ json: makeSnapshotResponse() }) },
      { method: 'GET', path: '/api/repos/alpha/vitals', respond: () => ({ json: makeVitals() }) },
      record({
        method: 'POST',
        path: '/api/repos/alpha/explain',
        body: explainBody('L1_SYNTAX'),
        respond: () => ({
          json: makeExplain('L1_SYNTAX', {
            annotations: [
              {
                line_start: 3,
                line_end: 5,
                construct: 'function definition',
                explanation: 'Defines build.',
                what_if_removed: 'Nothing could build the graph.',
              },
              {
                line_start: 6,
                line_end: 6,
                construct: 'return statement',
                explanation: 'Returns the graph.',
                what_if_removed: '',
              },
            ],
          }),
        }),
      }),
      {
        method: 'POST',
        path: '/api/repos/alpha/explain',
        body: (b) => explainBody('L2_FLOW')(b) && (b as { target_id: string }).target_id === SYMBOL,
        respond: () => ({ json: makeExplain('L2_FLOW', { dsa_cards: [dsaCard] }) }),
      },
      {
        method: 'POST',
        path: '/api/repos/alpha/explain',
        body: (b) => explainBody('L2_FLOW')(b) && (b as { target_id: string }).target_id === WALK,
        respond: () => ({
          json: makeExplain('L2_FLOW', { llm_content_available: false, dsa_cards: [] }, WALK),
        }),
      },
      {
        method: 'POST',
        path: '/api/repos/alpha/explain',
        body: explainBody('L3_ARCHITECTURE'),
        respond: () => {
          l3Attempts += 1;
          if (l3Attempts <= 2) {
            return { status: 503, json: { error: { code: 'llm_unavailable', message: 'raw server text' } } };
          }
          return { json: makeExplain('L3_ARCHITECTURE', { spec_rationale: null }, 'alpha') };
        },
      },
    ];
    mock = installFetchMock(routes);
    const explainCalls = () =>
      mock!.calls.filter((c) => c.method === 'POST' && c.path === '/api/repos/alpha/explain');

    render(
      <ApiProvider>
        <StoreProvider>
          <NoticeProvider>
            <DataLoader />
            <Capture />
            <AutopsySlab />
          </NoticeProvider>
        </StoreProvider>
      </ApiProvider>,
    );

    // Empty state with no selection.
    expect(screen.getByRole('complementary', { name: 'Autopsy slab' })).toBeInTheDocument();
    await waitFor(() => expect(dispatch).not.toBeNull());
    act(() => dispatch!({ type: 'repo-selected', repoId: 'alpha' }));
    await waitFor(() => expect(mock!.calls.some((c) => c.path === '/api/repos/alpha/snapshot')).toBe(true));

    // File selection with L1 and L2 sends no explain request and never a file path as target_id.
    await waitFor(() => expect(mock!.calls.some((c) => c.path === '/api/repos/alpha/vitals')).toBe(true));
    act(() => dispatch!({ type: 'select-target', target: { kind: 'file', path: FILE } }));
    expect(await screen.findByText('Pick a symbol in this file to explain it.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'L2 Flow + DSA' }));
    expect(screen.getByText('Pick a symbol in this file to explain it.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'L1 Syntax' }));
    expect(explainCalls()).toHaveLength(0);

    // Pick a symbol: L1 request with the symbol id.
    fireEvent.click(screen.getByRole('button', { name: 'build' }));
    await screen.findByText('Defines build.');
    expect(explainCalls().map((c) => c.body)).toEqual([{ target_id: SYMBOL, lens: 'L1_SYNTAX' }]);
    requested.push(...(explainCalls().map((c) => c.body) as { target_id: string; lens: string }[]));
    expect(requested.every((r) => r.target_id !== FILE)).toBe(true);

    // Tabs: tablist semantics.
    const tablist = screen.getByRole('tablist', { name: 'Lens' });
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['L1 Syntax', 'L2 Flow + DSA', 'L3 Architecture']);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', tabs[0]!.id);

    // L1: HTML shown as text, empty what_if_removed hidden.
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveTextContent(HOSTILE_TEXT.replace(/\s+/g, ' '));
    expect(panel.querySelector('b')).toBeNull();
    expect(panel.querySelector('script')).toBeNull();
    expect(panel.querySelector('code')).toBeNull();
    expect(panel.querySelector('a')).toBeNull();
    expect(screen.getByText('Returns the graph.')).toBeInTheDocument();
    expect(screen.getAllByText('What breaks if removed?')).toHaveLength(1);
    expect(screen.getByText('Nothing could build the graph.')).toBeInTheDocument();

    // Keyboard: ArrowRight moves to L2 with DSA cards.
    tabs[0]!.focus();
    fireEvent.keyDown(tabs[0]!, { key: 'ArrowRight' });
    expect(await screen.findByText('DSA-in-the-Wild')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'L2 Flow + DSA' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'L2 Flow + DSA' })).toHaveFocus();
    expect(screen.getByText('Create the graph')).toBeInTheDocument();
    expect(screen.getByText('Upstream callers')).toBeInTheDocument();
    expect(screen.getByText('Blast radius')).toBeInTheDocument();
    expect(screen.getByText('Breadth-first search')).toBeInTheDocument();
    expect(screen.getByText('O(V+E)')).toBeInTheDocument();
    expect(screen.queryByText(/Generated flow content is unavailable/)).toBeNull();

    // L3 via End: first request fails, error with retry, not cached.
    fireEvent.keyDown(screen.getByRole('tab', { name: 'L2 Flow + DSA' }), { key: 'End' });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The explanation service is unavailable. No explanation was produced.');
    expect(alert).not.toHaveTextContent('raw server text');
    expect(explainCalls().filter((c) => (c.body as { lens: string }).lens === 'L3_ARCHITECTURE')).toHaveLength(1);
    // Other Lenses stay usable; coming back refetches because failures are not cached.
    fireEvent.click(screen.getByRole('tab', { name: 'L1 Syntax' }));
    await screen.findByText('Defines build.');
    fireEvent.click(screen.getByRole('tab', { name: 'L3 Architecture' }));
    await screen.findByRole('alert');
    expect(explainCalls().filter((c) => (c.body as { lens: string }).lens === 'L3_ARCHITECTURE')).toHaveLength(2);

    // Retry sends exactly one more request and shows the L3 matrix with a Selected row.
    fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Retry' }));
    const table = await screen.findByRole('table');
    expect(explainCalls().filter((c) => (c.body as { lens: string }).lens === 'L3_ARCHITECTURE')).toHaveLength(3);
    const rows = within(table).getAllByRole('row');
    const selectedRows = rows.filter((r) => within(r).queryByText('Selected') !== null);
    expect(selectedRows).toHaveLength(1);
    expect(selectedRows[0]).toHaveTextContent('Hexagonal / Clean Architecture');
    expect(within(table).getByText('Layered MVC')).toBeInTheDocument();
    expect(screen.queryByText('Spec rationale')).toBeNull();

    // Another symbol on L2: degraded notice, deterministic fields, and no DSA section.
    act(() => dispatch!({ type: 'select-target', target: { kind: 'symbol', id: WALK, filePath: FILE } }));
    fireEvent.click(screen.getByRole('tab', { name: 'L2 Flow + DSA' }));
    await screen.findByText(/Generated flow content is unavailable/);
    expect(screen.getByText('Create the graph')).toBeInTheDocument();
    expect(screen.queryByText('DSA-in-the-Wild')).toBeNull();

    // No explain request ever carried a file path as target_id.
    for (const c of explainCalls()) {
      expect((c.body as { target_id: string }).target_id).not.toBe(FILE);
    }
    expect(mock.unmatched).toEqual([]);
  });
});
