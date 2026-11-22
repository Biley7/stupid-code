// Compact header of the Autopsy_Slab (Requirements 18.1 to 18.8, 19.1, 27.1, 27.6, 27.7,
// 11.4, 11.6). Shows the subject (symbol, file, or directory), one truncated ast_hash
// pill with a copy button, and the mastery state. Plain text only; no source code.
// Recent commits and spec provenance live in SlabProvenance, below the lenses.
import { Check, Copy } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { MasteryDot } from '../shared/MasteryDot';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';
import { useSlabSubject } from './useSlabSubject';

const HASH_PREVIEW = 10;

function previewHash(hash: string): string {
  return hash.length > HASH_PREVIEW ? `${hash.slice(0, HASH_PREVIEW)}…` : hash;
}

/** One ast_hash pill: truncated text with the full value in the tooltip, plus a copy button. */
function HashPill({ hash }: { hash: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
  );
  async function copy() {
    if (timer.current !== null) clearTimeout(timer.current);
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
        throw new Error('clipboard unavailable');
      }
      await navigator.clipboard.writeText(hash);
      setState('copied');
      timer.current = setTimeout(() => setState('idle'), 1500);
    } catch {
      setState('failed');
    }
  }
  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <span className="inline-flex min-w-0 items-center border border-hairline bg-obsidian">
        <span className="border-r border-hairline px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
          ast_hash
        </span>
        <PlainText text={previewHash(hash)} title={hash} className="select-text truncate px-1.5 py-0.5 font-mono text-[11px] text-bone" />
        <button
          type="button"
          onClick={() => void copy()}
          aria-label="Copy ast_hash"
          title="Copy ast_hash"
          className="border-l border-hairline px-1.5 py-1 text-muted hover:text-bone"
        >
          {state === 'copied' ? <Check aria-hidden="true" size={12} /> : <Copy aria-hidden="true" size={12} />}
        </button>
      </span>
      {state === 'failed' ? (
        <span role="status" className="text-[11px] text-signal">
          Copy failed
        </span>
      ) : null}
      {state === 'copied' ? (
        <span role="status" className="sr-only">
          Copied
        </span>
      ) : null}
    </span>
  );
}

export function SlabMetadata() {
  const subject = useSlabSubject();
  if (subject.kind === 'loading') return <StateBlock variant="loading" label="Loading snapshot" />;
  if (subject.kind === 'empty') return <StateBlock variant="empty" label="Nothing selected" />;
  if (subject.kind === 'directory') {
    return (
      <dl aria-label="Directory metadata" data-subject="directory" className="m-0 flex min-w-0 flex-col gap-1">
        <div className="min-w-0">
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted">Directory</dt>
          <dd className="m-0 break-all font-mono text-[13px] text-bone">
            <PlainText text={subject.path} />
          </dd>
        </div>
        <div>
          <dt className="text-[10px] font-semibold uppercase tracking-wider text-muted">Role</dt>
          <dd className="m-0 text-sm text-bone">
            <PlainText text={subject.role} />
          </dd>
        </div>
      </dl>
    );
  }
  const { file, symbol, mastery, hasState, vitalsReady, explainSource } = subject;
  const fileName = file.file_path.slice(file.file_path.lastIndexOf('/') + 1);
  return (
    <div data-subject={symbol ? 'symbol' : 'file'} className="flex min-w-0 flex-col gap-2">
      <dl aria-label={symbol ? 'Symbol metadata' : 'File metadata'} className="m-0 flex min-w-0 flex-col gap-1.5">
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <dt className="sr-only">{symbol ? 'Qualname' : 'File name'}</dt>
            <dd className="m-0 min-w-0 break-all font-mono text-[15px] font-semibold leading-snug text-bone">
              <PlainText text={symbol ? symbol.qualname : fileName} />
            </dd>
          </div>
          <div className="shrink-0 pt-0.5">
            <dt className="sr-only">{symbol ? 'File-level state' : 'Mastery'}</dt>
            <dd className="m-0">
              <span data-testid="slab-mastery" data-unaudited-fallback={!hasState && vitalsReady}>
                <MasteryDot presentation={mastery} showLabel />
              </span>
            </dd>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted">
          <dt className="sr-only">Kind</dt>
          <dd className="m-0 font-semibold uppercase tracking-wider">
            <PlainText text={symbol ? String(symbol.kind) : String(file.language)} />
          </dd>
          {symbol ? (
            <>
              <dt className="sr-only">Lines</dt>
              <dd className="m-0 font-mono">
                L{symbol.start_line}–{symbol.end_line}
              </dd>
            </>
          ) : (
            <>
              <dt className="sr-only">LOC</dt>
              <dd className="m-0 font-mono">{file.loc} LOC</dd>
            </>
          )}
          {explainSource ? (
            <>
              <dt className="sr-only">Explain source</dt>
              <dd className="m-0">{explainSource}</dd>
            </>
          ) : null}
        </div>
        <div className="min-w-0">
          <dt className="sr-only">{symbol ? 'File' : 'Path'}</dt>
          <dd className="m-0 break-all font-mono text-[11px] text-muted">
            <PlainText text={file.file_path} />
          </dd>
        </div>
        {symbol ? (
          <div className="min-w-0">
            <dt className="sr-only">Signature</dt>
            <dd
              className="m-0 line-clamp-2 break-all border-l-2 border-hairline bg-obsidian px-2 py-1 font-mono text-[11px] text-bone"
              title={symbol.signature}
            >
              <PlainText text={symbol.signature} />
            </dd>
          </div>
        ) : null}
        <div className="min-w-0">
          <dt className="sr-only">ast_hash</dt>
          <dd className="m-0">
            <HashPill hash={symbol ? symbol.ast_hash : file.ast_hash} />
          </dd>
        </div>
      </dl>
      {!symbol ? (
        <p className="m-0 text-[11px] text-muted">File-level blast radius is not provided by the backend</p>
      ) : null}
    </div>
  );
}
