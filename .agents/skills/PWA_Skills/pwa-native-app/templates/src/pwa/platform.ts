// platform.ts — environment detection + native-feel helpers. Framework-agnostic.

export type OS = 'ios' | 'android' | 'windows' | 'macos' | 'linux' | 'chromeos' | 'other';

const ua = navigator.userAgent;

export const os: OS =
  /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) ? 'ios'
  : /Android/.test(ua) ? 'android'
  : /CrOS/.test(ua) ? 'chromeos'
  : /Windows/.test(ua) ? 'windows'
  : /Mac OS X/.test(ua) ? 'macos'
  : /Linux/.test(ua) ? 'linux' : 'other';

/** In-app browsers (Instagram, Facebook, TikTok, LINE, WebViews) can't install — tell users to open in Safari/Chrome. */
export const isInAppBrowser = /FBAN|FBAV|Instagram|Line\/|TikTok|Snapchat|Twitter|LinkedInApp|GSA\/|; wv\)/i.test(ua);

const DISPLAY_MODES = ['standalone', 'fullscreen', 'minimal-ui', 'window-controls-overlay'] as const;

export function isStandalone(): boolean {
  return DISPLAY_MODES.some((m) => matchMedia(`(display-mode: ${m})`).matches)
    || (navigator as Navigator & { standalone?: boolean }).standalone === true;          // iOS < 16.4
}

/** Launched from a store wrapper? (PWABuilder packages) */
export function launchSource(): 'play' | 'microsoft-store' | 'ios-app' | 'installed' | 'browser' {
  if (document.referrer.startsWith('android-app://')) return 'play';
  if (document.referrer.startsWith('app-info://platform/microsoft-store')) return 'microsoft-store';
  if (document.cookie.includes('app-platform=iOS App Store')) return 'ios-app';
  return isStandalone() ? 'installed' : 'browser';
}

/** Put <html data-os="ios" data-standalone="true"> so CSS can make small platform adaptations. */
export function applyPlatformAttributes(root = document.documentElement): void {
  root.dataset.os = os;
  const sync = () => { root.dataset.standalone = String(isStandalone()); };
  sync();
  for (const m of DISPLAY_MODES) matchMedia(`(display-mode: ${m})`).addEventListener('change', sync);
}

/**
 * Keyboard awareness. Chromium/Firefox honour `interactive-widget=resizes-content`;
 * iOS does not, so measure the visual viewport and expose --kb-inset + data-keyboard.
 */
export function trackVirtualKeyboard(root = document.documentElement): void {
  const vv = window.visualViewport;
  if (!vv) return;
  let raf = 0;
  const update = () => {
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      root.style.setProperty('--kb-inset', `${Math.round(inset)}px`);
      root.dataset.keyboard = inset > 120 ? 'open' : 'closed';
    });
  };
  vv.addEventListener('resize', update);
  vv.addEventListener('scroll', update);
  update();
}

/**
 * Haptic tick. Android/Chromium: Vibration API. iOS 18+ Safari: toggling a hidden
 * <input type=checkbox switch> fires the system haptic (unofficial — call only inside a user gesture,
 * keep it subtle, and expect it may stop working). Respects reduced motion.
 */
let hapticLabel: HTMLLabelElement | null = null;
export function haptic(pattern: number | number[] = 10): void {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if ('vibrate' in navigator) { navigator.vibrate(pattern); return; }
  if (os !== 'ios') return;
  if (!hapticLabel) {
    const input = document.createElement('input');
    input.type = 'checkbox'; input.id = '__haptic'; input.setAttribute('switch', '');
    input.style.cssText = 'position:fixed;opacity:0;pointer-events:none;inset:0 auto auto 0;width:1px;height:1px';
    input.setAttribute('aria-hidden', 'true'); input.tabIndex = -1;
    hapticLabel = document.createElement('label');
    hapticLabel.htmlFor = '__haptic'; hapticLabel.style.display = 'none';
    document.body.append(input, hapticLabel);
  }
  hapticLabel.click();
}

/** Online/offline as a signal (navigator.onLine=true only means "has a network interface"). */
export function onConnectivityChange(cb: (online: boolean) => void): () => void {
  const on = () => cb(true), off = () => cb(false);
  addEventListener('online', on); addEventListener('offline', off);
  cb(navigator.onLine);
  return () => { removeEventListener('online', on); removeEventListener('offline', off); };
}

/** Ask the browser not to evict our data (granted heuristically; installed apps usually qualify). */
export async function requestPersistentStorage(): Promise<boolean> {
  if (!navigator.storage?.persist) return false;
  if (await navigator.storage.persisted()) return true;
  return navigator.storage.persist();
}

/** Keep the screen awake (e.g. turn-by-turn, scanning, recipes). Re-acquire after tab becomes visible. */
export async function keepAwake(): Promise<() => void> {
  if (!('wakeLock' in navigator)) return () => {};
  let lock: WakeLockSentinel | null = await navigator.wakeLock.request('screen').catch(() => null);
  const onVis = async () => { if (document.visibilityState === 'visible' && lock?.released !== false) lock = await navigator.wakeLock.request('screen').catch(() => null); };
  document.addEventListener('visibilitychange', onVis);
  return () => { document.removeEventListener('visibilitychange', onVis); lock?.release(); };
}
