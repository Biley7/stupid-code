// Render-less. Owns the loading effects: repos on mount, snapshot and vitals when the
// selected repository changes. Panels read the DataStore and never start these loads.
import { useRepos } from '../../data/useRepos';
import { useSnapshot } from '../../data/useSnapshot';
import { useVitals } from '../../data/useVitals';

export function DataLoader(): null {
  useRepos({ autoload: true });
  useSnapshot({ autoload: true });
  useVitals({ autoload: true });
  return null;
}
