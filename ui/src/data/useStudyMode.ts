import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError } from '../api/errors';
import { presentError, type PresentedError } from '../core/present';
import { useAppDispatch, useAppState, useDataDispatch, useRequestScope } from '../state/store';
import { useLatest } from './useLatest';
import { useRefreshVitals } from './useVitals';

export interface UseStudyMode {
  /** True while a toggle request is in flight. The displayed value does not change meanwhile. */
  pending: boolean;
  error: PresentedError | null;
  /** Single flight: ignored while `pending`. */
  toggle: (enabled: boolean) => void;
}

/**
 * Study Mode is set only from the POST response (and from vitals elsewhere). On
 * failure nothing changes, so the previous value is restored by never leaving it.
 */
export function useStudyMode(): UseStudyMode {
  const api = useApi();
  const scope = useRequestScope();
  const appDispatch = useAppDispatch();
  const dataDispatch = useDataDispatch();
  const refreshVitals = useRefreshVitals();
  const appRef = useLatest(useAppState());
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<PresentedError | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const toggle = useCallback(
    (enabled: boolean) => {
      const repoId = appRef.current.repoId;
      if (repoId === null || inFlight.current) return;
      inFlight.current = true;
      setPending(true);
      setError(null);
      const signal = scope.signal;
      void (async () => {
        try {
          const response = await api.setStudyMode(repoId, enabled, { signal });
          if (signal.aborted || appRef.current.repoId !== repoId) return;
          dataDispatch({
            type: 'repo-study-mode-patched',
            repoId,
            enabled: response.study_mode_enabled,
          });
          appDispatch({ type: 'study-mode-set', value: response.study_mode_enabled });
          void refreshVitals(repoId, 'replace');
        } catch (e) {
          if (e instanceof ApiAbortError || !mounted.current) return;
          setError(presentError(e, 'generic'));
        } finally {
          inFlight.current = false;
          if (mounted.current) setPending(false);
        }
      })();
    },
    [api, scope, appDispatch, dataDispatch, refreshVitals, appRef],
  );

  return { pending, error, toggle };
}
