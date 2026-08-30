import { test, expect } from '@playwright/test';
test('closed dashboard run path', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText(/Research runs/i).first()).toBeVisible();
  await page.getByRole('link', { name: /New research/i }).first().click();
  await expect(page.getByRole('heading', { name: /What should we look at next/i })).toBeVisible();
});

