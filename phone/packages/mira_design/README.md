# mira_design (Flutter)

Mira Voice tokens and Material 3 theme for **Mira Phone**. `lib/src/mira_tokens.g.dart` is generated from `design-system/tokens.json` — never edit it; change the JSON and run `node design-system/tools/build-tokens.mjs` from the repo root.

- `MiraTheme.light()` / `MiraTheme.dark()` — `ThemeData` (Material 3). `arabic: true` switches to IBM Plex Sans Arabic and the Arabic type sizes.
- `MiraTokens.of(context)` — every semantic and component colour (`miraRed`, `stateLive`, `callAnswerBg`, …) for the current theme. Primitives are not exposed on purpose.
- `MiraSpace`, `MiraRadius`, `MiraSize`, `MiraDuration`, `MiraEasing`, `MiraTextStyles`, `MiraFonts` — the scales.

Rules (design-system/2-token-architecture.md): tokens only, no raw colours; `EdgeInsetsDirectional` / `AlignmentDirectional` everywhere for RTL; phone numbers, timers and the dial pad stay LTR (`Directionality(textDirection: TextDirection.ltr, …)`); one red thing per screen.

Fonts (IBM Plex Sans, IBM Plex Sans Arabic, IBM Plex Mono, Archivo — all SIL OFL) are bundled by the Mira Phone app in Phase 3; until then Flutter falls back to the platform font.

```bash
cd phone/packages/mira_design
flutter pub get && flutter analyze && flutter test
```
