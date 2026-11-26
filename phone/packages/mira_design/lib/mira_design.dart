/// Mira Voice design system for Flutter (Mira Phone).
///
/// ```dart
/// MaterialApp(
///   theme: MiraTheme.light(),
///   darkTheme: MiraTheme.dark(),
///   themeMode: ThemeMode.system,
/// );
/// // in a widget:
/// final mira = MiraTokens.of(context);
/// Container(color: mira.callAnswerBg, padding: const EdgeInsetsDirectional.all(MiraSpace.space4));
/// ```
library;

export 'src/mira_theme.dart';
export 'src/mira_tokens.g.dart';
