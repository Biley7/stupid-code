// File tree of the Specimen_Rail (Requirements 12.1 to 12.18, 11.4, 27.9).
// Flat row list with tree semantics, roving tabindex, and windowing above 1,000 rows.
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, UIEvent } from 'react';
import type { FileAnalysis } from '../../api/types';
import { fileMasteryView } from '../../core/mastery';
import { presentError } from '../../core/present';
import { buildFileTree, ancestorsOf, flattenVisible, type TreeRow } from '../../core/fileTree';
import { buildSnapshotIndex, resolveTarget, type SnapshotIndex } from '../../core/snapshotIndex';
import { useSnapshot } from '../../data/useSnapshot';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';
import { MasteryBadge } from '../shared/MasteryBadge';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

const ROW_HEIGHT = 28;
const WINDOW_THRESHOLD = 1000;
const OVERSCAN = 10;
const DEFAULT_VIEWPORT = 400;

const rowKey = (row: TreeRow): string =>
  row.kind === 'folder' ? `d:${row.path}` : row.kind === 'file' ? `f:${row.path}` : `s:${row.id}`;

function selectedKeyOf(file: string | null, symbol: string | null): string | null {
  if (symbol !== null) return `s:${symbol}`;
  if (file !== null) return `f:${file}`;
  return null;
}

/** Folders to open so the selected row is visible. */
function expansionFor(file: string | null, symbol: string | null): string[] {
  if (file === null) return [];
  const out = ancestorsOf(file);
  if (symbol !== null) out.push(file);
  return out;
}

interface TreeViewProps {
  files: FileAnalysis[];
  index: SnapshotIndex;
}

