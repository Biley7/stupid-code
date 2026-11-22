// Autopsy / Lab visual mode (Requirement 10). Independent of Study Mode.
import { useAppDispatch, useAppState } from '../../state/store';

export function VisualModeToggle() {
  const { visualMode } = useAppState();
  const dispatch = useAppDispatch();
  const lab = visualMode === 'Lab';
  return (
    <button
      type="button"
      aria-pressed={lab}
      onClick={() => dispatch({ type: 'visual-mode-set', value: lab ? 'Autopsy' : 'Lab' })}
      className="border border-hairline px-2 py-1 text-sm text-bone"
    >
      {lab ? 'Lab Mode' : 'Autopsy Mode'}
    </button>
  );
}
