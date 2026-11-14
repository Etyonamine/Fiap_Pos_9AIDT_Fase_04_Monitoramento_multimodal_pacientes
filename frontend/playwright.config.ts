import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 0,
  outputDir: './e2e/results',
  globalTeardown: './e2e/global-teardown.cjs',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:4211',
    permissions: ['camera', 'microphone'],
    trace: 'retain-on-failure',
    launchOptions: { args: [
      '--autoplay-policy=no-user-gesture-required',
      '--use-fake-device-for-media-stream',
      '--use-fake-ui-for-media-stream',
    ] },
  },
  webServer: [
    {
      command: 'node e2e/start-backend.cjs',
      url: 'http://127.0.0.1:8011/e2e-health',
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      command: 'npx ng serve --host 127.0.0.1 --port 4211 --proxy-config e2e/proxy.conf.json',
      url: 'http://127.0.0.1:4211',
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
