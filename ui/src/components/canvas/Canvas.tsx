// Canvas region (Requirements 3.14, 5, 15, 17). A Graph/Topology tablist, exactly one
// active view in the App_Store, wrapped in an ErrorBoundary. Switching views only sets
// `view`, so the selected node is preserved. The Autopsy grid lives on this container.
import type { AppView } from '../../state/appReducer';
import { useSnapshot } from '../../data/useSnapshot';
import { useAppDispatch, useAppState } from '../../state/store';
import { ErrorBoundary } from '../shared/ErrorBoundary';
import { StateBlock } from '../shared/StateBlock';
import { Tabs, tabId, type TabItem } from '../shared/Tabs';
import { GraphView } from './GraphView';
import { TopologyView } from './TopologyView';

export const VIEW_TAB_ID_PREFIX = 'view';
export const VIEW_PANEL_ID = 'view-tabpanel';

export const VIEW_TABS: readonly (TabItem & { id: AppView })[] = [
  { id: 'graph', label: 'Graph' },
  { id: 'topology', label: 'Topology' },
];

function isView(id: string): id is AppView {
  return VIEW_TABS.some((t) => t.id === id);
}

function ViewTabs() {
  const { view } = useAppState();
  const dispatch = useAppDispatch();
  return (
    <Tabs
      tabs={VIEW_TABS}
      selectedId={view}
      onSelect={(id) => {
        if (isView(id)) dispatch({ type: 'view-set', value: id });
      }}
      ariaLabel="View"
      idPrefix={VIEW_TAB_ID_PREFIX}
      panelId={VIEW_PANEL_ID}
    />
  );
}

function ActiveView() {
  const { repoId, view } = useAppState();
  const { snapshot } = useSnapshot({ autoload: false });
  if (repoId === null) return <StateBlock variant="empty" label="No repository selected." />;
  if (snapshot.status === 'ready') {
    if (snapshot.data.snapshot.files.length === 0) {
      return <StateBlock variant="empty" label="This repository has no analyzed files." />;
    }
    if (view === 'graph' && snapshot.data.snapshot.edges.length === 0) {
      return (
        <div className="flex h-full min-h-0 flex-col">
          <StateBlock variant="empty" label="No dependency edges were found." />
          <div className="min-h-0 flex-1">
            <GraphView />
          </div>
        </div>
      );
    }
  }
  return view === 'graph' ? <GraphView /> : <TopologyView />;
}

export function Canvas() {
  const { view } = useAppState();
  return (
    <main aria-label="Canvas" className="canvas-grid flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overflow-x-hidden">
      <ViewTabs />
      <div
        role="tabpanel"
        id={VIEW_PANEL_ID}
        aria-labelledby={tabId(VIEW_TAB_ID_PREFIX, view)}
        className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden"
      >
        <ErrorBoundary region="Canvas">
          <ActiveView />
        </ErrorBoundary>
      </div>
    </main>
  );
}
