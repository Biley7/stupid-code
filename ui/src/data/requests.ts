// Request tickets for the data hooks. A ticket carries the sequence number the
// DataStore reducer will hold for the same start action, plus an AbortSignal linked
// to the per-repository scope. The mirror counters reset exactly when the scope
// rotates (repository change), matching the reducer's reset on `repo-selected`.

import type { RequestScope } from './requestScope';

export type RequestKey = 'repos' | 'snapshot' | 'vitals' | `explain:${string}`;

export interface RequestTicket {
  /** Sequence number to pass to `resource-success` and `resource-failure`. */
  readonly seq: number;
  readonly signal: AbortSignal;
  /** True while no newer request for the key started and the repository is unchanged. */
  isCurrent(): boolean;
  abort(): void;
  /** Detaches the scope listener once the request settled. */
  release(): void;
}

interface Mirror {
  epoch: AbortSignal;
  counters: Map<string, number>;
  inflight: Map<string, AbortController>;
}

const mirrors = new WeakMap<RequestScope, Mirror>();
// `repos` is not repository scoped: its counter never resets.
const reposCounters = new WeakMap<RequestScope, { seq: number; controller: AbortController | null }>();

function mirrorFor(scope: RequestScope): Mirror {
  let mirror = mirrors.get(scope);
  if (mirror === undefined || mirror.epoch !== scope.signal) {
    mirror = { epoch: scope.signal, counters: new Map(), inflight: new Map() };
    mirrors.set(scope, mirror);
  }
  return mirror;
}

/**
 * Starts a request for `key`: increments the sequence number, aborts the previous
 * request for the same key, and returns a ticket. Call it right before dispatching
 * the matching `resource-start`.
 */
export function beginRequest(scope: RequestScope, key: RequestKey): RequestTicket {
  const controller = new AbortController();

  if (key === 'repos') {
    let entry = reposCounters.get(scope);
    if (entry === undefined) {
      entry = { seq: 0, controller: null };
      reposCounters.set(scope, entry);
    }
    entry.controller?.abort();
    entry.controller = controller;
    entry.seq += 1;
    const seq = entry.seq;
    const state = entry;
    return {
      seq,
      signal: controller.signal,
      isCurrent: () => state.seq === seq && !controller.signal.aborted,
      abort: () => controller.abort(),
      release: () => {
        if (state.controller === controller) state.controller = null;
      },
    };
  }

  const mirror = mirrorFor(scope);
  const epoch = mirror.epoch;
  mirror.inflight.get(key)?.abort();
  mirror.inflight.set(key, controller);
  const seq = (mirror.counters.get(key) ?? 0) + 1;
  mirror.counters.set(key, seq);

  const onScopeAbort = (): void => controller.abort();
  if (epoch.aborted) controller.abort();
  else epoch.addEventListener('abort', onScopeAbort, { once: true });

  return {
    seq,
    signal: controller.signal,
    isCurrent: () =>
      scope.signal === epoch && mirror.counters.get(key) === seq && !controller.signal.aborted,
    abort: () => controller.abort(),
    release: () => {
      epoch.removeEventListener('abort', onScopeAbort);
      if (mirror.inflight.get(key) === controller) mirror.inflight.delete(key);
    },
  };
}
