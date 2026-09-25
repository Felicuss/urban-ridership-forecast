import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@fontsource-variable/onest';
import '@fontsource-variable/jetbrains-mono';
import './styles/global.css';
import { App } from './App';

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// статичная заставка из index.html видна, пока грузится JS; дальше её сменяет заставка React
requestAnimationFrame(() => document.getElementById('boot')?.remove());

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
