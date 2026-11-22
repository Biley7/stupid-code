// Command_Bar (Requirement 5.1). Tab order: repository selector, Ingest,
// vitals, Study Mode switch, visual mode toggle.
import { useState } from 'react';
import { IngestModal } from './IngestModal';
import { RepoSelector } from './RepoSelector';
import { StudyModeSwitch } from './StudyModeSwitch';
import { VisualModeToggle } from './VisualModeToggle';
import { VitalsMeter } from './VitalsMeter';

export function CommandBar() {
  const [ingestOpen, setIngestOpen] = useState(false);
  return (
    <header
      role="banner"
      aria-labelledby="command-bar-heading"
      className="relative z-30 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-hairline bg-surface px-3 py-2"
    >
      <div className="flex items-baseline gap-2">
        <h1
          id="command-bar-heading"
          tabIndex={-1}
          className="m-0 text-sm font-bold uppercase tracking-[0.18em] text-bone"
        >
          Stupid Code
        </h1>
        <span
          aria-hidden="true"
          className="border-l border-hairline pl-2 font-mono text-[10px] uppercase tracking-widest text-muted"
        >
          Code Autopsy
        </span>
      </div>
      <div className="flex items-center gap-2">
        <RepoSelector onIngest={() => setIngestOpen(true)} />
        <button
          type="button"
          onClick={() => setIngestOpen(true)}
          className="rounded-sm border border-hairline px-2.5 py-1 text-sm text-bone hover:border-muted"
        >
          Ingest
        </button>
      </div>
      <div className="min-w-[18rem] flex-1">
        <VitalsMeter />
      </div>
      <div className="flex items-center gap-3">
        <StudyModeSwitch />
        <VisualModeToggle />
      </div>
      {ingestOpen ? <IngestModal onClose={() => setIngestOpen(false)} /> : null}
    </header>
  );
}
