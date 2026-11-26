# DialPad

A 3×4 keypad with a display, delete button and a call button, for Mira Phone and the Mira Desk keypad popover.

- Keys are 72 px circles in `dialkey-bg` (bone) — the logo's off-white — with ABC letters in `dialkey-letters`.
- The pad and the number are **always left-to-right**, also in Arabic and RTL layouts; Western Arabic digits (0–9) are used for numbers.
- During a call the same pad sends DTMF tones (IVR navigation); then hide the call button.
- Long-press 0 types `+`. Paste is accepted and cleaned (spaces and dashes removed).

The consumer provides `onCall` (and `onChange` if the number is needed elsewhere, e.g. contact search as you type).
