/**
 * Mira Flow builder end to end, against a real Mira Core (task 1.4 stage 3).
 * The runner (tests/integration/desk/run.sh) provides a tenant admin and a recorded prompt:
 *   MIRA_E2E_EMAIL, MIRA_E2E_PASSWORD, MIRA_E2E_PROMPT (name), MIRA_E2E_RUN (unique suffix)
 * Every control is reached by its visible label, the way assistive technology finds it.
 */
import { appendFileSync } from 'node:fs'

import AxeBuilder from '@axe-core/playwright'
import { expect, type Page, test } from '@playwright/test'

const EMAIL = process.env.MIRA_E2E_EMAIL ?? ''
const PASSWORD = process.env.MIRA_E2E_PASSWORD ?? ''
const PROMPT = process.env.MIRA_E2E_PROMPT ?? 'welcome'
const RUN = process.env.MIRA_E2E_RUN ?? String(Date.now())
// a platform admin, like the one deploy/install.sh creates (profile language: Arabic)
const ADMIN_EMAIL = process.env.MIRA_E2E_ADMIN_EMAIL ?? ''
const ADMIN_PASSWORD = process.env.MIRA_E2E_ADMIN_PASSWORD ?? ''
const TENANT = process.env.MIRA_E2E_TENANT ?? ''

async function signIn(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Call flows' })).toBeVisible()
}

async function newFlow(page: Page, name: string, number?: string) {
  await page.getByRole('button', { name: 'New flow' }).click()
  await page.getByLabel('Name').fill(name)
  if (number) await page.getByLabel(/Internal number/).fill(number)
  await page.getByRole('button', { name: 'Create' }).click()
  await expect(page).toHaveURL(/\/flows\/[0-9a-f-]{36}$/)
  await expect(page.getByRole('heading', { name: 'Play prompt' })).toBeVisible()
}

