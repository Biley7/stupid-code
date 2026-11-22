// Consistent loading, empty, and error states (Requirements 3.1 to 3.3, 3.6,
// 3.15, 3.16). Loading and empty use role="status"; error uses role="alert".

import { useEffect, useState } from 'react';
import { PlainText } from './PlainText';

export type StateBlockProps =
  | { variant: 'loading'; label: string; className?: string }
  | { variant: 'empty'; label: string; className?: string }
  | {
      variant: 'error';
      message: string;
      onRetry?: () => void;
      /** Shown when a retry follows a network error and the health check fails. */
      healthNote?: string;
      /** Disables retry until the countdown reaches zero. */
      retryAfterSeconds?: number;
      className?: string;
    };

function useCountdown(seconds: number | undefined): number {
  const start = seconds !== undefined && Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : 0;
  const [remaining, setRemaining] = useState(start);
  useEffect(() => {
    setRemaining(start);
    if (start <= 0) return undefined;
    const id = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(id);
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [start]);
  return remaining;
}

function ErrorBlock(props: Extract<StateBlockProps, { variant: 'error' }>) {
  const { message, onRetry, healthNote, retryAfterSeconds, className } = props;
  const remaining = useCountdown(retryAfterSeconds);
  const gated = remaining > 0;
  return (
    <div role="alert" className={`border border-crimson bg-surface p-3 text-sm ${className ?? ''}`}>
      <PlainText text={message} as="p" className="text-signal" />
      {healthNote ? <PlainText text={healthNote} as="p" className="mt-1 text-muted" /> : null}
      {gated ? (
        <p className="mt-1 font-mono text-xs text-muted">Retry available in {remaining} s</p>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          disabled={gated}
          className="mt-2 border border-hairline px-2 py-1 text-bone disabled:text-muted"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function StateBlock(props: StateBlockProps) {
  if (props.variant === 'error') return <ErrorBlock {...props} />;
  return (
    <div
      role="status"
      data-state={props.variant}
      className={`p-3 text-sm text-muted ${props.className ?? ''}`}
    >
      <PlainText text={props.label} />
    </div>
  );
}
