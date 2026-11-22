// Dismissible notices (deep-link outcomes). The list is local UI state, not part of
// the App_Store or DataStore. Text is rendered as plain text.
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { PlainText } from '../shared/PlainText';

export interface Notice {
  id: string;
  text: string;
}

interface NoticeApi {
  notices: Notice[];
  /** Adds a notice and returns its id. */
  pushNotice: (text: string) => string;
  dismissNotice: (id: string) => void;
}

const NoticeContext = createContext<NoticeApi | null>(null);

export function NoticeProvider({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const counter = useRef(0);
  const pushNotice = useCallback((text: string) => {
    counter.current += 1;
    const id = `notice-${counter.current}`;
    setNotices((list) => [...list, { id, text }]);
    return id;
  }, []);
  const dismissNotice = useCallback((id: string) => {
    setNotices((list) => list.filter((n) => n.id !== id));
  }, []);
  const value = useMemo(() => ({ notices, pushNotice, dismissNotice }), [notices, pushNotice, dismissNotice]);
  return <NoticeContext.Provider value={value}>{children}</NoticeContext.Provider>;
}

export function useNotices(): NoticeApi {
  const api = useContext(NoticeContext);
  if (api === null) throw new Error('useNotices must be used inside <NoticeProvider>');
  return api;
}

export function NoticeBar() {
  const { notices, dismissNotice } = useNotices();
  if (notices.length === 0) return null;
  return (
    <div role="status" aria-label="Notices" className="border-b border-hairline bg-surface">
      <ul className="m-0 list-none p-0">
        {notices.map((notice) => (
          <li key={notice.id} className="flex items-center justify-between gap-3 px-3 py-1 text-sm">
            <PlainText text={notice.text} className="text-bone" />
            <button
              type="button"
              onClick={() => dismissNotice(notice.id)}
              aria-label={`Dismiss notice: ${notice.text}`}
              className="border border-hairline px-2 py-0.5 text-muted"
            >
              Dismiss
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
