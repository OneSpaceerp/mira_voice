// transitions.ts — SPA page transitions: Navigation API (Baseline 2026) + View Transitions with
// direction types ('forward' | 'back') that app.css animates. Falls back to instant swaps.
type Render = (url: URL) => Promise<void> | void;

type VT = { finished: Promise<void>; types?: Set<string> };
type DocVT = Document & { startViewTransition?: (cb: () => Promise<void> | void) => VT };

function withTransition(update: () => Promise<void> | void, direction: 'forward' | 'back' | 'none'): Promise<void> {
  const doc = document as DocVT;
  if (!doc.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve(update());
  const vt = doc.startViewTransition(update);
  if (direction !== 'none') vt.types?.add(direction);          // Chrome 125+/Safari 18.2+; ignored elsewhere
  return vt.finished;
}

/** Intercept same-origin navigations and render client-side with a native-style slide. */
export function startRouter(render: Render): void {
  const nav = (window as Window & { navigation?: any }).navigation;
  if (nav) {
    nav.addEventListener('navigate', (event: any) => {
      if (!event.canIntercept || event.hashChange || event.downloadRequest || event.formData) return;
      const url = new URL(event.destination.url);
      if (url.origin !== location.origin) return;
      const back = event.navigationType === 'traverse' && event.destination.index < nav.currentEntry.index;
      const direction = event.navigationType === 'replace' ? 'none' : back ? 'back' : 'forward';
      event.intercept({
        scroll: 'after-transition',                              // restore scroll position per entry
        handler: () => withTransition(() => render(url), direction),
      });
    });
    return;
  }
  // Fallback: click interception + popstate (older Safari/Firefox)
  document.addEventListener('click', (e) => {
    const a = (e.target as Element).closest('a');
    if (!a || a.target || a.hasAttribute('download') || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const url = new URL(a.href);
    if (url.origin !== location.origin || url.hash && url.pathname === location.pathname) return;
    e.preventDefault();
    history.pushState({}, '', url);
    withTransition(() => render(url), 'forward');
  });
  addEventListener('popstate', () => withTransition(() => render(new URL(location.href)), 'back'));
}
