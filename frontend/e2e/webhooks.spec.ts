import { createHmac } from 'node:crypto';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import {
  deleteAllWebhooks,
  MOCK_ERP,
  MOCK_ERP_INTERNAL,
  MOCK_ERP_SECRET,
  resetMockErp,
  SCREENSHOT_DIR,
  uploadViaApi,
  waitForReview,
} from './helpers';

interface Received {
  event: string;
  signature: string;
  signature_valid: boolean;
  attempt_number: number;
  raw_body: string;
  payload: { event: string; data: { document: { id: string }; invoice: Record<string, unknown> } };
}
interface ReceivedList {
  count: number;
  forced_failures: number;
  items: Received[];
}

function verify(signature: string, body: string): boolean {
  const parts = Object.fromEntries(
    signature.split(',').map((p) => p.split('=') as [string, string]),
  );
  const expected = createHmac('sha256', MOCK_ERP_SECRET).update(`${parts.t}.${body}`).digest('hex');
  return expected === parts.v1;
}

test.beforeEach(async ({ request }) => {
  await deleteAllWebhooks(request);
  await resetMockErp(request);
});

test.afterAll(async ({ request }) => {
  await deleteAllWebhooks(request);
});

test('configure webhook in settings → approve → mock ERP receives a signed payload', async ({
  page,
  request,
}) => {
  await page.goto('/settings');
  const form = page.getByRole('form', { name: 'Add webhook endpoint' });
  await form.getByLabel('Endpoint URL').fill(`${MOCK_ERP_INTERNAL}/webhooks/invoices`);
  await form.getByLabel('Signing secret').fill(MOCK_ERP_SECRET);
  await form.getByLabel('Description').fill('Mock ERP');
  await form.getByRole('button', { name: /add/i }).click();
  const row = page.getByTestId('webhook-row');
  await expect(row).toContainText('mock-erp:9000');
  await row.getByRole('button', { name: /send test/i }).click();
  await expect(page.getByText('Ping delivered (HTTP 200)')).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'settings.png') });

  const docId = await uploadViaApi(request, 'invoice_03_minimal_de.pdf');
  await page.goto(`/documents/${docId}`);
  await waitForReview(page);
  await page.getByRole('button', { name: /^approve/i }).click();
  await expect(page.getByText('Approved — fields are locked.')).toBeVisible();

  await expect
    .poll(
      async () =>
        (
          (await (
            await request.get(`${MOCK_ERP}/received?event=invoice.approved`)
          ).json()) as ReceivedList
        ).count,
    )
    .toBe(1);
  const received = (await (
    await request.get(`${MOCK_ERP}/received?event=invoice.approved`)
  ).json()) as ReceivedList;
  const item = received.items[0]!;
  expect(item.signature_valid).toBe(true);
  expect(verify(item.signature, item.raw_body)).toBe(true);
  expect(verify(item.signature, item.raw_body + ' ')).toBe(false);
  expect(item.payload.event).toBe('invoice.approved');
  expect(item.payload.data.document.id).toBe(docId);
  expect(item.payload.data.invoice.currency).toBe('EUR');
});

test('retry path: mock ERP fails twice, delivery eventually succeeds', async ({ request }) => {
  const created = await request.post('/api/v1/webhook-endpoints', {
    data: { url: `${MOCK_ERP_INTERNAL}/webhooks/invoices`, secret: MOCK_ERP_SECRET, active: true },
  });
  expect(created.status()).toBe(201);
  const endpoint = (await created.json()) as { id: number };
  expect((await request.post(`${MOCK_ERP}/fail-next?count=2`)).ok()).toBe(true);

  const docId = await uploadViaApi(request, 'invoice_09_minimal_fi.pdf');
  expect((await request.post(`/api/v1/documents/${docId}/approve`)).ok()).toBe(true);

  await expect
    .poll(
      async () =>
        ((await (await request.get(`${MOCK_ERP}/received`)).json()) as ReceivedList).count,
      {
        timeout: 20_000,
      },
    )
    .toBe(1);
  const received = (await (await request.get(`${MOCK_ERP}/received`)).json()) as ReceivedList;
  expect(received.forced_failures).toBe(2);
  expect(received.items[0]!.attempt_number).toBe(3);
  expect(received.items[0]!.payload.data.document.id).toBe(docId);

  await expect
    .poll(async () => {
      const list = (await (
        await request.get(`/api/v1/webhook-endpoints/${endpoint.id}/deliveries`)
      ).json()) as {
        status: string;
        attempts: number;
      }[];
      return list[0] && `${list[0].status}/${list[0].attempts}`;
    })
    .toBe('succeeded/3');
});
