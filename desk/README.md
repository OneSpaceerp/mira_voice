# desk/ — Mira Desk

Installable PWA, Vue 3 + TypeScript + Vite: agent desk, Mira Flow (IVR builder), Mira Pulse (reports and wallboards), admin, and the WebRTC softphone. Covers Windows and macOS desktops (ADR 0002).

Conventions: TypeScript strict, ESLint + oxlint + Prettier, Vitest, Playwright. Design tokens only (`design-system/`), AR/EN/FR strings, RTL with logical CSS properties; phone numbers, timers and the dial pad stay LTR. Decisions: ADR 0005 (tokens), ADR 0011 (Desk foundations, the flow builder).

## What is here (task 1.4)

- Sign in, a shell with the rail (tenant, language, theme), **Call flows**, the **flow editor**, **Prompts**.
- Flow editor: palette | canvas (Vue Flow) | inspector, plus problems and versions. Everything works without the mouse: "Then" selects create and link steps, the toolbar's step picker selects any step, arrow keys move it, Ctrl+S saves. Drafts save unfinished; Publish validates.

| Folder | What |
| --- | --- |
| `src/api/` | `http.ts` (token in sessionStorage, errors), `mira.ts` (Mira Core endpoints), `types.ts` |
| `src/i18n/` | `en.ts` (master), `ar.ts`, `fr.ts` — typed against English, so a missing key fails the type check |
| `src/flow/` | `nodeTypes.ts` (steps, outputs, links), `graph.ts` (add/remove/rename/layout, draft export) |
| `src/components/`, `src/views/` | shell, canvas, node card, inspector; pages |
| `src/styles/` | generated `tokens.css` / `tokens.ts`, `base.css`, `app.css` (`mv-*` classes) |
| `e2e/` | Playwright browser tests against a real Mira Core |

## Commands

```bash
npm ci
npm run dev            # http://localhost:5173, /api proxied to MIRA_CORE_URL (default http://127.0.0.1:8000)
npm run build          # vue-tsc + vite build -> dist/
npm run test:unit -- --run
npm run lint
```

On Windows run Vitest from PowerShell, not Git Bash (see docs/stack-versions.md).

Browser tests need a running Mira Core with a tenant. On the test server:

```bash
sudo bash tests/integration/desk/run.sh
```

It creates a throw-away tenant, admin and prompt, builds the Desk outside the source tree, runs `e2e/` (build and publish by keyboard, problems panel, Arabic RTL, axe in light and dark) and deletes the tenant.
