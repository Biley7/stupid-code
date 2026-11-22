// Compact mastery indicator: a colored dot plus the real state label. The label is
// always in the DOM (visible or screen-reader only) so color is never the only signal.
// All presentation comes from presentMastery via core/mastery.
import { presentMastery } from '../../core/mastery';
import type { ColorToken, MasteryPresentation } from '../../core/mastery';

const DOT_CLASS: Readonly<Record<ColorToken, string>> = {
  crimson: 'bg-crimson',
  bone: 'border border-bone bg-transparent',
  verified: 'bg-verified',
  stale: 'bg-stale',
  muted: 'border border-muted bg-transparent',
};

const TEXT_CLASS: Readonly<Record<ColorToken, string>> = {
  crimson: 'text-signal',
  bone: 'text-bone',
  verified: 'text-verified',
  stale: 'text-stale',
  muted: 'text-muted',
};

export interface MasteryDotProps {
  state?: unknown;
  presentation?: MasteryPresentation;
  /** Show the label next to the dot. Otherwise it is screen-reader only plus a tooltip. */
  showLabel?: boolean;
  className?: string;
}

export function MasteryDot({ state, presentation, showLabel = false, className }: MasteryDotProps) {
  const p = presentation ?? presentMastery(state);
  return (
    <span
      data-mastery={p.category}
      title={p.label}
      className={`inline-flex shrink-0 items-center gap-1.5 ${className ?? ''}`}
    >
      <span aria-hidden="true" className={`inline-block h-2 w-2 shrink-0 rounded-full ${DOT_CLASS[p.token]}`} />
      <span
        className={
          showLabel ? `text-[11px] font-medium uppercase tracking-wide ${TEXT_CLASS[p.token]}` : 'sr-only'
        }
      >
        {p.label}
      </span>
    </span>
  );
}
