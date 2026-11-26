#!/usr/bin/env node
// pwa-check.mjs — zero-dependency PWA audit (Node 18+).
// Checks HTML head, manifest (incl. PWABuilder packaging rules), icons/screenshots on disk, and the service worker.
// Usage:  node pwa-check.mjs dist            (built output folder)
//         node pwa-check.mjs https://app.example.com   (deployed site; also checks headers)
// Exit code 1 if any ERROR.
import { readFile, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';

const target = process.argv[2] ?? 'dist';
const isUrl = /^https?:\/\//.test(target);
const results = [];
const err = (m) => results.push(['ERROR', m]);
const warn = (m) => results.push(['WARN ', m]);
const ok = (m) => results.push(['ok   ', m]);

const base = isUrl ? new URL(target.endsWith('/') ? target : target + '/') : null;
async function get(path, binary = false) {
  if (isUrl) {
    const res = await fetch(new URL(path, base), { redirect: 'follow' }).catch(() => null);
    if (!res || !res.ok) return null;
    return { body: binary ? Buffer.from(await res.arrayBuffer()) : await res.text(), headers: res.headers };
  }
  const file = join(resolve(target), decodeURIComponent(new URL(path, 'http://x/').pathname));
  try { await stat(file); } catch { return null; }
  return { body: binary ? await readFile(file) : await readFile(file, 'utf8'), headers: new Map() };
}
const attr = (tag, name) => tag.match(new RegExp(`${name}\\s*=\\s*["']([^"']*)["']`, 'i'))?.[1];
const tags = (html, tag) => html.match(new RegExp(`<${tag}\\b[^>]*>`, 'gi')) ?? [];
const pngSize = (buf) => (buf?.length > 24 && buf.toString('ascii', 1, 4) === 'PNG') ? `${buf.readUInt32BE(16)}x${buf.readUInt32BE(20)}` : null;
const isHex = (c) => /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(c ?? '');

// ---------- HTML ----------
const page = await get(isUrl ? '' : 'index.html');
if (!page) { console.error(`Cannot read ${isUrl ? target : join(target, 'index.html')}`); process.exit(2); }
const html = page.body;
const metas = tags(html, 'meta'), links = tags(html, 'link');
const meta = (n) => metas.find((t) => attr(t, 'name')?.toLowerCase() === n);
const vp = attr(meta('viewport') ?? '', 'content') ?? '';
if (!vp.includes('width=device-width')) err('viewport meta missing width=device-width');
if (!vp.includes('viewport-fit=cover')) warn('viewport lacks viewport-fit=cover (needed for edge-to-edge + safe-area insets)');
if (/user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b/.test(vp)) warn('viewport blocks zoom (accessibility failure) — fix the 16px input font instead');
if (!meta('theme-color')) warn('no <meta name="theme-color"> (add light + dark variants with media=)');
if (!/<html[^>]*\slang=/i.test(html)) warn('<html> has no lang attribute');
const appleIcon = links.find((l) => attr(l, 'rel') === 'apple-touch-icon');
if (!appleIcon) warn('no <link rel="apple-touch-icon"> (180x180, opaque background) for iOS');
else if (!(await get(attr(appleIcon, 'href'), true))) err(`apple-touch-icon not found: ${attr(appleIcon, 'href')}`);
const manLink = links.find((l) => attr(l, 'rel') === 'manifest');
if (!manLink) { err('no <link rel="manifest">'); report(); }

// ---------- Manifest ----------
const manPath = attr(manLink, 'href');
const manRes = await get(manPath);
if (!manRes) { err(`manifest not found: ${manPath}`); report(); }
let m;
try { m = JSON.parse(manRes.body); ok(`manifest parsed (${manPath})`); } catch (e) { err(`manifest is invalid JSON: ${e.message}`); report(); }
if (isUrl) {
  const ct = manRes.headers.get('content-type') ?? '';
  if (!/manifest\+json|application\/json/.test(ct)) warn(`manifest served as "${ct}" (use application/manifest+json)`);
}
(function noNestedEmptyArrays(v, p = 'manifest') {   // PWABuilder: "Failed to download icon … 404"
  if (Array.isArray(v)) v.forEach((x, i) => { if (Array.isArray(x) && x.length === 0) err(`${p}[${i}] is an empty nested array`); noNestedEmptyArrays(x, `${p}[${i}]`); });
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) noNestedEmptyArrays(x, `${p}.${k}`);
})(m);

