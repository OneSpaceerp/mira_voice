# tests/

Cross-component tests. Unit tests live next to their code (`core/tests`, `desk/src/**/*.spec.ts`, `phone/test`).

| Folder | What |
| --- | --- |
| [sipp/](sipp/) | SIPp call and load scenarios (pilot hardening: 2× peak calls) |
| [e2e/](e2e/) | Playwright end-to-end tests for Mira Desk |
| [integration/](integration/) | Mira Core ↔ Asterisk / Kamailio / Mira Connect tests |
