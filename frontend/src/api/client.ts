import createClient from 'openapi-fetch';
import type { paths } from './schema';
import type { Problem } from './types';

/** Empty means same origin (Vite proxy in dev, nginx in Docker). Absolute so it also works in Node tests. */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '') || globalThis.location.origin;

// Late-bound fetch so test interceptors (MSW) patched after import still apply.
export const api = createClient<paths>({
  baseUrl: API_BASE,
  fetch: (request) => globalThis.fetch(request),
});

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;

  constructor(status: number, problem: Problem | null, fallback = 'Request failed') {
    super(problem?.detail ?? fallback);
    this.name = 'ApiError';
    this.status = status;
    this.problem = problem;
  }
}

function isProblem(value: unknown): value is Problem {
  return typeof value === 'object' && value !== null && 'status' in value && 'detail' in value;
}

/** Unwrap an openapi-fetch result: return data or throw an ApiError carrying the problem. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw new ApiError(
      result.response.status,
      isProblem(result.error) ? result.error : null,
      `Request failed with ${result.response.status}`,
    );
  }
  return result.data as T;
}

export function fileUrl(documentId: string): string {
  return `${API_BASE}/api/v1/documents/${encodeURIComponent(documentId)}/file`;
}

/** Upload with progress (fetch has no upload progress, so this uses XHR). */
export function uploadWithProgress(
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<{ id: string; status: string; status_url: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/api/v1/documents`);
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      const body: unknown = xhr.response;
      if (xhr.status === 202 && typeof body === 'object' && body !== null && 'id' in body) {
        onProgress(1);
        resolve(body as { id: string; status: string; status_url: string });
      } else {
        reject(new ApiError(xhr.status, isProblem(body) ? body : null, 'Upload failed'));
      }
    };
    xhr.onerror = () => {
      reject(new ApiError(0, null, 'Network error while uploading'));
    };
    signal?.addEventListener('abort', () => {
      xhr.abort();
    });
    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

/** Download an export and hand it to the browser as a file. */
export async function downloadExport(format: 'csv' | 'xlsx', ids?: string[]): Promise<string> {
  const params = new URLSearchParams({ format });
  if (ids?.length) params.set('ids', ids.join(','));
  const res = await fetch(`${API_BASE}/api/v1/exports?${params.toString()}`);
  if (!res.ok) {
    let problem: Problem | null = null;
    try {
      const body: unknown = await res.json();
      problem = isProblem(body) ? body : null;
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, problem, 'Export failed');
  }
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `invoicelens-export.${format}`;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return filename;
}
