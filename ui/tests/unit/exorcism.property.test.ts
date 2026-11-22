import { describe, expect, it } from 'vitest';
import fc from 'fast-check';
import {
  EXORCISM_SECONDS,
  MAX_ANSWER_LENGTH,
  initialExorcismState,
  transition,
  type ExorcismEvent,
  type ExorcismState,
} from '../../src/core/exorcism';
import {
  ApiAbortError,
  ApiHttpError,
  ApiMalformedError,
  ApiNetworkError,
  type ApiError,
} from '../../src/api/errors';
import type { SocraticQuestion, SocraticVerdict } from '../../src/api/types';

/**
 * Property 11: Exorcism state machine invariants.
 * **Validates: Requirements 23.8, 23.10, 23.13, 23.14, 23.15, 24.1, 24.2, 24.4, 24.5, 24.7, 24.11, 24.12, 24.15**
 */

const IDS = ['q1', 'q2', 'q3'];

const question = (id: string): SocraticQuestion => ({
  question_id: id,
  target_id: 't',
  prompt: `p-${id}`,
  line_reference: 'f.py:1',
  expected_concepts: [],
});

const validStart = fc
  .oneof(fc.constant(['q1']), fc.constant(['q1', 'q2']), fc.constant(['q2', 'q3']))
  .map((ids): ExorcismEvent => ({ type: 'start_ok', questions: ids.map(question) }));

const text = fc.oneof(
  fc.string({ maxLength: 20 }),
  fc.constantFrom('', ' ', '  \n\t ', ' ok ', 'answer'),
  fc.constantFrom(0, 1, 1999, 2000, 2001, 2002).map((n) => 'x'.repeat(n)),
  fc.constantFrom(1999, 2000, 2001).map((n) => ` ${'y'.repeat(n)} `),
);

const apiError: fc.Arbitrary<ApiError> = fc.oneof(
  fc.constant<ApiError>(new ApiNetworkError()),
  fc.constant<ApiError>(new ApiMalformedError('op')),
  fc.constant<ApiError>(new ApiAbortError()),
  fc
    .constantFrom(
      'study_mode_disabled',
      'grading_unavailable',
      'llm_unavailable',
      'invalid_llm_output',
      'unknown_target',
      'internal_error',
      null,
    )
    .map<ApiError>((code) => new ApiHttpError(code === 'study_mode_disabled' ? 403 : 500, code, 'm')),
);

const verdict: fc.Arbitrary<SocraticVerdict> = fc.record({
  target_id: fc.constant('t'),
  passed: fc.boolean(),
  score: fc.double({ min: 0, max: 1, noNaN: true }),
  feedback: fc.string({ maxLength: 20 }),
  new_state: fc.constantFrom('UNAUDITED', 'DISSECTED', 'MASTERED', 'STALE') as fc.Arbitrary<
    SocraticVerdict['new_state']
  >,
  next_review_at: fc.constantFrom(null, '2030-01-01T00:00:00Z'),
});

const event: fc.Arbitrary<ExorcismEvent> = fc.oneof(
  { weight: 1, arbitrary: validStart },
  { weight: 1, arbitrary: apiError.map((error): ExorcismEvent => ({ type: 'start_failed', error })) },
  {
    weight: 5,
    arbitrary: fc
      .tuple(fc.constantFrom(...IDS), text)
      .map(([questionId, t]): ExorcismEvent => ({ type: 'type', questionId, text: t })),
  },
  { weight: 8, arbitrary: fc.constant<ExorcismEvent>({ type: 'tick' }) },
  { weight: 3, arbitrary: fc.constant<ExorcismEvent>({ type: 'submit' }) },
  { weight: 2, arbitrary: verdict.map((v): ExorcismEvent => ({ type: 'submit_ok', verdict: v })) },
  { weight: 2, arbitrary: apiError.map((error): ExorcismEvent => ({ type: 'submit_failed', error })) },
  { weight: 1, arbitrary: fc.constant<ExorcismEvent>({ type: 'new_check' }) },
  { weight: 1, arbitrary: fc.constant<ExorcismEvent>({ type: 'restart' }) },
  { weight: 1, arbitrary: fc.constant<ExorcismEvent>({ type: 'retry' }) },
);

// Ticks are heavily weighted, so long sequences reach zero.
const sequence = fc.array(event, { minLength: 0, maxLength: 200 });

const NO_SUBMIT_PHASES = ['verdict', 'expired', 'study_off', 'read_only_off', 'submitting'];

function start(ids: string[]): ExorcismState {
  return transition(initialExorcismState(), { type: 'start_ok', questions: ids.map(question) }).state;
}

