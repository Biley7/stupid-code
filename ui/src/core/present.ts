import {
  ApiAbortError,
  ApiHttpError,
  ApiMalformedError,
  ApiNetworkError,
} from '../api/errors';

export interface PresentedError {
  message: string;
  retryable: boolean;
  retryAfterSeconds?: number;
}

export type ErrorContext = 'generic' | 'explain' | 'socratic' | 'ingest';

const EXPLAIN_UNAVAILABLE = 'The explanation service is unavailable. No explanation was produced.';
const GRADING_UNAVAILABLE = 'The grading service is unavailable. Your answers were not graded.';
const RATE_LIMITED = 'GitHub ingestion is rate limited.';
const LOCAL_INGEST_DISABLED = 'Local path ingestion is disabled on this server.';
const NETWORK = 'Could not reach the server. Check your connection and retry.';
const MALFORMED = 'The server returned an unexpected response.';
const UNKNOWN = 'Something went wrong.';

/** Maps an error to user-visible text. Returns null for aborts (show nothing). */
export function presentError(error: unknown, context: ErrorContext): PresentedError | null {
  if (error instanceof ApiAbortError) return null;
  if (error instanceof ApiHttpError) {
    const code = error.code;
    if (context === 'explain' && (code === 'llm_unavailable' || code === 'invalid_llm_output')) {
      return { message: EXPLAIN_UNAVAILABLE, retryable: true };
    }
    if (
      context === 'socratic' &&
      (code === 'llm_unavailable' || code === 'invalid_llm_output' || code === 'grading_unavailable')
    ) {
      return { message: GRADING_UNAVAILABLE, retryable: true };
    }
    if (context === 'ingest' && code === 'rate_limited') {
      const seconds = error.retryAfterSeconds;
      if (typeof seconds === 'number' && Number.isFinite(seconds) && seconds >= 0) {
        return {
          message: `${RATE_LIMITED} Retry in ${seconds} seconds.`,
          retryable: true,
          retryAfterSeconds: seconds,
        };
      }
      return { message: RATE_LIMITED, retryable: true };
    }
    if (context === 'ingest' && code === 'local_ingest_disabled') {
      return { message: LOCAL_INGEST_DISABLED, retryable: false };
    }
    return { message: error.message, retryable: true };
  }
  if (error instanceof ApiNetworkError) return { message: NETWORK, retryable: true };
  if (error instanceof ApiMalformedError) return { message: MALFORMED, retryable: true };
  return { message: UNKNOWN, retryable: true };
}
