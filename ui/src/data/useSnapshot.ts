import { useCallback, useEffect } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError, type ApiError } from '../api/errors';
import type { SnapshotResponse } from '../api/types';
import type { Remote } from '../state/dataReducer';
import { useAppState, useDataDispatch, useDataState, useRequestScope } from '../state/store';
import { beginRequest } from './requests';
import { useLatest } from './useLatest';

export interface UseSnapshot {
  snapshot: Remote<SnapshotResponse>;
  reload: () => Promise<boolean>;
}

/** Loads the snapshot when the selected repository changes. No request without one. */
export function useSnapshot(options: { autoload?: boolean } = {}): UseSnapshot {
  const autoload = options.autoload ?? true;
  const api = useApi();
  const scope = useRequestScope();
  const dispatch = useDataDispatch();
  const { repoId } = useAppState();
  const snapshot = useDataState().snapshot;
  const dataRef = useLatest(useDataState());

  const load = useCallback(
    async (id: string): Promise<boolean> => {
      if (dataRef.current.repoId !== id) return false;
      const ticket = beginRequest(scope, 'snapshot');
      dispatch({ type: 'resource-start', resource: 'snapshot', repoId: id });
      try {
        const data = await api.getSnapshot(id, { signal: ticket.signal });
        if (!ticket.isCurrent()) return false;
        dispatch({ type: 'resource-success', resource: 'snapshot', repoId: id, seq: ticket.seq, data });
        return true;
      } catch (error) {
        if (error instanceof ApiAbortError || !ticket.isCurrent()) return false;
        dispatch({
          type: 'resource-failure',
          resource: 'snapshot',
          repoId: id,
          seq: ticket.seq,
          error: error as ApiError,
        });
        return false;
      } finally {
        ticket.release();
      }
    },
    [api, scope, dispatch, dataRef],
  );

  useEffect(() => {
    if (!autoload || repoId === null) return;
    void load(repoId);
  }, [autoload, repoId, load]);

  const reload = useCallback(
    () => (repoId === null ? Promise.resolve(false) : load(repoId)),
    [repoId, load],
  );

  return { snapshot, reload };
}
