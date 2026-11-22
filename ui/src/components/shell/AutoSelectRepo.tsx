// Render-less. When the landing URL names no repository, selects the first listed one
// as soon as the list is ready, so `/` never shows an empty "No repository selected" view.
// A `?repo_id=` param is the deep link's business: it is left to DeepLinkController,
// including the not-found notice.
import { useEffect, useRef } from 'react';
import { parseDeepLink } from '../../core/deepLink';
import { useAppDispatch, useAppState, useDataState } from '../../state/store';

export function AutoSelectRepo(): null {
  const { repoId } = useAppState();
  const repos = useDataState().repos;
  const dispatch = useAppDispatch();
  // Read once: DeepLinkController rewrites the query string after it resolves.
  const hadRepoParam = useRef<boolean | null>(null);
  if (hadRepoParam.current === null) {
    hadRepoParam.current = parseDeepLink(window.location.search).repoId.present;
  }
  const first = repos.status === 'ready' ? (repos.data[0]?.repo_id ?? null) : null;
  useEffect(() => {
    if (hadRepoParam.current === true) return;
    if (repoId !== null || first === null) return;
    dispatch({ type: 'repo-selected', repoId: first });
  }, [repoId, first, dispatch]);
  return null;
}
