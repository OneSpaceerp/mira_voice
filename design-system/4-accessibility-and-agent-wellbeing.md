# Accessibility and agent wellbeing

**Agents sit in Mira for eight hours a day, often on shared PCs and unreliable connections; the system is designed for that worst case, which makes it better for everyone.** Targets: WCAG 2.2 AA everywhere, AAA where cheap.

## Contrast (computed from the tokens, both themes)

| Foreground | Background | Light | Dark | Needs |
| --- | --- | --- | --- | --- |
| `ink` | `surface` | 16.27:1 | 16.7:1 | 4.5:1 |
| `ink` | `surface-raised` | 18.2:1 | 15.3:1 | 4.5:1 |
| `ink` | `bone` | 14.06:1 | 13.38:1 | 4.5:1 |
| `ink-muted` | `surface` | 6.4:1 | 9.4:1 | 4.5:1 |
| `ink-muted` | `surface-raised` | 7.15:1 | 8.61:1 | 4.5:1 |
| `ink-muted` | `bone` | 5.53:1 | 7.53:1 | 4.5:1 |
| `ink-subtle` | `surface` | 4.96:1 | 5.09:1 | 4.5:1 |
| `ink-subtle` | `surface-raised` | 5.55:1 | 4.66:1 | 4.5:1 |
| `mira-red-text` | `surface` | 5.88:1 | 8.86:1 | 4.5:1 |
| `mira-red-text` | `surface-raised` | 6.58:1 | 8.12:1 | 4.5:1 |
| `on-red` | `mira-red` | 6.58:1 | 6.58:1 | 4.5:1 |
| `on-red` | `mira-red-hover` | 8.49:1 | 8.49:1 | 4.5:1 |
| `ink` | `mira-red-soft` | 15.1:1 | 14.09:1 | 4.5:1 |
| `state-live` | `surface` | 6.56:1 | 9.88:1 | 4.5:1 |
| `state-live` | `state-live-soft` | 6.23:1 | 7.77:1 | 4.5:1 |
| `on-red` | `state-live-strong` | 5.19:1 | 5.19:1 | 4.5:1 |
| `state-ringing` | `surface` | 7.13:1 | 9.01:1 | 4.5:1 |
| `state-ringing` | `state-ringing-soft` | 6.63:1 | 7.37:1 | 4.5:1 |
| `state-hold` | `surface` | 7.13:1 | 9.3:1 | 4.5:1 |
| `state-hold` | `state-hold-soft` | 6.68:1 | 7.56:1 | 4.5:1 |
| `state-offline` | `surface` | 6.4:1 | 9.4:1 | 4.5:1 |
| `state-offline` | `state-offline-soft` | 5.53:1 | 7.53:1 | 4.5:1 |
| `danger` | `surface` | 7.38:1 | 8.93:1 | 4.5:1 |
| `danger` | `danger-soft` | 6.88:1 | 7.41:1 | 4.5:1 |
| `line-strong` | `surface` | 3.28:1 | 3.36:1 | 3:1 |
| `line-strong` | `surface-raised` | 3.67:1 | 3.08:1 | 3:1 |
| `focus-ring` | `surface` | 5.02:1 | 6.69:1 | 3:1 |
| `focus-ring` | `surface-raised` | 5.61:1 | 6.13:1 | 3:1 |
| `mira-red` | `surface` | 5.88:1 | 2.84:1 ⚠ | 3:1 |
| `ink` | `callpanel-bar-ringing` | 15.15:1 | 13.65:1 | 4.5:1 |
| `ink` | `callpanel-bar-hold` | 15.26:1 | 13.56:1 | 4.5:1 |
| `dialkey-letters` | `bone` | 5.53:1 | 7.53:1 | 4.5:1 |
| `chart-1` | `surface-raised` | 6.58:1 | 5.64:1 | 3:1 |
| `chart-3` | `surface-raised` | 5.61:1 | 6.13:1 | 3:1 |
| `chart-4` | `surface-raised` | 4.09:1 | 8.26:1 | 3:1 |
| `chart-5` | `surface-raised` | 5.19:1 | 6.58:1 | 3:1 |
| `chart-6` | `surface-raised` | 3.67:1 | 3.08:1 | 3:1 |

⚠ `mira-red` as a fill on the dark page is 2.8:1. It is allowed because every red control carries a white label at 6.6:1; never use an outline-only red control in dark.

## Calm, not alarming (from design-justice)

- **No flashing, pulsing or shaking** anywhere — not for incoming calls, breached SLAs or errors. Use sound, the native call screen and a single colour change.
- Errors use terracotta `danger` with an icon and plain words, never the brand red alone.
- KPI tiles that go bad change tint and say "Below target"; they do not blink.
- Plain language at about a 6th–8th grade reading level in all three languages.
- Wrap-up time is shown as a calm countdown in the status pill, not a red timer.

## Shared workstations and privacy

- Agents often share a PC between shifts: "Remember me" is off by default, logout is always visible in the top bar, and the session ends with a 60-second warning after the shift's idle limit.
- No customer data cached in the browser after logout; recordings stream through short-lived signed URLs and are never downloaded by default.
- Supervisor views of other agents never show the customer card, only state and timers.

## Flaky networks

- The softphone shows its connection state at all times: Connected / Reconnecting… / Offline, with the reason ("Microphone blocked", "Network lost").
- Dispositions and notes save locally on every change and sync when the connection returns ("Saved on this device · syncing").
- If WebRTC drops mid-call, the panel says so and offers "Call me back on my mobile" through the GSM gateway or trunk.

## Keyboard and screen readers

- Every action in Mira Desk has a shortcut: **A** answer, **H** hold, **M** mute, **T** transfer, **K** keypad, **Esc** close; shown in tooltips and in a "?" sheet.
- Focus ring: 2 px `focus-ring` blue with a 2 px gap, never removed.
- Status changes are announced (`role="status"`); round call buttons carry `aria-label`; the call timer is not announced every second.
- Touch targets ≥ 44 px (`touch-min`); dial keys 72 px; call buttons 64 px.
- Respect `prefers-reduced-motion`, OS text size (Dynamic Type on iOS, font scale on Android) and high-contrast modes.
