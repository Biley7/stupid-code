// Providers, hooks, and selectors for the App_Store and the DataStore.
// Reducers stay pure in appReducer.ts and dataReducer.ts (Requirements 4.1 to 4.14).

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  type Dispatch,
  type ReactNode,
} from 'react';
import type { VisualMode } from '../core/mastery';
import { createRequestScope, type RequestScope } from '../data/requestScope';
import { appReducer, initialAppState, type AppAction, type AppState } from './appReducer';
import {
  dataReducer,
  initialDataState,
  type DataAction,
  type DataState,
} from './dataReducer';

export const VISUAL_MODE_KEY = 'stupid-code.visual-mode';

function readStoredVisualMode(): VisualMode {
  try {
    const stored = window.localStorage.getItem(VISUAL_MODE_KEY);
    if (stored === 'Autopsy' || stored === 'Lab') return stored;
  } catch {
    // Storage unavailable: use the default.
  }
  return 'Autopsy';
}

function applyVisualMode(mode: VisualMode): void {
  document.documentElement.dataset.visualMode = mode === 'Lab' ? 'lab' : 'autopsy';
}

const AppStateContext = createContext<AppState | null>(null);
const AppDispatchContext = createContext<Dispatch<AppAction> | null>(null);
const DataStateContext = createContext<DataState | null>(null);
const DataDispatchContext = createContext<Dispatch<DataAction> | null>(null);
const ScopeContext = createContext<RequestScope | null>(null);

function required<T>(value: T | null, name: string): T {
  if (value === null) throw new Error(`${name} must be used inside <StoreProvider>`);
  return value;
}

export interface StoreProviderProps {
  children: ReactNode;
  /** Test hook: overrides the restored visual mode. */
  initialVisualMode?: VisualMode;
}

export function StoreProvider({ children, initialVisualMode }: StoreProviderProps) {
  const [app, rawAppDispatch] = useReducer(appReducer, undefined, () =>
    initialAppState(initialVisualMode ?? readStoredVisualMode()),
  );
  const [data, dataDispatch] = useReducer(dataReducer, initialDataState);

  const scopeRef = useRef<RequestScope | null>(null);
  if (scopeRef.current === null) scopeRef.current = createRequestScope();
  const scope = scopeRef.current;

  // Tracks the repoId synchronously so a repository change aborts the previous
  // repository's requests and clears DataStore data before any new request starts.
  const repoRef = useRef<string | null>(app.repoId);

  const appDispatch = useCallback<Dispatch<AppAction>>(
    (action) => {
      if (action.type === 'repo-selected' && action.repoId !== repoRef.current) {
        repoRef.current = action.repoId;
        scope.rotate();
        dataDispatch({ type: 'repo-selected', repoId: action.repoId });
      }
      rawAppDispatch(action);
    },
    [scope],
  );

  // Persist only the visual mode; update the attribute before paint. Study Mode is
  // never written to browser storage (Requirements 4.11, 4.12).
  useLayoutEffect(() => {
    applyVisualMode(app.visualMode);
    try {
      window.localStorage.setItem(VISUAL_MODE_KEY, app.visualMode);
    } catch {
      // Keep the in-memory value (Requirement 4.13).
    }
  }, [app.visualMode]);

  useEffect(() => () => scope.dispose(), [scope]);

  return (
    <ScopeContext.Provider value={scope}>
      <AppDispatchContext.Provider value={appDispatch}>
        <AppStateContext.Provider value={app}>
          <DataDispatchContext.Provider value={dataDispatch}>
            <DataStateContext.Provider value={data}>{children}</DataStateContext.Provider>
          </DataDispatchContext.Provider>
        </AppStateContext.Provider>
      </AppDispatchContext.Provider>
    </ScopeContext.Provider>
  );
}

export const useAppState = (): AppState => required(useContext(AppStateContext), 'useAppState');
export const useAppDispatch = (): Dispatch<AppAction> =>
  required(useContext(AppDispatchContext), 'useAppDispatch');
export const useDataState = (): DataState => required(useContext(DataStateContext), 'useDataState');
export const useDataDispatch = (): Dispatch<DataAction> =>
  required(useContext(DataDispatchContext), 'useDataDispatch');
export const useRequestScope = (): RequestScope => required(useContext(ScopeContext), 'useRequestScope');

/** Select one slice of the App_Store. */
export function useAppSelector<T>(selector: (state: AppState) => T): T {
  return selector(useAppState());
}

/** Select one slice of the DataStore. */
export function useDataSelector<T>(selector: (state: DataState) => T): T {
  return selector(useDataState());
}

export const useSelection = () => {
  const { repoId, file, symbol, node } = useAppState();
  return useMemo(() => ({ repoId, file, symbol, node }), [repoId, file, symbol, node]);
};
