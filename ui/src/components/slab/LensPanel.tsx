// Lens content of the Autopsy_Slab (Requirements 3.10, 19.1 to 19.15). Resolves the
// explain target, sends a request only for a valid target, and owns loading, error,
// and retry. A file path is never sent as a target id.
import { useMemo } from 'react';
import { resolveExplainTarget } from '../../core/explainTarget';
import { presentError } from '../../core/present';
import { buildSnapshotIndex } from '../../core/snapshotIndex';
import { useExplain } from '../../data/useExplain';
import { useRetry } from '../../data/useRetry';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';
import { LENS_PANEL_ID, lensTabId } from './LensTabs';
import { L1Panel } from './L1Panel';
import { L2Panel } from './L2Panel';
import { L3Panel } from './L3Panel';

function SymbolPicker({ filePath }: { filePath: string }) {
  const data = useDataState();
  const dispatch = useAppDispatch();
  const symbols = useMemo(() => {
    if (data.snapshot.status !== 'ready') return [];
    const index = buildSnapshotIndex(data.snapshot.data.snapshot, data.snapshot.data.topology);
    return index.symbolsByFile.get(filePath) ?? [];
  }, [data.snapshot, filePath]);
  if (symbols.length === 0) {
    return <StateBlock variant="empty" label="This file has no explainable symbols." />;
  }
  return (
    <div className="flex flex-col gap-2 p-3">
      <p className="m-0 text-sm text-muted">Pick a symbol in this file to explain it.</p>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {symbols.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => dispatch({ type: 'select-target', target: { kind: 'symbol', id: s.id, filePath: s.file_path } })}
              className="w-full border border-hairline px-2 py-1 text-left font-mono text-[13px] text-bone hover:border-bone"
            >
              <PlainText text={s.qualname} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LensPanel() {
  const app = useAppState();
  const data = useDataState();
  const snapshot = data.snapshot;
  const index = useMemo(
    () =>
      snapshot.status === 'ready' ? buildSnapshotIndex(snapshot.data.snapshot, snapshot.data.topology) : null,
    [snapshot],
  );
  const target = resolveExplainTarget({
    repoId: app.repoId,
    lens: app.lens,
    file: app.file,
    symbol: app.symbol,
    node: app.node,
    index,
  });
  const targetId = target.kind === 'ok' ? target.targetId : null;
  const { explain, retry: reload } = useExplain(targetId, app.lens);
  const lastError = explain.status === 'error' ? explain.error : null;
  const retry = useRetry(reload, lastError);

  let body;
  if (target.kind === 'pick-symbol') {
    body = <SymbolPicker filePath={target.filePath} />;
  } else if (target.kind === 'none') {
    body = <StateBlock variant="empty" label="Nothing to explain for this selection." />;
  } else if (explain.status === 'error') {
    const presented = presentError(explain.error, 'explain');
    body = presented ? (
      <StateBlock
        variant="error"
        message={presented.message}
        onRetry={retry.retry}
        retryAfterSeconds={retry.secondsLeft ?? presented.retryAfterSeconds}
        healthNote={retry.health === 'unreachable' ? 'The server did not answer the health check.' : undefined}
      />
    ) : null;
  } else if (explain.status === 'ready') {
    const { envelope } = explain.data;
    if (envelope.lens !== app.lens) {
      body = <StateBlock variant="loading" label="Loading explanation" />;
    } else if (envelope.lens === 'L1_SYNTAX') {
      body = <L1Panel l1={envelope.l1} />;
    } else if (envelope.lens === 'L2_FLOW') {
      body = <L2Panel response={explain.data} />;
    } else {
      body = <L3Panel l3={envelope.l3} />;
    }
  } else {
    body = <StateBlock variant="loading" label="Loading explanation" />;
  }

  return (
    <div
      role="tabpanel"
      id={LENS_PANEL_ID}
      aria-labelledby={lensTabId(app.lens)}
      aria-busy={explain.status === 'loading'}
      tabIndex={0}
      className="min-w-0 break-words p-3"
    >
      {body}
    </div>
  );
}
