import process from 'node:process'

import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests of Mira Desk against a real Mira Core (the test server runs them through
 * tests/integration/desk/run.sh, which creates the tenant and the admin and passes them in).
 * MIRA_DESK_URL=https://127.0.0.1 tests the installed site (nginx, ADR 0012: its TLS, headers
 * and content security policy). Without it, `vite preview` serves the build and forwards /api.
 */
const installed = process.env.MIRA_DESK_URL
export default defineConfig({
  testDir: './e2e',
  timeout: 60 * 1000,
  expect: { timeout: 10_000 },
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1, // one shared tenant
  reporter: [['list']],
  use: {
    baseURL: installed ?? 'http://127.0.0.1:4173',
    // the installer's certificate is self-signed until task 2.6
    ignoreHTTPSErrors: !!installed,
    trace: 'retain-on-failure',
    headless: true,
    locale: 'en-US',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: installed
    ? undefined
    : {
        command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
        url: 'http://127.0.0.1:4173',
        reuseExistingServer: true,
      },
})
