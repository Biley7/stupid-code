/** Fixed message used when an error response has no usable envelope. */
export const GENERIC_HTTP_MESSAGE = 'The server returned an error.';

const NETWORK_MESSAGE = 'Network request failed.';
const MALFORMED_MESSAGE = 'Malformed response.';
const ABORT_MESSAGE = 'Request aborted.';

/** Non-2xx response. `code` is null when the body was not a valid error envelope. */
export class ApiHttpError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly retryAfterSeconds: number | undefined;

  constructor(status: number, code: string | null, message: string, retryAfterSeconds?: number) {
    super(message);
    this.name = 'ApiHttpError';
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** The request never produced a response. No cause is attached. */
export class ApiNetworkError extends Error {
  constructor() {
    super(NETWORK_MESSAGE);
    this.name = 'ApiNetworkError';
  }
}

/** A 2xx response whose body failed JSON parsing or validation. */
export class ApiMalformedError extends Error {
  readonly operation: string;

  constructor(operation: string) {
    super(MALFORMED_MESSAGE);
    this.name = 'ApiMalformedError';
    this.operation = operation;
  }
}

/** The request was cancelled through its AbortSignal. */
export class ApiAbortError extends Error {
  constructor() {
    super(ABORT_MESSAGE);
    this.name = 'ApiAbortError';
  }
}

export type ApiError = ApiHttpError | ApiNetworkError | ApiMalformedError | ApiAbortError;
