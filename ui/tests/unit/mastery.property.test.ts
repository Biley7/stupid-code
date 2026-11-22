import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import {
  fileMasteryView,
  isShrouded,
  presentMastery,
  type MasteryCategory,
  type VisualMode,
  type VitalsRemote,
} from '../../src/core/mastery';
import type { ComprehensionVitals } from '../../src/api/types';
import { makeVitals } from '../fixtures/builders';

const KNOWN = ['UNAUDITED', 'DISSECTED', 'MASTERED', 'STALE'] as const;
const CATEGORIES: MasteryCategory[] = [
  'UNAUDITED',
  'DISSECTED',
  'MASTERED',
  'STALE',
  'NO TRACKED SYMBOLS',
  'STATE UNKNOWN',
];

const anyInput = fc.oneof(
  fc.string(),
  fc.constant(undefined),
  fc.constant(null),
  fc.double(),
  fc.boolean(),
  fc.object(),
  fc.array(fc.anything()),
  fc.constantFrom('unaudited', 'Mastered', ' STALE', 'DISSECTED ', 'toString', '__proto__', 'constructor'),
);

const unknownString = fc.string().filter((s) => !(KNOWN as readonly string[]).includes(s));

const pathArb = fc.string({ minLength: 1, maxLength: 20 });
const stateArb = fc.oneof(fc.constantFrom(...KNOWN), unknownString);

describe('Property 1: mastery presentation', () => {
  /** **Validates: Requirements 11.1, 11.2, 11.3, 11.5, 27.5, 28.9** */
  it('Property 1: mastery presentation', () => {
    // Step 1: presentMastery is total and maps unknown input to STATE UNKNOWN
    {
    fc.assert(
      fc.property(anyInput, (input) => {
        const p = presentMastery(input);
        if (typeof input === 'string' && (KNOWN as readonly string[]).includes(input)) {
          expect(p.label).toBe(input);
          expect(p.category).toBe(input);
        } else {
          expect(p.label).toBe('STATE UNKNOWN');
          expect(p.token).toBe('muted');
        }
      }),
    );
    }

  /** **Validates: Requirements 11.1, 11.2, 11.3, 28.9** */
    // Step 2: six categories have distinct label and icon; four known states have distinct tokens
    {
    const ps = CATEGORIES.map((c) => (c === 'NO TRACKED SYMBOLS'
      ? fileMasteryView({ status: 'ready', data: { file_states: {} } }, 'x')
      : presentMastery(c)));
    expect(new Set(ps.map((p) => p.label)).size).toBe(6);
    expect(new Set(ps.map((p) => p.icon)).size).toBe(6);
    expect(ps.map((p) => p.category)).toEqual(CATEGORIES);
    expect(new Set(KNOWN.map((s) => presentMastery(s).token)).size).toBe(4);
    }

  /** **Validates: Requirements 11.4, 11.7, 11.8, 27.9** */
    // Step 3: fileMasteryView is STATE UNKNOWN unless the vitals status is ready
    {
    const notReady: VitalsRemote[] = [
      { status: 'idle' },
      { status: 'loading' },
      { status: 'error', error: new Error('x') },
    ];
    fc.assert(
      fc.property(fc.constantFrom(...notReady), pathArb, (remote, path) => {
        expect(fileMasteryView(remote, path).label).toBe('STATE UNKNOWN');
      }),
    );
    }

  /** **Validates: Requirements 11.4, 11.7, 11.8, 27.9** */
    // Step 4: ready vitals: missing key is NO TRACKED SYMBOLS, present key is presentMastery(value), independent of counts
    {
    fc.assert(
      fc.property(
        fc.dictionary(pathArb, stateArb, { maxKeys: 8 }),
        pathArb,
        fc.array(fc.nat(1000), { minLength: 5, maxLength: 5 }),
        fc.array(fc.string(), { maxLength: 4 }),
        fc.boolean(),
        (fileStates, probe, counts, due, refreshFailed) => {
          // Skip prototype-pollution-prone keys; JSON-derived objects cannot carry them as own keys here.
          fc.pre(probe !== '__proto__' && !('__proto__' in fileStates && Object.keys(fileStates).includes('__proto__')));
          const base = makeVitals();
          const [a, b, c, d, e] = counts as [number, number, number, number, number];
          const vitals: ComprehensionVitals = {
            ...base,
            // Unknown state strings are deliberate: the backend value is untrusted at runtime.
            file_states: fileStates as ComprehensionVitals['file_states'],
            total_modules: a,
            unaudited_count: b,
            dissected_count: c,
            mastered_count: d,
            stale_count: e,
            mastery_percentage: a % 101,
            due_for_review: due,
          };
          const remote: VitalsRemote = { status: 'ready', data: vitals, refreshFailed };
          const view = fileMasteryView(remote, probe);
          if (Object.prototype.hasOwnProperty.call(fileStates, probe)) {
            expect(view).toEqual(presentMastery(fileStates[probe]));
          } else {
            expect(view.label).toBe('NO TRACKED SYMBOLS');
          }
          // Same result with all counts and due list changed.
          const changed: ComprehensionVitals = {
            ...vitals,
            total_modules: 0,
            unaudited_count: 0,
            due_for_review: [],
          };
          const other: VitalsRemote = { status: 'ready', data: changed };
          expect(fileMasteryView(other, probe)).toEqual(view);
        },
      ),
    );
    }

  /** **Validates: Requirements 15.11, 11.5** */
    // Step 5: Shroud is true only for UNAUDITED in Autopsy mode
    {
    const modes: VisualMode[] = ['Autopsy', 'Lab'];
    fc.assert(
      fc.property(anyInput, fc.constantFrom(...modes), (input, mode) => {
        const p = presentMastery(input);
        expect(isShrouded(p, mode)).toBe(p.category === 'UNAUDITED' && mode === 'Autopsy');
      }),
    );
    expect(isShrouded(presentMastery('UNAUDITED'), 'Autopsy')).toBe(true);
    expect(isShrouded(presentMastery('UNAUDITED'), 'Lab')).toBe(false);
    }
  });
});
