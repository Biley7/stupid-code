import { useCallback, useEffect } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError, type ApiError } from '../api/errors';
import type { RepoSummary } from '../api/types';
import type { Remote } from '../state/dataReducer';
import { useAppDispatch, useAppState, useDataDispatch, useDataState, useRequestScope } from '../state/store';
import { beginRequest } from './requests';
import { useLatest } from './useLatest';

export interface UseRepos {
  repos: Remote<RepoSummary[]>;
  /** Resolves with the refreshed list, or null when the request failed or was superseded. */
  reload: () => Promise<RepoSummary[] | null>;
}

/** Loads the repository list on mount and on `reload`. */
export function useRepos(options: { autoload?: boolean } = {}): UseRepos {
  const autoload = options.autoload ?? true;
  const api = useApi();
  const scope = useRequestScope();
  const dataDispatch = useDataDispatch();
  const appDispatch = useAppDispatch();
  const repos = useDataState().repos;
  const appRef = useLatest(useAppState());

  const reload = useCallback(async (): Promise<RepoSummary[] | null> => {
    const ticket = beginRequest(scope, 'repos');
    dataDispatch({ type: 'resource-start', resource: 'repos' });
    try {
      const data = await api.listRepos({ signal: ticket.signal });
      if (!ticket.isCurrent()) return null;
      dataDispatch({ type: 'resource-success', resource: 'repos', seq: ticket.seq, data });
      // A selected repository missing from the refreshed list is cleared (6.10).
      const selected = appRef.current.repoId;
      if (selected !== null && !data.some((repo) => repo.repo_id === selected)) {
        appDispatch({ type: 'repo-selected', repoId: null });
      }
      return data;
    } catch (error) {
      if (error instanceof ApiAbortError || !ticket.isCurrent()) return null;
      dataDispatch({ type: 'resource-failure', resource: 'repos', seq: ticket.seq, error: error as ApiError });
      return null;
    } finally {
      ticket.release();
    }
  }, [api, scope, dataDispatch, appDispatch, appRef]);

  useEffect(() => {
    if (!autoload) return;
    void reload();
  }, [autoload, reload]);

  return { repos, reload };
}
