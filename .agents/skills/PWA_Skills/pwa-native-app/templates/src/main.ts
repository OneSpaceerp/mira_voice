import { applyPlatformAttributes, haptic, onConnectivityChange, requestPersistentStorage, trackVirtualKeyboard } from './pwa/platform';
import { registerServiceWorker } from './pwa/register';
import { availability, install, manualInstallSteps, onAvailabilityChange, snoozeInstall } from './pwa/install';
import { enableSheetDrag, openSheet } from './pwa/sheet';
import { enqueue, installOutboxTriggers } from './pwa/outbox';

applyPlatformAttributes();
trackVirtualKeyboard();

// ---- Toast (snackbar) ----
const toastEl = document.querySelector<HTMLElement>('.toast')!;
let toastTimer = 0;
function toast(text: string, action?: { label: string; run: () => void }, ms = 4000) {
  toastEl.querySelector('.toast-text')!.textContent = text;
  const btn = toastEl.querySelector<HTMLButtonElement>('.toast-action')!;
  btn.hidden = !action;
  if (action) { btn.textContent = action.label; btn.onclick = () => { toastEl.hidden = true; action.run(); }; }
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  if (!action) toastTimer = window.setTimeout(() => (toastEl.hidden = true), ms);
}

// ---- Service worker + update UX ----
registerServiceWorker({
  onUpdateReady: (apply) => toast('A new version is ready', { label: 'Reload', run: apply }),
  onOfflineReady: () => toast('Ready to work offline'),
});

// ---- Connectivity pill ----
const pill = document.querySelector<HTMLElement>('.net-pill')!;
onConnectivityChange((online) => { pill.hidden = online; });

// ---- Install CTA ----
const installBtn = document.querySelector<HTMLButtonElement>('[data-install]')!;
onAvailabilityChange((a) => { installBtn.hidden = a === 'installed' || a === 'open-in-browser'; });
installBtn.addEventListener('click', async () => {
  const outcome = await install();
  if (outcome === 'manual') toast(manualInstallSteps[availability() === 'manual-ios' ? 'ios' : 'other'].join(' → '), undefined, 8000);
  if (outcome === 'dismissed') snoozeInstall();
  if (outcome === 'accepted') requestPersistentStorage();
});

// ---- Bottom sheet + offline-first save ----
const sheet = document.querySelector<HTMLDialogElement>('#new-note')!;
enableSheetDrag(sheet);
document.querySelector('[data-open-sheet]')!.addEventListener('click', () => openSheet(sheet));
sheet.addEventListener('close', async () => {
  if (sheet.returnValue !== 'save') return;
  const form = sheet.querySelector('form')!;
  const data = Object.fromEntries(new FormData(form));
  form.reset();
  haptic([6, 30, 6]);
  await enqueue({ url: '/api/notes', method: 'POST', body: data });   // saved locally first = instant
  toast(navigator.onLine ? 'Note saved' : 'Saved offline · will sync');
});
installOutboxTriggers();

// ---- Tabs: haptic tick + aria-current ----
document.querySelectorAll<HTMLAnchorElement>('.tab').forEach((tab) => tab.addEventListener('click', () => {
  haptic(5);
  document.querySelectorAll('.tab').forEach((t) => t.removeAttribute('aria-current'));
  tab.setAttribute('aria-current', 'page');
}));
