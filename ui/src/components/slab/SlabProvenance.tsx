// Recent commits and spec provenance of the selected file, as collapsible sections below
// the lenses so the pedagogical content stays above the fold (Requirements 18.5, 18.6).
import type { SpecLink } from '../../api/types';
import { Collapsible } from '../shared/Collapsible';
import { PlainText } from '../shared/PlainText';
import { useSlabSubject } from './useSlabSubject';

const MAX_COMMITS = 20;

/** `hash|subject` split at the first `|`; a string without `|` is one text. */
function CommitItem({ entry }: { entry: string }) {
  const at = entry.indexOf('|');
  if (at < 0) {
    return <PlainText text={entry} className="break-words text-xs text-bone" />;
  }
  return (
    <span className="flex min-w-0 gap-2 text-xs">
      <PlainText text={entry.slice(0, at)} className="shrink-0 font-mono text-muted" />
      <PlainText text={entry.slice(at + 1)} className="min-w-0 break-words text-bone" />
    </span>
  );
}

function SpecLinkItem({ link }: { link: SpecLink }) {
  return (
    <li className="min-w-0 border border-hairline p-2 text-xs">
      <PlainText text={link.section_title} as="div" className="break-words font-medium text-bone" />
      <div className="mt-0.5 break-all font-mono text-[11px] text-muted">
        <PlainText text={link.spec_name} /> <PlainText text={link.source_file} />
      </div>
      <PlainText text={link.excerpt} as="p" className="m-0 mt-1 break-words text-muted" />
    </li>
  );
}

export function SlabProvenance() {
  const subject = useSlabSubject();
  if (subject.kind !== 'file' && subject.kind !== 'symbol') return null;
  const { file, provenance } = subject;
  const has = (record: object) => Object.prototype.hasOwnProperty.call(record, file.file_path);
  const commits = (has(provenance.recent_commits) ? (provenance.recent_commits[file.file_path] ?? []) : []).slice(
    0,
    MAX_COMMITS,
  );
  const links = has(provenance.spec_links) ? (provenance.spec_links[file.file_path] ?? []) : [];
  return (
    <div className="flex min-w-0 flex-col">
      <Collapsible title="Recent commits" ariaLabel="Recent commits" badge={commits.length}>
        {commits.length === 0 ? (
          <PlainText text="No commit history available for this file" as="p" className="m-0 text-sm text-muted" />
        ) : (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {commits.map((c, i) => (
              <li key={`${i}:${c}`} className="min-w-0">
                <CommitItem entry={c} />
              </li>
            ))}
          </ul>
        )}
      </Collapsible>
      {links.length > 0 ? (
        <Collapsible title="Spec provenance" ariaLabel="Spec links" badge={links.length}>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {links.map((l, i) => (
              <SpecLinkItem key={`${i}:${l.spec_name}:${l.section_title}`} link={l} />
            ))}
          </ul>
        </Collapsible>
      ) : null}
    </div>
  );
}
