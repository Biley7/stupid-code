import { afterEach, describe, expect, it, vi } from 'vitest';
import fc from 'fast-check';
import { createApiClient } from '../../src/api/client';

interface Captured {
  url: string;
  init: RequestInit;
}

const OPERATIONS = [
  'getHealth',
  'listRepos',
  'ingestRepo',
  'getSnapshot',
  'explain',
  'getVitals',
  'setStudyMode',
  'startSocratic',
  'submitSocratic',
] as const;
type Operation = (typeof OPERATIONS)[number];

interface Expectation {
  method: 'GET' | 'POST';
  /** Path before/after the repo_id segment; `null` means no repo_id segment. */
  suffix: string;
  hasRepo: boolean;
  /** Expected exact body keys, or null when the operation has no body. */
  keys: string[] | null;
}

const EXPECTED: Record<Operation, Expectation> = {
  getHealth: { method: 'GET', suffix: '/health', hasRepo: false, keys: null },
  listRepos: { method: 'GET', suffix: '/api/repos', hasRepo: false, keys: null },
  ingestRepo: { method: 'POST', suffix: '/api/repos/ingest', hasRepo: false, keys: ['url'] },
  getSnapshot: { method: 'GET', suffix: '/snapshot', hasRepo: true, keys: null },
  explain: { method: 'POST', suffix: '/explain', hasRepo: true, keys: ['lens', 'target_id'] },
  getVitals: { method: 'GET', suffix: '/vitals', hasRepo: true, keys: null },
  setStudyMode: { method: 'POST', suffix: '/study-mode', hasRepo: true, keys: ['enabled'] },
  startSocratic: { method: 'POST', suffix: '/socratic/start', hasRepo: true, keys: ['target_id'] },
  submitSocratic: {
    method: 'POST',
    suffix: '/socratic/submit',
    hasRepo: true,
    keys: ['answers', 'target_id'],
  },
};

const NASTY = ['/', '?', '#', '%', ' ', '%2F', '..', 'é', '日本', '😀'];
const repoId = fc
  .tuple(
    fc.fullUnicodeString({ minLength: 0, maxLength: 20 }),
    fc.array(fc.constantFrom(...NASTY), { maxLength: 4 }),
  )
  .map(([s, extra]) => s + extra.join(''));

const slashes = fc.integer({ min: 0, max: 4 }).map((n) => '/'.repeat(n));
const baseUrl = fc.oneof(
  fc.constant<string | undefined>(undefined),
  fc.constant<string | undefined>(''),
  fc.tuple(fc.constantFrom('http://localhost:8000', 'https://api.example.com/v1', 'x'), slashes).map(
    ([b, s]) => b + s,
  ),
  fc.string({ maxLength: 15 }),
);

async function run(
  op: Operation,
  base: string | undefined,
  id: string,
  ingestKey: 'url' | 'path',
): Promise<Captured> {
  const captured: Captured[] = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    captured.push({ url, init });
    return new Response('{}', { status: 500 });
  });
  const client = createApiClient({ baseUrl: base });
  const calls: Record<Operation, () => Promise<unknown>> = {
    getHealth: () => client.getHealth(),
    listRepos: () => client.listRepos(),
    ingestRepo: () => client.ingestRepo({ [ingestKey]: id } as never),
    getSnapshot: () => client.getSnapshot(id),
    explain: () => client.explain(id, { target_id: id, lens: 'L1_SYNTAX' } as never),
    getVitals: () => client.getVitals(id),
    setStudyMode: () => client.setStudyMode(id, true),
    startSocratic: () => client.startSocratic(id, 't'),
    submitSocratic: () =>
      client.submitSocratic(id, { target_id: 't', answers: [{ question_id: 'q', answer: 'a' }] } as never),
  };
  await calls[op]().catch(() => undefined);
  expect(captured).toHaveLength(1);
  return captured[0]!;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Property 3: Request construction', () => {
  /** **Validates: Requirements 1.7, 1.8, 2.5, 2.6, 2.7** */
  it('builds URL, method, headers, and body from base, repo_id, and operation', async () => {
    await fc.assert(
      fc.asyncProperty(
        baseUrl,
        repoId,
        fc.constantFrom(...OPERATIONS),
        fc.constantFrom<'url' | 'path'>('url', 'path'),
        async (base, id, op, ingestKey) => {
          const exp = EXPECTED[op];
          const { url, init } = await run(op, base, id, ingestKey);
          const normalized = (base ?? '').replace(/\/+$/, '');

          expect(url.startsWith(normalized)).toBe(true);
          const path = url.slice(normalized.length);
          expect(path.startsWith('/')).toBe(true);

          if (exp.hasRepo) {
            const prefix = '/api/repos/';
            expect(path.startsWith(prefix)).toBe(true);
            const rest = path.slice(prefix.length);
            const segments = rest.split('/');
            const [seg, ...tail] = segments;
            expect(`/${tail.join('/')}`).toBe(exp.suffix);
            expect(decodeURIComponent(seg!)).toBe(id);
            expect(seg).not.toMatch(/[/?#]/);
          } else {
            expect(path).toBe(exp.suffix);
          }

          expect(init.method).toBe(exp.method);

          if (exp.keys === null) {
            expect(init.body).toBeUndefined();
          } else {
            const headers = new Headers(init.headers);
            expect(headers.get('Content-Type')).toBe('application/json');
            const body = JSON.parse(init.body as string) as Record<string, unknown>;
            const expectedKeys = op === 'ingestRepo' ? [ingestKey] : exp.keys;
            expect(Object.keys(body).sort()).toEqual([...expectedKeys].sort());
          }
        },
      ),
    );
  });
});
