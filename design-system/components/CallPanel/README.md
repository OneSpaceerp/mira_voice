# CallPanel

The docked panel in Mira Desk (right side, `call-panel` = 360 px) and the in-app call screen on Mira Phone; it is the most-used surface in the product.

**States:** `ringing` (amber bar, Decline + Answer), `connected` (red bar — the brand moment — with Mute, Hold, Transfer, Keypad and Hang up), `hold` (blue bar). Mute and Hold toggle and show their ON state with `call-control-on-*`.

**Anatomy:** state bar (state, queue, timer) → caller name and number (number always LTR, monospaced) → ERPNext customer card (`fields`: 2–4 facts the agent needs before saying hello: customer, balance, open issue, last order) → controls.

**Rules**
- Answer is green and on the end side, Decline/Hang up is red and on the start side, matching iOS and Android call screens. They swap automatically in RTL.
- Round call buttons are 64 px; every control is at least 44 px tall.
- The panel never covers the ERPNext record the agent is reading; it docks beside it.
- On mobile, incoming calls use the native CallKit / ConnectionService screen first; this panel appears once the app is open.

The consumer provides: caller data, timer string, the customer-card fields from Mira Connect, and handlers for each action.
