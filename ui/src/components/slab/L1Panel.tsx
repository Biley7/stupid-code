// L1 Syntax lens (Requirement 20). All backend text is rendered via PlainText.

import type { L1Explanation } from '../../api/types';
import { PlainText } from '../shared/PlainText';

export interface L1PanelProps {
  l1: L1Explanation;
}

function lineRange(start: number, end: number): string {
  return start === end ? `${start}` : `${start}-${end}`;
}

export function L1Panel({ l1 }: L1PanelProps) {
  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="l1-summary">
        <h3 id="l1-summary" className="m-0 text-xs font-semibold uppercase text-muted">
          Summary
        </h3>
        <PlainText as="p" className="m-0 mt-1 text-bone" text={l1.summary} />
      </section>

      <section aria-labelledby="l1-language">
        <h3 id="l1-language" className="m-0 text-xs font-semibold uppercase text-muted">
          Language
        </h3>
        <PlainText as="p" className="m-0 mt-1 font-mono text-bone" text={l1.language} />
      </section>

      <section aria-labelledby="l1-annotations">
        <h3 id="l1-annotations" className="m-0 text-xs font-semibold uppercase text-muted">
          Annotations
        </h3>
        {l1.annotations.length === 0 ? (
          <p className="m-0 mt-1 text-muted">No annotations were returned</p>
        ) : (
          <ol className="m-0 mt-1 flex list-none flex-col gap-3 p-0">
            {l1.annotations.map((a, i) => (
              <li key={i} className="border border-hairline p-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-xs text-muted">
                    <span className="sr-only">Lines </span>
                    {lineRange(a.line_start, a.line_end)}
                  </span>
                  <PlainText className="font-mono text-bone" text={a.construct} />
                </div>
                <PlainText as="p" className="m-0 mt-1 text-bone" text={a.explanation} />
                {a.what_if_removed.trim() !== '' && (
                  <div className="mt-2 border-l-2 border-crimson bg-surface p-2">
                    <h4 className="m-0 text-xs font-semibold text-muted">What breaks if removed?</h4>
                    <PlainText as="p" className="m-0 mt-1 text-bone" text={a.what_if_removed} />
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="l1-takeaway">
        <h3 id="l1-takeaway" className="m-0 text-xs font-semibold uppercase text-muted">
          Key takeaway
        </h3>
        <PlainText as="p" className="m-0 mt-1 text-bone" text={l1.key_takeaway} />
      </section>
    </div>
  );
}
