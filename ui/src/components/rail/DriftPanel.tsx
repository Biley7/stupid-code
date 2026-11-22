// Spec drift and provenance panel (Requirement 14). Lists the backend's drift
// items in order, filters them locally by type, and shows spec links for the
// selected file. No drift is computed here and recent commits are not shown
// (the Autopsy_Slab owns them, Requirement 14.17).
import { useMemo, useState } from 'react';
import type { DriftItem } from '../../api/types';
import { presentError } from '../../core/present';
import { buildSnapshotIndex, resolveTarget } from '../../core/snapshotIndex';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

type DriftFilter = 'All' | 'UNSPECIFIED_CODE' | 'UNIMPLEMENTED_SPEC';
const FILTERS: readonly DriftFilter[] = ['All', 'UNSPECIFIED_CODE', 'UNIMPLEMENTED_SPEC'];

export function DriftPanel() {
  const snapshot = useDataState().snapshot;
  const { repoId, file, node } = useAppState();
  // Keyed by repository so the filter returns to `All` when the repository changes.
  const [filterState, setFilterState] = useState<{ repoId: string | null; value: DriftFilter }>({
    repoId,
    value: 'All',
  });
  const filter: DriftFilter = filterState.repoId === repoId ? filterState.value : 'All';
  const dispatch = useAppDispatch();

  const data = snapshot.status === 'ready' ? snapshot.data : null;
  const index = useMemo(() => (data ? buildSnapshotIndex(data.snapshot) : null), [data]);

  if (snapshot.status === 'idle') return null;
  if (snapshot.status === 'loading') {
    return <StateBlock variant="loading" label="Loading provenance…" />;
  }
  if (snapshot.status === 'error') {
    const presented = presentError(snapshot.error, 'generic');
    if (!presented) return null;
    return <StateBlock variant="error" message={presented.message} />;
  }
  if (!data || !index) return null;

  const provenance = data.provenance;
  if (!provenance.has_kiro_specs) {
    return (
      <StateBlock variant="empty" label="This repository has no .kiro/specs/ documents." />
    );
  }

  const items = provenance.drift_items;
  const count = (f: DriftFilter): number =>
    f === 'All' ? items.length : items.filter((i) => i.drift_type === f).length;
  const visible: DriftItem[] = filter === 'All' ? items : items.filter((i) => i.drift_type === filter);
  const links = file !== null ? (provenance.spec_links[file] ?? []) : [];

  return (
    <section aria-label="Spec drift" className="text-sm">
      {items.length === 0 ? (
        <StateBlock variant="empty" label="No drift was detected." />
      ) : null}

      <div role="group" aria-label="Drift filter" className="flex flex-wrap gap-1 p-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            onClick={() => setFilterState({ repoId, value: f })}
            className={`border px-2 py-1 text-[11px] font-medium ${
              filter === f ? 'border-bone text-bone' : 'border-hairline text-muted'
            }`}
          >
            {f} ({count(f)})
          </button>
        ))}
      </div>

      {items.length > 0 && visible.length === 0 ? (
        <StateBlock variant="empty" label="No entries of this type" />
      ) : null}

      {visible.length > 0 ? (
        <ul aria-label="Drift entries" className="m-0 list-none p-0">
          {visible.map((item, i) => {
            const target = resolveTarget(index, item.target);
            // Requirement 14.7 selects files only; a symbol id is not a drift target.
            const navigable = target !== null && target.kind === 'file';
            const selected = navigable && node === item.target;
            return (
              <li key={`${i}:${item.drift_type}:${item.target}`}>
                <button
                  type="button"
                  aria-label={`${item.drift_type} ${item.target}`}
                  aria-current={selected ? 'true' : undefined}
                  aria-disabled={navigable ? undefined : true}
                  onClick={() => {
                    if (navigable && target) dispatch({ type: 'select-target', target });
                  }}
                  className={`block w-full border-l-2 border-crimson px-2 py-1 text-left ${
                    selected ? 'bg-surface text-bone' : 'text-muted'
                  } ${navigable ? '' : 'cursor-not-allowed'}`}
                >
                  <PlainText text={item.drift_type} as="div" className="text-[11px] font-semibold tracking-wide text-signal" />
                  <PlainText text={item.target} as="div" className="break-all font-mono text-[13px] text-bone" />
                  <PlainText text={item.details} as="div" className="break-words text-xs" />
                  {navigable ? null : (
                    <span className="text-[11px] font-medium text-muted">NOT IN SNAPSHOT</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}

      {file !== null ? (
        <div aria-label="Spec links" role="region" className="mt-2 border-t border-hairline p-2">
          {links.length === 0 ? (
            <PlainText text="No spec links for this file" as="p" className="text-muted" />
          ) : (
            <ul className="m-0 list-none p-0">
              {links.map((link, i) => (
                <li key={`${i}:${link.spec_name}:${link.section_title}`} className="mb-2">
                  <PlainText text={link.spec_name} as="div" className="break-words text-bone" />
                  <PlainText text={link.source_file} as="div" className="break-all font-mono text-xs text-muted" />
                  <PlainText text={link.section_title} as="div" className="text-bone" />
                  <PlainText text={link.excerpt} as="div" className="break-words text-xs text-muted" />
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}