describe('Property 11: Exorcism state machine invariants', () => {
  it('Property 11: Exorcism state machine invariants', () => {
    // Step 1: holds for arbitrary event sequences from a valid start
    {
    fc.assert(
      fc.property(validStart, sequence, (first, events) => {
        let s = transition(initialExorcismState(), first).state;
        expect(s.phase).toBe('answering');
        let disabledAnswers: Record<string, string> | null = null;

        for (const e of events) {
          const prev = s;
          const { state: next, command } = transition(prev, e);

          // remaining bounds, and non-increasing unless a fresh start was issued.
          expect(next.remaining).toBeGreaterThanOrEqual(0);
          expect(next.remaining).toBeLessThanOrEqual(EXORCISM_SECONDS);
          if (command?.type === 'call_start') {
            expect(next.remaining).toBe(EXORCISM_SECONDS);
            expect(next.phase).toBe('starting');
            disabledAnswers = null;
          } else if (!(prev.phase === 'starting' && e.type === 'start_ok')) {
            expect(next.remaining).toBeLessThanOrEqual(prev.remaining);
          }

          if (command?.type === 'call_submit') {
            expect(NO_SUBMIT_PHASES).not.toContain(prev.phase);
            expect(prev.phase).toBe('answering');
            expect(next.phase).toBe('submitting');
            const ids = prev.questions.map((q) => q.question_id);
            expect(command.answers.map((a) => a.question_id)).toEqual(ids);
            expect(new Set(ids).size).toBe(ids.length);
            for (const a of command.answers) {
              expect(a.answer).toBe(a.answer.trim());
              expect(a.answer.length).toBeGreaterThan(0);
              expect(a.answer.length).toBeLessThanOrEqual(MAX_ANSWER_LENGTH);
              expect(a.answer).toBe((prev.answers[a.question_id] ?? '').trim());
            }
            // Nothing fabricated: answers state is untouched by submitting.
            expect(next.answers).toEqual(prev.answers);
            expect(disabledAnswers).toBeNull();
          }

          // Zero with an invalid answer expires without submitting.
          if (e.type === 'tick' && prev.phase === 'answering' && prev.remaining === 1) {
            const bad = prev.questions.some((q) => {
              const n = (prev.answers[q.question_id] ?? '').trim().length;
              return n === 0 || n > MAX_ANSWER_LENGTH;
            });
            if (bad) {
              expect(next.phase).toBe('expired');
              expect(command?.type).not.toBe('call_submit');
              expect(next.remaining).toBe(0);
            } else {
              expect(next.phase).toBe('submitting');
              expect(command?.type).toBe('call_submit');
            }
          }

          // Verdict stored exactly as returned.
          if (e.type === 'submit_ok' && prev.phase === 'submitting') {
            expect(next.phase).toBe('verdict');
            expect(next.verdict).toBe(e.verdict);
            expect(next.verdict?.passed).toBe(e.verdict.passed);
          }

          // study_mode_disabled on submit: answers kept, no further submit.
          if (
            e.type === 'submit_failed' &&
            prev.phase === 'submitting' &&
            e.error instanceof ApiHttpError &&
            e.error.code === 'study_mode_disabled'
          ) {
            expect(next.phase).toBe('read_only_off');
            expect(next.answers).toEqual(prev.answers);
            disabledAnswers = prev.answers;
          }
          if (disabledAnswers !== null) {
            expect(command?.type).not.toBe('call_submit');
            expect(next.answers).toEqual(disabledAnswers);
          }

          s = next;
        }
      }),
      { numRuns: 300 },
    );
    }

    // Step 2: expires at zero with a blank answer and emits no submit
    {
    let s = start(['q1', 'q2']);
    s = transition(s, { type: 'type', questionId: 'q1', text: 'a' }).state;
    let last = transition(s, { type: 'tick' });
    for (let i = 1; i < EXORCISM_SECONDS; i++) {
      s = last.state;
      last = transition(s, { type: 'tick' });
    }
    expect(last.state.phase).toBe('expired');
    expect(last.state.remaining).toBe(0);
    expect(last.command?.type).not.toBe('call_submit');
    expect(last.state.answers).toEqual({ q1: 'a', q2: '' });
    }

    // Step 3: submits trimmed answers at zero when all are valid
    {
    let s = start(['q1']);
    s = transition(s, { type: 'type', questionId: 'q1', text: '  hi  ' }).state;
    let last = transition(s, { type: 'tick' });
    for (let i = 1; i < EXORCISM_SECONDS; i++) last = transition(last.state, { type: 'tick' });
    expect(last.command).toEqual({ type: 'call_submit', answers: [{ question_id: 'q1', answer: 'hi' }] });
    }

    // Step 4: rejects a submit_failed study_mode_disabled retry path
    {
    let s = start(['q1']);
    s = transition(s, { type: 'type', questionId: 'q1', text: 'a' }).state;
    s = transition(s, { type: 'submit' }).state;
    const err = new ApiHttpError(403, 'study_mode_disabled', 'off');
    const r = transition(s, { type: 'submit_failed', error: err });
    expect(r.state.phase).toBe('read_only_off');
    expect(r.state.answers).toEqual({ q1: 'a' });
    expect(transition(r.state, { type: 'submit' }).command).toBeUndefined();
    }
  });
});
