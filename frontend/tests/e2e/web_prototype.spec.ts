import { test, expect } from '@playwright/test';
import path from 'node:path';

const mockDashboard = {
  metrics: [
    { date: '2026-08-17', hrv: 42, sleep: 74, readiness: 80, riskScore: 40 },
    { date: '2026-08-18', hrv: 39, sleep: 68, readiness: 73, riskScore: 61 },
  ],
  alerts: [],
  currentRisk: 61,
  lastSync: '2026-08-18',
  summary: { date: '2026-08-18', summary: 'Synthetic summary for UI contract test.' },
  modelPrediction: {
    day: '2026-08-18',
    prediction: 'ELEVATED',
    p_elevated: 0.73,
    model: 'logreg_stress',
    explanation: [
      {
        feature: 'hrv_balance',
        raw: 42,
        z: -1.22,
        coef: -0.31,
        contribution: 0.38,
        direction: 'toward_elevated',
      },
    ],
  },
};

test('web prototype form submits evening check-in', async ({ page }) => {
  await page.route('**/api/dashboard', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockDashboard),
    })
  );

  await page.route('http://localhost:8001/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Logged' }),
    })
  );

  await page.goto('/');

  await expect(page.getByTestId('ios-checkin-form')).toBeVisible();
  await expect(page.getByTestId('ml-signal-card')).toBeVisible();

  await page.selectOption('#entry-session', 'evening');

  await page.selectOption('#energy', '3');
  await page.selectOption('#new_projects', 'Yes');
  await page.selectOption('#effortful', 'No');
  await page.selectOption('#concentration', '3');
  await page.selectOption('#mood', '3');
  await page.selectOption('#irritable', 'No');
  await page.selectOption('#impulsive', 'No');
  await page.selectOption('#withdrew', 'No');
  await page.selectOption('#alcohol', 'None');
  await page.selectOption('#illness', 'No');
  await page.selectOption('#travel', 'No');
  await page.selectOption('#life_stress', 'No');
  await page.selectOption('#classification_day', 'Euthymic');

  await page.fill('#notes', 'Playwright web prototype contract run.');
  await page.getByTestId('submit-checkin').click();

  await expect(page.getByTestId('form-status')).toHaveText('Saved successfully');

  await page.screenshot({ path: path.join(test.info().outputDir, 'web-prototype-final.png'), fullPage: true });
});
