// Playwright config for the WebRTC lab test. Chromium uses a fake microphone (a beep tone),
// so audio really flows and can be measured with getStats().
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.mjs',
  timeout: 90_000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    ignoreHTTPSErrors: true,
    permissions: ['microphone'],
    launchOptions: {
      args: [
        '--use-fake-ui-for-media-stream',
        '--use-fake-device-for-media-stream',
        // Web Audio (tone source, analyser) without a user gesture
        '--autoplay-policy=no-user-gesture-required',
        // lab certificate is self-signed
        '--ignore-certificate-errors',
        // allow real host candidates (no mDNS .local names) so the lab works offline
        '--disable-features=WebRtcHideLocalIpsWithMdns',
      ],
    },
  },
  webServer: {
    command: 'npm run serve',
    url: 'http://127.0.0.1:8765/softphone.html',
    reuseExistingServer: true,
  },
})
