import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { createElement, useEffect, type ReactNode } from 'react';
import { toast } from 'sonner';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { resetMockDb } from '@/mocks/handlers';
import { server } from '@/mocks/server';

// react-pdf needs canvas + a worker; replace it with a light stand-in for jsdom.
vi.mock('react-pdf', () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({
    children,
    onLoadSuccess,
  }: {
    children: ReactNode;
    onLoadSuccess?: (pdf: { numPages: number }) => void;
  }) => {
    useEffect(() => {
      onLoadSuccess?.({ numPages: 2 });
    }, [onLoadSuccess]);
    return createElement('div', { 'data-testid': 'pdf-document' }, children);
  },
  Page: ({ pageNumber }: { pageNumber: number }) =>
    createElement('div', { 'data-testid': 'pdf-page' }, `Page ${pageNumber}`),
}));

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
Object.defineProperty(globalThis, 'ResizeObserver', { value: ResizeObserverStub, writable: true });

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

URL.createObjectURL = vi.fn(() => 'blob:mock');
URL.revokeObjectURL = vi.fn();
Element.prototype.scrollIntoView = vi.fn();

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});
afterEach(() => {
  toast.dismiss();
  cleanup();
  server.resetHandlers();
  resetMockDb();
  localStorage.clear();
});
afterAll(() => {
  server.close();
});
