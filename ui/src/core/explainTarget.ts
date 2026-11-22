import type { Lens } from '../api/types';
import { classifyNode, type SnapshotIndex } from './snapshotIndex';

export type ExplainTarget =
  | { kind: 'ok'; targetId: string }
  | { kind: 'pick-symbol'; filePath: string }
  | { kind: 'none' };

export interface ExplainTargetInput {
  repoId: string | null;
  lens: Lens;
  file: string | null;
  symbol: string | null;
  node: string | null;
  index: SnapshotIndex | null;
}

const NONE: ExplainTarget = { kind: 'none' };

/**
 * Resolves the explain target for the current selection. The target id is a
 * symbol id (L1, L2), a directory key, or the repo id (L3). It is never a file path.
 */
export function resolveExplainTarget(input: ExplainTargetInput): ExplainTarget {
  const { repoId, lens, file, symbol, node, index } = input;
  if (repoId === null || repoId === '') return NONE;

  if (lens === 'L3_ARCHITECTURE') {
    if (index !== null && node !== null && classifyNode(index, undefined, node) === 'directory') {
      return { kind: 'ok', targetId: node };
    }
    const hasValidSelection =
      index !== null &&
      ((file !== null && index.filesByPath.has(file)) || (symbol !== null && index.symbolsById.has(symbol)));
    return hasValidSelection ? { kind: 'ok', targetId: repoId } : NONE;
  }

  if (index === null) return NONE;
  if (symbol !== null && index.symbolsById.has(symbol)) {
    return { kind: 'ok', targetId: symbol };
  }
  if (symbol === null && file !== null && index.filesByPath.has(file)) {
    return { kind: 'pick-symbol', filePath: file };
  }
  return NONE;
}
