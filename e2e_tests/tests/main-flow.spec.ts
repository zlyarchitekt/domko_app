import { test, expect } from '@playwright/test';

test('has title', async ({ page }) => {
  await page.goto('/');

  // Upewniamy się, że aplikacja startuje pomyślnie
  await expect(page).toHaveTitle(/DOMKO_APP|DOMKO/);
});

test('sidebar renders correctly', async ({ page }) => {
  await page.goto('/');

  // Oczekujemy, że z renderu React ujrzymy sidebar
  const sidebarHeading = page.locator('text=DOMKO_APP').first();
  await expect(sidebarHeading).toBeVisible();

  // Oczekujemy zakładek 
  await expect(page.locator('text=Słońce')).toBeVisible();
  await expect(page.locator('text=Optymalizacja')).toBeVisible();
});
