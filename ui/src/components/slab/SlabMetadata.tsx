// Metadata of the selected file, symbol, or directory (Requirements 18.1 to 18.8,
// 19.1, 27.1, 27.6, 27.7, 27.9, 11.4, 11.6). Plain text only; no source code.
import { useMemo, useState } from 'react';
import type { SpecLink } from '../../api/types';
import { resolveExplainTarget } from '../../core/explainTarget';
import { fileMasteryView } from '../../core/mastery';
import { buildSnapshotIndex, classifyNode } from '../../core/snapshotIndex';
import { explainKey } from '../../state/dataReducer';
import { useAppState, useDataState } from '../../state/store';
import { MasteryBadge } from '../shared/MasteryBadge';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

const MAX_COMMITS = 20;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-1">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="break-all text-sm text-bone">{children}</dd>
    </div>
  );
}

function Mono({ text }: { text: string }) {
  return <PlainText text={text} className="select-text font-mono" />;
}

function HashRow({ label, hash }: { label: string; hash: string }) {
  const [failed, setFailed] = useState(false);
  async function copy() {
    setFailed(false);
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
        throw new Error('clipboard unavailable');
      }
      await navigator.clipboard.writeText(hash);
    } catch {
      setFailed(true);
    }
  }
  return (
    <Row label={label}>
      <span className="flex flex-wrap items-center gap-2">
        <Mono text={hash} />
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={`Copy ${label}`}
          className="border border-hairline px-1.5 py-0.5 text-xs text-bone"
        >
          Copy
        </button>
        {failed ? (
          <span role="status" className="text-xs text-signal">
            Copy failed
          </span>
        ) : null}
      </span>
    </Row>
  );
}

/** `hash|subject` split at the first `|`; a string without `|` is one text. */
function CommitItem({ entry }: { entry: string }) {
  const at = entry.indexOf('|');
  if (at < 0) {
    return <PlainText text={entry} className="font-mono text-xs" />;
  }
  return (
    <span className="flex gap-2 text-xs">
      <PlainText text={entry.slice(0, at)} className="font-mono text-muted" />
      <PlainText text={entry.slice(at + 1)} />
    </span>
  );
}

function SpecLinkItem({ link }: { link: SpecLink }) {
  return (
    <li className="border border-hairline p-2 text-xs">
      <div className="font-mono text-muted">
        <PlainText text={link.spec_name} /> <PlainText text={link.source_file} />
      </div>
      <PlainText text={link.section_title} as="div" className="text-bone" />
      <PlainText text={link.excerpt} as="p" className="mt-1 text-muted" />
    </li>
  );
}

