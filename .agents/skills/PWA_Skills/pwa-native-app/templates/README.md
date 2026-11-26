# pwa-native-app template (tested: vite 7 + vite-plugin-pwa 2.0 + Workbox 7.4)

npm install
npm run build          # generates icons from public/logo.svg, manifest, sw.js
npm run preview &      # http://localhost:4173
npm run test:pwa       # Playwright: SW control, offline reload, offline deep link, sheet, outbox, store screenshots
npm run build && npm run check:pwa   # manifest/head/SW audit (0 errors = ready for PWABuilder)

Key files: src/styles/app.css (tokens + native behaviour layer), src/sw.ts, src/pwa/{platform,install,register,sheet,outbox,transitions}.ts
