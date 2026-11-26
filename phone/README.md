# phone/ — Mira Phone

Flutter mobile softphone for Android and iOS: `sip_ua` (dart-sip-ua) + flutter-webrtc, CallKit / ConnectionService, push wake-up through Mira Core's own gateway. Open-source SDKs only.

Conventions: `flutter analyze`, `flutter test`; `EdgeInsetsDirectional` for RTL; state management (Riverpod or Bloc) chosen in Phase 3 and recorded in an ADR.

Theme: package [packages/mira_design](packages/mira_design/) (task 0.5, ADR 0005) — `MiraTheme.light()/dark(arabic:)` and the `MiraTokens` ThemeExtension, generated from `design-system/tokens.json`. The app itself is Phase 3.
