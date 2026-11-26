# Mira Voice — brand book and design system (v2)

**Mira Voice** (Arabic: **ميرا ڤويس**) is NSD's contact-center platform: IVR and auto attendant, queues, dialer, recording, wallboards, desktop and mobile softphones, WhatsApp/SMS/web chat, and native ERPNext / Frappe CRM integration. It ships as **Mira Cloud** and as **Mira Server** (on-premise). Line: **Where every voice matters.** Home: a subdomain of nsd-eg.com (suggested `voice.nsd-eg.com`).

This is version 2, rebuilt after comparing Mira with Ziwo and running the project's design skills (trend analysis, UI/UX Pro Max, design-system architecture, critique, Apple HIG, design justice, brand, banner and slide guidance). Read these sections in order:

1. **This page** — the idea, voice, logo, colour, type, shape, icons, motion.
2. **Design direction** — why it looks like this: trend choice, what we took and rejected from the skills, how we stand apart from Ziwo, and the critique that drove v2.
3. **Token architecture** — three token tiers, naming, how to use them in Vue, Flutter, Frappe and Tailwind.
4. **Product patterns** — Mira Desk, Mira Phone, wallboards, Mira Flow, reports, Mira Connect, RTL.
5. **Accessibility and agent wellbeing** — contrast table, calm alerts, shared workstations, flaky networks.
6. **Marketing and presentations** — banners, social, slides, the extruded block.

---

## 1. The idea

A contact center is where a company is judged one voice at a time. Mira's job: no caller lost, no agent blind, no manager guessing. The brand says it with three moves:

- **One bold red block.** The logo is a solid, softly-cornered red block that reads as an "m" and as stacked speech bubbles, with a darker extruded edge. Confident, memorable after one look.
- **Warm, quiet neutrals everywhere else.** The bone off-white of the logo type and a warm near-black carry the product. Red is earned: one red thing per screen.
- **Heavy, friendly type against calm working type.** "mira" is set heavy and lowercase; the product UI is calm, legible IBM Plex.

### Personality

| We are | We are not |
| --- | --- |
| Clear — a wallboard number reads from across the room | Clever — no puns on "calls" or "lines" |
| Calm under load — the screen stays still when the queue is on fire | Alarming — no flashing, no sirens, no screaming red errors |
| Trilingual by default — Arabic, English and French are equals | An English product with translations bolted on |
| Honest with numbers — "Service level 78% / 20 s" | Cheerleading — "Great day!" |
| Ours to run — cloud or on your own servers | Locked in |

## 2. Voice and copy

- Plain, short, active sentences. Verb first on buttons: "Answer", "Transfer", "Start campaign".
- Sentence case everywhere except the `overline` style (Latin only).
- Agent states, always the same seven words: **Available, Ringing, On call, On hold, Wrap-up, Break, Offline** — متاح، يرن، في مكالمة، قيد الانتظار، إنهاء المكالمة، استراحة، غير متصل — Disponible, Sonnerie, En appel, En attente, Post-appel, Pause, Hors ligne.
- Durations `mm:ss` (`04:12`); service level with its threshold (`SL 82% / 20 s`); money with currency code first (`EGP 42,300`, `SAR 1,250`).
- Arabic is written, not translated: clear Modern Standard Arabic in the UI; Egyptian or Gulf colloquial only in IVR prompts when the customer asks.
- Errors say what happened and what to do, without blame: "Can't reach the gateway. Calls are using the backup trunk." — not "Error 503".
- No emoji in product UI. No exclamation marks in system messages.

### IVR and sonic identity

Prompts are part of the brand. One voice per customer, warm and unhurried (~150 words/minute). Lead with the most-chosen option, at most four options per menu, always "0 for an agent" and "9 to repeat". Mira's own demo line: a female voice in Arabic, then English, then French on "3".

## 3. Logo

Master: **Assets → Logos → `miravoice-primary.png`** (red block, bone "mira voice" and tagline). The designer is supplying the vector set: SVG master, symbol-only mark, one-line horizontal wordmark, bone-on-transparent, ink, and the Arabic lock-up **ميرا ڤويس**.

