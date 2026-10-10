import { QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { ReactNode } from 'react';
import { mockDb } from '@/mocks/handlers';
import { server } from '@/mocks/server';
import { testQueryClient } from '@/test/utils';
import { ApiError } from './client';
import {
  useApprove,
  useCorrectFields,
  useCreateWebhook,
  useDeleteDocument,
  useDeleteWebhook,
  useDocument,
  useDocuments,
  useExtraction,
  useLoadSample,
  useReprocess,
  useSamples,
  useSettings,
  useTestWebhook,
  useToggleWebhook,
  useUpdateSettings,
  useWebhooks,
} from './hooks';

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={testQueryClient()}>{children}</QueryClientProvider>;
}

describe('query hooks', () => {
  it('lists documents with filters', async () => {
    const { result } = renderHook(
      () => useDocuments({ page: 1, page_size: 20, needs_review: true }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.total).toBe(3);
    expect(result.current.data?.items[0]?.vendor_name).toBeTruthy();
  });

  it('loads a document and its extraction', async () => {
    const { result } = renderHook(
      () => ({ doc: useDocument('doc-1'), ext: useExtraction('doc-1', true) }),
      {
        wrapper,
      },
    );
    await waitFor(() => {
      expect(result.current.ext.isSuccess).toBe(true);
    });
    expect(result.current.doc.data?.filename).toBe('invoice_02_modern_se.pdf');
    expect(result.current.ext.data?.data.payment_reference.confidence).toBeLessThan(0.8);
  });

  it('surfaces problem+json errors as ApiError', async () => {
    const { result } = renderHook(() => useDocument('missing'), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).status).toBe(404);
    expect(result.current.error?.message).toBe('Document missing was not found');
  });

  it('falls back to a generic message when the error is not a problem', async () => {
    server.use(http.get('*/api/v1/settings', () => new HttpResponse('nope', { status: 502 })));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error?.message).toMatch(/502/);
  });
});

describe('mutation hooks', () => {
  it('corrects a field with the right PATCH body', async () => {
    let body: unknown;
    server.events.on('request:start', ({ request }) => {
      if (request.method === 'PATCH') {
        void request
          .clone()
          .json()
          .then((b: unknown) => {
            body = b;
          });
      }
    });
    const { result } = renderHook(() => useCorrectFields('doc-1'), { wrapper });
    const data = await result.current.mutateAsync({
      corrections: [{ field: 'payment_reference', value: 'RF6336016105500875' }],
    });
    expect(body).toEqual({
      corrections: [{ field: 'payment_reference', value: 'RF6336016105500875' }],
    });
    expect(data.data.payment_reference.value).toBe('RF6336016105500875');
    expect(data.corrected_fields).toContain('payment_reference');
    server.events.removeAllListeners();
  });

  it('approves, reprocesses and deletes', async () => {
    const { result } = renderHook(
      () => ({
        approve: useApprove('doc-2'),
        reprocess: useReprocess('doc-3'),
        del: useDeleteDocument(),
      }),
      { wrapper },
    );
    expect((await result.current.approve.mutateAsync()).status).toBe('approved');
    await expect(result.current.approve.mutateAsync()).rejects.toThrow('already approved');
    await result.current.reprocess.mutateAsync();
    expect(mockDb().documents.get('doc-3')?.status).toBe('processing');
    await result.current.del.mutateAsync('doc-3');
    expect(mockDb().documents.has('doc-3')).toBe(false);
  });

  it('manages settings and samples', async () => {
    const { result } = renderHook(
      () => ({ update: useUpdateSettings(), samples: useSamples(), load: useLoadSample() }),
      { wrapper },
    );
    expect((await result.current.update.mutateAsync(0.5)).confidence_threshold).toBe(0.5);
    await waitFor(() => {
      expect(result.current.samples.data).toHaveLength(2);
    });
    const res = await result.current.load.mutateAsync('invoice_02_modern_se.pdf');
    expect(res.id).toMatch(/^new-/);
  });

  it('manages webhook endpoints', async () => {
    const { result } = renderHook(
      () => ({
        list: useWebhooks(),
        create: useCreateWebhook(),
        toggle: useToggleWebhook(),
        test: useTestWebhook(),
        del: useDeleteWebhook(),
      }),
      { wrapper },
    );
    const ep = await result.current.create.mutateAsync({
      url: 'https://erp.test/h',
      secret: 'secret-1234',
      active: true,
    });
    expect(ep.secret_hint).toBe('••••1234');
    expect((await result.current.toggle.mutateAsync({ id: ep.id, active: false })).active).toBe(
      false,
    );
    expect((await result.current.test.mutateAsync(ep.id)).status).toBe('succeeded');
    await result.current.del.mutateAsync(ep.id);
    await waitFor(() => {
      expect(result.current.list.data).toEqual([]);
    });
  });
});
