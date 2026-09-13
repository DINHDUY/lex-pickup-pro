import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 40_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5187',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    reducedMotion: 'reduce',
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : [
        {
          command: 'sh ../backend/start-e2e.sh',
          url: 'http://127.0.0.1:8017/api/v1/health',
          timeout: 60_000,
          reuseExistingServer: false,
        },
        {
          command: 'API_PROXY_TARGET=http://127.0.0.1:8017 npm run dev -- --port 5187 --strictPort',
          url: 'http://127.0.0.1:5187',
          timeout: 60_000,
          reuseExistingServer: false,
        },
      ],
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
})
