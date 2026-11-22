// Vital organs quick-jump (Requirement 13). Lists `snapshot.vital_organs` in the
// backend order with no re-sorting, deduplication, or dropped entry, and shows no
// rank or score the backend did not return.
import { useMemo } from 'react';
import { buildSnapshotIndex, resolveTarget } from '../../core/snapshotIndex';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

export function VitalOrgansList() {
  const snapshot = useDataState().snapshot;
  const { node } = useAppState();
  const dispatch = useAppDispatch();

  const data = snapshot.status === 'ready' ? snapshot.data.snapshot : null;
  const index = useMemo(() => (data ? buildSnapshotIndex(data) : null), [data]);

  if (!data || !index) return null;
  if (data.vital_organs.length === 0) {
    return <StateBlock variant="empty" label="The backend reported no vital organs." />;
  }

  return (
    <ul aria-label="Vital organs" className="m-0 list-none p-0">
      {data.vital_organs.map((id, i) => {
        const target = resolveTarget(index, id);
        const sym = target?.kind === 'symbol' ? index.symbolsById.get(target.id) : undefined;
        const label = target === null ? 'UNRESOLVED' : target.kind === 'file' ? 'FILE' : 'SYMBOL';
        const selected = target !== null && node === id;
        return (
          <li key={`${i}:${id}`}>
            <button
              type="button"
              aria-current={selected ? 'true' : undefined}
              aria-disabled={target === null ? true : undefined}
              onClick={() => {
                if (target) dispatch({ type: 'select-target', target });
              }}
              className={`flex w-full items-start gap-2 border-l-2 px-2 py-1 text-left text-sm ${
                selected ? 'border-bone bg-surface text-bone' : 'border-transparent text-muted'
              } ${target === null ? 'cursor-not-allowed' : ''}`}
            >
              <span aria-hidden="true" className="font-mono">
                {selected ? '▶' : target?.kind === 'file' ? '▤' : target ? 'ƒ' : '?'}
              </span>
              <span className="min-w-0 flex-1">
                <span className="font-mono text-xs">{label}</span>{' '}
                {sym ? (
                  <>
                    <PlainText text={sym.qualname} className="font-mono text-bone" />
                    <PlainText text={sym.file_path} as="div" className="font-mono text-xs break-all" />
                  </>
                ) : (
                  <PlainText text={id} className="font-mono break-all" />
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
