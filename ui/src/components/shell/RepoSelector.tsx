// Repository list and selection (Requirement 6). Lists only what the backend
// returned, in backend order. `repo_id` is plain monospace text. The list opens from a
// trigger button; selecting an entry closes it.
import { ChevronDown } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useRepos } from '../../data/useRepos';
import { useAppDispatch, useAppState } from '../../state/store';
import { PlainText } from '../shared/PlainText';
import { StateBlock } from '../shared/StateBlock';

export interface RepoSelectorProps {
  /** Invoked by the Ingest action of the empty state. */
  onIngest?: () => void;
}

export function RepoSelector({ onIngest }: RepoSelectorProps) {
  const { repos, reload } = useRepos({ autoload: false }); // DataLoader owns the single list load.
  const { repoId } = useAppState();
  const dispatch = useAppDispatch();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listId = useId();

  // Close on outside press and on Escape (focus returns to the trigger).
  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current !== null && event.target instanceof Node && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const select = (next: string) => {
    setOpen(false);
    if (next === repoId) return; // 6.7: no request, no state change.
    dispatch({ type: 'repo-selected', repoId: next });
  };

  let body;
  if (repos.status === 'idle' || repos.status === 'loading') {
    // 6.2: loading blocks selection, so no entries are rendered.
    body = <StateBlock variant="loading" label="Loading repositories" className="p-0" />;
  } else if (repos.status === 'error') {
    // 6.4: no repositories listed, selection untouched.
    body = (
      <StateBlock
        variant="error"
        message={repos.error.message}
        onRetry={() => {
          void reload();
        }}
        className="p-1"
      />
    );
  } else if (repos.data.length === 0) {
    body = (
      <div className="flex items-center gap-2">
        <StateBlock variant="empty" label="No repositories ingested" className="p-0" />
        <button
          type="button"
          onClick={() => onIngest?.()}
          className="rounded-sm border border-hairline px-2 py-1 text-sm text-bone"
        >
          Ingest
        </button>
      </div>
    );
  } else {
    // The list stays in the DOM and is hidden by the `hidden` class while closed.
    body = (
      <div className="relative">
        <button
          ref={triggerRef}
          type="button"
          aria-haspopup="true"
          aria-expanded={open}
          aria-controls={listId}
          aria-label={repoId === null ? 'Select repository' : `Repository: ${repoId}`}
          onClick={() => setOpen((o) => !o)}
          className="flex w-56 items-center gap-2 rounded-sm border border-hairline bg-obsidian px-2.5 py-1 text-left text-sm text-bone hover:border-muted"
        >
          <span
            aria-hidden="true"
            className={`h-2 w-2 shrink-0 rounded-full ${repoId === null ? 'border border-muted' : 'bg-verified'}`}
          />
          <span className={`min-w-0 flex-1 truncate ${repoId === null ? 'text-muted' : 'font-mono text-xs'}`}>
            {repoId ?? 'Select repository'}
          </span>
          <ChevronDown aria-hidden="true" size={14} className="shrink-0 text-muted" />
        </button>
        <ul
          id={listId}
          aria-label="Repositories"
          className={`${
            open ? '' : 'hidden '
          }absolute left-0 top-full z-40 m-0 mt-1 max-h-72 w-80 list-none overflow-y-auto border border-hairline bg-surface p-1`}
        >
          {repos.data.map((repo) => {
            const selected = repo.repo_id === repoId;
            return (
              <li key={repo.repo_id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  aria-current={selected ? 'true' : undefined}
                  aria-label={`${repo.repo_id}, ${repo.file_count} files, ${repo.symbol_count} symbols`}
                  title={repo.repo_id}
                  onClick={() => select(repo.repo_id)}
                  className={`flex w-full items-center gap-3 border-l-2 px-2 py-1.5 text-left text-sm hover:bg-obsidian ${
                    selected ? 'border-verified text-bone' : 'border-transparent text-muted'
                  }`}
                >
                  <PlainText text={repo.repo_id} className="min-w-0 flex-1 truncate font-mono text-xs" />
                  <span className="shrink-0 text-xs tabular-nums">{repo.file_count} files</span>
                  <span className="shrink-0 text-xs tabular-nums">{repo.symbol_count} symbols</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <section ref={rootRef} aria-label="Repository selector" className="text-sm">
      {body}
    </section>
  );
}
