// Test case 12: repository list. Requirements 6.1-6.6, 6.12, 28.5, 28.14.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { DeepLinkController } from '../../src/components/shell/DeepLinkController';
import { NoticeBar, NoticeProvider } from '../../src/components/shell/NoticeBar';
import { useRepos } from '../../src/data/useRepos';
import { useAppState } from '../../src/state/store';
import { RepoSelector } from '../../src/components/shell/RepoSelector';
import { makeRepos, makeSnapshotResponse, makeVitals } from '../fixtures/builders';
import { renderApp } from '../helpers/renderApp';

// RepoSelector does not load the list itself (DataLoader does). Stand-in for DataLoader in
// cases that must not trigger snapshot or vitals requests on selection.
function ListLoader() {
  useRepos({ autoload: true });
  return null;
}

function SelectorWithLoader(props: { onIngest?: () => void }) {
  return (
    <>
      <ListLoader />
      <RepoSelector {...props} />
    </>
  );
}

function StateProbe() {
  const app = useAppState();
  return <output data-testid="state">{JSON.stringify({ repo: app.repoId, file: app.file, view: app.view })}</output>;
}

function deepLinkRoutes() {
  return [
    { method: 'GET' as const, path: '/api/repos', respond: () => ({ json: makeRepos() }) },
    { method: 'GET' as const, path: '/api/repos/alpha/snapshot', respond: () => ({ json: makeSnapshotResponse() }) },
    { method: 'GET' as const, path: '/api/repos/alpha/vitals', respond: () => ({ json: makeVitals() }) },
  ];
}

async function renderDeepLink(search: string) {
  window.history.replaceState(null, '', `/${search}`);
  const historyLength = window.history.length;
  const view = renderApp(
    <NoticeProvider>
      <DataLoader />
      <DeepLinkController />
      <NoticeBar />
      <RepoSelector />
      <StateProbe />
    </NoticeProvider>,
    deepLinkRoutes(),
  );
  await screen.findByRole('list', { name: 'Repositories' });
  const state = () => JSON.parse(screen.getByTestId('state').textContent ?? '{}') as {
    repo: string | null;
    file: string | null;
    view: string;
  };
  return { ...view, state, historyLength };
}

const GRAPH_FILE = 'backend/engines/graph.py';

