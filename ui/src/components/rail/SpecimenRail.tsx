// Specimen_Rail (Requirements 5.2 to 5.4, 5.6 to 5.8, 12, 13, 14). Hosts the file
// tree, vital organs, and spec drift as collapsible sections. When the rail is
// collapsed, the content is unmounted so its controls leave the tab order; selection
// lives in the app store and the panels never start requests, so collapsing neither
// loses selection nor sends a request. The Canvas is flex-1, so the freed width goes to
// it. The rail is one of the three independently scrolling columns.
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useState } from 'react';
import { useDataState } from '../../state/store';
import { Collapsible } from '../shared/Collapsible';
import { DriftPanel } from './DriftPanel';
import { FileTree } from './FileTree';
import { VitalOrgansList } from './VitalOrgansList';

export function SpecimenRail() {
  const [collapsed, setCollapsed] = useState(false);
  const snapshot = useDataState().snapshot;
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const fileCount = snapshot.status === 'ready' ? snapshot.data.snapshot.files.length : null;
  const driftCount =
    snapshot.status === 'ready' && snapshot.data.provenance.has_kiro_specs
      ? snapshot.data.provenance.drift_items.length
      : null;
  return (
    <nav
      aria-label="Specimen rail"
      className={`flex min-h-0 shrink-0 flex-col overflow-hidden border-r border-hairline bg-surface ${
        collapsed ? 'w-10' : 'w-80'
      }`}
    >
      <button
        type="button"
        aria-label={collapsed ? 'Expand specimen rail' : 'Collapse specimen rail'}
        aria-expanded={!collapsed}
        onClick={() => setCollapsed((c) => !c)}
        className="flex h-9 w-full shrink-0 items-center justify-center border-b border-hairline text-muted hover:text-bone"
      >
        <Icon aria-hidden="true" size={16} />
      </button>
      {collapsed ? null : (
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
          <Collapsible
            title="Files"
            headingLevel="h2"
            defaultOpen
            badge={fileCount}
            className="border-t-0"
          >
            <div className="-mx-2">
              <FileTree />
            </div>
          </Collapsible>
          <Collapsible title="Vital organs" headingLevel="h2" defaultOpen>
            <div className="-mx-2">
              <VitalOrgansList />
            </div>
          </Collapsible>
          <Collapsible title="Spec drift" headingLevel="h2" badge={driftCount}>
            <div className="-mx-2">
              <DriftPanel />
            </div>
          </Collapsible>
        </div>
      )}
    </nav>
  );
}
