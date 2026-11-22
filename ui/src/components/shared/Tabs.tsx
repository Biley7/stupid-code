import { useRef, type KeyboardEvent } from 'react';

export interface TabItem {
  id: string;
  label: string;
}

export interface TabsProps {
  tabs: readonly TabItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  /** Accessible name of the tablist. */
  ariaLabel: string;
  /** Unique prefix; each tab gets id `${idPrefix}-tab-${id}`. */
  idPrefix: string;
  /** Id of the single tabpanel the owner renders, with `aria-labelledby` set to the selected tab id. */
  panelId: string;
}

/** Tab id helper so the owner can label its tabpanel. */
export function tabId(idPrefix: string, id: string): string {
  return `${idPrefix}-tab-${id}`;
}

/** `tablist` with roving tabindex: Left/Right with wrap, Home, End. Selection follows focus. */
export function Tabs({ tabs, selectedId, onSelect, ariaLabel, idPrefix, panelId }: TabsProps) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function move(index: number) {
    const next = tabs[(index + tabs.length) % tabs.length];
    if (!next) return;
    onSelect(next.id);
    refs.current[next.id]?.focus();
  }

  function onKeyDown(event: KeyboardEvent, index: number) {
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault();
        move(index + 1);
        break;
      case 'ArrowLeft':
        event.preventDefault();
        move(index - 1);
        break;
      case 'Home':
        event.preventDefault();
        move(0);
        break;
      case 'End':
        event.preventDefault();
        move(tabs.length - 1);
        break;
    }
  }

  const hasSelected = tabs.some((t) => t.id === selectedId);

  return (
    <div role="tablist" aria-label={ariaLabel} className="flex border-b border-hairline">
      {tabs.map((tab, index) => {
        const selected = tab.id === selectedId;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            type="button"
            role="tab"
            id={tabId(idPrefix, tab.id)}
            aria-selected={selected}
            aria-controls={panelId}
            tabIndex={selected || (!hasSelected && index === 0) ? 0 : -1}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => onKeyDown(e, index)}
            className={`px-3 py-2 text-sm ${
              selected
                ? 'border-b-2 border-bone font-semibold text-bone'
                : 'border-b-2 border-transparent text-muted hover:text-bone'
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
