// Vital organs quick-jump (Requirement 13). Lists `snapshot.vital_organs` in the
// backend order with no re-sorting or deduplication, and shows no rank or score the
// backend did not return. A display filter hides test files by default so production
// architecture modules come first; it falls back to the full list when every entry is a
// test file, and a toggle brings the hidden entries back.
import { useMemo, useState } from 'react';
import { buildSnapshotIndex, resolveTarget } from '../../core/snapshotIndex';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

const TEST_DIRS = new Set(['tests', 'test', '__tests__']);

/** True for `tests/` directories, `test_*.py`, `*_test.py`, `conftest.py`, and `*.test.*` / `*.spec.*` files. */
export function isTestPath(id: string): boolean {
  const filePath = id.split('::')[0] ?? id;
  const segments = filePath.split('/').filter((s) => s !== '');
  const base = segments[segments.length - 1] ?? '';
  const dirs = segments.slice(0, -1);
  if (dirs.some((d) => TEST_DIRS.has(d))) return true;
  return (
    base === 'conftest.py' ||
    /^test_.*\.py$/.test(base) ||
    /_test\.py$/.test(base) ||
    /\.(test|spec)\.[a-z]+$/.test(base)
  );
}

export function VitalOrgansList() {
  const snapshot = useDataState().snapshot;
  const { node } = useAppState();
  const dispatch = useAppDispatch();
  const [showTests, setShowTests] = useState(false);
  const data = snapshot.status === 'ready' ? snapshot.data.snapshot : null;
  const index = useMemo(() => (data ? buildSnapshotIndex(data) : null), [data]);
  const split = useMemo(() => {
    const organs = data?.vital_organs ?? [];
    const production = organs.filter((id) => !isTestPath(id));
    // Every entry is a test file: show them all rather than an empty list.
    if (production.length === 0) return { visible: organs, hidden: 0, fallback: organs.length > 0 };
    return { visible: showTests ? organs : production, hidden: organs.length - production.length, fallback: false };
  }, [data, showTests]);
  if (!data || !index) return null;
  if (data.vital_organs.length === 0) {
    return <StateBlock variant="empty" label="The backend reported no vital organs." />;
  }
  return (
    <div>
      <ul aria-label="Vital organs" className="m-0 list-none p-0">
        {split.visible.map((id, i) => {
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
                className={`flex w-full items-start gap-2 border-l-2 px-3 py-1.5 text-left text-sm hover:bg-obsidian ${
                  selected ? 'border-bone bg-obsidian text-bone' : 'border-transparent text-muted'
                } ${target === null ? 'cursor-not-allowed' : ''}`}
              >
                <span aria-hidden="true" className="w-3 shrink-0 text-center font-mono text-xs leading-5">
                  {selected ? '▶' : target?.kind === 'file' ? '▤' : target ? 'ƒ' : '?'}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</span>{' '}
                  {sym ? (
                    <>
                      <PlainText text={sym.qualname} as="div" className="break-all font-mono text-[13px] text-bone" />
                      <PlainText text={sym.file_path} as="div" className="break-all font-mono text-[11px]" />
                    </>
                  ) : (
                    <PlainText text={id} as="div" className="break-all font-mono text-[13px]" />
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {split.hidden > 0 ? (
        <button
          type="button"
          aria-pressed={showTests}
          onClick={() => setShowTests((v) => !v)}
          className="mx-3 mt-1 text-[11px] text-muted underline-offset-2 hover:text-bone hover:underline"
        >
          {showTests ? 'Hide' : 'Show'} {split.hidden} test {split.hidden === 1 ? 'file' : 'files'}
        </button>
      ) : null}
      {split.fallback ? (
        <p className="m-0 px-3 pt-1 text-[11px] text-muted">Only test files were reported.</p>
      ) : null}
    </div>
  );
}
