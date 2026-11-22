// L2 Flow lens (Requirement 21). All backend text is rendered via PlainText.
// Blast-radius chips are crimson, never emerald (Requirements 16.3, 27.8).
import { useMemo } from 'react';
import type { ExplainResponse, L2Explanation } from '../../api/types';
import { buildSnapshotIndex, resolveTarget } from '../../core/snapshotIndex';
import { useAppDispatch, useDataState } from '../../state/store';
import { PlainText } from '../shared/PlainText';

export interface L2PanelProps {
  response: ExplainResponse;
}

const HEADING = 'm-0 text-xs font-semibold uppercase text-muted';

function lineRange(start: number, end: number): string {
  return start === end ? `${start}` : `${start}-${end}`;
}

function StringList({ id, title, items }: { id: string; title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section aria-labelledby={id}>
      <h3 id={id} className={HEADING}>
        {title}
      </h3>
      <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0">
        {items.map((s, i) => (
          <li key={i}>
            <PlainText className="font-mono text-bone" text={s} />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface ChipProps {
  id: string;
  direction: 'Upstream' | 'Downstream';
  score: string;
  selectable: boolean;
  onSelect: () => void;
}

function Chip({ id, direction, score, selectable, onSelect }: ChipProps) {
  const body = (
    <>
      <span className="text-xs uppercase text-signal">{direction}</span>
      <PlainText className="font-mono text-bone" text={id} />
      <span className="font-mono text-xs text-muted">impact {score}</span>
    </>
  );
  const base = 'inline-flex items-baseline gap-2 border border-crimson px-2 py-1 text-sm';
  if (selectable) {
    return (
      <button
        type="button"
        onClick={onSelect}
        className={`${base} bg-surface text-left hover:bg-obsidian focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal`}
      >
        {body}
      </button>
    );
  }
  return <span className={base}>{body}</span>;
}

export function L2Panel({ response }: L2PanelProps) {
  const l2: L2Explanation | null = response.envelope.l2;
  const blast = response.blast_radius;
  const dispatch = useAppDispatch();
  const snapshot = useDataState().snapshot;
  const index = useMemo(
    () =>
      snapshot.status === 'ready'
        ? buildSnapshotIndex(snapshot.data.snapshot, snapshot.data.topology)
        : null,
    [snapshot],
  );

  if (l2 === null) return null;

  const steps = l2.execution_steps
    .map((s, i) => ({ s, i }))
    .sort((a, b) => a.s.step_number - b.s.step_number || a.i - b.i)
    .map((x) => x.s);

  const chips = [
    ...blast.upstream_callers.map((id) => ({ id, direction: 'Upstream' as const })),
    ...blast.downstream_callees.map((id) => ({ id, direction: 'Downstream' as const })),
  ];
  const score = blast.impact_score.toFixed(2);

  const allEmpty =
    steps.length === 0 &&
    l2.upstream_callers.length === 0 &&
    l2.downstream_callees.length === 0 &&
    l2.side_effects.length === 0 &&
    l2.dsa_cards.length === 0 &&
    chips.length === 0;

  return (
    <div className="flex flex-col gap-4">
      {!l2.llm_content_available && (
        <p role="status" className="m-0 border border-crimson bg-surface p-2 text-bone">
          Generated flow content is unavailable. Deterministic fields are shown below.
        </p>
      )}
      {allEmpty && <p className="m-0 text-muted">No flow data was returned for this target</p>}

      {steps.length > 0 && (
        <section aria-labelledby="l2-steps">
          <h3 id="l2-steps" className={HEADING}>
            Execution steps
          </h3>
          <ol className="m-0 mt-1 flex list-none flex-col gap-3 p-0">
            {steps.map((s, i) => (
              <li key={i} className="border border-hairline p-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-xs text-muted">
                    <span className="sr-only">Step </span>
                    {s.step_number}
                  </span>
                  <PlainText className="font-mono text-bone" text={s.location} />
                </div>
                <PlainText as="p" className="m-0 mt-1 text-bone" text={s.action} />
                <PlainText as="p" className="m-0 mt-1 text-muted" text={s.data_transformation} />
              </li>
            ))}
          </ol>
        </section>
      )}

      <StringList id="l2-callers" title="Upstream callers" items={l2.upstream_callers} />
      <StringList id="l2-callees" title="Downstream callees" items={l2.downstream_callees} />
      <StringList id="l2-effects" title="Side effects" items={l2.side_effects} />

      {l2.dsa_cards.length > 0 && (
        <section aria-labelledby="l2-dsa">
          <h3 id="l2-dsa" className={HEADING}>
            DSA-in-the-Wild
          </h3>
          <ul className="m-0 mt-1 flex list-none flex-col gap-3 p-0">
            {l2.dsa_cards.map((c, i) => (
              <li key={i} className="border border-hairline bg-surface p-2">
                <div className="flex flex-wrap items-baseline gap-2">
                  <PlainText className="text-xs uppercase text-muted" text={c.chapter} />
                  <PlainText className="font-semibold text-bone" text={c.pattern_name} />
                  <span className="font-mono text-xs text-muted">
                    <span className="sr-only">Lines </span>
                    {lineRange(c.start_line, c.end_line)}
                  </span>
                </div>
                <PlainText as="p" className="m-0 mt-1 text-bone" text={c.why_used_here} />
                <dl className="m-0 mt-2 flex gap-4 font-mono text-xs text-muted">
                  <div>
                    <dt className="inline">Time </dt>
                    <dd className="m-0 inline">
                      <PlainText text={c.time_complexity} />
                    </dd>
                  </div>
                  <div>
                    <dt className="inline">Space </dt>
                    <dd className="m-0 inline">
                      <PlainText text={c.space_complexity} />
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </section>
      )}

      {chips.length > 0 && (
        <section aria-labelledby="l2-blast">
          <h3 id="l2-blast" className={HEADING}>
            Blast radius
          </h3>
          <ul className="m-0 mt-1 flex list-none flex-wrap gap-2 p-0">
            {chips.map((c, i) => {
              const target = index ? resolveTarget(index, c.id) : null;
              const symbol = target !== null && target.kind === 'symbol' ? target : null;
              return (
                <li key={`${c.direction}-${c.id}-${i}`}>
                  <Chip
                    id={c.id}
                    direction={c.direction}
                    score={score}
                    selectable={symbol !== null}
                    onSelect={() => {
                      if (symbol) dispatch({ type: 'select-target', target: symbol });
                    }}
                  />
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