if (!m.name || m.name.length < 2) err('name missing or < 2 chars');
if (!m.short_name) err('short_name missing (required by PWABuilder packaging)');
else if (m.short_name.length < 3) err('short_name must be ≥ 3 chars for store packaging');
else if (m.short_name.length > 12) warn(`short_name "${m.short_name}" > 12 chars — truncated under icons`);
if (!m.description) warn('description missing (store listings, install dialog, Store.app require it)');
if (!m.id) warn('id missing — set a stable id (e.g. "/") so identity survives start_url changes; needed by navigator.install()/<install>');
if (!m.start_url) err('start_url missing');
const scopeUrl = new URL(m.scope ?? './', new URL(manPath, 'https://h/'));
const startUrl = new URL(m.start_url ?? '/', new URL(manPath, 'https://h/'));
if (!startUrl.href.startsWith(scopeUrl.href)) err(`start_url ${startUrl.pathname} is outside scope ${scopeUrl.pathname}`);
if (!['standalone', 'fullscreen', 'minimal-ui'].includes(m.display)) warn(`display is "${m.display ?? 'browser (default)'}" — use "standalone" for an app window`);
for (const k of ['theme_color', 'background_color']) {
  if (!m[k]) warn(`${k} missing`);
  else if (m[k] === 'none' || m[k] === 'transparent') err(`${k}: "${m[k]}" breaks packaging — omit it or use hex`);
  else if (!isHex(m[k])) warn(`${k} "${m[k]}" is not hex (PWABuilder expects hex)`);
}

// Icons
const icons = Array.isArray(m.icons) ? m.icons : [];
if (!icons.length) err('icons array missing/empty');
const sizesOf = (i) => (i.sizes ?? '').split(/\s+/).map((s) => s.toLowerCase());
const purposes = (i) => (i.purpose ?? 'any').split(/\s+/);
const anyIcons = icons.filter((i) => purposes(i).includes('any'));
const maxAny = Math.max(0, ...anyIcons.flatMap(sizesOf).map((s) => s === 'any' ? 1024 : parseInt(s)));
if (!anyIcons.length) err('no icon with purpose "any"');
if (maxAny < 512) err('need an "any" icon ≥ 512x512 (PWABuilder/Play/Store)');
if (!anyIcons.some((i) => sizesOf(i).some((s) => s === 'any' || parseInt(s) >= 192))) err('need an "any" icon ≥ 192x192');
if (icons.some((i) => purposes(i).includes('any') && purposes(i).includes('maskable'))) err('"any maskable" combined purpose — ship a SEPARATE maskable icon (PWABuilder rejects combined)');
if (!icons.some((i) => purposes(i).includes('maskable'))) warn('no maskable icon (Android adaptive icons will be letterboxed)');
if (!icons.some((i) => purposes(i).includes('monochrome'))) results.push(['info ', 'optional: monochrome icon for Android themed icons / notification badge']);
for (const icon of icons) {
  const buf = await get(new URL(icon.src, new URL(manPath, 'https://h/')).pathname, true);
  if (!buf) { err(`icon not found: ${icon.src}`); continue; }
  const dim = pngSize(buf.body);
  if (dim && icon.sizes && !sizesOf(icon).includes(dim)) err(`icon ${icon.src} is ${dim} but declares ${icon.sizes}`);
  if (icon.type === 'image/png' && !dim) warn(`icon ${icon.src} declared image/png but isn't a PNG`);
}

