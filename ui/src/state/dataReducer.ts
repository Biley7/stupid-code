// Pure DataStore reducer. No React, no I/O. Every async result is guarded by the
// repository id and a per-resource sequence number, so a stale response can never
// change state (Requirements 4.4, 4.14, 8.9, 8.10, 19.15, 25.7, 25.9, 25.10).

import type { ApiError } from '../api/errors';
import type {
  ComprehensionVitals,
  ExplainResponse,
  Lens,
  RepoSummary,
  SnapshotResponse,
} from '../api/types';

/**
 * Remote value. Structurally compatible with `VitalsRemote` in `core/mastery.ts`.
 * `refreshFailed` is set only on a `ready` value whose `keep` refresh failed.
 */
export type Remote<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: T; refreshFailed?: boolean }
  | { status: 'error'; error: ApiError };

export type VitalsRefreshMode = 'replace' | 'keep';

export interface DataSeq {
  repos: number;
  snapshot: number;
  vitals: number;
  explain: Record<string, number>;
}

export interface DataState {
  /** The one repository the snapshot, vitals, and explain data belong to. */
  repoId: string | null;
  repos: Remote<RepoSummary[]>;
  snapshot: Remote<SnapshotResponse>;
  vitals: Remote<ComprehensionVitals>;
  /** Key = `explainKey(repoId, targetId, lens)`. */
  explain: Record<string, Remote<ExplainResponse>>;
  seq: DataSeq;
}

export type ScopedResource = 'snapshot' | 'vitals';

export type DataAction =
  | { type: 'repo-selected'; repoId: string | null }
  | { type: 'resource-start'; resource: 'repos' }
  | { type: 'resource-start'; resource: ScopedResource; repoId: string; mode?: VitalsRefreshMode }
  | { type: 'resource-start'; resource: 'explain'; repoId: string; key: string }
  | { type: 'resource-success'; resource: 'repos'; seq: number; data: RepoSummary[] }
  | { type: 'resource-success'; resource: 'snapshot'; repoId: string; seq: number; data: SnapshotResponse }
  | { type: 'resource-success'; resource: 'vitals'; repoId: string; seq: number; data: ComprehensionVitals }
  | { type: 'resource-success'; resource: 'explain'; repoId: string; key: string; seq: number; data: ExplainResponse }
  | { type: 'resource-failure'; resource: 'repos'; seq: number; error: ApiError }
  | { type: 'resource-failure'; resource: ScopedResource; repoId: string; seq: number; error: ApiError; mode?: VitalsRefreshMode }
  | { type: 'resource-failure'; resource: 'explain'; repoId: string; key: string; seq: number; error: ApiError }
  /** Removes a non-ready explain entry when its effect is cleaned up. */
  | { type: 'explain-remove'; repoId: string; key: string }
  /** Patches `study_mode_enabled` on one list entry after a successful toggle. */
  | { type: 'repo-study-mode-patched'; repoId: string; enabled: boolean };

export const explainKey = (repoId: string, targetId: string, lens: Lens): string =>
  `${repoId}\u0000${targetId}\u0000${lens}`;

export const initialDataState: DataState = {
  repoId: null,
  repos: { status: 'idle' },
  snapshot: { status: 'idle' },
  vitals: { status: 'idle' },
  explain: {},
  seq: { repos: 0, snapshot: 0, vitals: 0, explain: {} },
};

export function dataReducer(state: DataState, action: DataAction): DataState {
  switch (action.type) {
    case 'repo-selected': {
      if (action.repoId === state.repoId) return state;
      return {
        ...state,
        repoId: action.repoId,
        snapshot: { status: 'idle' },
        vitals: { status: 'idle' },
        explain: {},
        seq: { repos: state.seq.repos, snapshot: 0, vitals: 0, explain: {} },
      };
    }

    case 'resource-start': {
      if (action.resource === 'repos') {
        const seq = state.seq.repos + 1;
        return { ...state, repos: { status: 'loading' }, seq: { ...state.seq, repos: seq } };
      }
      if (action.repoId !== state.repoId) return state;
      if (action.resource === 'explain') {
        const seq = (state.seq.explain[action.key] ?? 0) + 1;
        return {
          ...state,
          explain: { ...state.explain, [action.key]: { status: 'loading' } },
          seq: { ...state.seq, explain: { ...state.seq.explain, [action.key]: seq } },
        };
      }
      const seq = state.seq[action.resource] + 1;
      const nextSeq = { ...state.seq, [action.resource]: seq };
      // A `keep` refresh never shows loading, so the previous values stay visible.
      if (action.resource === 'vitals' && action.mode === 'keep' && state.vitals.status === 'ready') {
        return { ...state, seq: nextSeq };
      }
      return { ...state, [action.resource]: { status: 'loading' }, seq: nextSeq };
    }

    case 'resource-success': {
      if (action.resource === 'repos') {
        if (action.seq <= 0 || action.seq !== state.seq.repos) return state;
        return { ...state, repos: { status: 'ready', data: action.data } };
      }
      if (action.repoId !== state.repoId) return state;
      if (action.resource === 'explain') {
        if (action.seq <= 0 || action.seq !== state.seq.explain[action.key]) return state;
        return { ...state, explain: { ...state.explain, [action.key]: { status: 'ready', data: action.data } } };
      }
      if (action.seq <= 0 || action.seq !== state.seq[action.resource]) return state;
      return { ...state, [action.resource]: { status: 'ready', data: action.data } };
    }

    case 'resource-failure': {
      if (action.resource === 'repos') {
        if (action.seq <= 0 || action.seq !== state.seq.repos) return state;
        return { ...state, repos: { status: 'error', error: action.error } };
      }
      if (action.repoId !== state.repoId) return state;
      if (action.resource === 'explain') {
        if (action.seq <= 0 || action.seq !== state.seq.explain[action.key]) return state;
        return { ...state, explain: { ...state.explain, [action.key]: { status: 'error', error: action.error } } };
      }
      if (action.seq <= 0 || action.seq !== state.seq[action.resource]) return state;
      if (action.resource === 'vitals' && action.mode === 'keep' && state.vitals.status === 'ready') {
        return { ...state, vitals: { status: 'ready', data: state.vitals.data, refreshFailed: true } };
      }
      return { ...state, [action.resource]: { status: 'error', error: action.error } };
    }

    case 'explain-remove': {
      if (action.repoId !== state.repoId) return state;
      const entry = state.explain[action.key];
      if (entry === undefined || entry.status === 'ready') return state;
      const { [action.key]: _removed, ...rest } = state.explain;
      return { ...state, explain: rest };
    }

    case 'repo-study-mode-patched': {
      if (state.repos.status !== 'ready') return state;
      let changed = false;
      const data = state.repos.data.map((repo) => {
        if (repo.repo_id !== action.repoId || repo.study_mode_enabled === action.enabled) return repo;
        changed = true;
        return { ...repo, study_mode_enabled: action.enabled };
      });
      return changed ? { ...state, repos: { status: 'ready', data } } : state;
    }
  }
}
