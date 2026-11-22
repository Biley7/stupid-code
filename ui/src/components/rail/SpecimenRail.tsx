// Specimen_Rail (Requirements 5.2 to 5.4, 5.6 to 5.8, 12, 13, 14). Hosts the file
// tree, vital organs, and spec drift sections. When collapsed, the content is
// unmounted so its controls leave the tab order; selection lives in the app store
// and the panels never start requests, so collapsing neither loses selection nor
// sends a request. The Canvas is flex-1, so the freed width goes to it.
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useState } from 'react';
import { DriftPanel } from './DriftPanel';
import { FileTree } from './FileTree';
import { VitalOrgansList } from './VitalOrgansList';

const HEADING = 'px-2 pb-1 pt-3 font-mono text-xs uppercase tracking-wide text-muted';

export function SpecimenRail() {
  const [collapsed, setCollapsed] = useState(false);
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;
  return (
    <nav
      aria-label="Specimen rail"
      className={`flex shrink-0 flex-col overflow-hidden border-r border-hairline bg-surface ${
        collapsed ? 'w-10' : 'w-72'
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
        <div className="min-h-0 flex-1 overflow-auto">
          <section aria-labelledby="rail-files-heading">
            <h2 id="rail-files-heading" className={HEADING}>
              Files
            </h2>
            <FileTree />
          </section>
          <section aria-labelledby="rail-organs-heading">
            <h2 id="rail-organs-heading" className={HEADING}>
              Vital organs
            </h2>
            <VitalOrgansList />
          </section>
          <section aria-labelledby="rail-drift-heading">
            <h2 id="rail-drift-heading" className={HEADING}>
              Spec drift
            </h2>
            <DriftPanel />
          </section>
        </div>
      )}
    </nav>
  );
}
