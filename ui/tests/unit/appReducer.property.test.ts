import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { appReducer, type AppAction, type AppState } from '../../src/state/appReducer';
import { buildSnapshotIndex, resolveTarget, type SnapshotIndex } from '../../src/core/snapshotIndex';
import { snapshotResponseArb } from '../fixtures/arbitraries';
import type { Lens } from '../../src/api/types';
import type { VisualMode } from '../../src/core/mastery';

const lensArb = fc.constantFrom<Lens>('L1_SYNTAX', 'L2_FLOW', 'L3_ARCHITECTURE');
const visualArb = fc.constantFrom<VisualMode>('Autopsy', 'Lab');
const maybe = fc.option(fc.string({ maxLength: 8 }), { nil: null });

const stateArb: fc.Arbitrary<AppState> = fc.record({
  repoId: maybe,
  file: maybe,
  symbol: maybe,
  node: maybe,
  view: fc.constantFrom<'graph' | 'topology'>('graph', 'topology'),
  lens: lensArb,
  studyMode: fc.constantFrom<boolean | 'unknown'>(true, false, 'unknown'),
  visualMode: visualArb,
});

/**
 * Actions as the UI dispatches them: a selection target is first resolved against the index and
 * nothing is dispatched when it is absent (Requirement 4.9).
 */
function actionArb(index: SnapshotIndex): fc.Arbitrary<AppAction | null> {
  const ids = [...index.filesByPath.keys(), ...index.symbolsById.keys()];
  const dirs = Object.keys(index.directoryRoles);
  const rawTarget = fc.oneof(
    fc.constant('absent-target-id'),
    fc.string({ maxLength: 8 }),
    ...(ids.length > 0 ? [fc.constantFrom(...ids)] : []),
  );
  return fc.oneof(
    rawTarget.map((raw) => {
      const target = resolveTarget(index, raw);
      return target ? ({ type: 'select-target', target } as AppAction) : null;
    }),
    fc.oneof(fc.string({ maxLength: 8 }), ...(dirs.length > 0 ? [fc.constantFrom(...dirs)] : [])).map(
      (dir): AppAction => ({ type: 'select-directory', dir }),
    ),
    fc.constant<AppAction>({ type: 'node-cleared' }),
    fc.boolean().map((keepNode): AppAction => ({ type: 'layer-changed', keepNode })),
    fc.constantFrom<'graph' | 'topology'>('graph', 'topology').map((value): AppAction => ({ type: 'view-set', value })),
    lensArb.map((value): AppAction => ({ type: 'lens-set', value })),
    fc.constantFrom<boolean | 'unknown'>(true, false, 'unknown').map(
      (value): AppAction => ({ type: 'study-mode-set', value }),
    ),
    visualArb.map((value): AppAction => ({ type: 'visual-mode-set', value })),
    maybe.map((repoId): AppAction => ({ type: 'repo-selected', repoId })),
  );
}

const scenario = snapshotResponseArb.chain((resp) => {
  const index = buildSnapshotIndex(resp.snapshot, resp.topology);
  return fc.record({
    index: fc.constant(index),
    start: stateArb,
    actions: fc.array(actionArb(index), { maxLength: 25 }),
  });
});

const sel = (s: AppState) => [s.file, s.symbol, s.node] as const;

describe('appReducer', () => {
  // Feature: 04-autopsy-ui, Property 6: Selection updates are atomic, validated, and idempotent
  /** **Validates: Requirements 4.4, 4.6, 4.7, 4.8, 4.9, 4.10, 9.14, 10.5, 17.9, 19.2** */
  it('Property 6: selection updates are atomic, validated, and idempotent', () => {
    fc.assert(
      fc.property(scenario, ({ index, start, actions }) => {
        let state = start;
        for (const action of actions) {
          const prev = state;
          if (action === null) continue; // absent target: nothing is dispatched, state untouched
          state = appReducer(prev, action);

          // Atomic: (file, symbol, node) is either the previous tuple or exactly the specified one.
          const unchanged = sel(state).every((v, i) => v === sel(prev)[i]);
          switch (action.type) {
            case 'select-target': {
              const t = action.target;
              if (t.kind === 'file') {
                expect(sel(state)).toEqual([t.path, null, t.path]);
              } else {
                expect(sel(state)).toEqual([index.symbolsById.get(t.id)!.file_path, t.id, t.id]);
              }
              // Idempotent: selecting the current target returns the same reference.
              expect(appReducer(state, action)).toBe(state);
              if (unchanged) expect(state).toBe(prev);
              break;
            }
            case 'repo-selected':
              if (action.repoId !== prev.repoId) {
                expect(sel(state)).toEqual([null, null, null]);
                expect(state.studyMode).toBe('unknown');
                expect(state.repoId).toBe(action.repoId);
                expect(state.view).toBe(prev.view);
                expect(state.lens).toBe(prev.lens);
                expect(state.visualMode).toBe(prev.visualMode);
              } else {
                expect(state).toBe(prev);
              }
              break;
            case 'select-directory':
              expect(state.node).toBe(action.dir);
              expect(state.file).toBe(prev.file);
              expect(state.symbol).toBe(prev.symbol);
              expect(state.lens).toBe('L3_ARCHITECTURE');
              expect(appReducer(state, action)).toBe(state);
              break;
            case 'node-cleared':
              expect(state.node).toBeNull();
              expect(state.file).toBe(prev.file);
              expect(state.symbol).toBe(prev.symbol);
              break;
            case 'layer-changed':
              expect(state.file).toBe(prev.file);
              expect(state.symbol).toBe(prev.symbol);
              if (action.keepNode) expect(state).toBe(prev);
              else expect(state.node).toBeNull();
              break;
            default:
              expect(unchanged).toBe(true);
          }

          // Same-reference rule: an unchanged value implies the same state object.
          if (JSON.stringify(state) === JSON.stringify(prev)) expect(state).toBe(prev);

          // visualMode is touched only by visual-mode-set, which touches nothing else.
          if (action.type === 'visual-mode-set') {
            expect(state).toEqual({ ...prev, visualMode: action.value });
          } else {
            expect(state.visualMode).toBe(prev.visualMode);
          }
        }
      }),
    );
  });
});
