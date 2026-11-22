// Application layout (Requirement 5). Landmarks in tab order: Command_Bar,
// Specimen_Rail, Canvas, Autopsy_Slab. The regions below are minimal placeholders;
// later tasks replace each with CommandBar, SpecimenRail, Canvas, and AutopsySlab.
import { CommandBar } from './CommandBar';
import { SpecimenRail } from '../rail/SpecimenRail';
import { Canvas } from '../canvas/Canvas';
import { NoticeBar } from './NoticeBar';
import { AutopsySlab } from '../slab/AutopsySlab';

export function Shell() {
  return (
    <div className="flex h-full flex-col bg-obsidian text-bone">
      <CommandBar />
      <NoticeBar />
      <div className="flex min-h-0 flex-1">
        <SpecimenRail />
        <Canvas />
        <AutopsySlab />
      </div>
      {/* Modals portal into #modal-root (index.html); this mount marks where ModalRoot content is composed. */}
      <div data-region="modal-mount" />
    </div>
  );
}
