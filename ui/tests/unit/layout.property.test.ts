import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { RepoGraphSnapshot } from '../../src/api/types';
import { buildGraphModel, type Layer } from '../../src/core/graph';
import { layoutGraph, NODE_HEIGHT, NODE_WIDTH } from '../../src/core/layout';
import { snapshotResponseArb } from '../fixtures/arbitraries';

/** Deterministic permutation driven by generated sort keys. */
function permute<T>(items: readonly T[], keys: readonly number[]): T[] {
  return items
    .map((item, i) => ({ item, key: keys[i % Math.max(keys.length, 1)] ?? 0, i }))
    .sort((a, b) => a.key - b.key || a.i - b.i)
    .map((x) => x.item);
}

function permuteSnapshot(s: RepoGraphSnapshot, keys: readonly number[]): RepoGraphSnapshot {
  return {
    ...s,
    files: permute(
      s.files.map((f) => ({ ...f, symbols: permute(f.symbols, keys.slice().reverse()) })),
      keys,
    ),
    edges: permute(s.edges, keys.map((k) => -k)),
  };
}

const keysArb = fc.array(fc.integer({ min: -1000, max: 1000 }), { minLength: 1, maxLength: 16 });
const layerArb = fc.constantFrom<Layer>('files', 'symbols');

describe('Property 4: layout is deterministic and independent of input order', () => {
  // **Validates: Requirements 15.6, 15.8**
  it('Property 4: layout is deterministic and independent of input order', () => {
    // Step 1: is permutation-independent, repeatable, integer-valued, and keeps boxes in bounds
    {
    fc.assert(
      fc.property(snapshotResponseArb, layerArb, keysArb, (resp, layer, keys) => {
        const snap = resp.snapshot;
        const a = layoutGraph(buildGraphModel(snap, layer));
        const again = layoutGraph(buildGraphModel(snap, layer));
        const b = layoutGraph(buildGraphModel(permuteSnapshot(snap, keys), layer));

        for (const other of [again, b]) {
          expect(other.width).toBe(a.width);
          expect(other.height).toBe(a.height);
          expect([...other.positions.entries()].sort()).toEqual([...a.positions.entries()].sort());
        }

        for (const [, p] of a.positions) {
          expect(Number.isInteger(p.x)).toBe(true);
          expect(Number.isInteger(p.y)).toBe(true);
          expect(p.x).toBeGreaterThanOrEqual(0);
          expect(p.y).toBeGreaterThanOrEqual(0);
          expect(p.x + NODE_WIDTH).toBeLessThanOrEqual(a.width);
          expect(p.y + NODE_HEIGHT).toBeLessThanOrEqual(a.height);
        }
      }),
    );
    }

    // Step 2: positions every node, including nodes with no edge
    {
    fc.assert(
      fc.property(snapshotResponseArb, layerArb, (resp, layer) => {
        const model = buildGraphModel(resp.snapshot, layer);
        const result = layoutGraph(model);
        expect(result.positions.size).toBe(model.nodes.length);
        for (const n of model.nodes) expect(result.positions.has(n.id)).toBe(true);
      }),
    );
    }
  });
});
