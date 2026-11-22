import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../api/context';
import { ApiHttpError, ApiNetworkError } from '../api/errors';

export type RetryHealth = 'idle' | 'checking' | 'answered' | 'unreachable';

export interface UseRetry {
  /** Runs the health pre-check after a network error, then `reload` once. */
  retry: () => void;
  health: RetryHealth;
  /** Seconds left of a `rate_limited` countdown; null when none runs. */
  secondsLeft: number | null;
  /** True while checking health or while a rate-limit countdown runs. */
  disabled: boolean;
}

/**
 * Retry control for one failed request. After an `ApiNetworkError` it calls
 * `getHealth` once and re-sends the request only when the backend answers
 * `{status:'ok', service:'stupid-code'}`. A `rate_limited` error with a readable
 * `retryAfterSeconds` disables retry until the timer-driven countdown ends.
 */
export function useRetry(reload: () => unknown, lastError: unknown): UseRetry {
  const api = useApi();
  const [health, setHealth] = useState<RetryHealth>('idle');
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const busy = useRef(false);
  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);

  const retryAfter =
    lastError instanceof ApiHttpError && lastError.code === 'rate_limited'
      ? lastError.retryAfterSeconds
      : undefined;

  // Countdown driven by timer ticks, not clock reads.
  useEffect(() => {
    setHealth('idle');
    if (retryAfter === undefined || retryAfter <= 0) {
      setSecondsLeft(null);
      return;
    }
    setSecondsLeft(retryAfter);
    const id = setInterval(() => {
      setSecondsLeft((current) => {
        if (current === null || current <= 1) {
          clearInterval(id);
          return null;
        }
        return current - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [lastError, retryAfter]);

  const retry = useCallback(() => {
    if (busy.current || secondsLeft !== null) return;
    if (!(lastError instanceof ApiNetworkError)) {
      reload();
      return;
    }
    busy.current = true;
    const ctl = new AbortController();
    controller.current = ctl;
    setHealth('checking');
    void (async () => {
      try {
        const result = await api.getHealth({ signal: ctl.signal });
        if (!mounted.current) return;
        if (result.status === 'ok' && result.service === 'stupid-code') {
          setHealth('answered');
          reload();
        } else {
          setHealth('unreachable');
        }
      } catch {
        if (mounted.current && !ctl.signal.aborted) setHealth('unreachable');
      } finally {
        busy.current = false;
        if (controller.current === ctl) controller.current = null;
      }
    })();
  }, [api, reload, lastError, secondsLeft]);

  return { retry, health, secondsLeft, disabled: health === 'checking' || secondsLeft !== null };
}
