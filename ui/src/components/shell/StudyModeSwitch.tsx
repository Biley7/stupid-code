// Study Mode switch (Requirement 9). The displayed value changes only after the
// backend confirms; while pending the previous value stays and aria-busy is set.
import { useStudyMode } from '../../data/useStudyMode';
import { useAppState } from '../../state/store';
import { PlainText } from '../shared/PlainText';

export function StudyModeSwitch() {
  const { repoId, studyMode } = useAppState();
  const { pending, error, toggle } = useStudyMode();
  const on = studyMode === true;
  const label = studyMode === 'unknown' ? 'Study Mode unknown' : on ? 'Study Mode on' : 'Study Mode off';
  return (
    <div className="flex items-center gap-2 text-sm">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-busy={pending}
        aria-label={label}
        disabled={repoId === null || pending}
        onClick={() => toggle(!on)}
        className={`border px-2 py-1 disabled:text-muted ${on ? 'border-verified text-bone' : 'border-hairline text-muted'}`}
      >
        {on ? 'Study Mode: On' : studyMode === 'unknown' ? 'Study Mode: —' : 'Study Mode: Off'}
      </button>
      {pending ? <span className="text-xs text-muted">Updating…</span> : null}
      {error ? <PlainText as="span" text={error.message} className="text-xs text-signal" /> : null}
      <span role="status" aria-live="polite" className="sr-only">
        {error ? error.message : label}
      </span>
    </div>
  );
}
