// Resolves what the Autopsy_Slab is showing (Requirements 18.8, 18.9): a directory under
// L3, else the selected symbol, else the selected file. Shared by the slab header and the
// provenance sections so both read the same subject.
import { useMemo } from 'react';
import type { FileAnalysis, ProvenanceReport, SymbolNode } from '../../api/types';
import { resolveExplainTarget } from '../../core/explainTarget';
import { fileMasteryView, type MasteryPresentation } from '../../core/mastery';
import { buildSnapshotIndex, classifyNode } from '../../core/snapshotIndex';
import { explainKey } from '../../state/dataReducer';
import { useAppState, useDataState } from '../../state/store';

export type SlabSubject =
  | { kind: 'loading' }
  | { kind: 'empty' }
  | { kind: 'directory'; path: string; role: string }
  | {
      kind: 'file' | 'symbol';
      file: FileAnalysis;
      symbol: SymbolNode | null;
      mastery: MasteryPresentation;
      hasState: boolean;
      vitalsReady: boolean;
      /** `cached` or `fresh` when an explain response for the subject is loaded. */
      explainSource: 'cached' | 'fresh' | null;
      provenance: ProvenanceReport;
    };

export function useSlabSubject(): SlabSubject {
  const app = useAppState();
  const data = useDataState();
  const snapshotRemote = data.snapshot;
  const index = useMemo(
    () =>
      snapshotRemote.status === 'ready'
        ? buildSnapshotIndex(snapshotRemote.data.snapshot, snapshotRemote.data.topology)
        : null,
    [snapshotRemote],
  );
  if (snapshotRemote.status === 'loading') return { kind: 'loading' };
  if (snapshotRemote.status !== 'ready' || index === null) return { kind: 'empty' };
  const { provenance } = snapshotRemote.data;
  if (
    app.lens === 'L3_ARCHITECTURE' &&
    app.node !== null &&
    classifyNode(index, undefined, app.node) === 'directory'
  ) {
    return { kind: 'directory', path: app.node, role: String(index.directoryRoles[app.node]) };
  }
  const symbol = app.symbol !== null ? index.symbolsById.get(app.symbol) : undefined;
  const filePath = symbol?.file_path ?? (app.symbol === null ? app.file : null);
  const file = filePath !== null && filePath !== undefined ? index.filesByPath.get(filePath) : undefined;
  if (!file || (app.symbol !== null && !symbol)) return { kind: 'empty' };
  const target = resolveExplainTarget({
    repoId: app.repoId,
    lens: app.lens,
    file: app.file,
    symbol: app.symbol,
    node: app.node,
    index,
  });
  const entry =
    app.repoId !== null && target.kind === 'ok'
      ? data.explain[explainKey(app.repoId, target.targetId, app.lens)]
      : undefined;
  const envelope = entry && entry.status === 'ready' ? entry.data.envelope : null;
  const vitalsReady = data.vitals.status === 'ready';
  const hasState =
    data.vitals.status === 'ready' &&
    Object.prototype.hasOwnProperty.call(data.vitals.data.file_states, file.file_path);
  return {
    kind: symbol ? 'symbol' : 'file',
    file,
    symbol: symbol ?? null,
    mastery: fileMasteryView(data.vitals, file.file_path),
    hasState,
    vitalsReady,
    explainSource: envelope ? (envelope.cached ? 'cached' : 'fresh') : null,
    provenance,
  };
}
