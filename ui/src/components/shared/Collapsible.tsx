// Disclosure section: a header button that shows or hides its content. The content is
// unmounted while collapsed, so its controls leave the tab order.
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';

export interface CollapsibleProps {
  title: string;
  /** Short value shown at the right of the header, such as an item count. */
  badge?: ReactNode;
  defaultOpen?: boolean;
  /** Accessible name of the section landmark. Defaults to the title. */
  ariaLabel?: string;
  headingLevel?: 'h2' | 'h3';
  className?: string;
  children: ReactNode;
}

export function Collapsible({
  title,
  badge,
  defaultOpen = false,
  ariaLabel,
  headingLevel = 'h3',
  className,
  children,
}: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const Heading = headingLevel;
  const Icon = open ? ChevronDown : ChevronRight;
  return (
    <section aria-label={ariaLabel ?? title} className={`min-w-0 border-t border-hairline ${className ?? ''}`}>
      <Heading className="m-0">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-muted hover:text-bone"
        >
          <Icon aria-hidden="true" size={13} className="shrink-0" />
          <span className="min-w-0 flex-1 truncate">{title}</span>
          {badge !== undefined ? (
            <span className="shrink-0 text-[11px] font-medium normal-case tracking-normal tabular-nums text-muted">
              {badge}
            </span>
          ) : null}
        </button>
      </Heading>
      {open ? (
        <div id={panelId} className="min-w-0 px-2 pb-3">
          {children}
        </div>
      ) : null}
    </section>
  );
}