describe('repository list (test case 12)', () => {
  it('loads, shows empty and error states with retry, selects, and renders repo_id as plain text', async () => {
    // Step 1: loading, then the list in backend order; selection marks one entry.
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const first = renderApp(<SelectorWithLoader />, [
      {
        method: 'GET',
        path: '/api/repos',
        respond: async () => {
          await gate;
          return { json: makeRepos() };
        },
      },
    ]);
    expect(await screen.findByText('Loading repositories')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Repositories' })).toBeNull();
    release();
    const list = await screen.findByRole('list', { name: 'Repositories' });
    const buttons = within(list).getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveAccessibleName('alpha, 2 files, 3 symbols');
    expect(buttons[1]).toHaveAccessibleName('beta/with space, 0 files, 0 symbols');
    expect(buttons.every((b) => b.getAttribute('aria-pressed') === 'false')).toBe(true);

    fireEvent.click(buttons[1]!);
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'true');
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(buttons[0]!);
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true');
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'false');
    first.unmount();
    first.fetchMock.restore();

    // Step 2: empty list shows the empty state and an Ingest action.
    let ingestClicks = 0;
    const empty = renderApp(<SelectorWithLoader onIngest={() => (ingestClicks += 1)} />, [
      { method: 'GET', path: '/api/repos', respond: () => ({ json: [] }) },
    ]);
    expect(await screen.findByText('No repositories ingested')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ingest' }));
    expect(ingestClicks).toBe(1);
    empty.unmount();
    empty.fetchMock.restore();

    // Step 3: error lists nothing; Retry reloads and shows the list.
    let attempts = 0;
    const failing = renderApp(<SelectorWithLoader />, [
      {
        method: 'GET',
        path: '/api/repos',
        respond: () => {
          attempts += 1;
          return attempts === 1 ? { status: 500, json: { detail: 'boom' } } : { json: makeRepos() };
        },
      },
    ]);
    const alert = await screen.findByRole('alert');
    expect(screen.queryByRole('list', { name: 'Repositories' })).toBeNull();
    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('list', { name: 'Repositories' })).toBeInTheDocument();
    expect(attempts).toBe(2);
    expect(screen.queryByRole('alert')).toBeNull();
    failing.unmount();
    failing.fetchMock.restore();

    // Step 4: an HTML-tag repo_id is text, never markup.
    const hostile = '<img src=x onerror=alert(1)>';
    const plain = renderApp(<SelectorWithLoader />, [
      {
        method: 'GET',
        path: '/api/repos',
        respond: () => ({
          json: [{ repo_id: hostile, file_count: 1, symbol_count: 1, study_mode_enabled: false }],
        }),
      },
    ]);
    const item = await screen.findByText(hostile);
    expect(item.textContent).toBe(hostile);
    expect(plain.container.querySelector('img')).toBeNull();
    await waitFor(() => expect(plain.container.querySelectorAll('li')).toHaveLength(1));

    plain.unmount();
    plain.fetchMock.restore();

    // Step 5: valid repo_id and file select both; URL is kept in sync without new history entries.
    const ok = await renderDeepLink(`?repo_id=alpha&file=${GRAPH_FILE}&keep=1`);
    await waitFor(() => expect(ok.state().file).toBe(GRAPH_FILE));
    expect(ok.state().repo).toBe('alpha');
    expect(screen.queryByRole('status', { name: 'Notices' })).toBeNull();
    await waitFor(() => expect(window.location.search).toContain('view=graph'));
    const params = new URLSearchParams(window.location.search);
    expect(params.get('repo_id')).toBe('alpha');
    expect(params.get('file')).toBe(GRAPH_FILE);
    expect(params.get('keep')).toBe('1');
    expect(window.history.length).toBe(ok.historyLength);
    expect(ok.fetchMock.unmatched).toEqual([]);
    // Normal loading only: DataLoader loads the list exactly once; the controller adds nothing.
    expect(ok.fetchMock.calls.filter((c) => c.path === '/api/repos')).toHaveLength(1);
    const paths = ok.fetchMock.calls.map((c) => `${c.method} ${c.path}`);
    expect([...new Set(paths)].sort()).toEqual([
      'GET /api/repos',
      'GET /api/repos/alpha/snapshot',
      'GET /api/repos/alpha/vitals',
    ]);
    expect(paths.filter((p) => p.endsWith('/snapshot'))).toHaveLength(1);
    expect(paths.filter((p) => p.endsWith('/vitals'))).toHaveLength(1);
    ok.unmount();
    ok.fetchMock.restore();

    // Step 6: view=topology opens topology.
    const topo = await renderDeepLink('?view=topology');
    await waitFor(() => expect(topo.state().view).toBe('topology'));
    expect(topo.state().repo).toBeNull();
    expect(screen.queryByRole('status', { name: 'Notices' })).toBeNull();
    topo.unmount();
    topo.fetchMock.restore();

    // Step 7: unknown repo shows a notice and selects nothing; no snapshot request.
    const unknownRepo = await renderDeepLink('?repo_id=nope&file=x.py');
    expect(await screen.findByText('Repository not found: nope')).toBeInTheDocument();
    expect(unknownRepo.state().repo).toBeNull();
    expect(unknownRepo.state().file).toBeNull();
    expect(new Set(unknownRepo.fetchMock.calls.map((c) => c.path))).toEqual(new Set(['/api/repos']));
    unknownRepo.unmount();
    unknownRepo.fetchMock.restore();

    // Step 8: unknown file keeps the repo and shows a notice.
    const unknownFile = await renderDeepLink('?repo_id=alpha&file=missing.py');
    expect(await screen.findByText('File not found in snapshot: missing.py')).toBeInTheDocument();
    expect(unknownFile.state().repo).toBe('alpha');
    expect(unknownFile.state().file).toBeNull();
    unknownFile.unmount();
    unknownFile.fetchMock.restore();

    // Step 9: unsupported view defaults to graph with no notice.
    const badView = await renderDeepLink('?view=sideways');
    expect(badView.state().view).toBe('graph');
    expect(screen.queryByRole('status', { name: 'Notices' })).toBeNull();
    badView.unmount();
    badView.fetchMock.restore();

    // Step 10: file without repo_id is ignored silently.
    const orphan = await renderDeepLink(`?file=${GRAPH_FILE}`);
    expect(orphan.state().repo).toBeNull();
    expect(orphan.state().file).toBeNull();
    expect(screen.queryByRole('status', { name: 'Notices' })).toBeNull();
    expect(new Set(orphan.fetchMock.calls.map((c) => c.path))).toEqual(new Set(['/api/repos']));
    expect(window.history.length).toBe(orphan.historyLength);
  });
});
