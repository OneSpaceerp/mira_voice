// register.ts — service worker registration + update UX (vite-plugin-pwa virtual module).
// For non-Vite stacks use workbox-window: new Workbox('/sw.js'); wb.addEventListener('waiting', …); wb.messageSkipWaiting().
import { registerSW } from 'virtual:pwa-register';

type Handlers = {
  onUpdateReady: (apply: () => Promise<void>) => void;   // show "Update available · Reload"
  onOfflineReady?: () => void;                            // show "Ready to work offline" once
};

const UPDATE_CHECK_MS = 60 * 60 * 1000;

export function registerServiceWorker({ onUpdateReady, onOfflineReady }: Handlers): void {
  if (!('serviceWorker' in navigator)) return;

  const updateSW = registerSW({
    immediate: true,
    onNeedRefresh() {
      // Never reload under the user's fingers: let them choose. updateSW(true) = SKIP_WAITING + reload.
      onUpdateReady(() => updateSW(true));
    },
    onOfflineReady,
    onRegisteredSW(swUrl, registration) {
      if (!registration) return;
      let last = Date.now();
      const check = async () => {
        if (!navigator.onLine || Date.now() - last < UPDATE_CHECK_MS / 4) return;
        last = Date.now();
        // Skip if the SW script is unreachable (offline/captive portal) to avoid a broken update.
        const resp = await fetch(swUrl, { cache: 'no-store', headers: { 'cache-control': 'no-cache' } }).catch(() => null);
        if (resp?.status === 200) await registration.update();
      };
      // Installed apps can stay open for days: check when brought to foreground + hourly.
      document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') check(); });
      setInterval(check, UPDATE_CHECK_MS);
    },
    onRegisterError(error) { console.error('[pwa] SW registration failed', error); },
  });
}
