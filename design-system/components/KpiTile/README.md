# KpiTile

One number that a supervisor acts on, with its target and a status word.

- `status`: `ok` (state-live), `warn` (state-ringing tint), `bad` (danger tint). The word ("On target", "At risk", "Below target") always shows; colour is never alone.
- `size="wallboard"` is the TV version: always dark (`wallboard-bg`), number in the display face at 96 px, readable from 5 m. Use 4–6 tiles per screen, no charts smaller than a third of the screen.
- Numbers are monospaced in apps so live values do not jump.
- Definitions are fixed in the study's KPI catalogue (service level, abandon rate, ASA, AHT…); never rename a KPI per customer.

No pulsing or flashing when a KPI turns bad — a calm colour change is enough (see Accessibility and agent wellbeing).
