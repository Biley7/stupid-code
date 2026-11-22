/**
 * Recompute counters. Each builder increments its counter when it actually
 * recomputes (not on a memo hit), so tests can assert that selection, vitals
 * and visual-mode changes cause no recomputation.
 */
export interface ComputeCounters {
  fileTree: number;
  graph: number;
  layout: number;
  cycleSet: number;
  masteryLookup: number;
}

export const computeCounters: ComputeCounters = {
  fileTree: 0,
  graph: 0,
  layout: 0,
  cycleSet: 0,
  masteryLookup: 0,
};

export function resetComputeCounters(): void {
  computeCounters.fileTree = 0;
  computeCounters.graph = 0;
  computeCounters.layout = 0;
  computeCounters.cycleSet = 0;
  computeCounters.masteryLookup = 0;
}
