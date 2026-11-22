/**
 * Exorcism modal state machine. Pure: no clock, no I/O, no React.
 * The hook runs the returned `command` and feeds API results back as events.
 */
import {
  ApiAbortError,
  ApiHttpError,
  ApiMalformedError,
  ApiNetworkError,
  type ApiError,
} from '../api/errors';
import type { SocraticQuestion, SocraticVerdict } from '../api/types';

export const EXORCISM_SECONDS = 60;
export const MAX_ANSWER_LENGTH = 2000;
export const MAX_QUESTIONS = 2;

export interface PresentedError {
  message: string;
  retryable: boolean;
  retryAfterSeconds?: number;
}

export type ExorcismPhase =
  | 'starting'
  | 'start_error'
  | 'study_off'
  | 'answering'
  | 'submitting'
  | 'verdict'
  | 'expired'
  | 'read_only_off';

export interface ExorcismState {
  phase: ExorcismPhase;
  questions: SocraticQuestion[];
  /** Raw text per question_id. */
  answers: Record<string, string>;
  /** Whole seconds, 60 down to 0. */
  remaining: number;
  /** Question ids that failed validation. */
  validation: string[];
  verdict: SocraticVerdict | null;
  error: PresentedError | null;
}

export type ExorcismEvent =
  | { type: 'start_ok'; questions: SocraticQuestion[] }
  | { type: 'start_failed'; error: ApiError }
  | { type: 'type'; questionId: string; text: string }
  | { type: 'tick' }
  | { type: 'submit' }
  | { type: 'submit_ok'; verdict: SocraticVerdict }
  | { type: 'submit_failed'; error: ApiError }
  | { type: 'new_check' }
  | { type: 'restart' }
  | { type: 'retry' };

export type ExorcismCommand =
  | { type: 'call_start' }
  | { type: 'call_submit'; answers: { question_id: string; answer: string }[] }
  | { type: 'stop_timer' };

export interface ExorcismResult {
  state: ExorcismState;
  command?: ExorcismCommand;
}

const STUDY_MODE_OFF_TEXT = 'Study Mode is off.';
const GRADING_UNAVAILABLE_TEXT = 'Grading is unavailable. Your answers are kept; try submitting again.';
const NETWORK_TEXT = 'Network request failed.';
const MALFORMED_TEXT = 'Malformed response.';

/** State at modal open; the hook issues `call_start` once. */
export function initialExorcismState(): ExorcismState {
  return {
    phase: 'starting',
    questions: [],
    answers: {},
    remaining: EXORCISM_SECONDS,
    validation: [],
    verdict: null,
    error: null,
  };
}

function errorCode(error: ApiError): string | null {
  return error instanceof ApiHttpError ? error.code : null;
}

function presentExorcismError(error: ApiError, context: 'start' | 'submit'): PresentedError {
  if (error instanceof ApiNetworkError) return { message: NETWORK_TEXT, retryable: true };
  if (error instanceof ApiMalformedError) return { message: MALFORMED_TEXT, retryable: true };
  if (error instanceof ApiAbortError) return { message: error.message, retryable: false };
  const code = errorCode(error);
  if (code === 'study_mode_disabled') return { message: STUDY_MODE_OFF_TEXT, retryable: false };
  if (context === 'submit' && (code === 'grading_unavailable' || code === 'llm_unavailable' || code === 'invalid_llm_output')) {
    return { message: GRADING_UNAVAILABLE_TEXT, retryable: true };
  }
  const retryAfter = error instanceof ApiHttpError ? error.retryAfterSeconds : undefined;
  return retryAfter === undefined
    ? { message: error.message, retryable: true }
    : { message: error.message, retryable: true, retryAfterSeconds: retryAfter };
}

function validQuestionSet(questions: SocraticQuestion[]): boolean {
  if (questions.length < 1 || questions.length > MAX_QUESTIONS) return false;
  return new Set(questions.map((q) => q.question_id)).size === questions.length;
}

