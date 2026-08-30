import { test, expect } from '@playwright/test';

test('closed stack submits a run and renders its evidence-backed report', async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Find the signal/i })).toBeVisible();
  await page.getByRole('link', { name: /New research/i }).first().click();
  await page.getByLabel(/Seed topic/i).fill('paper bridge');
  await page.getByRole('button', { name: /Run research/i }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+$/, { timeout: 60_000 });
  await expect(page.getByText(/fixture demo data/i).first()).toBeVisible();
  await expect(page.getByText(/Evidence records/i)).toBeVisible({ timeout: 60_000 });
  await page.locator('.candidate-card').first().click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+\/niches\/[0-9a-f-]+$/);
  await expect(page.getByText(/Candidate-specific action plan/i)).toBeVisible();
  await expect(page.getByText(/coherent mechanism thesis/i)).toBeVisible();
  await expect(page.getByText(/independent critic/i)).toBeVisible();
  await page.getByRole('link', { name: /View evidence/i }).click();
  await expect(page).toHaveURL(/\/runs\/[0-9a-f-]+\?tab=Evidence$/);
  await expect(page.getByRole('heading', { name: 'Evidence ledger' })).toBeVisible();
  await expect(page.getByText(/research_plan/i).first()).toBeVisible();
  await page.getByRole('tab', { name: 'Niches' }).click();
  await expect(page.getByText(/Ranked opportunities/i)).toBeVisible();
  await page.getByRole('tab', { name: 'Evidence' }).click();
  await expect(page.getByRole('heading', { name: 'Evidence ledger' })).toBeVisible();
  await expect(page.getByText(/research_plan/i).first()).toBeVisible();
});