function TreeView({ files, index }: TreeViewProps) {
  const dispatch = useAppDispatch();
  const { file, symbol } = useAppState();
  const vitals = useDataState().vitals;
  const root = useMemo(() => buildFileTree(files), [files]);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(
    () => new Set(expansionFor(file, symbol)),
  );
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef(false);

  const rows = useMemo(() => flattenVisible(root, expanded), [root, expanded]);
  const virtual = rows.length > WINDOW_THRESHOLD;
  const selectedKey = selectedKeyOf(file, symbol);

  // Selection from any source expands its ancestors (Requirement 12.14).
  useEffect(() => {
    const needed = expansionFor(file, symbol);
    setExpanded((prev) => {
      if (needed.every((p) => prev.has(p))) return prev;
      const next = new Set(prev);
      for (const p of needed) next.add(p);
      return next;
    });
  }, [file, symbol]);

  const indexOfKey = useCallback(
    (key: string | null): number => (key === null ? -1 : rows.findIndex((r) => rowKey(r) === key)),
    [rows],
  );

  // Exactly one row carries tabindex 0.
  const tabKey = useMemo(() => {
    if (focusKey !== null && indexOfKey(focusKey) >= 0) return focusKey;
    if (selectedKey !== null && indexOfKey(selectedKey) >= 0) return selectedKey;
    const first = rows[0];
    return first ? rowKey(first) : null;
  }, [focusKey, selectedKey, rows, indexOfKey]);

  const viewport = containerRef.current?.clientHeight || DEFAULT_VIEWPORT;

  const bringIntoView = useCallback(
    (idx: number) => {
      const el = containerRef.current;
      if (!el || !virtual) return;
      const top = idx * ROW_HEIGHT;
      const h = el.clientHeight || DEFAULT_VIEWPORT;
      let next = el.scrollTop;
      if (top < next) next = top;
      else if (top + ROW_HEIGHT > next + h) next = top + ROW_HEIGHT - h;
      if (next !== el.scrollTop) el.scrollTop = next;
      setScrollTop(next);
    },
    [virtual],
  );

  // Scroll the selected row into view when the selection changes.
  useLayoutEffect(() => {
    if (selectedKey === null) return;
    const idx = indexOfKey(selectedKey);
    if (idx < 0) return;
    if (virtual) {
      bringIntoView(idx);
      return;
    }
    const el = containerRef.current?.querySelector<HTMLElement>(`[data-row-key="${CSS.escape(selectedKey)}"]`);
    el?.scrollIntoView?.({ block: 'nearest' });
    // Only the selection drives this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  // Move DOM focus after the target row has rendered.
  useLayoutEffect(() => {
    if (!pendingFocus.current || focusKey === null) return;
    pendingFocus.current = false;
    containerRef.current
      ?.querySelector<HTMLElement>(`[data-row-key="${CSS.escape(focusKey)}"]`)
      ?.focus();
  });

  const toggle = useCallback((path: string, open?: boolean) => {
    setExpanded((prev) => {
      const isOpen = prev.has(path);
      const want = open ?? !isOpen;
      if (want === isOpen) return prev;
      const next = new Set(prev);
      if (want) next.add(path);
      else next.delete(path);
      return next;
    });
  }, []);

  const select = useCallback(
    (id: string) => {
      const target = resolveTarget(index, id);
      if (target) dispatch({ type: 'select-target', target });
    },
    [index, dispatch],
  );

  const activate = useCallback(
    (row: TreeRow) => {
      if (row.kind === 'folder') {
        toggle(row.path);
      } else if (row.kind === 'file') {
        select(row.path);
        if (row.hasSymbols) toggle(row.path, true);
      } else {
        select(row.id);
      }
    },
    [select, toggle],
  );

  const moveTo = useCallback(
    (idx: number) => {
      const row = rows[Math.max(0, Math.min(rows.length - 1, idx))];
      if (!row) return;
      pendingFocus.current = true;
      setFocusKey(rowKey(row));
      bringIntoView(rows.indexOf(row));
    },
    [rows, bringIntoView],
  );

  const parentIndex = (row: TreeRow, idx: number): number => {
    const parentKey =
      row.kind === 'symbol'
        ? `f:${row.filePath}`
        : (() => {
            const path = row.path;
            const slash = path.lastIndexOf('/');
            return slash < 0 ? null : `d:${path.slice(0, slash)}`;
          })();
    if (parentKey === null) return idx;
    const p = indexOfKey(parentKey);
    return p < 0 ? idx : p;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>, row: TreeRow, idx: number) => {
    const expandable = row.kind === 'folder' || (row.kind === 'file' && row.hasSymbols);
    const isOpen = row.kind !== 'symbol' && row.expanded;
    switch (event.key) {
      case 'ArrowDown':
        moveTo(idx + 1);
        break;
      case 'ArrowUp':
        moveTo(idx - 1);
        break;
      case 'Home':
        moveTo(0);
        break;
      case 'End':
        moveTo(rows.length - 1);
        break;
      case 'ArrowRight':
        if (expandable && !isOpen) toggle(row.path, true);
        else if (expandable && isOpen) {
          const next = rows[idx + 1];
          if (next && next.depth > row.depth) moveTo(idx + 1);
        }
        break;
      case 'ArrowLeft':
        if (expandable && isOpen) toggle(row.path, false);
        else moveTo(parentIndex(row, idx));
        break;
      case 'Enter':
      case ' ':
        activate(row);
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    if (virtual) setScrollTop(event.currentTarget.scrollTop);
  };

  let start = 0;
  let end = rows.length;
  if (virtual) {
    start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    end = Math.min(rows.length, Math.ceil((scrollTop + viewport) / ROW_HEIGHT) + OVERSCAN);
  }

  const rendered: JSX.Element[] = [];
  for (let i = start; i < end; i++) {
    const row = rows[i];
    if (!row) continue;
    const key = rowKey(row);
    const selected = key === selectedKey;
    const isFolderLike = row.kind === 'folder' || (row.kind === 'file' && row.hasSymbols);
    const ariaExpanded = isFolderLike ? row.expanded : undefined;
    const style = virtual
      ? { position: 'absolute' as const, top: i * ROW_HEIGHT, left: 0, right: 0, height: ROW_HEIGHT }
      : { minHeight: ROW_HEIGHT };
    rendered.push(
      <div
        key={key}
        role="treeitem"
        data-row-key={key}
        aria-level={row.depth + 1}
        aria-selected={selected}
        aria-expanded={ariaExpanded}
        aria-setsize={virtual ? rows.length : undefined}
        aria-posinset={virtual ? i + 1 : undefined}
        tabIndex={key === tabKey ? 0 : -1}
        onClick={() => {
          setFocusKey(key);
          activate(row);
        }}
        onFocus={() => setFocusKey(key)}
        onKeyDown={(e) => onKeyDown(e, row, i)}
        style={{ ...style, paddingLeft: 8 + row.depth * 14 }}
        className={`flex cursor-pointer items-center gap-2 pr-2 text-sm ${
          selected ? 'bg-surface text-bone' : 'text-bone'
        }`}
      >
        {row.kind === 'symbol' ? (
          <>
            <span className="w-3 shrink-0" aria-hidden="true" />
            <PlainText text={row.qualname} className="truncate font-mono" title={row.qualname} />
            <PlainText text={row.symbolKind} className="shrink-0 font-mono text-xs text-muted" />
          </>
        ) : (
          <>
            <span className="w-3 shrink-0 text-muted" aria-hidden="true">
              {isFolderLike ? (
                row.expanded ? (
                  <ChevronDown size={12} />
                ) : (
                  <ChevronRight size={12} />
                )
              ) : null}
            </span>
            <PlainText text={row.name} className="truncate font-mono" title={row.path} />
            {row.kind === 'file' ? (
              <>
                <PlainText
                  text={row.language}
                  className="shrink-0 border border-hairline px-1 font-mono text-xs text-muted"
                />
                {row.parseErrors ? (
                  <span className="shrink-0 border border-crimson px-1 font-mono text-xs text-signal">
                    PARSE ERRORS
                  </span>
                ) : null}
                <MasteryBadge
                  presentation={fileMasteryView(vitals, row.path)}
                  className="ml-auto shrink-0"
                />
              </>
            ) : null}
          </>
        )}
      </div>,
    );
  }

  return (
    <div
      ref={containerRef}
      role="tree"
      aria-label="Repository file tree"
      onScroll={onScroll}
      className="max-h-full overflow-auto"
      style={{ position: 'relative' }}
    >
      <div
        role="group"
        style={virtual ? { position: 'relative', height: rows.length * ROW_HEIGHT } : undefined}
      >
        {rendered}
      </div>
    </div>
  );
}

export function FileTree() {
  const { repoId } = useAppState();
  const { snapshot, reload } = useSnapshot({ autoload: false });
  const topology =
    snapshot.status === 'ready' ? snapshot.data.topology : undefined;
  const index = useMemo(
    () => (snapshot.status === 'ready' ? buildSnapshotIndex(snapshot.data.snapshot, topology) : null),
    [snapshot, topology],
  );

  if (repoId === null || snapshot.status === 'idle') {
    return <StateBlock variant="empty" label="No repository selected." />;
  }
  if (snapshot.status === 'loading') {
    return <StateBlock variant="loading" label="Loading file tree…" />;
  }
  if (snapshot.status === 'error') {
    const presented = presentError(snapshot.error, 'generic');
    if (presented === null) return <StateBlock variant="loading" label="Loading file tree…" />;
    return (
      <StateBlock
        variant="error"
        message={presented.message}
        onRetry={presented.retryable ? () => void reload() : undefined}
        retryAfterSeconds={presented.retryAfterSeconds}
      />
    );
  }
  const files = snapshot.data.snapshot.files;
  if (files.length === 0 || index === null) {
    return <StateBlock variant="empty" label="The snapshot contains no files." />;
  }
  return <TreeView key={repoId} files={files} index={index} />;
}
