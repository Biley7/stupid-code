import { render, type RenderResult } from '@testing-library/react';
import type { ReactElement } from 'react';
import { ApiProvider } from '../../src/api/context';
import { StoreProvider } from '../../src/state/store';
import { installFetchMock, type FetchMock, type Route } from './mockFetch';

export interface RenderAppResult extends RenderResult {
  fetchMock: FetchMock;
}

/** Render `ui` under the API and store providers with a mocked fetch. Generic on purpose. */
export function renderApp(ui: ReactElement, routes: Route[]): RenderAppResult {
  const fetchMock = installFetchMock(routes);
  const result = render(
    <ApiProvider>
      <StoreProvider>{ui}</StoreProvider>
    </ApiProvider>,
  );
  return Object.assign(result, { fetchMock });
}
