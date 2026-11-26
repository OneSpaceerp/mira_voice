# 0011: Mira Desk foundations and the Mira Flow visual builder

- Status: accepted (stage 3 of task 1.4)
- Date: 2026-11-26
- Task: 1.4 (BUILD_GUIDE)

## Context
Mira Desk is the first screen people use, so it sets the patterns for every later screen: agent desk, Mira Pulse and admin. Its first job is the Mira Flow builder: tenant admins draw an IVR from the `mira-flow/1` steps (ADR 0009) and publish it to the engine (ADR 0010).

Constraints:
- Trilingual with RTL.
- Design tokens only.
- WCAG 2.2 AA. 2.5.7 "Dragging movements" means every drag needs a non-drag alternative.
- Mira Server may have no internet, so nothing can load from a CDN.
- One person maintains the code.

## Decision

### 1. Scaffold and libraries
- Vue 3 + TypeScript (strict), scaffolded with create-vue 3.24. TypeScript 6.0, not 7: vue-tsc still needs the JS compiler API.
- vue-router and vue-i18n (composition mode).
- No UI kit. A small set of `mv-*` classes in `src/styles/app.css` is built only from `tokens.css`. A kit would bring its own colours, spacing and fonts, and the token rule forbids that.
- Fonts are self-hosted with @fontsource, icons come from lucide.
- Exact versions are in `docs/stack-versions.md`.

### 2. Canvas: Vue Flow
- **Vue Flow** (`@vue-flow/core`, MIT): the Vue-native node-graph library, with custom nodes, `Handle` ports and pan/zoom. Rete.js and Drawflow were the alternatives. Vue Flow has typed APIs, maintained releases and the largest documentation.
- The canvas is drawn left-to-right even in Arabic. A graph has no reading direction, and mirroring it would turn the same flow into a different picture for different users. Everything around the canvas (rail, palette, inspector, text) mirrors.

### 3. The canvas is optional (accessibility)
Everything the canvas does, the forms can also do:
- Each output has a **"Then" select**: an existing step, or "New step: <type>", which creates and links it.
- The palette adds a step below the selected one and links it.
- A **step picker** in the toolbar selects any step.
- Arrow keys move the selected step (Shift for bigger moves), and Ctrl+S saves.

So the end-to-end test builds and publishes a complete flow without dragging anything.

### 4. Drafts may be unfinished
- `PUT /flows/{id}` stores the draft even when steps are incomplete: no prompt yet, or an unlinked output. It returns the problems as a report (`<step>: <field>: <message>`). The editor saves early and often, and lists the problems so each one opens its step.
- Limits still apply to drafts: at most 200 steps and 256 KB.
- `publish` still runs full validation and refuses with the same report. Calls only ever run validated, immutable versions (ADR 0009 is unchanged).

### 5. Session
- The access token lives in `sessionStorage`: shared PCs in contact centres must not keep a session after the browser closes.
- Theme and language are remembered in `localStorage`.

## Consequences
- Every later Desk screen reuses the shell, `mv-*` classes, i18n typing (a missing Arabic or French key fails `vue-tsc`) and the e2e runner `tests/integration/desk/run.sh`.
- Layout widths for the rail, inspector and palette are fixed component dimensions in px. They aren't on the spacing scale, which governs gaps and padding. If more screens need them, they become tokens.
- The queue step can be drawn now but only routes once queues exist (task 1.5).
- The PWA parts (manifest, service worker, push) come in their own task. This stage is a plain SPA served by `vite preview` in tests.
