# Product patterns

**Five surfaces, one system.** Each pattern below says what the screen is for, how it is laid out, and which components it uses.

## Mira Desk — agent desktop (web and Windows/macOS app)

Three zones on a 12-column grid, 1280 px minimum design width:

1. **Navigation rail** (`sidebar` 240 px, collapsible to 64 px): Calls, Contacts, Campaigns, Chats, History, Reports.
2. **Work area**: the ERPNext / Frappe CRM record, chat thread or campaign list the agent is working on.
3. **Call panel** (`call-panel` 360 px) docked on the end side: StatusPill for own state at the top, CallPanel during a call, queue list and missed calls when idle.

Incoming calls show a toast (`shadow-overlay`) on top of whatever is open, with Answer and Decline; answering opens the CallPanel and the caller's ERPNext record side by side. After hang-up the panel switches to the disposition form (wrap-up countdown in the pill).

## Mira Phone — mobile softphone (iOS, Android)

Follows Apple's Human Interface Guidelines and Material 3 platform conventions rather than a custom chrome:

- Incoming calls use **CallKit** (iOS) and **ConnectionService** (Android) first, so calls ring on the lock screen like any phone call; Mira's own CallPanel appears when the app is open.
- Tab bar with at most 5 items: Keypad, Recents, Contacts, Chats, Me (status).
- Touch targets ≥ 44 pt; dial keys 72 px; respect safe areas and Dynamic Type; full dark mode.
- No custom glass or blur: use the platform's own materials where they exist, plain `surface-raised` elsewhere.
- The DialPad and the number are always LTR, also in Arabic.

## Wallboard (TV, Mira Pulse)

- Always the dark theme on `wallboard-bg`, regardless of the app theme.
- Bento grid of 4–6 KpiTiles (`size="wallboard"`), numbers in Archivo 96 px, labels 20 px — readable from 5 m.
- One queue per board or one board per team; the headline KPI may be red-filled (the screen's one red thing).
- No animation beyond a 200 ms colour change; auto-rotate boards at most every 30 s.

## Mira Flow — IVR / call-flow builder

- Canvas on `surface-sunken` with an 8 px dot grid; nodes are `radius-lg` cards on `surface-raised` with a 4 px top stripe by type: entry = `mira-red`, menu/collect = `state-hold`, queue = `state-live`, voicemail/hang-up = `state-offline`, HTTP / ERPNext data dip = `ink`.
- Connectors 1.5 px `line-strong` with arrowheads; the active test-call path highlights in `focus-ring` blue.
- Right inspector panel for node settings; prompts show their language chips (AR / EN / FR).

## Reports (Mira Pulse)

- Data-dense dashboard: KPI tile row, then charts, then sortable tables with sticky headers; 12-column grid, `space-4` gutters.
- Charts use `chart-1 … chart-6` in order; series 1 (red) is always "us". Legends and tooltips always on; never colour alone.
- Every table exports to Excel and PDF; scheduled reports reuse the same layouts.

## Mira Connect — inside ERPNext / Frappe CRM

- Respect Frappe Desk (v16) and Frappe CRM styles; Mira only adds: the call pop-up (red header bar when connected), click-to-call icons beside phone fields, the Call Log timeline entry with recording player, and the "Mira Voice" workspace.
- Never restyle ERPNext's own forms.

## Right-to-left

- Mirror layouts with `dir="rtl"`: navigation rail moves to the right, call panel to the left, Answer/Decline swap with the flow.
- Do not mirror: phone numbers, timers, the dial pad, media controls, charts' time axes, the phone-handset icon.
- Arabic text uses `ar-*` styles; mixed Arabic/English lines rely on IBM Plex's shared metrics; wrap embedded Latin or numbers in `<bdi>`.

## Empty, loading and error states

- Empty: one sentence + one action ("No calls waiting. Your queue is clear.").
- Loading: skeletons in `surface-sunken` for lists and tiles; never a full-screen spinner during a call.
- Error: `danger-soft` banner with icon, what happened, what Mira did about it, and one action.