// Screenshots (richer install UI on Android/desktop + store listings)
const shots = Array.isArray(m.screenshots) ? m.screenshots : [];
if (!shots.some((s) => s.form_factor === 'narrow')) warn('no screenshot with form_factor "narrow" (mobile rich install sheet)');
if (!shots.some((s) => s.form_factor === 'wide')) warn('no screenshot with form_factor "wide" (desktop rich install dialog)');
for (const s of shots) {
  const buf = await get(new URL(s.src, new URL(manPath, 'https://h/')).pathname, true);
  if (!buf) { err(`screenshot not found: ${s.src}`); continue; }
  const dim = pngSize(buf.body);
  if (dim && s.sizes && s.sizes !== dim) err(`screenshot ${s.src} is ${dim} but declares ${s.sizes}`);
  if (!s.label) warn(`screenshot ${s.src} has no label (used as alt text)`);
}

// Shortcuts / share target / handlers
for (const sc of m.shortcuts ?? []) {
  if (!sc.name || !sc.url) err(`shortcut missing name/url: ${JSON.stringify(sc)}`);
  if (sc.icons && !sc.icons.some((i) => sizesOf(i).includes('96x96'))) warn(`shortcut "${sc.name}" icons lack a 96x96 entry`);
}
if (m.share_target) {
  const st = m.share_target;
  if (!st.action || !st.params) err('share_target needs action + params');
  if (st.params?.files && (st.method !== 'POST' || st.enctype !== 'multipart/form-data')) err('share_target with files requires method POST + enctype multipart/form-data');
}
if (m.display_override?.includes('window-controls-overlay')) results.push(['info ', 'window-controls-overlay enabled — style env(titlebar-area-*) and app-region: drag']);

// ---------- Service worker ----------
const scripts = [...html.matchAll(/<script\b[^>]*src=["']([^"']+)["']/gi)].map((x) => x[1]);
let bundle = html;
for (const s of scripts) bundle += (await get(s))?.body ?? '';
const registers = /serviceWorker\.register\(|registerSW|Workbox|Serwist/.test(bundle);
const swRef = bundle.match(/["'`](\/?[\w\-./]*?(?:sw|service-worker|serwist)[\w\-]*\.m?js)["'`]/)?.[1];
if (!registers) warn('no service worker registration found in index.html or its entry scripts (may be lazy-loaded)');
const swCandidates = [swRef, 'sw.js', 'service-worker.js', 'serwist.js'].filter(Boolean);
let sw = null, swPath = '';
for (const p of swCandidates) { sw = await get(p); if (sw) { swPath = p; break; } }
if (!sw) err('service worker file not found (expected sw.js) — offline + install prompt need it');
else {
  ok(`service worker found: ${swPath}`);
  if (!/addEventListener\(\s*["']fetch|precacheAndRoute|registerRoute|Serwist|workbox/.test(sw.body)) warn('service worker has no fetch handling — no offline support, no Chromium install prompt');
  if (!/offline/i.test(sw.body)) warn('no offline fallback referenced in the SW (precache an offline page)');
  if (isUrl) {
    const cc = sw.headers.get('cache-control') ?? '';
    if (!/no-cache|max-age=0|no-store/.test(cc)) warn(`SW served with Cache-Control "${cc || '(none)'}" — serve sw.js with no-cache so updates ship`);
  }
}
if (isUrl && base.protocol !== 'https:' && base.hostname !== 'localhost') err('not served over HTTPS');
report();

function report() {
  const order = { 'ERROR': 0, 'WARN ': 1, 'info ': 2, 'ok   ': 3 };
  results.sort((a, b) => order[a[0]] - order[b[0]]);
  for (const [lvl, msg] of results) console.log(`${lvl}  ${msg}`);
  const e = results.filter((r) => r[0] === 'ERROR').length, w = results.filter((r) => r[0] === 'WARN ').length;
  console.log(`\n${e} error(s), ${w} warning(s) — ${e ? 'NOT ready to package' : 'ready for PWABuilder packaging checks'}`);
  process.exit(e ? 1 : 0);
}
