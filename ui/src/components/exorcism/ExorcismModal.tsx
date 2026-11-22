// Exorcism modal (Requirements 23, 24, 25.7). Pure view over the core/exorcism state.
// It computes no grade, score, pass result, or mastery state, and never shows
// `expected_concepts`.

import { MAX_ANSWER_LENGTH, type ExorcismState } from '../../core/exorcism';
import { MasteryBadge } from '../shared/MasteryBadge';
import { Modal } from '../shared/Modal';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

export interface ExorcismModalProps {
  state: ExorcismState;
  /** Symbol name shown in the accessible title. */
  symbolLabel: string;
  onClose: () => void;
  onType: (questionId: string, text: string) => void;
  onSubmit: () => void;
  onNewCheck: () => void;
  onRestart: () => void;
  onRetry: () => void;
  /** True when the post-verdict vitals refresh failed (the notice stays until it succeeds). */
  refreshFailed: boolean;
  onRetryRefresh: () => void;
}

const BUTTON =
  'border border-hairline px-3 py-1 text-sm text-bone hover:border-bone disabled:text-muted disabled:hover:border-hairline';

function formatReview(value: string): string {
  return value;
}

export function ExorcismModal(props: ExorcismModalProps) {
  const { state, symbolLabel } = props;
  const { phase } = state;
  const title = `Exorcism Check: ${symbolLabel}`;

  const locked = phase !== 'answering';
  const showQuestions =
    phase === 'answering' ||
    phase === 'submitting' ||
    phase === 'expired' ||
    phase === 'verdict' ||
    phase === 'read_only_off';

  return (
    <Modal title={title} onRequestClose={props.onClose}>
      <div className="flex flex-col gap-4" aria-busy={phase === 'starting' || phase === 'submitting'}>
        {phase === 'starting' ? <StateBlock variant="loading" label="Preparing the check…" /> : null}

        {phase === 'start_error' && state.error ? (
          <StateBlock
            variant="error"
            message={state.error.message}
            onRetry={state.error.retryable ? props.onRetry : undefined}
            retryAfterSeconds={state.error.retryAfterSeconds}
          />
        ) : null}

        {phase === 'study_off' ? (
          <p role="alert" className="m-0 border border-hairline p-3 text-sm text-bone">
            Study Mode is off. Turn it on to run an Exorcism Check.
          </p>
        ) : null}

        {showQuestions ? (
          <>
            {phase === 'answering' || phase === 'submitting' || phase === 'expired' ? (
              <p className="m-0 font-mono text-sm text-bone">
                Time remaining: <span className={state.remaining <= 10 ? 'text-signal' : ''}>{state.remaining}</span> s
              </p>
            ) : null}

            {phase === 'expired' ? (
              <div role="alert" className="border border-crimson p-3 text-sm">
                <p className="m-0 text-signal">Time expired. Some answers were blank, so nothing was submitted.</p>
                <button type="button" className={`${BUTTON} mt-2`} onClick={props.onRestart}>
                  Restart check
                </button>
              </div>
            ) : null}

            {phase === 'read_only_off' ? (
              <p role="alert" className="m-0 border border-hairline p-3 text-sm text-bone">
                Study Mode is off. Your answers are kept read-only and cannot be submitted.
              </p>
            ) : null}

            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                if (phase === 'answering') props.onSubmit();
              }}
            >
              {state.questions.map((q, i) => {
                const raw = state.answers[q.question_id] ?? '';
                const count = raw.trim().length;
                const invalid = state.validation.includes(q.question_id);
                const inputId = `exorcism-${q.question_id}`;
                return (
                  <div key={q.question_id} className="flex flex-col gap-1">
                    <label htmlFor={inputId} className="text-sm text-bone">
                      <span className="text-muted">Question {i + 1}. </span>
                      <PlainText text={q.prompt} />
                    </label>
                    <PlainText
                      as="span"
                      className="font-mono text-xs text-muted"
                      text={`Line reference: ${q.line_reference}`}
                    />
                    <textarea
                      id={inputId}
                      rows={4}
                      maxLength={MAX_ANSWER_LENGTH}
                      value={raw}
                      readOnly={locked}
                      aria-invalid={invalid}
                      aria-describedby={`${inputId}-count`}
                      onChange={(e) => props.onType(q.question_id, e.target.value)}
                      className={`w-full border bg-obsidian p-2 font-mono text-sm text-bone ${invalid ? 'border-crimson' : 'border-hairline'}`}
                    />
                    <span id={`${inputId}-count`} className="font-mono text-xs text-muted">
                      {count} / {MAX_ANSWER_LENGTH}
                    </span>
                  </div>
                );
              })}

              {state.validation.length > 0 ? (
                <p role="alert" className="m-0 text-sm text-signal">
                  {`Answer required (1 to ${MAX_ANSWER_LENGTH} characters) for: ${state.questions
                    .map((q, i) => ({ id: q.question_id, n: i + 1 }))
                    .filter((x) => state.validation.includes(x.id))
                    .map((x) => `question ${x.n}`)
                    .join(', ')}.`}
                </p>
              ) : null}

              {state.error && (phase === 'answering' || phase === 'submitting') ? (
                <StateBlock variant="error" message={state.error.message} />
              ) : null}

              {phase === 'submitting' ? <StateBlock variant="loading" label="Grading your answers…" /> : null}

              {phase === 'answering' || phase === 'submitting' ? (
                <div>
                  <button type="submit" className={BUTTON} disabled={phase !== 'answering'}>
                    Submit answers
                  </button>
                </div>
              ) : null}
            </form>
          </>
        ) : null}

        {phase === 'verdict' && state.verdict ? <Verdict {...props} verdict={state.verdict} /> : null}
      </div>
    </Modal>
  );
}

function Verdict(props: ExorcismModalProps & { verdict: NonNullable<ExorcismState['verdict']> }) {
  const { verdict, refreshFailed } = props;
  const passed = verdict.passed;
  const tone = passed ? 'border-verified text-verified' : 'border-crimson text-signal';
  return (
    <section aria-label="Verdict" className="flex flex-col gap-3">
      <div role="status" className={`border p-3 ${tone}`}>
        <p className="m-0 font-mono text-base font-semibold">{passed ? 'PASSED' : 'FAILED'}</p>
        <p className="m-0 font-mono text-sm">Score: {Math.round(verdict.score * 100)}%</p>
      </div>
      <PlainText as="p" className="m-0 text-sm text-bone" text={verdict.feedback} />
      <div className="flex items-center gap-2 text-sm text-muted">
        <span>New state:</span>
        <MasteryBadge state={verdict.new_state} />
      </div>
      {verdict.next_review_at !== null ? (
        <p className="m-0 font-mono text-sm text-muted">
          Next review: <PlainText text={formatReview(verdict.next_review_at)} />
        </p>
      ) : null}

      {refreshFailed ? (
        <div role="alert" className="border border-stale p-3 text-sm">
          <p className="m-0 text-stale">The display is out of date: the mastery refresh failed.</p>
          <button type="button" className={`${BUTTON} mt-2`} onClick={props.onRetryRefresh}>
            Retry refresh
          </button>
        </div>
      ) : null}

      <div className="flex gap-2">
        <button type="button" className={BUTTON} onClick={props.onNewCheck}>
          New check
        </button>
        <button type="button" className={BUTTON} onClick={props.onClose}>
          Close
        </button>
      </div>
    </section>
  );
}
