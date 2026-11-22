import { useState, type FormEvent } from 'react';
import { useIngest } from '../../data/useIngest';
import { Modal } from '../shared/Modal';
import { PlainText } from '../shared/PlainText';
import { presentError } from '../../core/present';
import { ApiNetworkError } from '../../api/errors';

type Source = 'url' | 'path';

const MAX_INPUT = 4096;
const GITHUB_PREFIX = 'https://github.com/';

export interface IngestModalProps {
  onClose: () => void;
}

function validate(source: Source, raw: string): string | null {
  const label = source === 'url' ? 'GitHub URL' : 'Local path';
  const value = raw.trim();
  if (value.length === 0) return `${label} must not be blank.`;
  if (value.length > MAX_INPUT) return `${label} must be at most ${MAX_INPUT} characters.`;
  if (source === 'url' && !value.startsWith(GITHUB_PREFIX)) {
    return `${label} must start with ${GITHUB_PREFIX}`;
  }
  return null;
}

export function IngestModal({ onClose }: IngestModalProps) {
  const ingest = useIngest();
  const [source, setSource] = useState<Source>('url');
  const [text, setText] = useState('');
  const [validation, setValidation] = useState<string | null>(null);

  const submitting = ingest.phase === 'submitting';
  const done = ingest.phase === 'done' && ingest.result !== null;
  const inputLabel = source === 'url' ? 'GitHub URL' : 'Local path';

  function changeSource(next: Source) {
    if (submitting || next === source) return;
    setSource(next);
    setValidation(null);
    ingest.reset();
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    const problem = validate(source, text);
    setValidation(problem);
    if (problem !== null) return;
    const value = text.trim();
    ingest.submit(source === 'url' ? { url: value } : { path: value });
  }

  const result = ingest.result;
  const followUpError = presentError(new ApiNetworkError(), 'generic');

  return (
    <Modal title="Ingest repository" onRequestClose={onClose} blockClose={submitting}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
        <fieldset className="flex gap-4" disabled={submitting}>
          <legend className="mb-1 text-sm text-muted">Source</legend>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="ingest-source"
              checked={source === 'url'}
              onChange={() => changeSource('url')}
            />
            GitHub URL
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="ingest-source"
              checked={source === 'path'}
              onChange={() => changeSource('path')}
            />
            Local path
          </label>
        </fieldset>

        <label className="flex flex-col gap-1 text-sm">
          <span>{inputLabel}</span>
          <input
            type="text"
            value={text}
            readOnly={submitting}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={validation !== null}
            aria-describedby={validation !== null ? 'ingest-validation' : undefined}
            placeholder={source === 'url' ? 'https://github.com/owner/repo' : '/path/to/repo'}
            className="border border-hairline bg-obsidian px-2 py-1 font-mono text-bone"
          />
        </label>

        {validation !== null && (
          <p id="ingest-validation" role="alert" className="text-sm text-signal">
            {validation}
          </p>
        )}

        {submitting && (
          <div role="status" aria-live="polite" className="text-sm text-muted">
            <progress aria-label="Ingesting repository" className="block w-full" />
            Ingesting…
          </div>
        )}

        {ingest.error !== null && (
          <p role="alert" className="text-sm text-signal">
            <PlainText text={ingest.error.message} />
          </p>
        )}

        {done && result !== null && (
          <section aria-label="Ingest result" className="flex flex-col gap-2 text-sm">
            <p>
              Repository: <PlainText text={result.repo_id} className="font-mono" />
            </p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono">
              <dt>Files</dt>
              <dd>{result.summary.file_count}</dd>
              <dt>Symbols</dt>
              <dd>{result.summary.symbol_count}</dd>
              <dt>Edges</dt>
              <dd>{result.summary.edge_count}</dd>
              <dt>DSA signals</dt>
              <dd>{result.summary.dsa_signal_count}</dd>
              <dt>Truncated</dt>
              <dd>{result.truncated ? 'Yes' : 'No'}</dd>
            </dl>
            {result.warnings.length === 0 ? (
              <p className="text-muted">No warnings were returned.</p>
            ) : (
              <ul className="flex flex-col gap-1">
                {result.warnings.map((w, i) => (
                  <li key={i} className="border border-hairline p-2">
                    <PlainText text={w.kind} className="font-mono" />{' '}
                    <PlainText text={w.path} className="font-mono" />
                    <PlainText text={w.detail} as="div" className="text-muted" />
                  </li>
                ))}
              </ul>
            )}
            {ingest.followUpFailed && (
              <div role="alert" className="flex items-center gap-2 text-signal">
                <span>
                  {followUpError?.message ?? 'Refreshing the repository list failed.'}
                </span>
                <button
                  type="button"
                  onClick={ingest.retryFollowUp}
                  className="border border-hairline px-2 py-1 text-bone"
                >
                  Retry
                </button>
              </div>
            )}
          </section>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="border border-hairline px-3 py-1 text-sm disabled:opacity-50"
          >
            {done ? 'Done' : 'Cancel'}
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="border border-crimson px-3 py-1 text-sm text-bone disabled:opacity-50"
          >
            Ingest
          </button>
        </div>
      </form>
    </Modal>
  );
}
