import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { Dispatch } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiProvider } from '../../src/api/context';
import { GraphView } from '../../src/components/canvas/GraphView';
import { FileTree } from '../../src/components/rail/FileTree';
import { CommandBar } from '../../src/components/shell/CommandBar';
import { DataLoader } from '../../src/components/shell/DataLoader';
import { NoticeProvider } from '../../src/components/shell/NoticeBar';
import { AutopsySlab } from '../../src/components/slab/AutopsySlab';
import type { AppAction } from '../../src/state/appReducer';
import { StoreProvider, useAppDispatch } from '../../src/state/store';
import {
  makeCheck,
  makeExplain,
  makeRepos,
  makeSnapshotResponse,
  makeVerdict,
  makeVitals,
} from '../fixtures/builders';
import { installFetchMock, type FetchMock } from '../helpers/mockFetch';

// jsdom has no layout, so ReactFlow renders nothing useful. This stand-in exposes the
// props GraphView computes (shroud flag and mastery label per node).
vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  return {
    ...actual,
    ReactFlow: (props: { nodes: { id: string; data: { shroud: boolean; mastery: { label: string } } }[] }) => (
      <div data-testid="flow">
        {props.nodes.map((n) => (
          <div key={n.id} data-testid={`node:${n.id}`} data-shroud={String(n.data.shroud)}>
            {n.data.mastery.label}
          </div>
        ))}
      </div>
    ),
  };
});

let mock: FetchMock | null = null;
afterEach(() => {
  vi.useRealTimers();
  mock?.restore();
  mock = null;
  document.getElementById('app-root')?.remove();
  document.getElementById('modal-root')?.remove();
});

const FILE = 'backend/engines/graph.py';
const SYMBOL = `${FILE}::build`;
const SECRET = 'SECRET_EXPECTED_CONCEPT';

let dispatch: Dispatch<AppAction> | null = null;
function Driver() {
  dispatch = useAppDispatch();
  return null;
}