/** Question ids whose trimmed answer is blank or longer than 2000 characters. */
function invalidIds(s: ExorcismState): string[] {
  return s.questions
    .filter((q) => {
      const len = (s.answers[q.question_id] ?? '').trim().length;
      return len === 0 || len > MAX_ANSWER_LENGTH;
    })
    .map((q) => q.question_id);
}

function buildSubmit(s: ExorcismState): { question_id: string; answer: string }[] {
  return s.questions.map((q) => ({
    question_id: q.question_id,
    answer: (s.answers[q.question_id] ?? '').trim(),
  }));
}

function startOver(): ExorcismResult {
  return { state: initialExorcismState(), command: { type: 'call_start' } };
}

function submitting(s: ExorcismState, remaining: number): ExorcismResult {
  return {
    state: { ...s, phase: 'submitting', remaining, validation: [], error: null },
    command: { type: 'call_submit', answers: buildSubmit(s) },
  };
}

export function transition(s: ExorcismState, e: ExorcismEvent): ExorcismResult {
  switch (e.type) {
    case 'start_ok': {
      if (s.phase !== 'starting') return { state: s };
      if (!validQuestionSet(e.questions)) {
        return {
          state: {
            ...s,
            phase: 'start_error',
            questions: [],
            answers: {},
            remaining: EXORCISM_SECONDS,
            error: {
              message: `The check returned ${e.questions.length} questions; expected 1 or 2.`,
              retryable: true,
            },
          },
        };
      }
      const answers: Record<string, string> = {};
      for (const q of e.questions) answers[q.question_id] = '';
      return {
        state: {
          ...s,
          phase: 'answering',
          questions: e.questions,
          answers,
          remaining: EXORCISM_SECONDS,
          validation: [],
          verdict: null,
          error: null,
        },
      };
    }

    case 'start_failed': {
      if (s.phase !== 'starting' || e.error instanceof ApiAbortError) return { state: s };
      const error = presentExorcismError(e.error, 'start');
      if (errorCode(e.error) === 'study_mode_disabled') {
        return { state: { ...s, phase: 'study_off', error } };
      }
      return { state: { ...s, phase: 'start_error', error } };
    }

    case 'type': {
      if (s.phase !== 'answering') return { state: s };
      if (!s.questions.some((q) => q.question_id === e.questionId)) return { state: s };
      return {
        state: {
          ...s,
          answers: { ...s.answers, [e.questionId]: e.text },
          validation: s.validation.filter((id) => id !== e.questionId),
        },
      };
    }

    case 'tick': {
      if (s.phase !== 'answering' || s.remaining <= 0) return { state: s };
      const remaining = Math.max(0, Math.min(EXORCISM_SECONDS, s.remaining - 1));
      if (remaining > 0) return { state: { ...s, remaining } };
      const bad = invalidIds(s);
      if (bad.length === 0) return submitting(s, 0);
      // No answer is fabricated: any blank or oversize answer at zero expires the check.
      return {
        state: { ...s, phase: 'expired', remaining: 0, validation: bad, error: null },
        command: { type: 'stop_timer' },
      };
    }

    case 'submit': {
      if (s.phase !== 'answering') return { state: s };
      const bad = invalidIds(s);
      if (bad.length > 0) return { state: { ...s, validation: bad } };
      return submitting(s, s.remaining);
    }

    case 'submit_ok': {
      if (s.phase !== 'submitting') return { state: s };
      return {
        state: { ...s, phase: 'verdict', verdict: e.verdict, validation: [], error: null },
        command: { type: 'stop_timer' },
      };
    }

    case 'submit_failed': {
      if (s.phase !== 'submitting' || e.error instanceof ApiAbortError) return { state: s };
      const error = presentExorcismError(e.error, 'submit');
      if (errorCode(e.error) === 'study_mode_disabled') {
        return {
          state: { ...s, phase: 'read_only_off', error },
          command: { type: 'stop_timer' },
        };
      }
      return { state: { ...s, phase: 'answering', error } };
    }

    case 'new_check':
      return s.phase === 'verdict' ? startOver() : { state: s };

    case 'restart':
      return s.phase === 'expired' ? startOver() : { state: s };

    case 'retry':
      return s.phase === 'start_error' ? startOver() : { state: s };
  }
}
