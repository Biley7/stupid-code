import type { Lens } from '../api/types';
import type { VisualMode } from '../core/mastery';
import type { ResolvedTarget } from '../core/snapshotIndex';

export type AppView = 'graph' | 'topology';
export type StudyModeValue = boolean | 'unknown';

/** Exactly the eight values of Requirement 4.1. */
export interface AppState {
  repoId: string | null;
  file: string | null;
  symbol: string | null;
  /** Graph node id; also holds a directory key after `select-directory`. */
  node: string | null;
  view: AppView;
  lens: Lens;
  studyMode: StudyModeValue;
  visualMode: VisualMode;
}

export type AppAction =
  | { type: 'repo-selected'; repoId: string | null }
  | { type: 'select-target'; target: ResolvedTarget }
  | { type: 'select-directory'; dir: string }
  | { type: 'node-cleared' }
  | { type: 'layer-changed'; keepNode: boolean }
  | { type: 'view-set'; value: AppView }
  | { type: 'lens-set'; value: Lens }
  | { type: 'study-mode-set'; value: StudyModeValue }
  | { type: 'visual-mode-set'; value: VisualMode };

export const initialAppState = (visualMode: VisualMode): AppState => ({
  repoId: null,
  file: null,
  symbol: null,
  node: null,
  view: 'graph',
  lens: 'L1_SYNTAX',
  studyMode: 'unknown',
  visualMode,
});

/** Returns `state` itself when the patch changes no field, otherwise a new object. */
function patch(state: AppState, next: Partial<AppState>): AppState {
  for (const key of Object.keys(next) as (keyof AppState)[]) {
    if (state[key] !== next[key]) return { ...state, ...next };
  }
  return state;
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'repo-selected':
      if (action.repoId === state.repoId) return state;
      return {
        ...state,
        repoId: action.repoId,
        file: null,
        symbol: null,
        node: null,
        studyMode: 'unknown',
      };
    case 'select-target': {
      const t = action.target;
      if (t.kind === 'file') {
        return patch(state, { file: t.path, node: t.path, symbol: null });
      }
      return patch(state, { file: t.filePath, node: t.id, symbol: t.id });
    }
    case 'select-directory':
      return patch(state, { node: action.dir, lens: 'L3_ARCHITECTURE' });
    case 'node-cleared':
      return patch(state, { node: null });
    case 'layer-changed':
      return action.keepNode ? state : patch(state, { node: null });
    case 'view-set':
      return patch(state, { view: action.value });
    case 'lens-set':
      return patch(state, { lens: action.value });
    case 'study-mode-set':
      return patch(state, { studyMode: action.value });
    case 'visual-mode-set':
      return patch(state, { visualMode: action.value });
    default:
      return state;
  }
}
