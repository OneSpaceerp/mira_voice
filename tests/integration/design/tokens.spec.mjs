// Mira Desk styles in Chromium: tokens.css + base.css as Mira Desk loads them.
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect } from '@playwright/test'

const styles = join(dirname(fileURLToPath(import.meta.url)), '../../../desk/src/styles')
const css = ['tokens.css', 'base.css'].map((f) => readFileSync(join(styles, f), 'utf8')).join('\n')

async function page(
  browser,
  { scheme = 'light', theme, lang = 'en', dir = 'ltr', reducedMotion = 'no-preference' } = {},
) {
  const ctx = await browser.newContext({ colorScheme: scheme, reducedMotion })
  const p = await ctx.newPage()
  const attr = theme ? ` data-theme="${theme}"` : ''
  await p.setContent(`<!doctype html><html lang="${lang}" dir="${dir}"${attr}><head><style>${css}</style></head>
    <body><p class="mv-title">Mira</p><span id="num" class="mv-number">+20 100 123 4567</span>
    <button id="b" style="transition: background var(--duration-base) var(--ease-standard)">OK</button></body></html>`)
  return p
}

const bodyBg = (p) => p.evaluate(() => getComputedStyle(document.body).backgroundColor)
const varOf = (p, name) =>
  p.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name)
// what a primitive renders as, to compare against the page background
const primitive = (p, name) =>
  p.evaluate((n) => {
    const el = document.createElement('div')
    el.style.background = `var(${n})`
    document.body.append(el)
    const c = getComputedStyle(el).backgroundColor
    el.remove()
    return c
  }, name)

test('light by default', async ({ browser }) => {
  const p = await page(browser)
  expect(await bodyBg(p)).toBe(await primitive(p, '--neutral-50'))
})

test('follows the OS into dark when no theme is chosen', async ({ browser }) => {
  const p = await page(browser, { scheme: 'dark' })
  expect(await bodyBg(p)).toBe(await primitive(p, '--neutral-900'))
  // Chromium resolves var() inside custom properties: compare resolved values
  expect(await varOf(p, '--ink')).toBe(await varOf(p, '--neutral-50'))
})

test('a chosen light theme beats a dark OS', async ({ browser }) => {
  const p = await page(browser, { scheme: 'dark', theme: 'light' })
  expect(await bodyBg(p)).toBe(await primitive(p, '--neutral-50'))
})

test('a chosen dark theme beats a light OS', async ({ browser }) => {
  const p = await page(browser, { scheme: 'light', theme: 'dark' })
  expect(await bodyBg(p)).toBe(await primitive(p, '--neutral-900'))
})

test('brand red stays the same in both themes', async ({ browser }) => {
  const light = await page(browser)
  const dark = await page(browser, { theme: 'dark' })
  expect(await varOf(light, '--mira-red')).toBe(await varOf(light, '--red-600'))
  expect(await varOf(dark, '--mira-red')).toBe(await varOf(light, '--red-600'))
})

test('Arabic: Arabic font first, phone numbers stay left-to-right', async ({ browser }) => {
  const p = await page(browser, { lang: 'ar', dir: 'rtl' })
  const font = await p.evaluate(() => getComputedStyle(document.body).fontFamily)
  expect(font.split(',')[0].replace(/"/g, '').trim()).toBe('IBM Plex Sans Arabic')
  expect(await p.evaluate(() => getComputedStyle(document.body).direction)).toBe('rtl')
  expect(await p.evaluate(() => getComputedStyle(document.getElementById('num')).direction)).toBe(
    'ltr',
  )
})

test('reduced motion removes transitions', async ({ browser }) => {
  const normal = await page(browser)
  const calm = await page(browser, { reducedMotion: 'reduce' })
  const dur = (p) =>
    p.evaluate(() => getComputedStyle(document.getElementById('b')).transitionDuration)
  expect(await dur(normal)).toBe('0.2s')
  expect(parseFloat(await dur(calm))).toBeLessThan(0.001)
})

test('keyboard focus shows the 2px focus ring', async ({ browser }) => {
  const p = await page(browser)
  await p.keyboard.press('Tab')
  const outline = await p.evaluate(() => {
    const s = getComputedStyle(document.activeElement)
    return {
      width: s.outlineWidth,
      style: s.outlineStyle,
      color: s.outlineColor,
      offset: s.outlineOffset,
    }
  })
  expect(outline).toMatchObject({ width: '2px', style: 'solid', offset: '2px' })
  expect(outline.color).toBe(await primitive(p, '--blue-600'))
})
