import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './index.css';

async function enableMocks(): Promise<void> {
  if (import.meta.env.VITE_API_MOCK !== 'true') return;
  const { worker } = await import('./mocks/browser');
  await worker.start({ onUnhandledRequest: 'bypass' });
}

void enableMocks().then(() => {
  const root = document.getElementById('root');
  if (!root) throw new Error('#root element missing');
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
