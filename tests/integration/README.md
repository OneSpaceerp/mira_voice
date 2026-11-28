# tests/integration/

Tests that run Mira against real services on the test server (Ubuntu 24.04 or 26.04 with Mira installed). Run as root.

| Folder | What | Run |
| --- | --- | --- |
| `install/` | install checks; uninstall, purge, then a fresh install | `bash install/verify-install.sh` |
| `telephony/` | real SIP/WebRTC calls with baresip and Chromium: extensions, trunks, call events, Mira Flow IVR | `bash telephony/run-tests.sh` |
| `design/` | design tokens in a real browser (themes, RTL, reduced motion, focus) | `npx playwright test` |
| `desk/` | Mira Desk in a real browser against the installed site (https://127.0.0.1, nginx) and Core: flow builder by keyboard, problems, Arabic RTL, axe in light and dark | `bash desk/run.sh` |

The browser suites need Node 24 (nvm, see `docs/stack-versions.md`). Every suite uses a throw-away tenant and deletes it afterwards.

## Known limits of the test machines

- **Ubuntu 26.04's `baresip-core` (1.1.0) answers `404 Not Found` to INVITEs for an account that does not register** (`regint=0`); registered test phones work. The fake carrier in `telephony/trunk-calls.sh` (section 4, outbound failover) is a baresip phone, so on a 26.04 test machine the carrier hears nothing and the outbound call record is missing: 3 checks fail although Mira sends the right INVITE (verified with `pjsip set logger on`: dead carrier tried, failover, correct caller ID). Mira runs in containers, so the host's Ubuntu version does not change this path: run the trunk test on a 24.04 test machine, where baresip answers.
- **WSL test machines:** WSL shuts an idle distro down seconds after the last command (Docker and Mira stop with it); start long runs in one `wsl.exe` call, or keep the distro awake (`wsl -d NAME -- sleep 14400 &`) and wait until every service is healthy. If the host sleeps during a run, the clock jumps on wake and the API's sign-in tokens look expired (401): rerun what failed.
