import fc from 'fast-check';
import { afterEach, describe, expect, it } from 'vitest';
import { createApiClient } from '../../src/api/client';
import {
  ApiAbortError,
  ApiHttpError,
  ApiMalformedError,
  ApiNetworkError,
  GENERIC_HTTP_MESSAGE,
} from '../../src/api/errors';
import { installFetchMock, type FetchMock, type MockReply } from '../helpers/mockFetch';

// Feature: autopsy-ui, Property 2: API_Client error and response mapping
// **Validates: Requirements 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 28.13**

const MARK = 'RAWBODY';
const LEAKS = /TypeError|SyntaxError|DOMException|AbortError|ReferenceError|\n\s+at |RAWBODY/;

let mock: FetchMock | null = null;
afterEach(() => {
  mock?.restore();
  mock = null;
});

async function capture(fn: () => Promise<unknown>): Promise<unknown> {
  try {
    await fn();
  } catch (error) {
    return error;
  }
  throw new Error('expected the call to reject');
}

function expectNoLeak(error: Error): void {
  expect(error.message).not.toMatch(LEAKS);
  for (const [key, value] of Object.entries(error)) {
    // `name` is the API error's own class label, not a leaked exception name.
    if (key !== 'name' && typeof value === 'string') expect(value).not.toMatch(LEAKS);
  }
  expect(Object.keys(error)).not.toContain('cause');
}

function errorClassCount(error: unknown): number {
  return [ApiHttpError, ApiNetworkError, ApiMalformedError, ApiAbortError].filter(
    (c) => error instanceof c,
  ).length;
}

function install(reply: () => MockReply): FetchMock {
  mock = installFetchMock([{ method: 'GET', path: '/health', respond: reply }]);
  return mock;
}

const nonSuccessStatus = fc.integer({ min: 300, max: 599 }).filter((s) => s !== 304);
const successStatus = fc.integer({ min: 200, max: 299 }).filter((s) => s !== 204 && s !== 205);

const retryAfterHeader = fc.oneof(
  fc.constant<string | undefined>(undefined),
  fc.nat({ max: 1_000_000 }).map(String),
  fc.nat({ max: 1000 }).map((n) => ` ${n} `),
  fc.stringMatching(/^[ -~]{0,12}$/),
  fc.constantFrom('-1', '1.5', '1e3', 'abc', '', '99999999999999999999', 'Wed, 21 Oct 2015 07:28:00 GMT'),
);

function expectedRetryAfter(status: number, header: string | undefined): number | undefined {
  if (status !== 429 || header === undefined) return undefined;
  const raw = new Headers({ 'Retry-After': header }).get('Retry-After');
  if (raw === null || !/^\d+$/.test(raw)) return undefined;
  const n = Number.parseInt(raw, 10);
  return Number.isSafeInteger(n) ? n : undefined;
}

type BodyKind =
  | { kind: 'envelope'; code: string; message: string }
  | { kind: 'other'; text: string };

const envelopeBody = fc
  .record({ code: fc.string({ maxLength: 30 }), message: fc.string({ maxLength: 60 }) })
  .map((e): BodyKind => ({ kind: 'envelope', ...e }));

const nonEnvelopeBody = fc.oneof(
  fc.constant<BodyKind>({ kind: 'other', text: '' }),
  fc.string({ maxLength: 40 }).map((s): BodyKind => ({ kind: 'other', text: `<<${MARK} ${s}` })),
  fc
    .oneof(
      fc.constant({ [MARK]: MARK }),
      fc.constant({ error: MARK }),
      fc.constant({ error: { code: 5, message: MARK } }),
      fc.constant({ error: { code: MARK } }),
      fc.constant({ error: { message: MARK } }),
      fc.constant({ error: null, detail: MARK }),
      fc.constant([MARK]),
      fc.constant(MARK),
      fc.constant(null),
    )
    .map((v): BodyKind => ({ kind: 'other', text: JSON.stringify(v) })),
);

describe('Property 2: API_Client error and response mapping', () => {
  it('Property 2: API_Client error and response mapping', async () => {
    // Step 1: non-2xx maps to an HTTP error by envelope shape, with Retry-After only for 429
    {
    await fc.assert(
      fc.asyncProperty(
        fc.oneof(nonSuccessStatus, fc.constant(429)),
        fc.oneof(envelopeBody, nonEnvelopeBody),
        retryAfterHeader,
        async (status, body, header) => {
          const headers: Record<string, string> = {};
          if (header !== undefined) headers['Retry-After'] = header;
          const text =
            body.kind === 'envelope'
              ? JSON.stringify({ error: { code: body.code, message: body.message } })
              : body.text;
          const fetchMock = install(() => ({ status, text, headers }));
          const error = await capture(() => createApiClient({ baseUrl: '' }).getHealth());
          fetchMock.restore();

          expect(errorClassCount(error)).toBe(1);
          expect(error).toBeInstanceOf(ApiHttpError);
          const http = error as ApiHttpError;
          expect(http.status).toBe(status);
          expect(http.retryAfterSeconds).toBe(expectedRetryAfter(status, header));
          if (body.kind === 'envelope') {
            expect(http.code).toBe(body.code);
            expect(http.message).toBe(body.message);
          } else {
            expect(http.code).toBeNull();
            expect(http.message).toBe(GENERIC_HTTP_MESSAGE);
            expectNoLeak(http);
          }
        },
      ),
    );
    }

    // Step 2: 2xx with empty, non-JSON, or shape-invalid body raises the malformed error naming the operation
    {
    await fc.assert(
      fc.asyncProperty(successStatus, nonEnvelopeBody, async (status, body) => {
        const text = body.kind === 'other' ? body.text : '';
        const fetchMock = install(() => ({ status, text }));
        const error = await capture(() => createApiClient({ baseUrl: '' }).getHealth());
        fetchMock.restore();

        expect(errorClassCount(error)).toBe(1);
        expect(error).toBeInstanceOf(ApiMalformedError);
        expect((error as ApiMalformedError).operation).toBe('getHealth');
        expectNoLeak(error as ApiMalformedError);
      }),
    );
    }

    // Step 3: a rejected fetch raises the abort error only when the signal is aborted, otherwise the network error
    {
    await fc.assert(
      fc.asyncProperty(fc.boolean(), async (abortMidFlight) => {
        const controller = new AbortController();
        const fetchMock = install(() => {
          if (abortMidFlight) controller.abort();
          return { network: true };
        });
        const error = await capture(() =>
          createApiClient({ baseUrl: '' }).getHealth({ signal: controller.signal }),
        );
        fetchMock.restore();

        expect(errorClassCount(error)).toBe(1);
        expect(error).toBeInstanceOf(abortMidFlight ? ApiAbortError : ApiNetworkError);
        expectNoLeak(error as Error);
      }),
    );
    }

    // Step 4: an already-aborted signal raises the abort error and sends no request
    {
    await fc.assert(
      fc.asyncProperty(fc.string({ maxLength: 20 }), async (reason) => {
        const controller = new AbortController();
        controller.abort(reason);
        const fetchMock = install(() => ({ status: 200, json: { status: 'ok' } }));
        const error = await capture(() =>
          createApiClient({ baseUrl: '' }).getHealth({ signal: controller.signal }),
        );
        const calls = fetchMock.calls.length;
        fetchMock.restore();

        expect(errorClassCount(error)).toBe(1);
        expect(error).toBeInstanceOf(ApiAbortError);
        expect(calls).toBe(0);
        expectNoLeak(error as Error);
      }),
    );
    }
  });
});