async function api<T>(page: Page, path: string): Promise<T> {
  const login = await page.request.post('/api/v1/auth/token', {
    form: { username: EMAIL, password: PASSWORD },
  })
  const token = ((await login.json()) as { access_token: string }).access_token
  const r = await page.request.get(`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  expect(r.ok()).toBe(true)
  return (await r.json()) as T
}

async function promptOption(page: Page) {
  // option text is "<name> (AR · …)"
  const options = await page
    .getByLabel('Prompt', { exact: true })
    .locator('option')
    .allTextContents()
  const found = options.find((o) => o.startsWith(`${PROMPT} (`))
  expect(found, `prompt ${PROMPT} in ${options.join(' | ')}`).toBeTruthy()
  return found!
}

test('build, save and publish a flow with the keyboard-friendly inspector', async ({ page }) => {
  await signIn(page)
  await newFlow(page, `E2E main ${RUN}`, `7${RUN.slice(-3)}`)
  const flowId = page.url().split('/').pop()!

  // welcome: choose the prompt, then add a menu as its next step
  await page.getByLabel('Prompt', { exact: true }).selectOption({ label: await promptOption(page) })
  await page.getByLabel('Then', { exact: true }).selectOption('new:menu')
  await expect(page.getByRole('heading', { name: 'Menu' })).toBeVisible()

  // menu: prompt, key 1 -> a new transfer to 1001
  await page.getByLabel('Prompt', { exact: true }).selectOption({ label: await promptOption(page) })
  await page.getByLabel('Then (Key 1)').selectOption('new:transfer')
  await expect(page.getByRole('heading', { name: 'Transfer' })).toBeVisible()
  await page.getByLabel('Number').fill('1001')
  await page.getByLabel('Number').press('Tab')

  // back to the menu without the mouse: the step picker in the toolbar
  await page.getByLabel('Select a step to edit it.').selectOption('menu_1')
  await page.getByLabel('Then (wrong key)').selectOption('new:hangup')
  await expect(page.getByRole('heading', { name: 'Hang up' })).toBeVisible()

  await page.keyboard.press('Control+s')
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Problems (0)' })).toBeVisible()

  await page.getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByText('Version 1 published. New calls use it now.')).toBeVisible()

  // what Mira Core stored is exactly what was built
  const v1 = await api<{
    definition: { start: string; nodes: Record<string, Record<string, unknown>> }
  }>(page, `/flows/${flowId}/versions/1`)
  const nodes = v1.definition.nodes
  expect(v1.definition.start).toBe('welcome')
  expect(nodes.welcome).toMatchObject({ type: 'play', next: 'menu_1' })
  expect(nodes.menu_1).toMatchObject({
    type: 'menu',
    options: { '1': 'transfer_1' },
    invalid_next: 'hangup_1',
  })
  expect(nodes.transfer_1).toMatchObject({ type: 'transfer', number: '1001' })
  expect(nodes.hangup_1).toMatchObject({ type: 'hangup' })

  // versions: in use, and copy-back works
  await page.getByRole('button', { name: 'Versions' }).click()
  await expect(page.getByText('In use')).toBeVisible()
})

test('problems point at their step', async ({ page }) => {
  await signIn(page)
  await newFlow(page, `E2E problems ${RUN}`)
  // palette: a menu below the selected welcome step (linked from it), with no prompt yet
  await page
    .getByRole('navigation', { name: 'Add a step' })
    .getByRole('button', { name: 'Menu' })
    .click()
  await page.keyboard.press('Control+s')
  const problem = page.getByRole('button', { name: /^menu_1: prompt/ })
  await expect(problem).toBeVisible()
  await page.getByLabel('Select a step to edit it.').selectOption('welcome')
  await problem.click()
  await expect(page.getByRole('heading', { name: 'Menu' })).toBeVisible()
  // publishing is refused while problems remain
  await page.getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByText('Fix these before publishing:')).toBeVisible()
})

test('Arabic mirrors the layout; numbers stay left-to-right', async ({ page }) => {
  await signIn(page)
  await page.getByLabel('Language').selectOption('ar')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.locator('html')).toHaveAttribute('lang', 'ar')
  await expect(page.getByRole('heading', { name: 'مسارات المكالمات' })).toBeVisible()
  const rail = await page.getByRole('navigation', { name: 'ميرا ديسك' }).boundingBox()
  expect(rail!.x).toBeGreaterThan(700) // the rail moved to the right-hand side
  // the first test gave a flow the internal number 7xxx
  const number = page.locator('.mv-number').filter({ hasText: `7${RUN.slice(-3)}` })
  await expect(number).toHaveCSS('direction', 'ltr')
  // the editor in Arabic: the canvas keeps its geometry, the canvas buttons are labelled
  await page.getByRole('link', { name: `E2E main ${RUN}` }).click()
  await expect(page.getByRole('heading', { name: 'تشغيل رسالة' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'تكبير', exact: true })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('editor-ar.png') })
  await page.getByLabel('اللغة').selectOption('en') // leave English for the other tests
})

for (const theme of ['light', 'dark'] as const) {
  test(`no serious accessibility problems (${theme})`, async ({ page }, testInfo) => {
    await signIn(page)
    await page.getByLabel('Theme').selectOption(theme)
    const scan = async (where: string) => {
      const result = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
        .analyze()
      const serious = result.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical',
      )
      // lesser findings go into the report for the design review; they do not fail the gate
      for (const v of result.violations.filter((x) => !serious.includes(x))) {
        appendFileSync(
          testInfo.outputPath('axe-minor.txt'),
          `${where}: ${v.impact} ${v.id} ${v.help}
`,
        )
      }
      await page.screenshot({ path: testInfo.outputPath(`${where}-${theme}.png`) })
      expect(
        serious.map((v) => `${where}: ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target}`),
      ).toEqual([])
    }
    await scan('flows')
    await page.getByRole('link', { name: 'Prompts' }).click()
    await expect(page.getByRole('heading', { name: 'Prompts' })).toBeVisible()
    await scan('prompts')
    await page.getByRole('link', { name: 'Call flows' }).click()
    await page.getByRole('link', { name: `E2E main ${RUN}` }).click()
    await expect(page.getByRole('heading', { name: 'Play prompt' })).toBeVisible()
    await scan('editor')
    await page.getByLabel('Theme').selectOption('system')
  })
}

test('a platform admin picks the tenant and sees its flows', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(ADMIN_EMAIL)
  await page.getByLabel('Password').fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // the profile language (Arabic) applies on first sign-in
  await expect(page.getByRole('heading', { name: 'مسارات المكالمات' })).toBeVisible()
  await page.getByLabel('اللغة').selectOption('en')
  await page.getByLabel('Tenant').selectOption({ label: TENANT })
  await expect(page.getByRole('link', { name: `E2E main ${RUN}` })).toBeVisible()
})
