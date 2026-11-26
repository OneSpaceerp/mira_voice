// outbox.ts — offline-first writes. Used by the page AND the service worker (same module, bundled twice).
// Write locally → enqueue → flush now if online → Background Sync (Chromium) → fallback flush on
// online / app foreground / app start (iOS & Firefox have no Background Sync).
import { openDB, type DBSchema } from 'idb';

export interface OutboxItem {
  id: string;                      // idempotency key — server must dedupe on it
  url: string;
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body: unknown;
  createdAt: number;
  attempts: number;
  lastError?: string;
}
interface AppDB extends DBSchema {
  outbox: { key: string; value: OutboxItem; indexes: { createdAt: number } };
}

export const SYNC_TAG = 'outbox-sync';
const MAX_ATTEMPTS = 8;

const db = () => openDB<AppDB>('app', 1, {
  upgrade(d) { d.createObjectStore('outbox', { keyPath: 'id' }).createIndex('createdAt', 'createdAt'); },
});

export async function enqueue(req: Omit<OutboxItem, 'id' | 'createdAt' | 'attempts'>): Promise<string> {
  const item: OutboxItem = { ...req, id: crypto.randomUUID(), createdAt: Date.now(), attempts: 0 };
  await (await db()).put('outbox', item);
  await requestSync();
  return item.id;
}

export async function pendingCount(): Promise<number> {
  return (await db()).count('outbox');
}

async function requestSync(): Promise<void> {
  const reg = await navigator.serviceWorker?.ready.catch(() => undefined);
  const sync = (reg as (ServiceWorkerRegistration & { sync?: { register(tag: string): Promise<void> } }) | undefined)?.sync;
  if (sync) { await sync.register(SYNC_TAG).catch(() => flush()); }
  else if (navigator.onLine) { await flush(); }
}

let flushing: Promise<{ sent: number; failed: number }> | null = null;
/** Send queued writes in order. 4xx (except 408/429) = permanent failure → keep for user review. */
export function flush(): Promise<{ sent: number; failed: number }> {
  flushing ??= (async () => {
    const d = await db();
    const items = await d.getAllFromIndex('outbox', 'createdAt');
    let sent = 0, failed = 0;
    for (const item of items) {
      try {
        const res = await fetch(item.url, {
          method: item.method,
          headers: { 'content-type': 'application/json', 'idempotency-key': item.id },
          body: item.method === 'DELETE' ? undefined : JSON.stringify(item.body),
        });
        if (res.ok || res.status === 409) { await d.delete('outbox', item.id); sent++; continue; }
        const retryable = res.status >= 500 || res.status === 408 || res.status === 429;
        await d.put('outbox', { ...item, attempts: item.attempts + 1, lastError: `HTTP ${res.status}` });
        failed++;
        if (!retryable || item.attempts + 1 >= MAX_ATTEMPTS) continue;
        break;                                          // server trouble: stop, keep order, retry later
      } catch (err) {
        await d.put('outbox', { ...item, attempts: item.attempts + 1, lastError: String(err) });
        failed++;
        throw err;                                      // network down: let Background Sync retry
      }
    }
    return { sent, failed };
  })().finally(() => { flushing = null; });
  return flushing;
}

/** Page-side fallback triggers (call once at startup). */
export function installOutboxTriggers(onChange?: (pending: number) => void): void {
  const run = () => flush().catch(() => {}).finally(async () => onChange?.(await pendingCount()));
  addEventListener('online', run);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && navigator.onLine) run(); });
  navigator.serviceWorker?.addEventListener('message', (e) => { if (e.data?.type === 'OUTBOX_FLUSHED') run(); });
  if (navigator.onLine) run();
}