describe('Exorcism flow (test case 17)', () => {
  it('runs expiry, fail, pass with vitals refresh, and study_mode_disabled on a new check', async () => {
    const appRoot = document.createElement('div');
    appRoot.id = 'app-root';
    const modalRoot = document.createElement('div');
    modalRoot.id = 'modal-root';
    document.body.append(appRoot, modalRoot);

    // Server-side truth the mocked backend reports.
    let fileState = 'UNAUDITED';
    let studyEnabled = true;
    let startMode: 'ok' | 'disabled' = 'ok';
    let verdictFor: 'fail' | 'pass' = 'fail';
    const starts: unknown[] = [];
    const submits: unknown[] = [];

    mock = installFetchMock([
      { method: 'GET', path: '/api/repos', respond: () => ({ json: makeRepos() }) },
      { method: 'GET', path: '/api/repos/alpha/snapshot', respond: () => ({ json: makeSnapshotResponse() }) },
      {
        method: 'GET',
        path: '/api/repos/alpha/vitals',
        respond: () => ({
          json: makeVitals({
            study_mode_enabled: studyEnabled,
            file_states: { [FILE]: fileState, 'backend/domain/models.py': 'MASTERED' },
          }),
        }),
      },
      {
        method: 'POST',
        path: '/api/repos/alpha/explain',
        respond: () => ({ json: makeExplain('L1_SYNTAX') }),
      },
      {
        method: 'POST',
        path: '/api/repos/alpha/socratic/start',
        respond: () => {
          starts.push(null);
          if (startMode === 'disabled') {
            studyEnabled = false;
            return { status: 403, json: { error: { code: 'study_mode_disabled', message: 'server text' } } };
          }
          const check = makeCheck();
          return {
            json: {
              ...check,
              questions: check.questions.map((q) => ({ ...q, expected_concepts: [SECRET] })),
            },
          };
        },
      },
      {
        method: 'POST',
        path: '/api/repos/alpha/socratic/submit',
        respond: () => {
          if (verdictFor === 'pass') {
            fileState = 'MASTERED';
            return { json: makeVerdict({ passed: true, score: 0.9, feedback: 'Well reasoned.', new_state: 'MASTERED' }) };
          }
          return {
            json: makeVerdict({ passed: false, score: 0.2, feedback: 'Missed the point.', new_state: 'UNAUDITED' }),
          };
        },
      },
    ]);

    render(
      <ApiProvider>
        <StoreProvider>
          <NoticeProvider>
            <DataLoader />
            <Driver />
            <CommandBar />
            <FileTree />
            <GraphView />
            <AutopsySlab />
          </NoticeProvider>
        </StoreProvider>
      </ApiProvider>,
      { container: appRoot },
    );

    act(() => dispatch!({ type: 'repo-selected', repoId: 'alpha' }));
    await screen.findByRole('tree', { name: 'Repository file tree' });
    await waitFor(() => expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true'));
    act(() => dispatch!({ type: 'select-target', target: { kind: 'symbol', id: SYMBOL, filePath: FILE } }));

    const treeRow = () => document.querySelector<HTMLElement>(`[data-row-key="f:${FILE}"]`);
    const node = () => screen.getByTestId(`node:${FILE}`);
    await waitFor(() => expect(treeRow()).not.toBeNull());
    expect(within(treeRow()!).getByText('UNAUDITED')).toBeInTheDocument();
    expect(node()).toHaveAttribute('data-shroud', 'true');

    const action = await screen.findByRole('button', { name: 'Exorcism Check' });

    // From here on, time is fake: no wall-clock waits.
    vi.useFakeTimers();
    const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const advance = (seconds: number) =>
      act(async () => { await vi.advanceTimersByTimeAsync(seconds * 1000); });
    const dialog = () => screen.getByRole('dialog');
    const answerFields = () => within(dialog()).getAllByRole('textbox') as HTMLTextAreaElement[];
    const startCalls = () => mock!.calls.filter((c) => c.path.endsWith('/socratic/start'));
    const submitCalls = () => mock!.calls.filter((c) => c.path.endsWith('/socratic/submit'));

    // ---- Run 1: start, countdown, blank at zero expires without submit.
    fireEvent.click(action);
    await flush();
    expect(startCalls()).toHaveLength(1);
    expect(startCalls()[0]!.body).toEqual({ target_id: SYMBOL });
    expect(dialog()).toHaveTextContent('What does line 4 return?');
    expect(dialog()).toHaveTextContent('Line reference: L4');
    expect(dialog()).not.toHaveTextContent(SECRET);
    expect(dialog()).not.toHaveTextContent(/expected_concepts/);
    expect(dialog()).toHaveTextContent('Time remaining: 60 s');
    await advance(5);
    expect(dialog()).toHaveTextContent('Time remaining: 55 s');

    fireEvent.change(answerFields()[0]!, { target: { value: 'only the first' } });
    await advance(54);
    expect(dialog()).toHaveTextContent('Time remaining: 1 s');
    await advance(1);
    expect(dialog()).toHaveTextContent('Time remaining: 0 s');
    expect(dialog()).toHaveTextContent('Time expired');
    expect(submitCalls()).toHaveLength(0);
    await advance(10);
    expect(submitCalls()).toHaveLength(0);

    // ---- Run 2: restart, submit trimmed answers, fail verdict.
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Restart check' }));
    await flush();
    expect(startCalls()).toHaveLength(2);
    expect(dialog()).toHaveTextContent('Time remaining: 60 s');
    fireEvent.change(answerFields()[0]!, { target: { value: '  first answer \n' } });
    fireEvent.change(answerFields()[1]!, { target: { value: '\n second answer  ' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Submit answers' }));
    await flush();
    expect(submitCalls()).toHaveLength(1);
    expect(submitCalls()[0]!.body).toEqual({
      target_id: SYMBOL,
      answers: [
        { question_id: 'q1', answer: 'first answer' },
        { question_id: 'q2', answer: 'second answer' },
      ],
    });
    const failed = within(dialog()).getByRole('region', { name: 'Verdict' });
    expect(failed).toHaveTextContent('FAILED');
    expect(failed).toHaveTextContent('Missed the point.');
    expect(failed).toHaveTextContent('UNAUDITED');
    // The refreshed vitals still say UNAUDITED: the shroud stays.
    expect(within(treeRow()!).getByText('UNAUDITED')).toBeInTheDocument();
    expect(node()).toHaveAttribute('data-shroud', 'true');

    // ---- Run 3: new check, pass verdict, refresh turns badge and shroud.
    verdictFor = 'pass';
    fireEvent.click(within(dialog()).getByRole('button', { name: 'New check' }));
    await flush();
    expect(startCalls()).toHaveLength(3);
    fireEvent.change(answerFields()[0]!, { target: { value: 'a' } });
    fireEvent.change(answerFields()[1]!, { target: { value: 'b' } });
    fireEvent.click(within(dialog()).getByRole('button', { name: 'Submit answers' }));
    await flush();
    const passed = within(dialog()).getByRole('region', { name: 'Verdict' });
    expect(passed).toHaveTextContent('PASSED');
    expect(passed).toHaveTextContent('Well reasoned.');
    expect(passed).toHaveTextContent('MASTERED');
    expect(passed).toHaveTextContent('2025-01-01T00:00:00Z');
    expect(within(treeRow()!).getByText('MASTERED')).toBeInTheDocument();
    expect(node()).toHaveAttribute('data-shroud', 'false');
    expect(node()).toHaveTextContent('MASTERED');

    // ---- New check after Study Mode was turned off on the server.
    startMode = 'disabled';
    fireEvent.click(within(dialog()).getByRole('button', { name: 'New check' }));
    await flush();
    expect(startCalls()).toHaveLength(4);
    expect(dialog()).toHaveTextContent('Study Mode is off.');
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch')).toHaveTextContent('Study Mode: Off');
    expect(starts).toHaveLength(4);
  });
});
