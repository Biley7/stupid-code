// L3 Architecture lens (Requirement 22). All backend text is rendered via PlainText.
// L3 shows no blast radius, impact_score, or mastery indication (22.9).

import type { L3Explanation } from '../../api/types';
import { PlainText } from '../shared/PlainText';

export interface L3PanelProps {
  l3: L3Explanation;
}

function NotApplicable() {
  return (
    <span className="text-muted">
      <span aria-hidden="true">— </span>not applicable
    </span>
  );
}

export function L3Panel({ l3 }: L3PanelProps) {
  return (
    <div className="flex flex-col gap-4">
      <section aria-labelledby="l3-pattern">
        <h3 id="l3-pattern" className="m-0 text-xs font-semibold uppercase text-muted">
          Topology pattern
        </h3>
        <PlainText as="p" className="m-0 mt-1 font-mono text-bone" text={l3.topology_pattern} />
      </section>

      <section aria-labelledby="l3-why">
        <h3 id="l3-why" className="m-0 text-xs font-semibold uppercase text-muted">
          Why this folder structure
        </h3>
        <PlainText as="p" className="m-0 mt-1 text-bone" text={l3.why_this_folder_structure} />
      </section>

      <section aria-labelledby="l3-evidence">
        <h3 id="l3-evidence" className="m-0 text-xs font-semibold uppercase text-muted">
          Structural evidence
        </h3>
        <ul className="m-0 mt-1 flex list-none flex-col gap-1 p-0">
          {l3.structural_evidence.map((e, i) => (
            <li key={i} className="border border-hairline p-2">
              <PlainText className="font-mono text-bone" text={e} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="l3-matrix">
        <h3 id="l3-matrix" className="m-0 text-xs font-semibold uppercase text-muted">
          Counterfactual tradeoffs
        </h3>
        {l3.alternatives.length === 0 ? (
          <p className="m-0 mt-1 text-muted">No alternatives were returned</p>
        ) : (
          <div className="mt-1 overflow-x-auto" tabIndex={0} role="region" aria-labelledby="l3-matrix">
            <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
              <caption className="sr-only">
                Counterfactual tradeoff matrix comparing the selected pattern with alternatives
              </caption>
              <thead>
                <tr>
                  <th scope="col" className="border border-hairline p-2 text-xs font-semibold text-muted">
                    Pattern
                  </th>
                  <th scope="col" className="border border-hairline p-2 text-xs font-semibold text-muted">
                    Why not selected
                  </th>
                  <th scope="col" className="border border-hairline p-2 text-xs font-semibold text-muted">
                    When to switch
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row" className="border border-hairline p-2 align-top font-normal text-bone">
                    <PlainText className="font-mono" text={l3.topology_pattern} />{' '}
                    <span className="border border-hairline px-1 text-xs font-semibold uppercase text-bone">
                      Selected
                    </span>
                  </th>
                  <td className="border border-hairline p-2 align-top">
                    <NotApplicable />
                  </td>
                  <td className="border border-hairline p-2 align-top">
                    <NotApplicable />
                  </td>
                </tr>
                {l3.alternatives.map((a, i) => (
                  <tr key={i}>
                    <th scope="row" className="border border-hairline p-2 align-top font-normal text-bone">
                      <PlainText className="font-mono" text={a.pattern_name} />
                    </th>
                    <td className="border border-hairline p-2 align-top text-bone">
                      <PlainText text={a.why_not_chosen} />
                    </td>
                    <td className="border border-hairline p-2 align-top text-bone">
                      <PlainText text={a.when_to_switch} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {l3.spec_rationale !== null && (
        <section aria-labelledby="l3-spec">
          <h3 id="l3-spec" className="m-0 text-xs font-semibold uppercase text-muted">
            Spec rationale
          </h3>
          <PlainText as="p" className="m-0 mt-1 text-bone" text={l3.spec_rationale} />
        </section>
      )}
    </div>
  );
}
