// Lens tablist of the Autopsy_Slab (Requirements 19.1, 19.2). The active Lens is held
// in the App_Store; changing it keeps the selection. The shared Tabs component
// provides tablist/tab semantics, roving focus, arrow keys with wrap, Home, End.
import type { Lens } from '../../api/types';
import { useAppDispatch, useAppState } from '../../state/store';
import { Tabs, tabId, type TabItem } from '../shared/Tabs';

/** Prefix of every lens tab id: `${LENS_TAB_ID_PREFIX}-tab-${lens}`. */
export const LENS_TAB_ID_PREFIX = 'lens';
/** Id of the single tabpanel that `LensPanel` renders. */
export const LENS_PANEL_ID = 'lens-tabpanel';

export const LENS_TABS: readonly (TabItem & { id: Lens })[] = [
  { id: 'L1_SYNTAX', label: 'L1 Syntax' },
  { id: 'L2_FLOW', label: 'L2 Flow + DSA' },
  { id: 'L3_ARCHITECTURE', label: 'L3 Architecture' },
];

/** Id of the tab for a lens, for `aria-labelledby` on the tabpanel. */
export const lensTabId = (lens: Lens): string => tabId(LENS_TAB_ID_PREFIX, lens);

function isLens(id: string): id is Lens {
  return LENS_TABS.some((t) => t.id === id);
}

export function LensTabs() {
  const { lens } = useAppState();
  const dispatch = useAppDispatch();
  return (
    <Tabs
      tabs={LENS_TABS}
      selectedId={lens}
      onSelect={(id) => {
        if (isLens(id)) dispatch({ type: 'lens-set', value: id });
      }}
      ariaLabel="Lens"
      idPrefix={LENS_TAB_ID_PREFIX}
      panelId={LENS_PANEL_ID}
      fill
    />
  );
}
