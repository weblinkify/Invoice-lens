import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const SAMPLE_DIR = path.resolve(import.meta.dirname, '../../sample-data');
export const MOCK_ERP = process.env.MOCK_ERP_URL ?? 'http://localhost:9000';
/** URL of mock-erp as seen from the backend container. */
export const MOCK_ERP_INTERNAL = process.env.MOCK_ERP_INTERNAL_URL ?? 'http://mock-erp:9000';
export const MOCK_ERP_SECRET = process.env.MOCK_ERP_SECRET ?? 'demo-webhook-secret';
export const SCREENSHOT_DIR = path.resolve(import.meta.dirname, '../../docs/screenshots');

export interface TruthField {
  value: string | number | null;
}
export type Truth = Record<string, TruthField> & { line_items: Record<string, TruthField>[] };

export function samplePath(name: string): string {
  return path.join(SAMPLE_DIR, name);
}

export function loadTruth(name: string): Truth {
  const file = samplePath(name.replace(/\.pdf$/, '.truth.json'));
  return (JSON.parse(readFileSync(file, 'utf8')) as { fields: Truth }).fields;
}

/** Upload through the API (multipart) and wait until extraction finishes. */
export async function uploadViaApi(request: APIRequestContext, name: string): Promise<string> {
  const res = await request.post('/api/v1/documents', {
    multipart: {
      file: { name, mimeType: 'application/pdf', buffer: readFileSync(samplePath(name)) },
    },
  });
  expect(res.status()).toBe(202);
  const { id } = (await res.json()) as { id: string };
  await expect
    .poll(async () => {
      const doc = (await (await request.get(`/api/v1/documents/${id}`)).json()) as {
        status: string;
      };
      return doc.status;
    })
    .toMatch(/needs_review|extracted/);
  return id;
}

export async function deleteAllWebhooks(request: APIRequestContext): Promise<void> {
  const endpoints = (await (await request.get('/api/v1/webhook-endpoints')).json()) as {
    id: number;
  }[];
  for (const ep of endpoints) await request.delete(`/api/v1/webhook-endpoints/${ep.id}`);
}

export async function resetMockErp(request: APIRequestContext): Promise<void> {
  expect((await request.delete(`${MOCK_ERP}/received`)).status()).toBe(204);
}

export async function waitForReview(page: Page): Promise<void> {
  await expect(page.getByRole('form', { name: 'Extracted invoice fields' })).toBeVisible();
}

/** E2E runs must be deterministic: reviewer corrections teach the extractor (few-shot), so
 * start from a clean slate. Deleting documents cascades to their stored corrections. */
export async function deleteAllDocuments(request: APIRequestContext): Promise<void> {
  for (;;) {
    const res = await request.get('/api/v1/documents?page_size=100');
    const { items } = (await res.json()) as { items: { id: string }[] };
    if (!items.length) return;
    for (const doc of items) await request.delete(`/api/v1/documents/${doc.id}`);
  }
}
