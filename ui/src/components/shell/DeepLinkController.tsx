// Render-less. Applies the Kiro Crew deep link once (Requirement 26) and then keeps
// the URL in sync with the App_Store through history.replaceState. It starts no request:
// it only reads the repository list and snapshot that DataLoader already loads.
import { useEffect, useRef, useState } from 'react';
import {
  buildSearch,
  parseDeepLink,
  resolveDeepLink,
  resolveFile,
  type ParsedDeepLink,
} from '../../core/deepLink';
import { buildSnapshotIndex, resolveTarget } from '../../core/snapshotIndex';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { useNotices } from './NoticeBar';

type Phase = 'repo' | 'file' | 'done';

const MAX_SHOWN = 200;

/** Untrusted value as display text; the notice renders it as plain text. */
function shown(value: string): string {
  return value.length > MAX_SHOWN ? `${value.slice(0, MAX_SHOWN)}…` : value;
}

export function DeepLinkController(): null {
  const app = useAppState();
  const data = useDataState();
  const dispatch = useAppDispatch();
  const { pushNotice } = useNotices();

  const parsedRef = useRef<ParsedDeepLink | null>(null);
  if (parsedRef.current === null) parsedRef.current = parseDeepLink(window.location.search);
  const parsed = parsedRef.current;

  const phaseRef = useRef<Phase | null>(null);
  if (phaseRef.current === null) {
    phaseRef.current = parsed.repoId.present ? 'repo' : 'done';
  }
  const viewAppliedRef = useRef(false);
  const [resolved, setResolved] = useState(phaseRef.current === 'done');

  // View applies immediately; it needs no repository data.
  useEffect(() => {
    if (viewAppliedRef.current) return;
    viewAppliedRef.current = true;
    if (parsed.view !== null) dispatch({ type: 'view-set', value: parsed.view });
  }, [parsed, dispatch]);

  // Step 1: wait for the repository list, then select only a listed repository.
  useEffect(() => {
    if (phaseRef.current !== 'repo') return;
    if (data.repos.status === 'error') {
      // Requirement 26.3: the error state shows; no not-found notice.
      phaseRef.current = 'done';
      setResolved(true);
      return;
    }
    if (data.repos.status !== 'ready') return;
    const result = resolveDeepLink(
      parsed,
      data.repos.data.map((r) => r.repo_id),
    );
    if (result.repoId === null) {
      const raw = parsed.repoId.present ? shown(parsed.repoId.value) : '';
      pushNotice(`Repository not found: ${raw}`);
      phaseRef.current = 'done';
      setResolved(true);
      return;
    }
    dispatch({ type: 'repo-selected', repoId: result.repoId });
    if (parsed.file.present) {
      phaseRef.current = 'file';
    } else {
      phaseRef.current = 'done';
      setResolved(true);
    }
  }, [data.repos, parsed, dispatch, pushNotice]);

  // Step 2: wait for that repository's snapshot, then select the file if it exists.
  useEffect(() => {
    if (phaseRef.current !== 'file') return;
    if (data.repoId !== app.repoId || data.repoId === null) return;
    if (data.snapshot.status === 'error') {
      phaseRef.current = 'done';
      setResolved(true);
      return;
    }
    if (data.snapshot.status !== 'ready') return;
    const index = buildSnapshotIndex(data.snapshot.data.snapshot, data.snapshot.data.topology);
    const result = resolveFile(parsed, new Set(index.filesByPath.keys()));
    if (result.file === null) {
      const raw = parsed.file.present ? shown(parsed.file.value) : '';
      pushNotice(`File not found in snapshot: ${raw}`);
    } else {
      const target = resolveTarget(index, result.file);
      if (target !== null) dispatch({ type: 'select-target', target });
    }
    phaseRef.current = 'done';
    setResolved(true);
  }, [data.repoId, data.snapshot, app.repoId, parsed, dispatch, pushNotice]);

  // Keep the URL in sync once the link is resolved. replaceState adds no history entry.
  useEffect(() => {
    if (!resolved) return;
    const search = buildSearch(window.location.search, {
      repoId: app.repoId,
      file: app.file,
      view: app.view,
    });
    if (search === window.location.search) return;
    const { pathname, hash } = window.location;
    window.history.replaceState(window.history.state, '', `${pathname}${search}${hash}`);
  }, [resolved, app.repoId, app.file, app.view]);

  return null;
}
