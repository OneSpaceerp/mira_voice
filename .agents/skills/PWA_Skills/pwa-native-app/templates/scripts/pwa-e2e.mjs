// pwa-e2e.mjs — Playwright smoke test: SW controls page, offline reload works, deep link offline, sheet opens,
// plus store screenshots (narrow 1080x1920, wide 1920x1080) into public/screenshots.
// Usage: npm run build && npx vite preview --port 4173 &  node scripts/pwa-e2e.mjs http://localhost:4173
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const url = process.argv[2] ?? 'http://localhost:4173';
const shotsDir = process.argv[3] ?? 'public/screenshots';
const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const fail = (m) => { console.error('FAIL', m); process.exitCode = 1; };
const pass = (m) => console.log('PASS', m);

for (const scheme of ['dark', 'light']) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, colorScheme: scheme });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload({ waitUntil: 'networkidle' });                       // now SW-controlled
  const controlled = await page.evaluate(() => !!navigator.serviceWorker.controller);
  controlled ? pass(`[${scheme}] service worker controls the page`) : fail(`[${scheme}] page not SW-controlled`);
  await page.screenshot({ path: `../shot-mobile-${scheme}.png` });

  if (scheme === 'dark') {
    await ctx.setOffline(true);
    await page.reload({ waitUntil: 'domcontentloaded' });
    (await page.locator('.display').isVisible()) ? pass('offline reload renders app shell') : fail('offline reload failed');
    await page.goto(url + '/some/deep/link', { waitUntil: 'domcontentloaded' });
    (await page.locator('.tabbar').isVisible()) ? pass('offline deep link served by SPA shell') : fail('offline deep link failed');
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    (await page.locator('.net-pill').isVisible()) ? pass('offline pill visible') : fail('offline pill not shown');
    await page.click('.fab');
    await page.waitForTimeout(500);
    (await page.locator('dialog.sheet[open]').isVisible()) ? pass('bottom sheet opens') : fail('sheet did not open');
    await page.screenshot({ path: `../shot-sheet-${scheme}.png` });
    await page.fill('input[name=title]', 'Site photos');
    await page.click('button[value=save]');
    await page.waitForTimeout(600);
    const queued = await page.evaluate(() => new Promise((res) => {
      const r = indexedDB.open('app'); r.onsuccess = () => { const c = r.result.transaction('outbox').objectStore('outbox').count(); c.onsuccess = () => res(c.result); };
    }));
    queued === 1 ? pass('offline write queued in IndexedDB outbox') : fail(`outbox count ${queued}`);
    await ctx.setOffline(false);
  }
  if (errors.length) fail(`[${scheme}] page errors: ${errors.join(' | ')}`);
  await ctx.close();
}

// Store screenshots (manifest "screenshots")
await mkdir(shotsDir, { recursive: true });
const narrow = await browser.newContext({ viewport: { width: 360, height: 640 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, colorScheme: 'dark' });
const np = await narrow.newPage(); await np.goto(url, { waitUntil: 'networkidle' });
await np.evaluate(() => document.querySelector('.toast')?.setAttribute('hidden', ''));
await np.screenshot({ path: `${shotsDir}/narrow-1.png` }); await narrow.close();
const wide = await browser.newContext({ viewport: { width: 1920, height: 1080 }, colorScheme: 'dark' });
const wp = await wide.newPage(); await wp.goto(url, { waitUntil: 'networkidle' });
await wp.evaluate(() => document.querySelector('.toast')?.setAttribute('hidden', ''));
await wp.screenshot({ path: `${shotsDir}/wide-1.png` }); await wide.close();
pass('store screenshots written');
await browser.close();
