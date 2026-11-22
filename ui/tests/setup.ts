import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import fc from 'fast-check';
import { afterEach, beforeEach, vi } from 'vitest';
import { getActiveFetchMock } from './helpers/mockFetch';

// Tests run offline with the mock provider. No test reads a real .env.
vi.stubEnv('LLM_PROVIDER', 'mock');

fc.configureGlobal({ numRuns: 100, seed: 20250101 });

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

class DOMMatrixReadOnlyStub {
  m22: number;
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([\d.]+)\)/)?.[1];
    this.m22 = scale ? Number(scale) : 1;
  }
}

/** Switchable `prefers-reduced-motion` for tests. Default: no preference. */
let reducedMotion = false;
export function setReducedMotion(value: boolean): void {
  reducedMotion = value;
}

function installStubs(): void {
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  vi.stubGlobal('DOMMatrixReadOnly', DOMMatrixReadOnlyStub);

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList =>
      ({
        matches: query.includes('prefers-reduced-motion') ? reducedMotion : false,
        media: query,
        onchange: null,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  });

  Element.prototype.scrollIntoView = vi.fn();

  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
}

installStubs();

beforeEach(() => {
  reducedMotion = false;
  installStubs();
  window.localStorage.clear();
  window.history.replaceState({}, '', '/');
});

afterEach(() => {
  cleanup();
  const mock = getActiveFetchMock();
  const unmatched = mock ? [...mock.unmatched] : [];
  mock?.restore();
  if (unmatched.length > 0) {
    throw new Error(`Unmatched request: ${unmatched.join('; ')}`);
  }
});
