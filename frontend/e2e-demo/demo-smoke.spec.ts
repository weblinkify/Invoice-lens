import { expect, test } from '@playwright/test';

test('static demo: sample invoice → review with PDF preview → approve', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (err) => errors.push(err.message));

  await page.goto('/');
  await expect(page.getByRole('heading', { name: /turn invoices into clean/i })).toBeVisible();
  await page.getByRole('button', { name: /try with sample invoice/i }).click();

  await expect(page).toHaveURL(/\/documents\/[^/]+/);
  await expect(page.locator('.react-pdf__Page canvas')).toBeVisible();
  await expect(page.getByText(/could not load the pdf/i)).toHaveCount(0);

  await page.getByRole('button', { name: /approve/i }).click();
  await expect(page.getByTestId('review-status')).toContainText(/approved/i);
  expect(errors).toEqual([]);
});

test('static demo: deep links are served by the SPA', async ({ page }) => {
  for (const path of ['/documents', '/settings']) {
    const res = await page.goto(path);
    expect(res?.status()).toBe(200);
    await expect(page.getByRole('navigation')).toBeVisible();
  }
});
