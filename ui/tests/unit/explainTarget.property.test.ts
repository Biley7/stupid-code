import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { resolveExplainTarget } from '../../src/core/explainTarget';
import { buildSnapshotIndex } from '../../src/core/snapshotIndex';
import { snapshotResponseArb } from '../fixtures/arbitraries';
import type { Lens } from '../../src/api/types';

const REPO = 'repo-under-test';

/** A snapshot index plus a selection drawn from valid and invalid values. */
const scenario = snapshotResponseArb.chain((resp) => {
  const index = buildSnapshotIndex(resp.snapshot, resp.topology);
  const files = [...index.filesByPath.keys()];
  const symbols = [...index.symbolsById.keys()];
  const dirs = Object.keys(index.directoryRoles);
  const pick = (pool: string[]) =>
    fc.oneof(
      fc.constant(null),
      fc.constant('unknown-id'),
      ...(pool.length > 0 ? [fc.constantFrom(...pool)] : []),
    );
  return fc.record({
    index: fc.constant(index),
    file: pick(files),
    symbol: pick(symbols),
    node: pick([...files, ...symbols, ...dirs]),
  });
});

const flowLens = fc.constantFrom<Lens>('L1_SYNTAX', 'L2_FLOW');

describe('Property 10: Explain targets are never file paths', () => {
  /** **Validates: Requirements 19.3, 19.7, 28.10** */
  it('Property 10: Explain targets are never file paths', () => {
    // Step 1: L1/L2 resolve ok only to the selected symbol id
    {
    fc.assert(
      fc.property(scenario, flowLens, ({ index, file, symbol, node }, lens) => {
        const r = resolveExplainTarget({ repoId: REPO, lens, file, symbol, node, index });
        if (r.kind === 'ok') {
          expect(symbol).not.toBeNull();
          expect(r.targetId).toBe(symbol);
          expect(index.symbolsById.has(r.targetId)).toBe(true);
        }
        if (symbol !== null && index.symbolsById.has(symbol)) {
          expect(r).toEqual({ kind: 'ok', targetId: symbol });
        }
      }),
    );
    }

  /** **Validates: Requirements 19.6, 19.7** */
    // Step 2: L1/L2 with only a file returns pick-symbol, and nothing valid returns none
    {
    fc.assert(
      fc.property(scenario, flowLens, ({ index, file, node }, lens) => {
        const r = resolveExplainTarget({ repoId: REPO, lens, file, symbol: null, node, index });
        if (file !== null && index.filesByPath.has(file)) {
          expect(r).toEqual({ kind: 'pick-symbol', filePath: file });
        } else {
          expect(r).toEqual({ kind: 'none' });
        }
        const none = resolveExplainTarget({ repoId: REPO, lens, file: null, symbol: null, node, index });
        expect(none).toEqual({ kind: 'none' });
      }),
    );
    }

  /** **Validates: Requirements 19.4, 19.5, 19.7, 28.10** */
    // Step 3: L3 resolves to the directory key, else the repo id for a file or symbol, else none
    {
    fc.assert(
      fc.property(scenario, ({ index, file, symbol, node }) => {
        const r = resolveExplainTarget({ repoId: REPO, lens: 'L3_ARCHITECTURE', file, symbol, node, index });
        const isDir =
          node !== null &&
          !index.filesByPath.has(node) &&
          !index.symbolsById.has(node) &&
          Object.prototype.hasOwnProperty.call(index.directoryRoles, node);
        const hasSel =
          (file !== null && index.filesByPath.has(file)) || (symbol !== null && index.symbolsById.has(symbol));
        if (isDir) expect(r).toEqual({ kind: 'ok', targetId: node });
        else if (hasSel) expect(r).toEqual({ kind: 'ok', targetId: REPO });
        else expect(r).toEqual({ kind: 'none' });
      }),
    );
    }

  /** **Validates: Requirements 19.3, 19.4, 19.5, 28.10** */
    // Step 4: never returns a snapshot file path as targetId
    {
    fc.assert(
      fc.property(
        scenario,
        fc.constantFrom<Lens>('L1_SYNTAX', 'L2_FLOW', 'L3_ARCHITECTURE'),
        ({ index, file, symbol, node }, lens) => {
          const r = resolveExplainTarget({ repoId: REPO, lens, file, symbol, node, index });
          if (r.kind === 'ok') expect(index.filesByPath.has(r.targetId)).toBe(false);
        },
      ),
    );
    }

  /** **Validates: Requirements 19.7** */
    // Step 5: returns none without a repository
    {
    fc.assert(
      fc.property(scenario, fc.constantFrom<Lens>('L1_SYNTAX', 'L2_FLOW', 'L3_ARCHITECTURE'), (s, lens) => {
        expect(resolveExplainTarget({ repoId: null, lens, ...s })).toEqual({ kind: 'none' });
      }),
    );
    }
  });
});
