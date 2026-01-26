import { test, expect } from '@playwright/test';

/**
 * Smoke tests - verify basic stack health
 */
test.describe('Stack Health', () => {
  test('Bridge UI loads', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Zephyr/i);
  });

  test('Bridge API responds', async ({ request }) => {
    const response = await request.get('http://localhost:7051/status');
    expect(response.ok()).toBeTruthy();
  });

  test('Admin console accessible (dev mode)', async ({ page }) => {
    await page.goto('/admin');
    // Should not redirect away if NEXT_PUBLIC_ENABLE_DEV_CONTROLS=1
    await expect(page.url()).toContain('/admin');
  });
});

/**
 * Placeholder tests for wrap/unwrap flows
 * These will need wallet connection mocking
 */
test.describe.skip('Wrap Flow', () => {
  test('can view wrap page', async ({ page }) => {
    await page.goto('/wrap');
    // TODO: Add assertions
  });

  test('can connect wallet', async ({ page }) => {
    // TODO: Implement wallet connection mocking
    // This will require either:
    // 1. Synpress for MetaMask automation
    // 2. Mock provider injection
    // 3. Frame wallet with system-wide provider
  });

  test('can initiate wrap', async ({ page }) => {
    // TODO: Implement after wallet connection
  });
});

test.describe.skip('Unwrap Flow', () => {
  test('can view unwrap page', async ({ page }) => {
    await page.goto('/unwrap');
    // TODO: Add assertions
  });

  test('can initiate unwrap', async ({ page }) => {
    // TODO: Implement after wallet connection
  });
});
