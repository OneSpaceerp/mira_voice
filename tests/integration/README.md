# tests/integration/

Tests that run Mira against real services on the test server (Ubuntu 24.04 or 26.04 with Mira installed). Run as root.

| Folder | What | Run |
| --- | --- | --- |
| `install/` | install checks; uninstall, purge, then a fresh install | `bash install/verify-install.sh` |
| `telephony/` | real SIP/WebRTC calls with baresip and Chromium: extensions, trunks, call events, Mira Flow IVR | `bash telephony/run-tests.sh` |
| `design/` | design tokens in a real browser (themes, RTL, reduced motion, focus) | `npx playwright test` |
| `desk/` | Mira Desk in a real browser against the installed site (https://127.0.0.1, nginx) and Core: flow builder by keyboard, problems, Arabic RTL, axe in light and dark | `bash desk/run.sh` |

The browser suites need Node 24 (nvm, see `docs/stack-versions.md`). Every suite uses a throw-away tenant and deletes it afterwards.
