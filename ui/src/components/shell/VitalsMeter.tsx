// Comprehension vitals (Requirement 8). Counts and percentage are shown verbatim
// from the backend. due_for_review and file_states are intentionally not rendered.
import { useRetry } from '../../data/useRetry';
import { useVitals } from '../../data/useVitals';
import { LiveRegion } from '../shared/LiveRegion';
import { StateBlock } from '../shared/StateBlock';
import { useAppState } from '../../state/store';

export function VitalsMeter() {
  const { repoId } = useAppState();
  const { vitals, reload } = useVitals({ autoload: false });
  const lastError = vitals.status === 'error' ? vitals.error : null;
  const retry = useRetry(() => void reload(), lastError);

  let body;
  let announce = '';
  if (repoId === null || vitals.status === 'idle') {
    body = <span className="text-muted">No repository selected</span>;
  } else if (vitals.status === 'loading') {
    body = <StateBlock variant="loading" label="Loading vitals" className="p-0" />;
  } else if (vitals.status === 'error') {
    body = (
      <StateBlock
        variant="error"
        message={vitals.error.message}
        onRetry={retry.retry}
        retryAfterSeconds={retry.secondsLeft ?? undefined}
        healthNote={retry.health === 'unreachable' ? 'The server did not answer the health check.' : undefined}
        className="p-1"
      />
    );
  } else {
    const v = vitals.data;
    if (v.total_modules === 0) {
      body = <StateBlock variant="empty" label="No modules to measure" className="p-0" />;
      announce = 'No modules to measure';
    } else {
      announce = `${v.mastery_percentage} percent mastered, ${v.mastered_count} of ${v.total_modules} modules`;
      const pct = (n: number): string => `${Math.max(0, Math.min(100, (n / v.total_modules) * 100))}%`;
      body = (
        <div className="flex min-w-0 flex-col gap-1">
          <div
            role="progressbar"
            aria-label="Mastery progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={v.mastery_percentage}
            aria-valuetext={`${v.mastery_percentage}% mastered`}
            className="flex h-2 w-full overflow-hidden border border-hairline bg-obsidian"
          >
            <span className="h-full bg-verified" style={{ width: pct(v.mastered_count) }} />
            <span className="h-full bg-stale" style={{ width: pct(v.stale_count) }} />
            <span className="h-full bg-muted" style={{ width: pct(v.dissected_count) }} />
            <span className="h-full bg-crimson" style={{ width: pct(v.unaudited_count) }} />
          </div>
          <dl className="m-0 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] tabular-nums">
            <div className="flex gap-1">
              <dt className="text-muted">Modules</dt>
              <dd className="m-0 text-bone">{v.total_modules}</dd>
            </div>
            <div className="flex items-center gap-1">
              <dt className="text-muted">Unaudited</dt>
              <dd className="m-0 text-signal">{v.unaudited_count}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-muted">Dissected</dt>
              <dd className="m-0 text-bone">{v.dissected_count}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-muted">Mastered</dt>
              <dd className="m-0 text-verified">{v.mastered_count}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-muted">Stale</dt>
              <dd className="m-0 text-stale">{v.stale_count}</dd>
            </div>
            <div className="ml-auto flex gap-1 font-semibold">
              <dt className="text-muted">Mastery</dt>
              <dd className="m-0 text-bone">{v.mastery_percentage}%</dd>
            </div>
          </dl>
        </div>
      );
      if (vitals.refreshFailed) {
        body = (
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1">{body}</div>
            <span role="status" className="text-xs text-stale">
              Out of date
            </span>
            <button
              type="button"
              onClick={retry.retry}
              disabled={retry.disabled}
              className="border border-hairline px-2 py-0.5 text-xs text-bone"
            >
              Retry
            </button>
          </div>
        );
      }
    }
  }

  return (
    <section aria-label="Comprehension vitals" className="text-sm">
      {body}
      <LiveRegion message={announce} />
    </section>
  );
}
