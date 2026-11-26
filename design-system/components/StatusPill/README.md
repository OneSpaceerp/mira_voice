# StatusPill

Shows an agent's or a call's state as a coloured pill with a dot and a word — colour is never the only cue.

| status | Tone | Meaning |
| --- | --- | --- |
| `available` | state-live (green) | Logged in and ready for calls |
| `ringing` | state-ringing (amber, ringed dot) | A call is being offered |
| `on-call` | mira-red fill | Talking — the only pill allowed to be red |
| `hold` | state-hold (blue) | Caller on hold |
| `wrap-up` | state-hold (blue) | After-call work; show the countdown in `timer` |
| `break` | state-offline (hollow dot) | Not-ready with a reason code |
| `offline` | state-offline (hollow dot) | Logged out / device unregistered |

`lang` gives built-in labels in English, Arabic and French. Pass `label` for a reason code ("Break · Prayer", "Break · Training"). `timer` is monospaced so it does not jitter.

Use it in the Mira Desk top bar (own status, clickable to change), agent tables and wallboards. Never animate it beyond a single colour transition (`duration-base`): no blinking.
