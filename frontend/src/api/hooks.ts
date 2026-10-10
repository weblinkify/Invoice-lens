import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from './client';
import type {
  CorrectionRequest,
  DocumentListQuery,
  DocumentOut,
  Extraction,
  WebhookEndpointIn,
} from './types';
import { isProcessing } from './types';

export const keys = {
  documents: ['documents'] as const,
  documentList: (q: DocumentListQuery) => ['documents', 'list', q] as const,
  document: (id: string) => ['documents', 'detail', id] as const,
  extraction: (id: string) => ['documents', 'extraction', id] as const,
  settings: ['settings'] as const,
  samples: ['samples'] as const,
  webhooks: ['webhooks'] as const,
  deliveries: (id: number) => ['webhooks', id, 'deliveries'] as const,
  accuracy: ['accuracy'] as const,
};

const POLL_MS = 1000;

export function useDocuments(query: DocumentListQuery) {
  return useQuery({
    queryKey: keys.documentList(query),
    queryFn: async () => unwrap(await api.GET('/api/v1/documents', { params: { query } })),
    placeholderData: (prev) => prev,
    refetchInterval: (q) =>
      q.state.data?.items.some((d) => isProcessing(d.status)) ? POLL_MS : false,
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: keys.document(id),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/documents/{document_id}', {
          params: { path: { document_id: id } },
        }),
      ),
    refetchInterval: (q) => (q.state.data && isProcessing(q.state.data.status) ? POLL_MS : false),
  });
}

export function useExtraction(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.extraction(id),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/documents/{document_id}/extraction', {
          params: { path: { document_id: id } },
        }),
      ),
  });
}

export function useCorrectFields(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CorrectionRequest) =>
      unwrap(
        await api.PATCH('/api/v1/documents/{document_id}/extraction', {
          params: { path: { document_id: id } },
          body,
        }),
      ),
    onSuccess: (data: Extraction) => {
      qc.setQueryData(keys.extraction(id), data);
      void qc.invalidateQueries({ queryKey: keys.document(id) });
    },
  });
}

export function useApprove(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/documents/{document_id}/approve', {
          params: { path: { document_id: id } },
        }),
      ),
    onSuccess: (doc: DocumentOut) => {
      qc.setQueryData(keys.document(id), doc);
      void qc.invalidateQueries({ queryKey: keys.documents });
    },
  });
}

export function useReprocess(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/documents/{document_id}/reprocess', {
          params: { path: { document_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.documents }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      unwrap(
        await api.DELETE('/api/v1/documents/{document_id}', {
          params: { path: { document_id: id } },
        }),
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.documents }),
  });
}

export function useSamples() {
  return useQuery({
    queryKey: keys.samples,
    queryFn: async () => unwrap(await api.GET('/api/v1/samples')),
    staleTime: Infinity,
  });
}

export function useLoadSample() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(await api.POST('/api/v1/samples/{name}', { params: { path: { name } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.documents }),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: async () => unwrap(await api.GET('/api/v1/settings')),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (confidence_threshold: number) =>
      unwrap(await api.PUT('/api/v1/settings', { body: { confidence_threshold } })),
    onSuccess: (data) => {
      qc.setQueryData(keys.settings, data);
      void qc.invalidateQueries({ queryKey: keys.documents });
    },
  });
}

export function useWebhooks() {
  return useQuery({
    queryKey: keys.webhooks,
    queryFn: async () => unwrap(await api.GET('/api/v1/webhook-endpoints')),
  });
}

export function useCreateWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: WebhookEndpointIn) =>
      unwrap(await api.POST('/api/v1/webhook-endpoints', { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.webhooks }),
  });
}

export function useDeleteWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      unwrap(
        await api.DELETE('/api/v1/webhook-endpoints/{endpoint_id}', {
          params: { path: { endpoint_id: id } },
        }),
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.webhooks }),
  });
}

export function useToggleWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, active }: { id: number; active: boolean }) =>
      unwrap(
        await api.PATCH('/api/v1/webhook-endpoints/{endpoint_id}', {
          params: { path: { endpoint_id: id } },
          body: { active },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.webhooks }),
  });
}

export function useTestWebhook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.POST('/api/v1/webhook-endpoints/{endpoint_id}/test', {
          params: { path: { endpoint_id: id } },
        }),
      ),
    onSuccess: (_d, id) => qc.invalidateQueries({ queryKey: keys.deliveries(id) }),
  });
}

export function useDeliveries(id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.deliveries(id),
    enabled,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/webhook-endpoints/{endpoint_id}/deliveries', {
          params: { path: { endpoint_id: id } },
        }),
      ),
  });
}

export function useAccuracy(enabled: boolean) {
  return useQuery({
    queryKey: keys.accuracy,
    enabled,
    staleTime: Infinity,
    queryFn: async () => unwrap(await api.GET('/api/v1/metrics/accuracy')),
  });
}
