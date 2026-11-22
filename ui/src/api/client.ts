import { buildUrl, normalizeBaseUrl } from './config';
import {
  ApiAbortError,
  ApiHttpError,
  ApiMalformedError,
  ApiNetworkError,
  GENERIC_HTTP_MESSAGE,
} from './errors';
import type {
  ComprehensionVitals,
  ExplainRequest,
  ExplainResponse,
  HealthResponse,
  IngestRequest,
  IngestResponse,
  RepoSummary,
  SnapshotResponse,
  SocraticCheck,
  SocraticSubmitRequest,
  SocraticVerdict,
  StudyModeResponse,
} from './types';
import {
  validateExplainResponse,
  validateHealth,
  validateIngestResponse,
  validateRepoList,
  validateSnapshotResponse,
  validateSocraticCheck,
  validateSocraticVerdict,
  validateStudyModeResponse,
  validateVitals,
  type Validator,
} from './validate';

export interface CallOpts {
  signal?: AbortSignal;
}

export interface ApiClient {
  getHealth(opts?: CallOpts): Promise<HealthResponse>;
  listRepos(opts?: CallOpts): Promise<RepoSummary[]>;
  ingestRepo(body: IngestRequest, opts?: CallOpts): Promise<IngestResponse>;
  getSnapshot(repoId: string, opts?: CallOpts): Promise<SnapshotResponse>;
  explain(repoId: string, body: ExplainRequest, opts?: CallOpts): Promise<ExplainResponse>;
  getVitals(repoId: string, opts?: CallOpts): Promise<ComprehensionVitals>;
  setStudyMode(repoId: string, enabled: boolean, opts?: CallOpts): Promise<StudyModeResponse>;
  startSocratic(repoId: string, targetId: string, opts?: CallOpts): Promise<SocraticCheck>;
  submitSocratic(
    repoId: string,
    body: SocraticSubmitRequest,
    opts?: CallOpts,
  ): Promise<SocraticVerdict>;
}

export interface ApiClientOptions {
  baseUrl?: string;
}

interface CallSpec<T> {
  operation: string;
  method: 'GET' | 'POST';
  path: string;
  body?: unknown;
  validate: Validator<T>;
  signal?: AbortSignal;
  /** Extra semantic check on a validated body; false means malformed. */
  check?: (value: T) => boolean;
}

function isAbort(error: unknown, signal: AbortSignal | undefined): boolean {
  if (signal?.aborted) return true;
  return typeof error === 'object' && error !== null && (error as { name?: unknown }).name === 'AbortError';
}

function parseRetryAfter(response: Response): number | undefined {
  if (response.status !== 429) return undefined;
  const raw = response.headers.get('Retry-After');
  if (raw === null || !/^\s*\d+\s*$/.test(raw)) return undefined;
  const seconds = Number.parseInt(raw, 10);
  return Number.isSafeInteger(seconds) ? seconds : undefined;
}

function errorFromBody(status: number, text: string, retryAfter: number | undefined): ApiHttpError {
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed === 'object' && parsed !== null) {
      const err = (parsed as { error?: unknown }).error;
      if (typeof err === 'object' && err !== null) {
        const { code, message } = err as { code?: unknown; message?: unknown };
        if (typeof code === 'string' && typeof message === 'string') {
          return new ApiHttpError(status, code, message, retryAfter);
        }
      }
    }
  } catch {
    // fall through to generic
  }
  return new ApiHttpError(status, null, GENERIC_HTTP_MESSAGE, retryAfter);
}

