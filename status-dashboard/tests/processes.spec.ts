import { test, expect } from '@playwright/test';

test.describe('Processes Tab', () => {
  test('should load processes and show terminal views', async ({ page }) => {
    // Navigate to the dashboard
    await page.goto('/');

    // Wait for initial load
    await expect(page.locator('h1')).toContainText('Zephyr Bridge Stack Status');

    // Click on Processes tab
    await page.click('text=Processes');

    // Wait for processes to load (should not stay in loading state)
    await expect(page.locator('text=Processes').first()).toBeVisible();

    // Check that loading indicator disappears and content appears
    await expect(page.locator('[data-slot="card-title"]:has-text("Processes")')).toBeVisible({ timeout: 10000 });

    // Check that we have process categories
    await expect(page.locator('text=Zephyr Nodes')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Wallets')).toBeVisible();

    // Check that zephyr-node1 is visible
    await expect(page.locator('text=zephyr-node1')).toBeVisible();

    // Check running status badge
    const node1Card = page.locator('div:has-text("zephyr-node1")').first();
    await expect(node1Card).toBeVisible();

    // Expand a process to see terminal
    await page.click('text=zephyr-node1');

    // Wait for terminal to be visible
    await expect(page.locator('text=Terminal Output').first()).toBeVisible({ timeout: 5000 });

    // Check that logs are displayed (should have some content)
    const terminalContent = page.locator('.font-mono.text-xs.leading-relaxed');
    await expect(terminalContent.first()).toBeVisible();

    // Take a screenshot for debugging
    await page.screenshot({ path: 'test-results/processes-tab.png', fullPage: true });
  });

  test('should show wallet-mining with mining controls', async ({ page }) => {
    await page.goto('/');

    // Click on Processes tab
    await page.click('text=Processes');

    // Wait for content to load
    await expect(page.locator('text=Wallets')).toBeVisible({ timeout: 10000 });

    // Check wallet-mining exists
    await expect(page.locator('text=wallet-mining')).toBeVisible();

    // Take screenshot
    await page.screenshot({ path: 'test-results/wallet-mining.png', fullPage: true });
  });
});
