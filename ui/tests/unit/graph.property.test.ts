import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import type { RepoGraphSnapshot } from '../../src/api/types';
import { buildGraphModel, highlightFor, type Layer } from '../../src/core/graph';
import { snapshotResponseArb } from '../fixtures/arbitraries';

const RUNS = { numRuns: 100, seed: 5 };
const EDGE_TYPE: Record<Layer, string> = { files: 'imports', symbols: 'calls' };

const snapshotArb = snapshotResponseArb.map((r) => r.snapshot);
const layerArb = fc.constantFrom<Layer>('files', 'symbols');

/** Ids that the snapshot offers for a layer, with possible duplicates preserved. */
function layerIds(snapshot: RepoGraphSnapshot, layer: Layer): string[] {
  return layer === 'files'
    ? snapshot.files.map((f) => f.file_path)
    : snapshot.files.flatMap((f) => f.symbols.map((s) => s.id));
}

const pairKey = (s: string, t: string) => JSON.stringify([s, t]);

describe('Property 5: graph model respects layers, cycles, and one-hop neighborhoods', () => {
  it('Property 5: graph model respects layers, cycles, and one-hop neighborhoods', () => {
    // Step 1: nodes are exactly the layer ids of the snapshot, without duplicates
    {
    /** **Validates: Requirements 15.3, 15.4** */
    fc.assert(
      fc.property(snapshotArb, layerArb, (snapshot, layer) => {
        const model = buildGraphModel(snapshot, layer);
        const ids = model.nodes.map((n) => n.id);
        expect(new Set(ids).size).toBe(ids.length);
        expect(new Set(ids)).toEqual(new Set(layerIds(snapshot, layer)));
      }),
      RUNS,
    );
    }

    // Step 2: keeps every matching edge between nodes and nothing else
    {
    /** **Validates: Requirements 15.3, 15.4, 15.5** */
    fc.assert(
      fc.property(snapshotArb, layerArb, (snapshot, layer) => {
        const model = buildGraphModel(snapshot, layer);
        const nodeIds = new Set(model.nodes.map((n) => n.id));
        const expected = new Set(
          snapshot.edges
            .filter(
              (e) => e.edge_type === EDGE_TYPE[layer] && nodeIds.has(e.source) && nodeIds.has(e.target),
            )
            .map((e) => pairKey(e.source, e.target)),
        );
        const actual = model.edges.map((e) => pairKey(e.source, e.target));
        expect(new Set(actual).size).toBe(actual.length);
        expect(new Set(actual)).toEqual(expected);
        for (const e of model.edges) {
          expect(e.edgeType).toBe(EDGE_TYPE[layer]);
          expect(nodeIds.has(e.source)).toBe(true);
          expect(nodeIds.has(e.target)).toBe(true);
        }
      }),
      RUNS,
    );
    }

    // Step 3: marks an edge circular iff its endpoints share a cycle entry
    {
    /** **Validates: Requirements 15.9** */
    fc.assert(
      fc.property(snapshotArb, layerArb, (snapshot, layer) => {
        const model = buildGraphModel(snapshot, layer);
        for (const e of model.edges) {
          const expected = snapshot.cycles.some(
            (entry) => entry.includes(e.source) && entry.includes(e.target),
          );
          expect(e.circular).toBe(expected);
          expect(model.circularEdgeIds.has(e.id)).toBe(expected);
        }
        expect(model.circularEdgeIds.size).toBe(model.edges.filter((e) => e.circular).length);
      }),
      RUNS,
    );
    }

    // Step 4: highlightFor returns the exact one-hop neighborhood restricted to layer nodes
    {
    /** **Validates: Requirements 16.2, 16.8** */
    fc.assert(
      fc.property(
        snapshotArb,
        layerArb,
        fc.string({ maxLength: 10 }),
        fc.nat(),
        (snapshot, layer, stranger, pick) => {
          const model = buildGraphModel(snapshot, layer);
          const ids = model.nodes.map((n) => n.id);
          const candidates = [...ids, stranger, ...snapshot.edges.flatMap((e) => [e.source, e.target])];
          const id = candidates[pick % candidates.length] ?? stranger;
          const h = highlightFor(model, id);
          if (!ids.includes(id)) {
            expect(h.selected).toBeNull();
            expect(h.upstream.size).toBe(0);
            expect(h.downstream.size).toBe(0);
            expect(h.blast.size).toBe(0);
            return;
          }
          expect(h.selected).toBe(id);
          expect(new Set(h.upstream)).toEqual(
            new Set(model.edges.filter((e) => e.target === id).map((e) => e.source)),
          );
          expect(new Set(h.downstream)).toEqual(
            new Set(model.edges.filter((e) => e.source === id).map((e) => e.target)),
          );
          for (const n of [...h.upstream, ...h.downstream]) expect(ids.includes(n)).toBe(true);
        },
      ),
      RUNS,
    );
    }

    // Step 5: blast ids from an explain result never include non-layer nodes
    {
    /** **Validates: Requirements 16.2, 16.8** */
    fc.assert(
      fc.property(snapshotArb, layerArb, (snapshot, layer) => {
        const model = buildGraphModel(snapshot, layer);
        const first = model.nodes[0];
        if (first === undefined) return;
        const h = highlightFor(model, first.id, {
          target_id: first.id,
          upstream_callers: [first.id, '__absent__'],
          downstream_callees: ['__absent_too__'],
          impact_score: 0,
        } as never);
        const ids = new Set(model.nodes.map((n) => n.id));
        for (const b of h.blast) expect(ids.has(b)).toBe(true);
        expect(h.blast.has('__absent__')).toBe(false);
        expect(h.blast.has('__absent_too__')).toBe(false);
      }),
      RUNS,
    );
    }
  });
});
