import { ApiProvider } from './api/context';
import { AutoSelectRepo } from './components/shell/AutoSelectRepo';
import { DataLoader } from './components/shell/DataLoader';
import { DeepLinkController } from './components/shell/DeepLinkController';
import { NoticeProvider } from './components/shell/NoticeBar';
import { Shell } from './components/shell/Shell';
import { StoreProvider } from './state/store';

export default function App() {
  return (
    <ApiProvider>
      <StoreProvider>
        <NoticeProvider>
          <DataLoader />
          <DeepLinkController />
          <AutoSelectRepo />
          <Shell />
        </NoticeProvider>
      </StoreProvider>
    </ApiProvider>
  );
}
