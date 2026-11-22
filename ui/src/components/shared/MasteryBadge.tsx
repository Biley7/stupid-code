// Mastery state as icon, real text label, and color token, all from
// presentMastery (Requirements 11.9, 29.3). Color is never the only signal.

import { CircleHelp, CircleSlash, Clock, ScanSearch, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { presentMastery } from '../../core/mastery';
import type { ColorToken, IconName, MasteryPresentation } from '../../core/mastery';

const ICONS: Readonly<Record<IconName, LucideIcon>> = {
  ShieldAlert,
  ScanSearch,
  ShieldCheck,
  Clock,
  CircleSlash,
  CircleHelp,
};

const TEXT_CLASS: Readonly<Record<ColorToken, string>> = {
  crimson: 'text-signal',
  bone: 'text-bone',
  verified: 'text-verified',
  stale: 'text-stale',
  muted: 'text-muted',
};

const BORDER_CLASS: Readonly<Record<ColorToken, string>> = {
  crimson: 'border-crimson',
  bone: 'border-hairline',
  verified: 'border-verified',
  stale: 'border-stale',
  muted: 'border-hairline',
};

export interface MasteryBadgeProps {
  /** A backend mastery state string (any value), or an already presented value. */
  state?: unknown;
  presentation?: MasteryPresentation;
  className?: string;
}

export function MasteryBadge({ state, presentation, className }: MasteryBadgeProps) {
  const p = presentation ?? presentMastery(state);
  const Icon = ICONS[p.icon];
  return (
    <span
      data-mastery={p.category}
      className={`inline-flex items-center gap-1 border px-1.5 py-0.5 font-mono text-xs ${TEXT_CLASS[p.token]} ${BORDER_CLASS[p.token]} ${className ?? ''}`}
    >
      <Icon aria-hidden="true" size={12} />
      <span>{p.label}</span>
    </span>
  );
}
