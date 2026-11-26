// Mira Voice — task 0.3 gate, browser part: WebRTC calls over WSS through
// Kamailio (8089) -> Asterisk, media DTLS-SRTP <-> RTPengine <-> RTP Asterisk.
// Each browser sends its own pure tone (A 440 Hz, B 880 Hz); the test checks RTP counters
// AND that the tone each side receives is the other side's tone.
// Needs: MIRA_WSS, MIRA_DOMAIN, EXT_A, PASS_A, EXT_B, PASS_B (run-tests.sh sets them).
import { test, expect } from '@playwright/test'

const env = (k) => {
  const v = process.env[k]
  if (!v) throw new Error(`${k} is not set — run tests/integration/telephony/run-tests.sh`)
  return v
}

async function phone(browser, ext, password, toneHz) {
  const context = await browser.newContext()
  const page = await context.newPage()
  page.on('console', (m) => {
    if (m.type() === 'error') console.log(`[${ext}] ${m.text()}`)
  })
  await page.goto('/softphone.html')
  await page.evaluate((a) => window.mira.start(a), {
    wss: env('MIRA_WSS'),
    domain: env('MIRA_DOMAIN'),
    ext,
    password,
    toneHz,
  })
  return page
}

async function expectAudio(page, who, expectedHz) {
  const s = await page.evaluate(() => window.mira.stats())
  const tone = await page.evaluate(() => window.mira.remoteTone())
  console.log(`${who}: stats ${JSON.stringify(s)} received tone ${JSON.stringify(tone)}`)
  expect(s.outbound?.packetsSent ?? 0, `${who} sent RTP`).toBeGreaterThan(100)
  expect(s.inbound?.packetsReceived ?? 0, `${who} received RTP`).toBeGreaterThan(100)
  expect(tone.db, `${who} received an audible signal`).toBeGreaterThan(-60)
  expect(
    Math.abs(tone.hz - expectedHz),
    `${who} heard ${tone.hz} Hz, expected ${expectedHz}`,
  ).toBeLessThan(expectedHz * 0.05)
}

test('browser registers over WSS and hears its own tone from the echo test (609)', async ({
  browser,
}) => {
  const a = await phone(browser, env('EXT_A'), env('PASS_A'), 440)
  await a.evaluate(() => window.mira.call('609'))
  await a.waitForTimeout(4000)
  await expectAudio(a, `ext ${env('EXT_A')} (echo)`, 440)
  await a.evaluate(() => window.mira.hangup())
  await a.evaluate(() => window.mira.stop())
})

test('two browsers call each other and each hears the other', async ({ browser }) => {
  const b = await phone(browser, env('EXT_B'), env('PASS_B'), 880)
  const a = await phone(browser, env('EXT_A'), env('PASS_A'), 440)
  await a.evaluate((t) => window.mira.call(t), env('EXT_B'))
  await b.evaluate(() => window.mira.waitForCall())
  await a.waitForTimeout(4000)
  await expectAudio(a, `caller ${env('EXT_A')}`, 880)
  await expectAudio(b, `callee ${env('EXT_B')}`, 440)
  // caller hangs up: Asterisk must reach the callee's browser with a BYE (in-dialog routing to WSS)
  await a.evaluate(() => window.mira.hangup())
  await b.evaluate(() => window.mira.waitForEnd())
  await a.evaluate(() => window.mira.stop())
  await b.evaluate(() => window.mira.stop())
})
