import { cleanup } from '@testing-library/react';
import { getActiveFetchMock } from './mockFetch';

/**
 * Isolation between sequential steps that share one `it` block. Mirrors the global
 * afterEach/beforeEach in setup.ts: unmount, fail on unmatched requests, restore fetch,
 * and reset localStorage and the URL.
 */
export function resetBetweenSteps(): void {
  cleanup();
  document.body.innerHTML = '';
  const mock = getActiveFetchMock();
  const unmatched = mock ? [...mock.unmatched] : [];
  mock?.restore();
  window.localStorage.clear();
  window.history.replaceState({}, '', '/');
  if (unmatched.length > 0) {
    throw new Error(`Unmatched request: ${unmatched.join('; ')}`);
  }
}
