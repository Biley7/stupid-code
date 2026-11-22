import { useCallback, useEffect } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError, type ApiError } from '../api/errors';
import { useAppDispatch, useAppState, useDataDispatch, useDataState, useRequestScope } from '../state/store';
import type { Remote, VitalsRefreshMode } from '../state/dataReducer';
import type { ComprehensionVitals } from '../api/types';
import { beginRequest } from './requests';
import { useLatest } from './useLatest';

export type RefreshVitals = (repoId: string, mode: VitalsRefreshMode) => Promise<boolean>;

/**
 * Stable function that loads vitals for `repoId`. Study Mode is set from the
 * response only. Results for a repository that is no longer selected, or that were
 * superseded by a newer request, change nothing. Resolves true on applied success.
 */
export function useRefreshVitals(): RefreshVitals {
  const api = useApi();
  const scope = useRequestScope();
  const dataDispatch = useDataDispatch();
  const appDispatch = useAppDispatch();
  const appRef = useLatest(useAppState());
  const dataRef = useLatest(useDataState());

  return useCallback(
    async (repoId, mode) => {
      if (appRef.current.repoId !== repoId || dataRef.current.repoId !== repoId) return false;
      const ticket = beginRequest(scope, 'vitals');
      dataDispatch({ type: 'resource-start', resource: 'vitals', repoId, mode });
      try {
        const data = await api.getVitals(repoId, { signal: ticket.signal });
        if (!ticket.isCurrent()) return false;
        dataDispatch({ type: 'resource-success', resource: 'vitals', repoId, seq: ticket.seq, data });
        appDispatch({ type: 'study-mode-set', value: data.study_mode_enabled });
        return true;
      } catch (error) {
        if (error instanceof ApiAbortError || !ticket.isCurrent()) return false;
        dataDispatch({
          type: 'resource-failure',
          resource: 'vitals',
          repoId,
          seq: ticket.seq,
          error: error as ApiError,
          mode,
        });
        return false;
      } finally {
        ticket.release();
      }
    },
    [api, scope, dataDispatch, appDispatch, appRef, dataRef],
  );
}

export interface UseVitals {
  vitals: Remote<ComprehensionVitals>;
  reload: () => Promise<boolean>;
  refreshVitals: RefreshVitals;
}

/** Loads vitals when the selected repository changes. No request without a repository. */
export function useVitals(options: { autoload?: boolean } = {}): UseVitals {
  const autoload = options.autoload ?? true;
  const { repoId } = useAppState();
  const vitals = useDataState().vitals;
  const refreshVitals = useRefreshVitals();

  useEffect(() => {
    if (!autoload || repoId === null) return;
    void refreshVitals(repoId, 'replace');
  }, [autoload, repoId, refreshVitals]);

  const reload = useCallback(
    () => (repoId === null ? Promise.resolve(false) : refreshVitals(repoId, 'replace')),
    [repoId, refreshVitals],
  );

  return { vitals, reload, refreshVitals };
}
