import { readFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import {
  deleteAllDocuments,
  loadTruth,
  samplePath,
  SCREENSHOT_DIR,
  uploadViaApi,
  waitForReview,
} from './helpers';

const SAMPLE = 'invoice_02_modern_se.pdf';
const HEADER = [
  'vendor_name',
  'vendor_vat_id',
  'invoice_number',
  'invoice_date',
  'due_date',
  'currency',
  'subtotal',
  'vat_total',
  'total',
  'iban',
  'payment_reference',
];

function parseCsv(text: string): Record<string, string>[] {
  const [header, ...rows] = text.trim().split('\n');
  const keys = header!.split(',');
  return rows.map((row) => Object.fromEntries(row.split(',').map((v, i) => [keys[i]!, v])));
}

test.beforeAll(async ({ request }) => {
  await deleteAllDocuments(request);
});

test('upload → review → correct low-confidence field → approve → export CSV', async ({ page }) => {
  const truth = loadTruth(SAMPLE);

  await page.goto('/');
  await expect(page.getByRole('heading', { name: /turn invoices into clean/i })).toBeVisible();
  await page.getByLabel('Upload invoice files').setInputFiles(samplePath(SAMPLE));
  const row = page.getByTestId('upload-row').filter({ hasText: SAMPLE });
  await row.getByRole('link', { name: /review/i }).click();
  await waitForReview(page);
  await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();

  // Fix every flagged header field whose value differs from ground truth.
  const flagged = page.locator('input[data-attention="true"]');
  await expect(flagged.first()).toBeVisible();
  const names = await flagged.evaluateAll((els) => els.map((e) => e.getAttribute('name') ?? ''));
  const wrong: string[] = [];
  for (const name of names.filter((n) => HEADER.includes(n))) {
    const input = page.locator(`input[name="${name}"]`);
    const expected = String(truth[name]?.value ?? '');
    if ((await input.inputValue()) !== expected) {
      wrong.push(name);
      await input.click();
      await expect(page.getByTestId('bbox-highlight')).toBeVisible();
      await input.fill(expected);
      await input.press('Enter');
      await expect(input).toHaveAttribute('data-band', 'verified');
    }
  }
  expect(wrong.length, 'the mock provider should have corrupted a field').toBeGreaterThan(0);

  // README screenshot: highlight the corrected field without scrolling the page away from the header
  await page.locator(`input[name="${wrong[0]}"]`).evaluate((el) => {
    (el as HTMLInputElement).focus({ preventScroll: true });
  });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
  });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'review.png') });

  await page.keyboard.press('Control+Enter');
  await expect(page.getByText('Approved — fields are locked.')).toBeVisible();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /export csv/i }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^invoicelens-.*\.csv$/);
  const rows = parseCsv(readFileSync(await download.path(), 'utf8'));
  expect(rows).toHaveLength(1);
  const exported = rows[0]!;
  expect(exported.status).toBe('approved');
  expect(exported.invoice_number).toBe(truth.invoice_number!.value);
  for (const name of wrong) expect(exported[name]).toBe(String(truth[name]!.value));
  expect(Number(exported.total)).toBeCloseTo(Number(truth.total!.value), 2);
});

test('corrections are reused for the next invoice from the same vendor', async ({
  page,
  request,
}) => {
  // The previous test corrected this vendor's OCR error; the same mistake is now fixed automatically.
  const truth = loadTruth(SAMPLE);
  const id = await uploadViaApi(request, SAMPLE);
  await page.goto(`/documents/${id}`);
  await waitForReview(page);
  const ref = page.locator('input[name="payment_reference"]');
  await expect(ref).toHaveValue(String(truth.payment_reference!.value));
  await expect(page.locator('[data-field="payment_reference"]')).toContainText('97%');
});

test('documents list, dark mode and settings screenshots', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByRole('heading', { name: 'Documents' })).toBeVisible();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'documents.png') });

  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.locator('tbody tr').first().click();
  await waitForReview(page);
  await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
  await page
    .locator('input[data-attention="true"]')
    .first()
    .evaluate((el) => {
      (el as HTMLInputElement).focus({ preventScroll: true });
    });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
  });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'review-dark.png') });
  await page.getByRole('button', { name: 'Switch to light mode' }).click();

  await page.goto('/');
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'upload.png') });
});
