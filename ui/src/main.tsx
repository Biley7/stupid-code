import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/index.css';

const VISUAL_MODE_KEY = 'stupid-code.visual-mode';

type VisualMode = 'Autopsy' | 'Lab';

function restoreVisualMode(): VisualMode {
  try {
    const stored = window.localStorage.getItem(VISUAL_MODE_KEY);
    if (stored === 'Autopsy' || stored === 'Lab') return stored;
  } catch {
    // Storage unavailable: fall back to the default.
  }
  return 'Autopsy';
}

// Set the attribute before the first render so no frame shows the wrong mode.
const mode = restoreVisualMode();
document.documentElement.dataset.visualMode = mode === 'Lab' ? 'lab' : 'autopsy';

const container = document.getElementById('app-root');
if (container) {
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
