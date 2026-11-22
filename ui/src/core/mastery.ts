// Pure mastery presentation. No React, no I/O. Every component that shows a
// mastery state goes through this module (Requirements 11.1 to 11.8, 15.11).

import type { ComprehensionVitals } from '../api/types';

export type MasteryCategory =
  | 'UNAUDITED'
  | 'DISSECTED'
  | 'MASTERED'
  | 'STALE'
  | 'NO TRACKED SYMBOLS'
  | 'STATE UNKNOWN';

/** lucide-react icon component names used for mastery states. */
export type IconName =
  | 'ShieldAlert'
  | 'ScanSearch'
  | 'ShieldCheck'
  | 'Clock'
  | 'CircleSlash'
  | 'CircleHelp';

export type ColorToken = 'crimson' | 'bone' | 'verified' | 'stale' | 'muted';

export type VisualMode = 'Autopsy' | 'Lab';

export interface MasteryPresentation {
  category: MasteryCategory;
  label: string;
  icon: IconName;
  token: ColorToken;
}

export type FileMastery = MasteryPresentation;

/**
 * Structural view of the `Remote<ComprehensionVitals>` store value. Only the
 * fields this module reads are declared, so it stays independent of `state/`.
 */
export type VitalsRemote =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: Pick<ComprehensionVitals, 'file_states'>; refreshFailed?: boolean }
  | { status: 'error'; error?: unknown };

const PRESENTATIONS: Readonly<Record<MasteryCategory, MasteryPresentation>> = {
  UNAUDITED: { category: 'UNAUDITED', label: 'UNAUDITED', icon: 'ShieldAlert', token: 'crimson' },
  DISSECTED: { category: 'DISSECTED', label: 'DISSECTED', icon: 'ScanSearch', token: 'bone' },
  MASTERED: { category: 'MASTERED', label: 'MASTERED', icon: 'ShieldCheck', token: 'verified' },
  STALE: { category: 'STALE', label: 'STALE', icon: 'Clock', token: 'stale' },
  'NO TRACKED SYMBOLS': {
    category: 'NO TRACKED SYMBOLS',
    label: 'NO TRACKED SYMBOLS',
    icon: 'CircleSlash',
    token: 'muted',
  },
  'STATE UNKNOWN': {
    category: 'STATE UNKNOWN',
    label: 'STATE UNKNOWN',
    icon: 'CircleHelp',
    token: 'muted',
  },
};

/** The four backend states, in a fixed order. */
const KNOWN_STATES = ['UNAUDITED', 'DISSECTED', 'MASTERED', 'STALE'] as const;

/** Total: any input yields a presentation, unknown input yields STATE UNKNOWN. */
export function presentMastery(input: unknown): MasteryPresentation {
  if (typeof input === 'string') {
    for (const state of KNOWN_STATES) {
      if (state === input) return PRESENTATIONS[state];
    }
  }
  return PRESENTATIONS['STATE UNKNOWN'];
}

/**
 * Per-file mastery, derived only from `file_states` of a ready vitals value.
 * A missing key means the file has no tracked symbols.
 */
export function fileMasteryView(vitals: VitalsRemote, filePath: string): FileMastery {
  if (vitals.status !== 'ready') return PRESENTATIONS['STATE UNKNOWN'];
  const states: unknown = vitals.data.file_states;
  if (
    typeof states !== 'object' ||
    states === null ||
    !Object.prototype.hasOwnProperty.call(states, filePath)
  ) {
    return PRESENTATIONS['NO TRACKED SYMBOLS'];
  }
  return presentMastery((states as Record<string, unknown>)[filePath]);
}

/** The Shroud applies only to UNAUDITED in Autopsy mode. */
export function isShrouded(mastery: MasteryPresentation, visualMode: VisualMode): boolean {
  return mastery.category === 'UNAUDITED' && visualMode === 'Autopsy';
}
