import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import {
  MAX_DEEP_LINK_VALUE_LENGTH,
  buildSearch,
  parseDeepLink,
  resolveDeepLink,
  type DeepLinkView,
} from '../../src/core/deepLink';

const value = fc.string({ minLength: 0, maxLength: 40 });
const nonEmpty = fc.string({ minLength: 1, maxLength: 40 });
const view = fc.constantFrom<DeepLinkView>('graph', 'topology');
const enc = encodeURIComponent;

describe('Property 8: deep-link parsing, resolution, and URL building', () => {
  /** **Validates: Requirements 26.1, 26.12, 26.13** */
  it('Property 8: deep-link parsing, resolution, and URL building', () => {
    // Step 1: returns the first occurrence of repo_id and file
    {
    fc.assert(
      fc.property(value, value, value, value, (r1, r2, f1, f2) => {
        const p = parseDeepLink(`?repo_id=${enc(r1)}&file=${enc(f1)}&repo_id=${enc(r2)}&file=${enc(f2)}`);
        expect(p.repoId).toEqual({ present: true, value: r1, matchable: true });
        expect(p.file).toEqual({ present: true, value: f1, matchable: true });
      }),
    );
    }

  /** **Validates: Requirements 26.1, 26.2** */
    // Step 2: marks values longer than 4096 characters as not matchable
    {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 5000 }), (n) => {
        const v = 'a'.repeat(n);
        const p = parseDeepLink(`?repo_id=${v}&file=${v}`);
        const expected = n <= MAX_DEEP_LINK_VALUE_LENGTH;
        expect(p.repoId).toMatchObject({ present: true, matchable: expected });
        expect(p.file).toMatchObject({ present: true, matchable: expected });
      }),
      { numRuns: 30 },
    );
    }

  /** **Validates: Requirements 26.4, 26.5** */
    // Step 3: accepts view only when exactly graph or topology
    {
    fc.assert(
      fc.property(value, (v) => {
        const p = parseDeepLink(`?view=${enc(v)}`);
        expect(p.view).toBe(v === 'graph' || v === 'topology' ? v : null);
      }),
    );
    expect(parseDeepLink('').view).toBeNull();
    expect(parseDeepLink('?view=Graph').view).toBeNull();
    expect(parseDeepLink('?view=graph&view=topology').view).toBe('graph');
    }

  /** **Validates: Requirements 26.2, 26.6, 26.7** */
    // Step 4: selects a repository only on exact case-sensitive match and ignores file otherwise
    {
    fc.assert(
      fc.property(nonEmpty, fc.array(nonEmpty, { maxLength: 6 }), (id, ids) => {
        const r = resolveDeepLink(parseDeepLink(`?repo_id=${enc(id)}&file=x`), ids);
        if (ids.includes(id)) {
          expect(r).toEqual({ repoId: id, notFound: false, ignoreFile: false });
        } else {
          expect(r).toEqual({ repoId: null, notFound: true, ignoreFile: true });
        }
      }),
    );
    const r = resolveDeepLink(parseDeepLink('?repo_id=Abc'), ['abc']);
    expect(r.repoId).toBeNull();
    const none = resolveDeepLink(parseDeepLink('?file=x'), ['x']);
    expect(none).toEqual({ repoId: null, notFound: false, ignoreFile: true });
    const long = 'a'.repeat(MAX_DEEP_LINK_VALUE_LENGTH + 1);
    expect(resolveDeepLink(parseDeepLink(`?repo_id=${long}`), [long]).repoId).toBeNull();
    }

  /** **Validates: Requirements 26.8, 26.11, 28.12** */
    // Step 5: buildSearch includes params by state, keeps unrelated ones, and round-trips
    {
    fc.assert(
      fc.property(
        fc.option(nonEmpty, { nil: null }),
        fc.option(nonEmpty, { nil: null }),
        view,
        fc.option(nonEmpty, { nil: null }),
        (repoId, file, v, other) => {
          const current = other === null ? '' : `?keep=${enc(other)}&view=old&repo_id=old&file=old`;
          const out = buildSearch(current, { repoId, file, view: v });
          const params = new URLSearchParams(out);
          expect(params.has('repo_id')).toBe(repoId !== null);
          expect(params.has('file')).toBe(file !== null);
          expect(params.get('view')).toBe(v);
          if (other !== null) expect(params.get('keep')).toBe(other);
          const p = parseDeepLink(out);
          expect(p.view).toBe(v);
          expect(p.repoId).toEqual(
            repoId === null ? { present: false } : { present: true, value: repoId, matchable: true },
          );
          expect(p.file).toEqual(
            file === null ? { present: false } : { present: true, value: file, matchable: true },
          );
        },
      ),
    );
    }
  });
});
