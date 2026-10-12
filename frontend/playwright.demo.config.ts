import { defineConfig, devices } from '@playwright/test';

/**
 * Smoke tests for the static, backend-free demo (MSW in the browser), as deployed to Vercel.
 * By default they build the demo and serve it with `vite preview`; set DEMO_URL to test a live deployment.
 */
const PORT = 4173;
const remote = process.env.DEMO_URL;

export default defineConfig({
  testDir: './e2e-demo',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: remote ?? `http://localhost:${PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: remote
    ? undefined
    : {
        command: `npm run build:demo && npx vite preview --mode mock --port ${PORT} --strictPort`,
        url: `http://localhost:${PORT}`,
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
      },
});
