// Test case 13: Ingest modal. Validates: Requirements 7.4, 7.5, 7.6, 7.8, 7.9, 7.11, 7.12, 28.6
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiProvider } from '../../src/api/context';
import type { IngestResponse } from '../../src/api/types';
import { CommandBar } from '../../src/components/shell/CommandBar';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { NoticeProvider } from '../../src/components/shell/NoticeBar';
import { StoreProvider } from '../../src/state/store';
import { makeRepos, makeSnapshotResponse, makeVitals } from '../fixtures/builders';
import { deferred } from '../helpers/deferred';
import { installFetchMock, type Route } from '../helpers/mockFetch';
import { resetBetweenSteps } from '../helpers/step';

function renderBar() {
  document.body.innerHTML = '<div id="app-root"></div><div id="modal-root"></div>';
  const container = document.getElementById('app-root')!;
  return render(
    <ApiProvider>
      <StoreProvider>
        <NoticeProvider>
          <DataLoader />
          <CommandBar />
        </NoticeProvider>
      </StoreProvider>
    </ApiProvider>,
    { container },
  );
}

function ingestResponse(repoId: string): IngestResponse {
  const snap = makeSnapshotResponse();
  return {
    repo_id: repoId,
    summary: { file_count: 7, symbol_count: 11, edge_count: 5, dsa_signal_count: 2 },
    provenance: snap.provenance,
    topology: snap.topology,
    truncated: false,
    warnings: [{ kind: 'skipped_large_file', path: 'big.py', detail: 'File too large.' }],
  };
}

const INGEST = (r: RegExp | string = '/api/repos/ingest'): Pick<Route, 'method' | 'path'> => ({
  method: 'POST',
  path: r,
});

async function openModal() {
  const user = userEvent.setup();
  renderBar();
  // Wait for the repository list so the bar is settled.
  await screen.findByRole('list', { name: 'Repositories' });
  const openers = screen.getAllByRole('button', { name: 'Ingest' });
  await user.click(openers[0]!);
  const dialog = await screen.findByRole('dialog');
  return { user, dialog };
}

const ingestCalls = (mock: ReturnType<typeof installFetchMock>) =>
  mock.calls.filter((c) => c.path === '/api/repos/ingest');

describe('Ingest modal (test case 13)', () => {
  it('Ingest modal (test case 13)', async () => {
    // Step 1: blocks blank and non-GitHub input without a request
    {
    const mock = installFetchMock([
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
    ]);
    const { user, dialog } = await openModal();
    const box = within(dialog).getByRole('textbox');

    await user.click(within(dialog).getByRole('button', { name: 'Ingest' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent('must not be blank');

    await user.type(box, '   http://github.com/o/r  ');
    await user.click(within(dialog).getByRole('button', { name: 'Ingest' }));
    expect(within(dialog).getByRole('alert')).toHaveTextContent('https://github.com/');

    expect(ingestCalls(mock)).toHaveLength(0);
    resetBetweenSteps();
    }

    // Step 2: shows the summary, refreshes the list, and selects the new repository
    {
    let ingested = false;
    const mock = installFetchMock([
      {
        method: 'GET',
        path: '/api/repos',
        respond: () => ({
          json: ingested
            ? [...makeRepos(), { repo_id: 'gamma', file_count: 7, symbol_count: 11, study_mode_enabled: false }]
            : makeRepos(),
        }),
      },
      {
        ...INGEST(),
        respond: () => {
          ingested = true;
          return { json: ingestResponse('gamma') };
        },
      },
      { method: 'GET', path: '/api/repos/gamma/snapshot', respond: () => ({ json: makeSnapshotResponse() }) },
      { method: 'GET', path: '/api/repos/gamma/vitals', respond: () => ({ json: makeVitals({ repo_id: 'gamma' }) }) },
    ]);
    const { user, dialog } = await openModal();

    await user.type(within(dialog).getByRole('textbox'), '  https://github.com/o/gamma  ');
    await user.click(within(dialog).getByRole('button', { name: 'Ingest' }));

    const result = await within(dialog).findByRole('region', { name: 'Ingest result' });
    expect(result).toHaveTextContent('gamma');
    expect(result).toHaveTextContent('skipped_large_file');
    expect(result).toHaveTextContent('File too large.');

    expect(ingestCalls(mock)).toHaveLength(1);
    expect(ingestCalls(mock)[0]!.body).toEqual({ url: 'https://github.com/o/gamma' });

    const selected = await screen.findByRole('button', { name: /^gamma, 7 files, 11 symbols$/ });
    await waitFor(() => expect(selected).toHaveAttribute('aria-pressed', 'true'));
    resetBetweenSteps();
    }

    // Step 3: maps rate_limited with Retry-After, without it, and local_ingest_disabled
    {
    let reply: 'with' | 'without' | 'local' = 'with';
    const mock = installFetchMock([
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
      {
        ...INGEST(),
        respond: () =>
          reply === 'local'
            ? { status: 403, json: { error: { code: 'local_ingest_disabled', message: 'server text' } } }
            : {
                status: 429,
                json: { error: { code: 'rate_limited', message: 'server text' } },
                headers: reply === 'with' ? { 'Retry-After': '42' } : { 'Retry-After': 'soon' },
              },
      },
    ]);
    const { user, dialog } = await openModal();
    const submit = () => user.click(within(dialog).getByRole('button', { name: 'Ingest' }));

    await user.type(within(dialog).getByRole('textbox'), 'https://github.com/o/r');
    await submit();
    expect(await within(dialog).findByText(/rate limited\. Retry in 42 seconds\./)).toBeInTheDocument();

    reply = 'without';
    await submit();
    await waitFor(() => {
      const alert = within(dialog).getByRole('alert');
      expect(alert).toHaveTextContent('GitHub ingestion is rate limited.');
      expect(alert).not.toHaveTextContent('Retry in');
    });
    // Input is kept after a failure.
    expect(within(dialog).getByRole('textbox')).toHaveValue('https://github.com/o/r');

    await user.click(within(dialog).getByRole('radio', { name: 'Local path' }));
    // Switching source keeps the text (Requirement 7.3).
    expect(within(dialog).getByRole('textbox')).toHaveValue('https://github.com/o/r');
    await user.clear(within(dialog).getByRole('textbox'));
    await user.type(within(dialog).getByRole('textbox'), '/tmp/repo');
    reply = 'local';
    await submit();
    expect(
      await within(dialog).findByText('Local path ingestion is disabled on this server.'),
    ).toBeInTheDocument();
    expect(ingestCalls(mock)[2]!.body).toEqual({ path: '/tmp/repo' });
    resetBetweenSteps();
    }

    // Step 4: sends one request for a double submit while in flight
    {
    const gate = deferred<void>();
    const mock = installFetchMock([
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
      {
        ...INGEST(),
        respond: async () => {
          await gate.promise;
          return { status: 429, json: { error: { code: 'rate_limited', message: 'x' } } };
        },
      },
    ]);
    const { user, dialog } = await openModal();
    await user.type(within(dialog).getByRole('textbox'), 'https://github.com/o/r');

    const form = within(dialog).getByRole('textbox').closest('form')!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    await within(dialog).findByRole('status');
    fireEvent.submit(form);

    expect(ingestCalls(mock)).toHaveLength(1);
    gate.resolve();
    await within(dialog).findByRole('alert');
    expect(ingestCalls(mock)).toHaveLength(1);
    resetBetweenSteps();
    }
  });
});
