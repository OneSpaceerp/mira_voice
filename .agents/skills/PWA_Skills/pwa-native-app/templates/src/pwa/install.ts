// install.ts — one install API for every platform.
// Order: beforeinstallprompt (Chromium) → navigator.install() (Web Install API, Chromium trial/rollout)
// → manual instructions (iOS/iPadOS/macOS Safari, Firefox) → open-in-browser (in-app browsers).
import { isInAppBrowser, isStandalone, os } from './platform';

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}
type NavigatorWithInstall = Navigator & { install?: (opts?: unknown) => Promise<unknown> };

export type InstallAvailability = 'installed' | 'prompt' | 'manual-ios' | 'manual-other' | 'open-in-browser';
export type InstallOutcome = 'accepted' | 'dismissed' | 'manual' | 'unavailable';

let deferred: BeforeInstallPromptEvent | null = null;
const listeners = new Set<(a: InstallAvailability) => void>();
const SNOOZE_KEY = 'pwa-install-snoozed-until';

addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();                       // keep the mini-infobar quiet; we show our own CTA at the right moment
  deferred = e as BeforeInstallPromptEvent;
  emit();
});
addEventListener('appinstalled', () => { deferred = null; emit(); /* analytics: track('pwa_installed') */ });

export function availability(): InstallAvailability {
  if (isStandalone()) return 'installed';
  if (isInAppBrowser) return 'open-in-browser';
  if (deferred || 'install' in navigator) return 'prompt';
  if (os === 'ios' || isMacSafari()) return 'manual-ios';   // Share ▸ Add to Home Screen / File ▸ Add to Dock
  return 'manual-other';                                     // Firefox: menu ▸ Install / Add to Home screen
}

export function onAvailabilityChange(cb: (a: InstallAvailability) => void): () => void {
  listeners.add(cb); cb(availability());
  return () => listeners.delete(cb);
}
function emit() { const a = availability(); listeners.forEach((cb) => cb(a)); }

/** Call ONLY from a click/tap handler (both APIs need user activation). */
export async function install(): Promise<InstallOutcome> {
  if (deferred) {
    const evt = deferred; deferred = null;
    await evt.prompt();
    const { outcome } = await evt.userChoice;
    emit();
    return outcome;
  }
  const nav = navigator as NavigatorWithInstall;
  if (nav.install) {
    try { await nav.install(); return 'accepted'; }          // needs manifest "id"
    catch (err) { return (err as DOMException)?.name === 'AbortError' ? 'dismissed' : 'unavailable'; }
  }
  return availability().startsWith('manual') ? 'manual' : 'unavailable';
}

/** Engagement gate: don't ask on first visit; ask after value is proven, and back off when dismissed. */
export function shouldOfferInstall(opts: { visits: number; completedKeyAction: boolean }): boolean {
  if (availability() === 'installed') return false;
  try { if (Date.now() < Number(localStorage.getItem(SNOOZE_KEY) ?? 0)) return false; } catch { /* storage blocked */ }
  return opts.completedKeyAction || opts.visits >= 3;
}
export function snoozeInstall(days = 14): void {
  try { localStorage.setItem(SNOOZE_KEY, String(Date.now() + days * 864e5)); } catch { /* ignore */ }
}

function isMacSafari(): boolean {
  const ua = navigator.userAgent;
  return os === 'macos' && /Safari\//.test(ua) && !/Chrome|Chromium|Edg\//.test(ua);
}

/** Copy for the manual path — render as a sheet with the real Share icon, not a wall of text. */
export const manualInstallSteps: Record<'ios' | 'mac' | 'firefox-android' | 'other', string[]> = {
  ios: ['Tap the Share button', 'Choose “Add to Home Screen”', 'Make sure “Open as Web App” is on, then tap Add'],
  mac: ['In Safari, open the File menu (or Share button)', 'Choose “Add to Dock”'],
  'firefox-android': ['Open the ⋮ menu', 'Tap “Add app to Home screen”'],
  other: ['Open your browser menu', 'Choose “Install app” or “Add to Home screen”'],
};
