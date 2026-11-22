import { useCallback, useEffect, useRef } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError, type ApiError } from '../api/errors';
import type { ExplainResponse, Lens } from '../api/types';
import { explainKey, type Remote } from '../state/dataReducer';
import { useAppState, useDataDispatch, useDataState, useRequestScope } from '../state/store';
import { beginRequest, type RequestTicket } from './requests';
import { useLatest } from './useLatest';
import { useRefreshVitals } from './useVitals';

export interface UseExplain {
  explain: Remote<ExplainResponse>;
  /** Drops the failed entry and sends exactly one new request. */
  retry: () => void;
}

const IDLE: Remote<ExplainResponse> = { status: 'idle' };

/**
 * Explain with a cache keyed by repo, target, and lens. Only `ready` entries are
 * served without a request. Failures are shown but never cached: the entry is removed
 * when the key's effect is cleaned up. `targetId` null means no request.
 */
export function useExplain(targetId: string | null, lens: Lens): UseExplain {
  const api = useApi();
  const scope = useRequestScope();
  const dispatch = useDataDispatch();
  const refreshVitals = useRefreshVitals();
  const { repoId } = useAppState();
  const dataState = useDataState();
  const dataRef = useLatest(dataState);
  const studyModeRef = useLatest(useAppState().studyMode);

  const retryTicket = useRef<RequestTicket | null>(null);

  const key = repoId !== null && targetId !== null ? explainKey(repoId, targetId, lens) : null;

  const run = useCallback(
    (id: string, target: string, theLens: Lens): RequestTicket | null => {
      const k = explainKey(id, target, theLens);
      const current = dataRef.current;
      if (current.repoId !== id) return null;
      const entry = current.explain[k];
      if (entry !== undefined && (entry.status === 'ready' || entry.status === 'loading')) return null;

      const ticket = beginRequest(scope, `explain:${k}`);
      dispatch({ type: 'resource-start', resource: 'explain', repoId: id, key: k });
      void (async () => {
        try {
          const data = await api.explain(id, { target_id: target, lens: theLens }, { signal: ticket.signal });
          if (!ticket.isCurrent()) return;
          dispatch({ type: 'resource-success', resource: 'explain', repoId: id, key: k, seq: ticket.seq, data });
          if (studyModeRef.current === true && (theLens === 'L1_SYNTAX' || theLens === 'L2_FLOW')) {
            void refreshVitals(id, 'keep');
          }
        } catch (error) {
          if (error instanceof ApiAbortError || !ticket.isCurrent()) return;
          dispatch({
            type: 'resource-failure',
            resource: 'explain',
            repoId: id,
            key: k,
            seq: ticket.seq,
            error: error as ApiError,
          });
        } finally {
          ticket.release();
        }
      })();
      return ticket;
    },
    [api, scope, dispatch, dataRef, studyModeRef, refreshVitals],
  );

  useEffect(() => {
    if (repoId === null || targetId === null) return;
    const ticket = run(repoId, targetId, lens);
    const k = explainKey(repoId, targetId, lens);
    return () => {
      ticket?.abort();
      retryTicket.current?.abort();
      retryTicket.current = null;
      dispatch({ type: 'explain-remove', repoId, key: k });
    };
  }, [repoId, targetId, lens, run, dispatch]);

  const retry = useCallback(() => {
    if (repoId === null || targetId === null) return;
    const k = explainKey(repoId, targetId, lens);
    const entry = dataRef.current.explain[k];
    if (entry === undefined || entry.status !== 'error') return;
    // `run` accepts an error entry; the start action replaces it with `loading`.
    retryTicket.current?.abort();
    retryTicket.current = run(repoId, targetId, lens);
  }, [repoId, targetId, lens, dataRef, run]);

  return { explain: key === null ? IDLE : (dataState.explain[key] ?? IDLE), retry };
}
