import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../api/context';
import { ApiAbortError, ApiHttpError, type ApiError } from '../api/errors';
import {
  initialExorcismState,
  transition,
  type ExorcismCommand,
  type ExorcismEvent,
  type ExorcismState,
} from '../core/exorcism';
import { useAppDispatch, useAppState } from '../state/store';
import { useLatest } from './useLatest';
import { useRefreshVitals } from './useVitals';

export interface UseSocratic {
  /** Null while the modal is closed. */
  state: ExorcismState | null;
  open: (repoId: string, targetId: string) => void;
  close: () => void;
  type: (questionId: string, text: string) => void;
  submit: () => void;
  newCheck: () => void;
  restart: () => void;
  retry: () => void;
  /** Re-runs the vitals refresh after a verdict (out-of-date notice retry). */
  retryRefresh: () => void;
}

interface Session {
  repoId: string;
  targetId: string;
  controller: AbortController;
}

/** Drives the pure Exorcism state machine: runs its commands and feeds results back. */
export function useSocratic(): UseSocratic {
  const api = useApi();
  const appDispatch = useAppDispatch();
  const refreshVitals = useRefreshVitals();
  const appRef = useLatest(useAppState());

  const [state, setState] = useState<ExorcismState | null>(null);
  const stateRef = useRef<ExorcismState | null>(null);
  const session = useRef<Session | null>(null);
  const mounted = useRef(true);

  const apply = useRef<(event: ExorcismEvent) => void>(() => undefined);

  const handleDisabled = useCallback(
    (repoId: string) => {
      appDispatch({ type: 'study-mode-set', value: false });
      void refreshVitals(repoId, 'replace');
    },
    [appDispatch, refreshVitals],
  );

  const runCommand = useCallback(
    (command: ExorcismCommand, current: Session) => {
      const { repoId, targetId } = current;
      const signal = current.controller.signal;
      const live = (): boolean => mounted.current && session.current === current && !signal.aborted;

      if (command.type === 'call_start') {
        void (async () => {
          try {
            const check = await api.startSocratic(repoId, targetId, { signal });
            if (live()) apply.current({ type: 'start_ok', questions: check.questions });
          } catch (e) {
            if (e instanceof ApiAbortError || !live()) return;
            apply.current({ type: 'start_failed', error: e as ApiError });
            if (e instanceof ApiHttpError && e.code === 'study_mode_disabled') handleDisabled(repoId);
          }
        })();
      } else if (command.type === 'call_submit') {
        void (async () => {
          try {
            const verdict = await api.submitSocratic(
              repoId,
              { target_id: targetId, answers: command.answers },
              { signal },
            );
            if (!live()) return;
            apply.current({ type: 'submit_ok', verdict });
            // Mastery is never computed here; vitals carry the new states.
            void refreshVitals(repoId, 'keep');
          } catch (e) {
            if (e instanceof ApiAbortError || !live()) return;
            apply.current({ type: 'submit_failed', error: e as ApiError });
            if (e instanceof ApiHttpError && e.code === 'study_mode_disabled') handleDisabled(repoId);
          }
        })();
      }
      // `stop_timer` needs no action: the tick effect stops when the phase leaves `answering`.
    },
    [api, handleDisabled, refreshVitals],
  );

  apply.current = (event) => {
    const current = session.current;
    const prev = stateRef.current;
    if (current === null || prev === null) return;
    const result = transition(prev, event);
    stateRef.current = result.state;
    setState(result.state);
    if (result.command) runCommand(result.command, current);
  };

  const close = useCallback(() => {
    session.current?.controller.abort();
    session.current = null;
    stateRef.current = null;
    setState(null);
  }, []);

  const open = useCallback(
    (repoId: string, targetId: string) => {
      session.current?.controller.abort();
      const next: Session = { repoId, targetId, controller: new AbortController() };
      session.current = next;
      const initial = initialExorcismState();
      stateRef.current = initial;
      setState(initial);
      runCommand({ type: 'call_start' }, next);
    },
    [runCommand],
  );

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      session.current?.controller.abort();
    };
  }, []);

  // A repository change ends the session: its results must not touch the new repository.
  const selectedRepo = appRef.current.repoId;
  useEffect(() => {
    if (session.current !== null && session.current.repoId !== selectedRepo) close();
  }, [selectedRepo, close]);

  // One tick per second while answering.
  const answering = state?.phase === 'answering';
  useEffect(() => {
    if (!answering) return;
    const id = setInterval(() => apply.current({ type: 'tick' }), 1000);
    return () => clearInterval(id);
  }, [answering]);

  return {
    state,
    open,
    close,
    type: (questionId, text) => apply.current({ type: 'type', questionId, text }),
    submit: () => apply.current({ type: 'submit' }),
    newCheck: () => apply.current({ type: 'new_check' }),
    restart: () => apply.current({ type: 'restart' }),
    retry: () => apply.current({ type: 'retry' }),
    retryRefresh: () => {
      const current = session.current;
      if (current !== null) void refreshVitals(current.repoId, 'keep');
    },
  };
}
