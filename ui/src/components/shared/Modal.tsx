import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/** Heading that receives focus when the opener no longer exists (Requirement 29.4). */
export const COMMAND_BAR_HEADING_SELECTOR = '#command-bar-heading';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface ModalProps {
  /** Accessible title, also rendered as the visible heading. */
  title: string;
  onRequestClose: () => void;
  /** While true, Escape and the close control are ignored (Requirement 29.6). */
  blockClose?: boolean;
  children: ReactNode;
}

function focusableIn(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true',
  );
}

export function Modal({ title, onRequestClose, blockClose = false, children }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const blockRef = useRef(blockClose);
  const closeRef = useRef(onRequestClose);
  blockRef.current = blockClose;
  closeRef.current = onRequestClose;

  // Mount: remember the opener, make the background inert, move focus inside.
  // Unmount: undo both and return focus.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const appRoot = document.getElementById('app-root');
    const hadInert = appRoot?.hasAttribute('inert') ?? false;
    appRoot?.setAttribute('inert', '');

    const dialog = dialogRef.current;
    if (dialog) {
      const first = focusableIn(dialog)[0];
      (first ?? dialog).focus();
    }

    return () => {
      if (appRoot && !hadInert) appRoot.removeAttribute('inert');
      if (opener && opener.isConnected) {
        opener.focus();
      } else {
        const heading = document.querySelector<HTMLElement>(COMMAND_BAR_HEADING_SELECTOR);
        if (heading) {
          if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
          heading.focus();
        }
      }
    };
  }, []);

  // Escape and focus trap.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const dialog = dialogRef.current;
      if (!dialog) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        if (!blockRef.current) closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const items = focusableIn(dialog);
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0] as HTMLElement;
      const last = items[items.length - 1] as HTMLElement;
      const active = document.activeElement;
      if (!dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  const root = document.getElementById('modal-root');
  if (!root) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-obsidian/80 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="flex max-h-full w-full max-w-lg flex-col overflow-auto border border-hairline bg-surface text-bone"
      >
        <div className="flex items-center justify-between gap-4 border-b border-hairline px-4 py-3">
          <h2 id={titleId} className="text-base font-semibold">
            {title}
          </h2>
          <button
            type="button"
            aria-label={`Close ${title}`}
            disabled={blockClose}
            onClick={() => {
              if (!blockClose) onRequestClose();
            }}
            className="border border-hairline px-2 py-1 text-sm text-muted hover:text-bone disabled:opacity-50"
          >
            Close
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>,
    root,
  );
}
