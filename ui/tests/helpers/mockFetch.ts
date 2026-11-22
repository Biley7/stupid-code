export type MockReply =
  | { status?: number; json?: unknown; text?: string; headers?: Record<string, string> }
  | { network: true };

export interface Route {
  method: 'GET' | 'POST';
  /** Matched on pathname plus search. */
  path: string | RegExp;
  /** Optional body matcher, called with the parsed JSON body. */
  body?: (parsed: unknown) => boolean;
  respond: () => MockReply | Promise<MockReply>;
}

export interface FetchMock {
  calls: { method: string; path: string; body: unknown }[];
  unmatched: string[];
  restore(): void;
}

// Shared across the active mock so the global afterEach can inspect it.
let active: FetchMock | null = null;
let original: typeof globalThis.fetch | null = null;

export function getActiveFetchMock(): FetchMock | null {
  return active;
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  try {
    const url = new URL(raw, 'http://localhost');
    return url.pathname + url.search;
  } catch {
    return raw;
  }
}

function parseBody(body: BodyInit | null | undefined): unknown {
  if (typeof body !== 'string') return undefined;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

function matches(route: Route, method: string, path: string, body: unknown): boolean {
  if (route.method !== method) return false;
  const pathOk = typeof route.path === 'string' ? route.path === path : route.path.test(path);
  if (!pathOk) return false;
  return route.body ? route.body(body) : true;
}

function toResponse(reply: Exclude<MockReply, { network: true }>): Response {
  const status = reply.status ?? 200;
  const headers = new Headers(reply.headers);
  let text = reply.text ?? '';
  if (reply.json !== undefined) {
    text = JSON.stringify(reply.json);
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  }
  const noBody = status === 204 || status === 205 || status === 304;
  return new Response(noBody ? null : text, { status, headers });
}

/**
 * Install a fetch mock. Unmatched requests are recorded and rejected; the global
 * afterEach in tests/setup.ts then fails the test with `Unmatched request: ...`.
 * Honors `init.signal`: an aborted signal rejects with an AbortError.
 */
export function installFetchMock(routes: Route[]): FetchMock {
  if (active) active.restore();
  original = globalThis.fetch;

  const mock: FetchMock = {
    calls: [],
    unmatched: [],
    restore() {
      if (original) globalThis.fetch = original;
      original = null;
      if (active === mock) active = null;
    },
  };

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const signal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
    if (signal?.aborted) throw abortError();

    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const path = pathOf(input);
    const body = parseBody(init?.body);
    mock.calls.push({ method, path, body });

    const route = routes.find((r) => matches(r, method, path, body));
    if (!route) {
      mock.unmatched.push(`${method} ${path}`);
      throw new TypeError(`Unmatched request: ${method} ${path}`);
    }

    const replyPromise = Promise.resolve(route.respond());
    const aborted = signal
      ? new Promise<never>((_, reject) => {
          signal.addEventListener('abort', () => reject(abortError()), { once: true });
        })
      : null;
    const reply = await (aborted ? Promise.race([replyPromise, aborted]) : replyPromise);

    if ('network' in reply) throw new TypeError('Failed to fetch');
    return toResponse(reply);
  }) as typeof globalThis.fetch;

  active = mock;
  return mock;
}
