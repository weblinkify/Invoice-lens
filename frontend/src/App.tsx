import { type QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Toaster } from 'sonner';
import { Layout } from '@/components/Layout';
import { Skeleton } from '@/components/ui/skeleton';
import { createQueryClient } from '@/lib/queryClient';
import { DocumentsPage } from '@/pages/DocumentsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { UploadPage } from '@/pages/UploadPage';

const ReviewPage = lazy(() =>
  import('@/pages/ReviewPage').then((m) => ({ default: m.ReviewPage })),
);

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<UploadPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route
          path="documents/:id"
          element={
            <Suspense fallback={<Skeleton className="h-[70vh] w-full" />}>
              <ReviewPage />
            </Suspense>
          }
        />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export function App({ queryClient = createQueryClient() }: { queryClient?: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
      <Toaster richColors position="bottom-right" closeButton />
    </QueryClientProvider>
  );
}