function explainMatches(request: ExplainRequest, response: ExplainResponse): boolean {
  const env = response.envelope;
  if (env.lens !== request.lens || env.target_id !== request.target_id) return false;
  const { l1, l2, l3 } = env;
  switch (request.lens) {
    case 'L1_SYNTAX':
      return l1 !== null && l2 === null && l3 === null && l1.target_id === request.target_id;
    case 'L2_FLOW':
      return l2 !== null && l1 === null && l3 === null && l2.target_id === request.target_id;
    case 'L3_ARCHITECTURE':
      return l3 !== null && l1 === null && l2 === null && l3.target_id === request.target_id;
    default:
      return false;
  }
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const base = normalizeBaseUrl(
    options.baseUrl !== undefined
      ? options.baseUrl
      : (import.meta.env.VITE_API_BASE_URL as string | undefined),
  );

  async function call<T>(spec: CallSpec<T>): Promise<T> {
    const { signal } = spec;
    if (signal?.aborted) throw new ApiAbortError();

    const init: RequestInit = { method: spec.method };
    if (signal) init.signal = signal;
    if (spec.body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(spec.body);
    }

    let response: Response;
    try {
      response = await globalThis.fetch(buildUrl(base, spec.path), init);
    } catch (error) {
      throw isAbort(error, signal) ? new ApiAbortError() : new ApiNetworkError();
    }

    let text: string;
    try {
      text = await response.text();
    } catch (error) {
      throw isAbort(error, signal) ? new ApiAbortError() : new ApiNetworkError();
    }

    if (response.status < 200 || response.status > 299) {
      throw errorFromBody(response.status, text, parseRetryAfter(response));
    }

    let json: unknown;
    try {
      json = JSON.parse(text);
    } catch {
      throw new ApiMalformedError(spec.operation);
    }
    const value = spec.validate(json);
    if (value === null) throw new ApiMalformedError(spec.operation);
    if (spec.check && !spec.check(value)) throw new ApiMalformedError(spec.operation);
    return value;
  }

  const repoPath = (repoId: string): string => `/api/repos/${encodeURIComponent(repoId)}`;

  return {
    getHealth: (opts) =>
      call({
        operation: 'getHealth',
        method: 'GET',
        path: '/health',
        validate: validateHealth,
        signal: opts?.signal,
      }),

    listRepos: (opts) =>
      call({
        operation: 'listRepos',
        method: 'GET',
        path: '/api/repos',
        validate: validateRepoList,
        signal: opts?.signal,
      }),

    ingestRepo: (body, opts) => {
      const hasUrl = body.url !== undefined;
      const hasPath = body.path !== undefined;
      if (hasUrl === hasPath) {
        throw new TypeError('ingestRepo requires exactly one of url or path');
      }
      return call({
        operation: 'ingestRepo',
        method: 'POST',
        path: '/api/repos/ingest',
        body,
        validate: validateIngestResponse,
        signal: opts?.signal,
      });
    },

    getSnapshot: (repoId, opts) =>
      call({
        operation: 'getSnapshot',
        method: 'GET',
        path: `${repoPath(repoId)}/snapshot`,
        validate: validateSnapshotResponse,
        signal: opts?.signal,
      }),

    explain: (repoId, body, opts) => {
      const request: ExplainRequest = { target_id: body.target_id, lens: body.lens };
      return call({
        operation: 'explain',
        method: 'POST',
        path: `${repoPath(repoId)}/explain`,
        body: request,
        validate: validateExplainResponse,
        signal: opts?.signal,
        check: (value) => explainMatches(request, value),
      });
    },

    getVitals: (repoId, opts) =>
      call({
        operation: 'getVitals',
        method: 'GET',
        path: `${repoPath(repoId)}/vitals`,
        validate: validateVitals,
        signal: opts?.signal,
      }),

    setStudyMode: (repoId, enabled, opts) =>
      call({
        operation: 'setStudyMode',
        method: 'POST',
        path: `${repoPath(repoId)}/study-mode`,
        body: { enabled },
        validate: validateStudyModeResponse,
        signal: opts?.signal,
      }),

    startSocratic: (repoId, targetId, opts) =>
      call({
        operation: 'startSocratic',
        method: 'POST',
        path: `${repoPath(repoId)}/socratic/start`,
        body: { target_id: targetId },
        validate: validateSocraticCheck,
        signal: opts?.signal,
      }),

    submitSocratic: (repoId, body, opts) =>
      call({
        operation: 'submitSocratic',
        method: 'POST',
        path: `${repoPath(repoId)}/socratic/submit`,
        body: {
          target_id: body.target_id,
          answers: body.answers.map((a) => ({ question_id: a.question_id, answer: a.answer })),
        },
        validate: validateSocraticVerdict,
        signal: opts?.signal,
      }),
  };
}
