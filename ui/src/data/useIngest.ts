import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError } from '../api/errors';
import type { IngestRequest, IngestResponse } from '../api/types';
import { presentError, type PresentedError } from '../core/present';
import { useAppDispatch, useAppState } from '../state/store';
import { useLatest } from './useLatest';
import { useRepos } from './useRepos';
import { useSnapshot } from './useSnapshot';
import { useRefreshVitals } from './useVitals';

export type IngestPhase = 'idle' | 'submitting' | 'done';

export interface UseIngest {
  phase: IngestPhase;
  result: IngestResponse | null;
  error: PresentedError | null;
  /** True when ingestion succeeded but a follow-up (list refresh) failed. */
  followUpFailed: boolean;
  /** Single flight: ignored while submitting. */
  submit: (body: IngestRequest) => void;
  /** Repeats only the failed follow-up steps. */
  retryFollowUp: () => void;
  reset: () => void;
}

/**
 * Ingests a repository, refreshes the list, then selects the new repository only if
 * the backend's refreshed list contains it. Snapshot and vitals load through the
 * selection (or are reloaded directly when the repository was already selected).
 */
export function useIngest(): UseIngest {
  const api = useApi();
  const appDispatch = useAppDispatch();
  const { reload: reloadRepos } = useRepos({ autoload: false });
  const { reload: reloadSnapshot } = useSnapshot({ autoload: false });
  const refreshVitals = useRefreshVitals();
  const appRef = useLatest(useAppState());
  const reloadSnapshotRef = useLatest(reloadSnapshot);

  const [phase, setPhase] = useState<IngestPhase>('idle');
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [error, setError] = useState<PresentedError | null>(null);
  const [followUpFailed, setFollowUpFailed] = useState(false);
  const inFlight = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);

  const followUps = useCallback(
    async (repoId: string): Promise<boolean> => {
      const list = await reloadRepos();
      if (list === null) return false;
      if (!list.some((repo) => repo.repo_id === repoId)) return true;
      if (appRef.current.repoId === repoId) {
        void reloadSnapshotRef.current();
        void refreshVitals(repoId, 'replace');
      } else {
        appDispatch({ type: 'repo-selected', repoId });
      }
      return true;
    },
    [reloadRepos, appRef, reloadSnapshotRef, refreshVitals, appDispatch],
  );

  const submit = useCallback(
    (body: IngestRequest) => {
      if (inFlight.current) return;
      inFlight.current = true;
      const ctl = new AbortController();
      controller.current = ctl;
      setPhase('submitting');
      setError(null);
      setResult(null);
      setFollowUpFailed(false);
      void (async () => {
        try {
          const response = await api.ingestRepo(body, { signal: ctl.signal });
          if (!mounted.current) return;
          setResult(response);
          setPhase('done');
          const ok = await followUps(response.repo_id);
          if (mounted.current) setFollowUpFailed(!ok);
        } catch (e) {
          if (e instanceof ApiAbortError || !mounted.current) return;
          setError(presentError(e, 'ingest'));
          setPhase('idle');
        } finally {
          inFlight.current = false;
          if (controller.current === ctl) controller.current = null;
        }
      })();
    },
    [api, followUps],
  );

  const retryFollowUp = useCallback(() => {
    if (result === null || !followUpFailed) return;
    void followUps(result.repo_id).then((ok) => {
      if (mounted.current) setFollowUpFailed(!ok);
    });
  }, [result, followUpFailed, followUps]);

  const reset = useCallback(() => {
    if (inFlight.current) return;
    setPhase('idle');
    setResult(null);
    setError(null);
    setFollowUpFailed(false);
  }, []);

  return { phase, result, error, followUpFailed, submit, retryFollowUp, reset };
}
