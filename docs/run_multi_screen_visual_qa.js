const { chromium } = require('playwright');
const path = require('path');

const output = path.join(process.cwd(), 'docs', 'screenshots');
const baseUrl = 'http://127.0.0.1:8091';

async function assertWidgetsFit(page, label) {
  const audit = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('.grid-stack-item-content > .card, .grid-stack-item-content > .chart-card'));
    return cards.map((card) => ({
      label: card.querySelector('.card-label')?.textContent?.trim() || 'Unnamed widget',
      isCard: card.classList.contains('card'),
      overflow: getComputedStyle(card).overflow,
      scrollHeight: card.scrollHeight,
      clientHeight: card.clientHeight,
      scrollWidth: card.scrollWidth,
      clientWidth: card.clientWidth,
    }));
  });
  const issues = audit.filter((item) => (item.isCard && item.overflow !== 'hidden') || item.scrollHeight > item.clientHeight + 1 || item.scrollWidth > item.clientWidth + 1);
  if (issues.length) throw new Error(label + ': ' + JSON.stringify(issues));
  console.log(label + ': ' + audit.length + ' widgets fit without scrollbars');
}

async function selectScreen(page, name) {
  await page.getByRole('button', { name, exact: true }).click();
  await page.waitForFunction((expected) => {
    const active = document.querySelector('.screen-tab.active');
    return active && active.textContent.trim() === expected;
  }, name);
  await page.waitForFunction(() => Array.from(document.querySelectorAll('.grid-stack-item-content > .card, .grid-stack-item-content > .chart-card')).every((card) => card.clientHeight >= 160 && card.clientWidth > 100));
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } });
  const page = await context.newPage();
  await page.goto(baseUrl + '/', { waitUntil: 'networkidle' });
  await page.waitForSelector('.grid-stack-item-content > .card');

  await assertWidgetsFit(page, 'Screen 1');
  await page.screenshot({ path: path.join(output, 'multi_screen_default_screen_1.png'), fullPage: true });

  await selectScreen(page, 'Analytics');
  await assertWidgetsFit(page, 'Screen 2');
  await page.screenshot({ path: path.join(output, 'multi_screen_default_screen_2.png'), fullPage: true });

  await selectScreen(page, 'Trends');
  await page.waitForSelector('.chart-card canvas');
  await assertWidgetsFit(page, 'Screen 3');
  await page.screenshot({ path: path.join(output, 'multi_screen_default_screen_3.png'), fullPage: true });

  await selectScreen(page, 'Activity & Recovery');
  await page.waitForSelector('.chart-card canvas');
  await assertWidgetsFit(page, 'Screen 4');
  await page.screenshot({ path: path.join(output, 'multi_screen_default_screen_4.png'), fullPage: true });

  await selectScreen(page, 'Lifts & Body');
  await page.getByRole('button', { name: 'Edit dashboard', exact: true }).click();
  await page.waitForSelector('.screen-name-input');
  await page.screenshot({ path: path.join(output, 'multi_screen_edit_tabs.png'), fullPage: true });

  const screenInputs = page.locator('.screen-name-input');
  await screenInputs.nth(0).fill('Lifts & Body Verified');
  await page.locator('.tray-add[data-widget-id="score.dots"]').click();
  await page.getByRole('button', { name: 'Add screen', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('.screen-name-input').length === 5);
  await page.locator('.screen-name-input').nth(4).fill('Competition view');
  await page.locator('.tray-add[data-widget-id="lift.squat"]').click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.waitForSelector('#edit-dashboard-btn:not([hidden])');

  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.grid-stack-item-content > .card');
  const saved = await page.evaluate(async () => fetch('/api/dashboard/layout').then((response) => response.json()));
  if (saved.screens.length !== 5 || saved.screens[0].name !== 'Lifts & Body Verified') {
    throw new Error('Saved screens did not persist as expected');
  }
  if (!saved.screens[0].widgets.some((widget) => widget.id === 'score.dots')) {
    throw new Error('Edited widget did not persist');
  }
  if (saved.screens[4].name !== 'Competition view' || !saved.screens[4].widgets.some((widget) => widget.id === 'lift.squat')) {
    throw new Error('New screen did not persist');
  }
  console.log('Screen layout, rename, and new screen persisted after reload');

  await page.goto(baseUrl + '/settings', { waitUntil: 'networkidle' });
  await page.getByLabel('Height (cm)').isVisible();
  await page.getByLabel('Rotation interval (seconds)').isVisible();
  await page.screenshot({ path: path.join(output, 'multi_screen_settings.png'), fullPage: true });

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
