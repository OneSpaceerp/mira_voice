// sheet.ts — bottom sheet on native <dialog>: back gesture closes it, drag-to-dismiss with velocity.
import { haptic } from './platform';

/** Open a <dialog> as a layer that the Android back gesture / browser back closes. */
export function openSheet(dialog: HTMLDialogElement): void {
  if (dialog.open) return;
  history.pushState({ sheet: dialog.id }, '');
  dialog.showModal();
  haptic(8);
  const onPop = () => { if (dialog.open) dialog.close('back'); };
  addEventListener('popstate', onPop, { once: true });
  dialog.addEventListener('close', () => {
    removeEventListener('popstate', onPop);
    if (history.state?.sheet === dialog.id) history.back();   // closed by UI → consume our history entry
  }, { once: true });
}

/** Drag the grabber (or the sheet when scrolled to top) down to dismiss. */
export function enableSheetDrag(dialog: HTMLDialogElement): void {
  const handle = dialog.querySelector<HTMLElement>('[data-sheet-drag]') ?? dialog;
  let startY = 0, lastY = 0, lastT = 0, velocity = 0, dragging = false;

  handle.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    dragging = true; startY = lastY = e.clientY; lastT = e.timeStamp; velocity = 0;
    handle.setPointerCapture(e.pointerId);
    dialog.classList.add('is-dragging');
  });
  handle.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dy = Math.max(0, e.clientY - startY);
    const dt = Math.max(1, e.timeStamp - lastT);
    velocity = (e.clientY - lastY) / dt;                 // px/ms
    lastY = e.clientY; lastT = e.timeStamp;
    dialog.style.translate = `0 ${dy < 0 ? dy / 3 : dy}px`;
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    dialog.classList.remove('is-dragging');
    const dy = lastY - startY;
    dialog.style.translate = '';
    if (dy > dialog.offsetHeight * 0.3 || velocity > 0.6) dialog.close('drag');
  };
  handle.addEventListener('pointerup', end);
  handle.addEventListener('pointercancel', end);
}