- Use as supplied; never redraw, re-type, recolour or re-space.
- **Clear space:** the height of the "m" of "mira" on every side.
- **Minimum size:** 120 px / 30 mm wide with tagline; smaller → lock-up without tagline.
- **Backgrounds:** `surface`, `surface-raised`, `bone`, or a calm photo area. On red, use the bone wordmark, never the red block on red.
- **Don't:** stretch, rotate, add gradients, glows or drop shadows, outline it, or set the tagline in another font.
- **App icon:** the red block filling a `radius-xl` tile with a bone lowercase **m**; same icon for Windows, macOS, Android, iOS and the favicon.

## 4. Colour

Small palette, three tiers (see Token architecture). What a designer needs to remember:

| Role | Light | Dark | Rule |
| --- | --- | --- | --- |
| **mira-red** | #BE0007 | #BE0007 | One red thing per screen: primary action, active-call bar, the headline KPI, the On-call pill. |
| surface / surface-raised | #F4F2EE / #FFFFFF | #141212 / #1E1B1B | Warm, never cool grey. |
| bone | #E4E2DD | #2A2626 | Keypad, call controls, quiet chips. |
| ink / ink-muted | #1A1414 / #5E5654 | #F4F2EE / #BDB7B1 | All text. |
| state-live | green | green | Connected, available, up. |
| state-ringing | amber | amber | Ringing, waiting, at risk. |
| state-hold | blue | blue | Hold, wrap-up, transfer, info. |
| state-offline | warm grey | warm grey | Break, logged out. |
| **danger** | terracotta #8B3111 | #FE9979 | Errors only. Deliberately not the brand red. |
| focus-ring | blue | blue | Keyboard focus, never red. |

Every text pair passes WCAG AA (4.5:1) in both themes; control borders and focus rings pass 3:1. The full table is in **Accessibility and agent wellbeing**. Primitives are stored in OKLCH so scales stay perceptually even.

## 5. Typography

| Role | Family | Why |
| --- | --- | --- |
| Display (marketing, slides, wallboard numbers) | **Archivo** 800–900 | Heavy grotesk, closest free match to the "mira" wordmark |
| Product UI (Latin + French) | **IBM Plex Sans** 400–600 | Neutral, technical, excellent at 13–14 px; designed as one family with… |
| Product UI (Arabic) | **IBM Plex Sans Arabic** 400–600 | …the same design DNA, so mixed Arabic/English screens look like one voice |
| Numbers, timers, phone numbers, SIP URIs | **IBM Plex Mono** 500 | Digits don't jump while a timer counts |

All four are free (OFL) Google Fonts and self-hostable for Mira Server installs with no internet. Arabic runs one step larger with taller line height (`ar-body` 15/26 vs `body` 14/20). Never letter-space Arabic. App body is 14 px for dense agent screens; reading surfaces (web, docs, mobile) use 16 px.

## 6. Shape, space, depth

- Corners echo the logo's soft blocks: `radius-md` 10 controls, `radius-lg` 16 cards and panels, `radius-xl` 24 brand blocks and sheets, `radius-pill` status pills and round call buttons.
- 4 px base grid, eight steps `space-1 … space-16`. If a layout needs 13 px, fix the layout, not the scale.
- Depth is quiet: `shadow-raised` for panels, `shadow-overlay` for dialogs and the incoming-call toast. **`shadow-extrude`** (hard 6 px offset in red-700) is the brand's signature for marketing tiles, slide covers and the login screen — never in working UI.

## 7. Icons

Line icons, 24 px grid, 1.75 stroke, round caps and joins. Reference set: **Lucide** (ISC licence) or **Phosphor Regular**; the system's `Icon` component holds the call-specific set (phone, mic, mic-off, pause, transfer, keypad, record). Icons never stand alone except in the round call buttons, which carry `aria-label`. Directional icons (arrows, transfer) mirror in RTL; the phone handset does not.

## 8. Motion

Three durations (`duration-fast` 120 ms, `duration-base` 200 ms, `duration-slow` 320 ms) and one easing (`ease-standard`). Motion only explains a change: the call panel slides in, a pill changes colour. Nothing loops, blinks or pulses — including incoming calls (use sound and the native call screen instead). `prefers-reduced-motion` removes all movement.

## 9. Components in this system

Button, StatusPill, CallPanel, DialPad, KpiTile, TextField (plus `Icon`) live in `components/bundle.js` as `window.MiraVoice` (React 18 reference implementation). They define the look; the production Vue 3 and Flutter components must match them token for token. Each component page shows its guidelines and a live preview in light and dark.
