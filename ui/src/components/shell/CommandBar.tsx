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
      className="flex flex-wrap items-center gap-3 border-b border-hairline bg-surface px-3 py-2"
    >
      <h1 id="command-bar-heading" tabIndex={-1} className="m-0 text-sm font-semibold">
        Code Autopsy
      </h1>
      <RepoSelector onIngest={() => setIngestOpen(true)} />
      <button
        type="button"
        onClick={() => setIngestOpen(true)}
        className="border border-hairline px-2 py-1 text-sm text-bone"
      >
        Ingest
      </button>
      <VitalsMeter />
      <StudyModeSwitch />
      <VisualModeToggle />
      {ingestOpen ? <IngestModal onClose={() => setIngestOpen(false)} /> : null}
    </header>
  );
}
