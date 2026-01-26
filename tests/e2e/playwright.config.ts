import { defineConfig, devices } from '@playwright/test';

/**
 * Zephyr Bridge Stack - E2E Test Configuration
 *
 * Run with: npx playwright test
 * Debug with: npx playwright test --debug
 */
export default defineConfig({
  testDir: './specs',
  fullyParallel: false, // Run tests sequentially for blockchain state consistency
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker for blockchain tests
  reporter: 'html',

  use: {
    // Base URL for the bridge UI
    baseURL: 'http://localhost:7050',

    // Collect trace on failure
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Add Firefox/Safari later if needed
  ],

  // Web server configuration - assumes stack is already running
  // Uncomment to auto-start the bridge
  // webServer: {
  //   command: 'cd ../../zephyr-bridge && npm run dev',
  //   url: 'http://localhost:7050',
  //   reuseExistingServer: !process.env.CI,
  // },
});
