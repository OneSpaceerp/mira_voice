# Button

Use a button for an action; use a link for navigation.

| Variant | Token | Use |
| --- | --- | --- |
| `primary` | `button-primary-bg` (mira-red) | The one thing this view is for: Answer next call, Start campaign, Save flow. **Max one per view.** |
| `secondary` | `button-secondary-*` | Every other action. The default. |
| `ghost` | ink on transparent | Cancel, toolbars, table row actions. |
| `danger` | `button-danger-*` (terracotta) | End campaign, delete IVR flow, force-logout agent. Always followed by a confirmation that names what will happen. |

Sizes: `sm` 32 px (tables), `md` 40 px (desktop default), `lg` 48 px (touch, mobile). On any touch screen use `lg` or keep the hit area ≥ `touch-min` (44 px).

**Labels:** verb first, sentence case, 1–3 words: "Transfer", "Export report". Same verbs in Arabic ("تحويل") and French ("Transférer"). Icons only alongside a label, except the round call buttons.

**Don't:** put two primary buttons side by side; use red for a destructive action (that is `danger`); disable a button without a hint explaining why.

The consumer provides: the label, the click handler, and any loading state (show a spinner inside and keep the width).
