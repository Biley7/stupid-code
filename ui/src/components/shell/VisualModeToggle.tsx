// Autopsy / Lab visual mode (Requirement 10). Independent of Study Mode.
// A two-segment switch: exactly one segment is pressed.
import type { VisualMode } from '../../core/mastery';
import { useAppDispatch, useAppState } from '../../state/store';

const SEGMENTS: readonly { value: VisualMode; label: string }[] = [
  { value: 'Autopsy', label: 'Autopsy' },
  { value: 'Lab', label: 'Lab' },
];

export function VisualModeToggle() {
  const { visualMode } = useAppState();
  const dispatch = useAppDispatch();
  return (
    <div
      role="group"
      aria-label="Visual mode"
      className="inline-flex items-stretch rounded-sm border border-hairline bg-obsidian p-0.5"
    >
      {SEGMENTS.map((segment) => {
        const active = visualMode === segment.value;
        return (
          <button
            key={segment.value}
            type="button"
            aria-pressed={active}
            onClick={() => {
              if (!active) dispatch({ type: 'visual-mode-set', value: segment.value });
            }}
            className={`rounded-[2px] px-3 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
              active
                ? segment.value === 'Autopsy'
                  ? 'bg-crimson text-bone'
                  : 'bg-bone text-obsidian'
                : 'text-muted hover:text-bone'
            }`}
          >
            {segment.label}
          </button>
        );
      })}
    </div>
  );
}
