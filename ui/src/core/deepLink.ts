/**
 * Deep-link parsing, resolution, and URL building (Requirement 26).
 * Pure: no DOM, no history access. Values are untrusted and only compared.
 */

export const MAX_DEEP_LINK_VALUE_LENGTH = 4096;

export type ParamValue =
  | { present: false }
  | { present: true; value: string; matchable: boolean };

export type DeepLinkView = 'graph' | 'topology';

export interface ParsedDeepLink {
  repoId: ParamValue;
  file: ParamValue;
  view: DeepLinkView | null;
}

function readParam(params: URLSearchParams, name: string): ParamValue {
  // `get` returns the first occurrence (26.12).
  const value = params.get(name);
  if (value === null) return { present: false };
  return { present: true, value, matchable: value.length <= MAX_DEEP_LINK_VALUE_LENGTH };
}

export function parseDeepLink(search: string): ParsedDeepLink {
  const params = new URLSearchParams(search);
  const view = params.get('view');
  return {
    repoId: readParam(params, 'repo_id'),
    file: readParam(params, 'file'),
    view: view === 'graph' || view === 'topology' ? view : null,
  };
}

export function resolveDeepLink(
  p: ParsedDeepLink,
  repoIds: readonly string[],
): { repoId: string | null; notFound: boolean; ignoreFile: boolean } {
  if (!p.repoId.present) {
    // `file` without `repo_id` is ignored silently (26.6).
    return { repoId: null, notFound: false, ignoreFile: true };
  }
  const { value, matchable } = p.repoId;
  if (matchable && repoIds.includes(value)) {
    return { repoId: value, notFound: false, ignoreFile: false };
  }
  return { repoId: null, notFound: true, ignoreFile: true };
}

export function resolveFile(
  p: ParsedDeepLink,
  filePaths: ReadonlySet<string>,
): { file: string | null; notFound: boolean } {
  if (!p.file.present) return { file: null, notFound: false };
  const { value, matchable } = p.file;
  if (matchable && filePaths.has(value)) return { file: value, notFound: false };
  return { file: null, notFound: true };
}

export function buildSearch(
  current: string,
  s: { repoId: string | null; file: string | null; view: DeepLinkView },
): string {
  const params = new URLSearchParams(current);
  if (s.repoId !== null) params.set('repo_id', s.repoId);
  else params.delete('repo_id');
  if (s.file !== null) params.set('file', s.file);
  else params.delete('file');
  params.set('view', s.view);
  return `?${params.toString()}`;
}
