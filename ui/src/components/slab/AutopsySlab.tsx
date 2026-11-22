// Autopsy_Slab landmark (Requirements 5.9, 18, 19, 22.10).
import { useAppState } from '../../state/store';
import { ErrorBoundary } from '../shared/ErrorBoundary';
import { StateBlock } from '../shared/StateBlock';
import { ExorcismAction } from './ExorcismAction';
import { LensPanel } from './LensPanel';
import { LensTabs } from './LensTabs';
import { SlabMetadata } from './SlabMetadata';

export function AutopsySlab() {
  const { file, symbol, node } = useAppState();
  const hasSelection = file !== null || symbol !== null || node !== null;
  return (
    <aside aria-label="Autopsy slab" className="w-96 shrink-0 overflow-auto border-l border-hairline bg-surface">
      <ErrorBoundary region="Autopsy slab">
        {hasSelection ? (
          <div className="flex flex-col gap-2 p-2">
            <SlabMetadata />
            <ExorcismAction />
            <LensTabs />
            <LensPanel />
          </div>
        ) : (
          <StateBlock variant="empty" label="Select a file or symbol to open its autopsy." />
        )}
      </ErrorBoundary>
    </aside>
  );
}