export function SlabMetadata() {
  const app = useAppState();
  const data = useDataState();
  const snapshotRemote = data.snapshot;

  const index = useMemo(
    () =>
      snapshotRemote.status === 'ready'
        ? buildSnapshotIndex(snapshotRemote.data.snapshot, snapshotRemote.data.topology)
        : null,
    [snapshotRemote],
  );

  if (snapshotRemote.status === 'loading') return <StateBlock variant="loading" label="Loading snapshot" />;
  if (snapshotRemote.status !== 'ready' || index === null) {
    return <StateBlock variant="empty" label="Nothing selected" />;
  }

  const { provenance } = snapshotRemote.data;
  const roles = index.directoryRoles;

  // Subject: directory under L3, else symbol, else file (18.8, 18.9).
  if (
    app.lens === 'L3_ARCHITECTURE' &&
    app.node !== null &&
    classifyNode(index, undefined, app.node) === 'directory'
  ) {
    return (
      <dl aria-label="Directory metadata" data-subject="directory">
        <Row label="Path">
          <Mono text={app.node} />
        </Row>
        <Row label="Role">
          <PlainText text={String(roles[app.node])} />
        </Row>
      </dl>
    );
  }

  const symbol = app.symbol !== null ? index.symbolsById.get(app.symbol) : undefined;
  const filePath = symbol?.file_path ?? (app.symbol === null ? app.file : null);
  const file = filePath !== null && filePath !== undefined ? index.filesByPath.get(filePath) : undefined;
  if (!file || (app.symbol !== null && !symbol)) {
    return <StateBlock variant="empty" label="Nothing selected" />;
  }

  const mastery = fileMasteryView(data.vitals, file.file_path);
  const target = resolveExplainTarget({
    repoId: app.repoId,
    lens: app.lens,
    file: app.file,
    symbol: app.symbol,
    node: app.node,
    index,
  });
  const entry =
    app.repoId !== null && target.kind === 'ok'
      ? data.explain[explainKey(app.repoId, target.targetId, app.lens)]
      : undefined;
  const envelope = entry && entry.status === 'ready' ? entry.data.envelope : null;

  const commits = (Object.prototype.hasOwnProperty.call(provenance.recent_commits, file.file_path)
    ? provenance.recent_commits[file.file_path] ?? []
    : []
  ).slice(0, MAX_COMMITS);
  const links = Object.prototype.hasOwnProperty.call(provenance.spec_links, file.file_path)
    ? provenance.spec_links[file.file_path] ?? []
    : [];
  const hasState =
    data.vitals.status === 'ready' &&
    Object.prototype.hasOwnProperty.call(data.vitals.data.file_states, file.file_path);

  return (
    <div data-subject={symbol ? 'symbol' : 'file'}>
      <dl aria-label={symbol ? 'Symbol metadata' : 'File metadata'}>
        {symbol ? (
          <>
            <Row label="Qualname">
              <Mono text={symbol.qualname} />
            </Row>
            <Row label="Kind">
              <PlainText text={String(symbol.kind)} />
            </Row>
            <Row label="Signature">
              <Mono text={symbol.signature} />
            </Row>
            <Row label="Lines">
              <span className="font-mono">
                {symbol.start_line} to {symbol.end_line}
              </span>
            </Row>
            <HashRow label="ast_hash" hash={symbol.ast_hash} />
            <Row label="File">
              <Mono text={file.file_path} />
            </Row>
          </>
        ) : (
          <>
            <Row label="Path">
              <Mono text={file.file_path} />
            </Row>
            <Row label="Language">
              <PlainText text={String(file.language)} />
            </Row>
            <Row label="LOC">
              <span className="font-mono">{file.loc}</span>
            </Row>
            <HashRow label="ast_hash" hash={file.ast_hash} />
          </>
        )}
        <Row label={symbol ? 'File-level state' : 'Mastery'}>
          <span data-testid="slab-mastery" data-unaudited-fallback={!hasState && data.vitals.status === 'ready'}>
            <MasteryBadge presentation={mastery} />
          </span>
        </Row>
        {envelope ? (
          <>
            <HashRow label="Explain ast_hash" hash={envelope.ast_hash} />
            <Row label="Explain source">
              <span className="font-mono">{envelope.cached ? 'cached' : 'fresh'}</span>
            </Row>
          </>
        ) : null}
        {!symbol ? (
          <Row label="Blast radius">
            <span className="text-muted">File-level blast radius is not provided by the backend</span>
          </Row>
        ) : null}
      </dl>

      <section aria-label="Recent commits" className="mt-2">
        <h3 className="text-xs text-muted">Recent commits</h3>
        {commits.length === 0 ? (
          <PlainText text="No commit history available for this file" as="p" className="text-sm text-muted" />
        ) : (
          <ul className="mt-1 flex flex-col gap-1">
            {commits.map((c, i) => (
              <li key={`${i}:${c}`}>
                <CommitItem entry={c} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {links.length > 0 ? (
        <section aria-label="Spec links" className="mt-2">
          <h3 className="text-xs text-muted">Spec links</h3>
          <ul className="mt-1 flex flex-col gap-1">
            {links.map((l, i) => (
              <SpecLinkItem key={`${i}:${l.spec_name}:${l.section_title}`} link={l} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
