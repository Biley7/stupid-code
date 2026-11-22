// Application layout (Requirement 5). Landmarks in tab order: Command_Bar,
// Specimen_Rail, Canvas, Autopsy_Slab. The shell fills the viewport and never scrolls:
// the Command_Bar stays fixed on top, and the three workspace columns each own their
// scrollbar.
import { CommandBar } from './CommandBar';
import { SpecimenRail } from '../rail/SpecimenRail';
import { Canvas } from '../canvas/Canvas';
import { NoticeBar } from './NoticeBar';
import { AutopsySlab } from '../slab/AutopsySlab';

export function Shell() {
  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-obsidian text-bone">
      <CommandBar />
      <NoticeBar />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <SpecimenRail />
        <Canvas />
        <AutopsySlab />
      </div>
      {/* Modals portal into #modal-root (index.html); this mount marks where ModalRoot content is composed. */}
      <div data-region="modal-mount" />
    </div>
  );
}
