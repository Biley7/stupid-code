// Repository list and selection (Requirement 6). Lists only what the backend
// returned, in backend order. `repo_id` is plain monospace text.
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

  const select = (next: string) => {
    if (next === repoId) return; // 6.7: no request, no state change.
    dispatch({ type: 'repo-selected', repoId: next });
  };

  let body;
  if (repos.status === 'idle' || repos.status === 'loading') {
    // 6.2: loading blocks selection, so no entries are rendered.
    body = <StateBlock variant="loading" label="Loading repositories" />;
  } else if (repos.status === 'error') {
    // 6.4: no repositories listed, selection untouched.
    body = (
      <StateBlock
        variant="error"
        message={repos.error.message}
        onRetry={() => {
          void reload();
        }}
      />
    );
  } else if (repos.data.length === 0) {
    body = (
      <div>
        <StateBlock variant="empty" label="No repositories ingested" />
        <button
          type="button"
          onClick={() => onIngest?.()}
          className="ml-3 border border-hairline px-2 py-1 text-sm text-bone"
        >
          Ingest
        </button>
      </div>
    );
  } else {
    body = (
      <ul aria-label="Repositories" className="m-0 list-none p-0">
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
                className={`flex w-full items-center gap-3 border px-2 py-1 text-left text-sm ${
                  selected ? 'border-verified text-bone' : 'border-hairline text-muted'
                }`}
              >
                <PlainText
                  text={repo.repo_id}
                  className="min-w-0 flex-1 truncate font-mono"
                />
                <span className="font-mono text-xs">{repo.file_count} files</span>
                <span className="font-mono text-xs">{repo.symbol_count} symbols</span>
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section aria-label="Repository selector" className="text-sm">
      {body}
    </section>
  );
}
