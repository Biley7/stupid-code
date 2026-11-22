// Folder topology blueprint (Requirement 17). Shows only what the Backend_API
// returned, as plain text. Directory rows offer only L3 (Requirement 17.6).
import { useMemo } from 'react';
import { presentError } from '../../core/present';
import { useSnapshot } from '../../data/useSnapshot';
import { useAppDispatch, useAppState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

const KNOWN_ROLES = new Set([
  'domain',
  'engines',
  'api',
  'ui',
  'tests',
  'config',
  'infrastructure',
  'services',
]);

export function TopologyView() {
  const { repoId, node } = useAppState();
  const dispatch = useAppDispatch();
  const { snapshot, reload } = useSnapshot({ autoload: false });
  const topology = snapshot.status === 'ready' ? snapshot.data.topology : null;
  const dirs = useMemo(
    () => (topology ? Object.keys(topology.directory_roles).sort() : []),
    [topology],
  );

  if (repoId === null || snapshot.status === 'idle') {
    return <StateBlock variant="empty" label="No repository selected." />;
  }
  if (snapshot.status === 'loading') {
    return <StateBlock variant="loading" label="Loading topology…" />;
  }
  if (snapshot.status === 'error') {
    const presented = presentError(snapshot.error, 'generic');
    if (presented === null) return <StateBlock variant="loading" label="Loading topology…" />;
    return (
      <StateBlock
        variant="error"
        message={presented.message}
        onRetry={presented.retryable ? () => void reload() : undefined}
        retryAfterSeconds={presented.retryAfterSeconds}
      />
    );
  }
  if (topology === null) return <StateBlock variant="empty" label="No topology is available." />;

  const m = topology.boundary_metrics;
  const metrics: Array<[string, string]> = [
    ['domain_isolation_score', m.domain_isolation_score.toFixed(2)],
    ['cross_folder_import_ratio', m.cross_folder_import_ratio.toFixed(2)],
    ['max_depth', String(Math.trunc(m.max_depth))],
    ['entry_point_count', String(Math.trunc(m.entry_point_count))],
  ];

  return (
    <div className="space-y-4 p-3 text-sm text-bone">
      <section aria-label="Detected pattern">
        <PlainText text={topology.detected_pattern} as="h2" className="text-base font-semibold" />
        <p className="font-mono text-xs text-muted">
          Confidence {Math.round(topology.confidence * 100)}%
        </p>
      </section>

      <section aria-label="Boundary metrics">
        <h3 className="text-xs uppercase tracking-wide text-muted">Boundary metrics</h3>
        <dl className="m-0 mt-1 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          {metrics.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="font-mono text-xs text-muted">{key}</dt>
              <dd className="m-0 font-mono text-xs">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-label="Directory roles">
        <h3 className="text-xs uppercase tracking-wide text-muted">Directory roles</h3>
        {dirs.length === 0 ? (
          <StateBlock variant="empty" label="The backend reported no directory roles." />
        ) : (
          <ul className="m-0 mt-1 list-none p-0">
            {dirs.map((dir) => {
              const role: string = topology.directory_roles[dir] ?? '';
              const selected = node === dir;
              const known = KNOWN_ROLES.has(role);
              return (
                <li key={dir}>
                  <button
                    type="button"
                    aria-current={selected ? 'true' : undefined}
                    onClick={() => dispatch({ type: 'select-directory', dir })}
                    className={`flex w-full items-baseline justify-between gap-3 border-l-2 px-2 py-1 text-left ${
                      selected ? 'border-bone bg-surface text-bone' : 'border-transparent text-muted'
                    }`}
                  >
                    <PlainText text={dir} className="min-w-0 break-all font-mono text-xs" />
                    <PlainText
                      text={role}
                      className={`font-mono text-xs ${known ? 'text-bone' : 'text-muted'}`}
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-label="Evidence">
        <h3 className="text-xs uppercase tracking-wide text-muted">Evidence</h3>
        {topology.evidence.length === 0 ? (
          <StateBlock variant="empty" label="The backend reported no evidence." />
        ) : (
          <ol className="m-0 mt-1 list-decimal pl-5">
            {topology.evidence.map((line, i) => (
              <li key={i}>
                <PlainText text={line} />
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
