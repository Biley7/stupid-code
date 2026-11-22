// Exorcism Check action (Requirements 9.9 to 9.12, 23.1 to 23.6, 23.17).
// Owns the useSocratic instance and renders the modal.

import { useEffect, useRef } from 'react';
import { useSocratic } from '../../data/useSocratic';
import { useAppState, useDataSelector } from '../../state/store';
import { ExorcismModal } from '../exorcism/ExorcismModal';

export function ExorcismAction() {
  const { repoId, symbol, studyMode } = useAppState();
  const socratic = useSocratic();
  const vitals = useDataSelector((d) => d.vitals);
  const refreshFailed = vitals.status === 'ready' && vitals.refreshFailed === true;

  const { state, close } = socratic;
  const phase = state?.phase;
  const studyOn = studyMode === true;

  // Study Mode off closes the modal, except when it shows the study-off message itself.
  useEffect(() => {
    if (!studyOn && state !== null && phase !== 'study_off' && phase !== 'read_only_off') close();
  }, [studyOn, state, phase, close]);

  // A different symbol or repository closes the modal (the hook also closes on repo change).
  const opened = useRef<{ repoId: string | null; symbol: string | null } | null>(null);
  useEffect(() => {
    const o = opened.current;
    if (state !== null && o !== null && (o.repoId !== repoId || o.symbol !== symbol)) close();
    if (state === null) opened.current = null;
  }, [state, repoId, symbol, close]);

  if (!studyOn && state === null) return null;

  const canOpen = repoId !== null && symbol !== null;
  const symbolLabel = (symbol ?? '').split('::').pop() || (symbol ?? '');

  return (
    <div className="flex flex-col gap-1">
      {studyOn ? (
        <>
          <button
            type="button"
            aria-disabled={!canOpen || state !== null}
            onClick={() => {
              if (!canOpen || state !== null || repoId === null || symbol === null) return;
              opened.current = { repoId, symbol };
              socratic.open(repoId, symbol);
            }}
            className="w-full border border-bone px-3 py-1.5 text-sm font-semibold tracking-wide text-bone hover:bg-bone hover:text-obsidian aria-disabled:border-hairline aria-disabled:text-muted aria-disabled:hover:bg-transparent aria-disabled:hover:text-muted"
          >
            Exorcism Check
          </button>
          {symbol === null ? (
            <p className="m-0 text-xs text-muted">Select a symbol to run an Exorcism Check.</p>
          ) : null}
        </>
      ) : null}
      {state !== null ? (
        <ExorcismModal
          state={state}
          symbolLabel={symbolLabel}
          onClose={socratic.close}
          onType={socratic.type}
          onSubmit={socratic.submit}
          onNewCheck={socratic.newCheck}
          onRestart={socratic.restart}
          onRetry={socratic.retry}
          refreshFailed={refreshFailed}
          onRetryRefresh={socratic.retryRefresh}
        />
      ) : null}
    </div>
  );
}
