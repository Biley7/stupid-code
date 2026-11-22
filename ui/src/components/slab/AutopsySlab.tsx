// Autopsy_Slab landmark (Requirements 5.9, 18, 19, 22.10). Above the fold: subject
// header, Exorcism Check (Study Mode on), and the lens tabs. The lens content follows,
// then collapsible commits and spec provenance. The slab owns its own scrollbar.
import { useAppState } from '../../state/store';
import { ErrorBoundary } from '../shared/ErrorBoundary';
import { StateBlock } from '../shared/StateBlock';
import { ExorcismAction } from './ExorcismAction';
import { LensPanel } from './LensPanel';
import { LensTabs } from './LensTabs';
import { SlabMetadata } from './SlabMetadata';
import { SlabProvenance } from './SlabProvenance';

export function AutopsySlab() {
  const { file, symbol, node } = useAppState();
  const hasSelection = file !== null || symbol !== null || node !== null;
  return (
    <aside
      aria-label="Autopsy slab"
      className="flex min-h-0 w-[26rem] max-w-[40vw] shrink-0 flex-col overflow-y-auto overflow-x-hidden border-l border-hairline bg-surface"
    >
      <ErrorBoundary region="Autopsy slab">
        {hasSelection ? (
          <div className="flex min-w-0 flex-col">
            <div className="flex min-w-0 flex-col gap-2 p-3 pb-2">
              <SlabMetadata />
              <ExorcismAction />
            </div>
            <div className="sticky top-0 z-10 bg-surface">
              <LensTabs />
            </div>
            <LensPanel />
            <SlabProvenance />
          </div>
        ) : (
          <StateBlock variant="empty" label="Select a file or symbol to open its autopsy." />
        )}
      </ErrorBoundary>
    </aside>
  );
}
