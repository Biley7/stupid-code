import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { ApiNetworkError } from '../../src/api/errors';
import {
  dataReducer,
  initialDataState,
  type DataAction,
  type DataState,
} from '../../src/state/dataReducer';

const REPOS = ['repo-a', 'repo-b', 'repo-c'];
const KEYS = ['k1', 'k2'];

const repoId = fc.constantFrom(...REPOS);
const key = fc.constantFrom(...KEYS);
const seq = fc.integer({ min: -1, max: 6 });
const error = new ApiNetworkError();
// The reducer stores response data opaquely, so a tagged marker stands in for it.
const marker = (n: number) => ({ marker: n }) as never;

const action: fc.Arbitrary<DataAction> = fc.oneof(
  fc.record({ type: fc.constant('repo-selected' as const), repoId: fc.oneof(repoId, fc.constant(null)) }),
  fc.constant<DataAction>({ type: 'resource-start', resource: 'repos' }),
  fc.record({
    type: fc.constant('resource-start' as const),
    resource: fc.constantFrom('snapshot' as const, 'vitals' as const),
    repoId,
    mode: fc.constantFrom('replace' as const, 'keep' as const),
  }),
  fc.record({ type: fc.constant('resource-start' as const), resource: fc.constant('explain' as const), repoId, key }),
  fc.record({ type: fc.constant('resource-success' as const), resource: fc.constant('repos' as const), seq, data: fc.constant([]) }),
  fc.record({
    type: fc.constant('resource-success' as const),
    resource: fc.constantFrom('snapshot' as const, 'vitals' as const),
    repoId,
    seq,
    data: fc.integer().map(marker),
  }),
  fc.record({
    type: fc.constant('resource-success' as const),
    resource: fc.constant('explain' as const),
    repoId,
    key,
    seq,
    data: fc.integer().map(marker),
  }),
  fc.record({ type: fc.constant('resource-failure' as const), resource: fc.constant('repos' as const), seq, error: fc.constant(error) }),
  fc.record({
    type: fc.constant('resource-failure' as const),
    resource: fc.constantFrom('snapshot' as const, 'vitals' as const),
    repoId,
    seq,
    error: fc.constant(error),
    mode: fc.constantFrom('replace' as const, 'keep' as const),
  }),
  fc.record({
    type: fc.constant('resource-failure' as const),
    resource: fc.constant('explain' as const),
    repoId,
    key,
    seq,
    error: fc.constant(error),
  }),
) as fc.Arbitrary<DataAction>;

const actions = fc.array(action, { maxLength: 40 });

function isStaleResponse(state: DataState, a: DataAction): boolean {
  if (a.type !== 'resource-success' && a.type !== 'resource-failure') return false;
  if (a.resource === 'repos') return a.seq !== state.seq.repos;
  if (a.repoId !== state.repoId) return true;
  const latest = a.resource === 'explain' ? state.seq.explain[a.key] : state.seq[a.resource];
  return a.seq !== latest;
}

describe('Property 9: stale responses never change data state', () => {
  /** **Validates: Requirements 4.14, 8.9, 25.9** */
  it('Property 9: stale responses never change data state', () => {
    // Step 1: stale or foreign-repository responses leave the state reference unchanged
    {
    fc.assert(
      fc.property(actions, (sequence) => {
        let state = initialDataState;
        for (const a of sequence) {
          const next = dataReducer(state, a);
          if (isStaleResponse(state, a)) expect(next).toBe(state);
          state = next;
        }
      }),
    );
    }

  /** **Validates: Requirements 4.4, 8.10, 25.10** */
    // Step 2: holds no data of the previous repository after a repository change
    {
    fc.assert(
      fc.property(actions, repoId, (sequence, target) => {
        let state = initialDataState;
        for (const a of sequence) state = dataReducer(state, a);
        const next = dataReducer(state, { type: 'repo-selected', repoId: target });
        if (target === state.repoId) {
          expect(next).toBe(state);
          return;
        }
        expect(next.repoId).toBe(target);
        expect(next.snapshot).toEqual({ status: 'idle' });
        expect(next.vitals).toEqual({ status: 'idle' });
        expect(next.explain).toEqual({});
      }),
    );
    }

  /** **Validates: Requirements 8.9, 8.10, 25.9, 25.10** */
    // Step 3: responses issued before a repository change cannot land after it
    {
    fc.assert(
      fc.property(
        repoId,
        repoId,
        fc.constantFrom('snapshot' as const, 'vitals' as const),
        (first, second, resource) => {
          fc.pre(first !== second);
          let state = dataReducer(initialDataState, { type: 'repo-selected', repoId: first });
          state = dataReducer(state, { type: 'resource-start', resource, repoId: first });
          const oldSeq = state.seq[resource];
          state = dataReducer(state, { type: 'repo-selected', repoId: second });
          state = dataReducer(state, { type: 'resource-start', resource, repoId: second });
          const before = state;
          for (const rid of [first, second]) {
            const stale = dataReducer(state, { type: 'resource-success', resource, repoId: rid, seq: oldSeq + 1 + 10, data: marker(1) });
            expect(stale).toBe(before);
          }
          const late = dataReducer(state, { type: 'resource-success', resource, repoId: first, seq: oldSeq, data: marker(1) });
          expect(late).toBe(before);
        },
      ),
    );
    }

  /** **Validates: Requirements 8.9, 25.10** */
    // Step 4: final data equals the most recently started request, whatever the arrival order
    {
    const scenario = fc
      .record({
        resource: fc.constantFrom('snapshot' as const, 'vitals' as const, 'explain' as const),
        count: fc.integer({ min: 1, max: 6 }),
      })
      .chain(({ resource, count }) =>
        fc.record({
          resource: fc.constant(resource),
          count: fc.constant(count),
          order: fc.shuffledSubarray(Array.from({ length: count }, (_, i) => i), { minLength: count, maxLength: count }),
          failures: fc.array(fc.boolean(), { minLength: count, maxLength: count }),
        }),
      );
    fc.assert(
      fc.property(scenario, ({ resource, count, order, failures }) => {
        const id = 'repo-a';
        const k = 'k1';
        let state = dataReducer(initialDataState, { type: 'repo-selected', repoId: id });
        const seqs: number[] = [];
        for (let i = 0; i < count; i += 1) {
          state =
            resource === 'explain'
              ? dataReducer(state, { type: 'resource-start', resource, repoId: id, key: k })
              : dataReducer(state, { type: 'resource-start', resource, repoId: id });
          seqs.push(resource === 'explain' ? state.seq.explain[k]! : state.seq[resource]);
        }
        for (const i of order) {
          const s = seqs[i]!;
          const a: DataAction =
            resource === 'explain'
              ? failures[i]
                ? { type: 'resource-failure', resource, repoId: id, key: k, seq: s, error }
                : { type: 'resource-success', resource, repoId: id, key: k, seq: s, data: marker(i) }
              : failures[i]
                ? { type: 'resource-failure', resource, repoId: id, seq: s, error }
                : { type: 'resource-success', resource, repoId: id, seq: s, data: marker(i) };
          state = dataReducer(state, a);
        }
        const last = count - 1;
        const result = resource === 'explain' ? state.explain[k] : state[resource];
        if (failures[last]) {
          expect(result).toEqual({ status: 'error', error });
        } else {
          expect(result).toEqual({ status: 'ready', data: marker(last) });
        }
      }),
    );
    }
  });
});
