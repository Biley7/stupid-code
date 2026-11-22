import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ApiProvider } from '../../src/api/context';
import { CommandBar } from '../../src/components/shell/CommandBar';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { NoticeProvider } from '../../src/components/shell/NoticeBar';
import { ExorcismAction } from '../../src/components/slab/ExorcismAction';
import { StoreProvider } from '../../src/state/store';
import { makeRepos, makeSnapshotResponse, makeVitals } from '../fixtures/builders';
import { deferred } from '../helpers/deferred';
import { resetBetweenSteps } from '../helpers/step';
import { installFetchMock, type FetchMock, type MockReply, type Route } from '../helpers/mockFetch';

let mock: FetchMock | null = null;
afterEach(() => {
  mock?.restore();
  mock = null;
});

function renderBar(routes: Route[]) {
  mock = installFetchMock(routes);
  return render(
    <ApiProvider>
      <StoreProvider>
        <NoticeProvider>
          <DataLoader />
          <CommandBar />
          <ExorcismAction />
        </NoticeProvider>
      </StoreProvider>
    </ApiProvider>,
  );
}

function baseRoutes(vitals: ReturnType<typeof makeVitals>, study?: () => MockReply | Promise<MockReply>): Route[] {
  let enabled = false;
  const studyRoute = study;
  study = studyRoute
    ? async () => {
        const reply = await studyRoute();
        if ('json' in reply && (reply.status ?? 200) < 300) enabled = true;
        return reply;
      }
    : undefined;
  const routes: Route[] = [
    { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
    { method: 'GET', path: '/api/repos/alpha/snapshot', respond: () => ({ json: makeSnapshotResponse() }) },
    { method: 'GET', path: '/api/repos/alpha/vitals', respond: () => ({ json: { ...vitals, study_mode_enabled: enabled } }) },
  ];
  if (study) routes.push({ method: 'POST', path: '/api/repos/alpha/study-mode', respond: study });
  return routes;
}

async function selectAlpha() {
  const btn = await screen.findByRole('button', { name: /^alpha, 2 files/ });
  fireEvent.click(btn);
}

describe('Vitals meter, Study Mode switch, and Exorcism action (test case 14)', () => {
  it('covers vitals, Study Mode pending and failure, and Exorcism action visibility', async () => {
    // Step 1: shows counts and percentage verbatim
    {
    renderBar(baseRoutes(makeVitals()));
    await selectAlpha();
    const meter = screen.getByRole('region', { name: 'Comprehension vitals' });
    await waitFor(() => expect(meter).toHaveTextContent('25%'));
    expect(meter.querySelectorAll('dd')).toHaveLength(6);
    expect(Array.from(meter.querySelectorAll('dd')).map((d) => d.textContent)).toEqual([
      '4',
      '1',
      '1',
      '1',
      '1',
      '25%',
    ]);
    resetBetweenSteps();
    }

    // Step 2: shows the empty state when total_modules is 0
    {
    renderBar(
      baseRoutes(
        makeVitals({ total_modules: 0, unaudited_count: 0, dissected_count: 0, mastered_count: 0, stale_count: 0, mastery_percentage: 0 }),
      ),
    );
    await selectAlpha();
    const meter = screen.getByRole('region', { name: 'Comprehension vitals' });
    await waitFor(() => expect(meter).toHaveTextContent('No modules to measure'));
    expect(meter.querySelector('dl')).toBeNull();
    resetBetweenSteps();
    }

    // Step 3: keeps the previous value with aria-busy while pending, then applies the confirmed value
    {
    const gate = deferred<MockReply>();
    renderBar(baseRoutes(makeVitals(), () => gate.promise));
    await selectAlpha();
    const sw = await screen.findByRole('switch');
    await waitFor(() => expect(sw).toBeEnabled());
    expect(sw).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-busy', 'true'));
    expect(sw).toHaveAttribute('aria-checked', 'false');
    expect(sw).toHaveTextContent('Study Mode: Off');

    await act(async () => {
      gate.resolve({ json: { repo_id: 'alpha', study_mode_enabled: true } });
    });
    await waitFor(() => expect(sw).toHaveAttribute('aria-checked', 'true'));
    expect(sw).toHaveAttribute('aria-busy', 'false');
    resetBetweenSteps();
    }

    // Step 4: restores the previous value and shows an error when the request fails
    {
    renderBar(baseRoutes(makeVitals(), () => ({ status: 500, text: 'boom' })));
    await selectAlpha();
    const sw = await screen.findByRole('switch');
    await waitFor(() => expect(sw).toBeEnabled());

    fireEvent.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-busy', 'false'));
    await waitFor(() => expect(screen.getAllByText(/./, { selector: 'span.text-signal' })).not.toHaveLength(0));
    expect(sw).toHaveAttribute('aria-checked', 'false');
    expect(sw).toHaveTextContent('Study Mode: Off');
    expect(screen.queryByText('Study Mode: On')).toBeNull();
    resetBetweenSteps();
    }

    // Step 5: is hidden while Study Mode is off and shown once it is on
    {
    renderBar(
      baseRoutes(makeVitals(), () => ({ json: { repo_id: 'alpha', study_mode_enabled: true } })),
    );
    await selectAlpha();
    const sw = await screen.findByRole('switch');
    await waitFor(() => expect(sw).toBeEnabled());
    expect(screen.queryByRole('button', { name: 'Exorcism Check' })).toBeNull();

    fireEvent.click(sw);
    expect(await screen.findByRole('button', { name: 'Exorcism Check' })).toBeInTheDocument();
    resetBetweenSteps();
    }
  });
});
