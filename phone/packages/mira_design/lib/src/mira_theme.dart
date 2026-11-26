import 'package:flutter/material.dart';

import 'mira_tokens.g.dart';

/// Material 3 [ThemeData] for Mira Phone, built only from Mira tokens.
///
/// Colour mapping (design-system/2-token-architecture.md): `mira-red` -> primary,
/// `surface` -> surface, `danger` -> error. Secondary is neutral ink, not a second brand
/// colour: one red thing per screen.
abstract final class MiraTheme {
  static ThemeData light({bool arabic = false}) =>
      build(MiraTokens.light, Brightness.light, arabic: arabic);

  static ThemeData dark({bool arabic = false}) =>
      build(MiraTokens.dark, Brightness.dark, arabic: arabic);

  static ColorScheme colorScheme(MiraTokens t, Brightness brightness) {
    return ColorScheme(
      brightness: brightness,
      primary: t.miraRed,
      onPrimary: t.onRed,
      primaryContainer: t.miraRedSoft,
      onPrimaryContainer: t.ink,
      secondary: t.ink,
      onSecondary: t.surface,
      secondaryContainer: t.bone,
      onSecondaryContainer: t.ink,
      tertiary: t.stateHold,
      onTertiary: t.surface,
      tertiaryContainer: t.stateHoldSoft,
      onTertiaryContainer: t.stateHold,
      error: t.danger,
      onError: t.surface,
      errorContainer: t.dangerSoft,
      onErrorContainer: t.danger,
      surface: t.surface,
      onSurface: t.ink,
      onSurfaceVariant: t.inkMuted,
      surfaceContainerLowest: t.surfaceRaised,
      surfaceContainerLow: t.surfaceRaised,
      surfaceContainer: t.surfaceRaised,
      surfaceContainerHigh: t.surfaceSunken,
      surfaceContainerHighest: t.bone,
      outline: t.lineStrong,
      outlineVariant: t.line,
      inverseSurface: t.ink,
      onInverseSurface: t.surface,
      inversePrimary: t.miraRedSoft,
      shadow: t.ink,
      scrim: t.ink,
      // Mira surfaces are flat colours; no Material 3 tint on elevation.
      surfaceTint: Colors.transparent,
    );
  }

  /// Text roles -> Mira type styles. [arabic] uses the Arabic family and Arabic sizes.
  static TextTheme textTheme(Color ink, {bool arabic = false}) {
    final theme = TextTheme(
      displayLarge: MiraTextStyles.displayXl,
      displayMedium: MiraTextStyles.displayL,
      headlineSmall: MiraTextStyles.lead,
      titleLarge: arabic ? MiraTextStyles.arTitle : MiraTextStyles.title,
      titleMedium: MiraTextStyles.heading,
      titleSmall: MiraTextStyles.bodyStrong,
      bodyLarge: MiraTextStyles.bodyL,
      bodyMedium: arabic ? MiraTextStyles.arBody : MiraTextStyles.body,
      bodySmall: arabic ? MiraTextStyles.arCaption : MiraTextStyles.caption,
      labelLarge: MiraTextStyles.bodyStrong,
      labelMedium: MiraTextStyles.label,
      labelSmall: MiraTextStyles.overline,
    );
    return theme.apply(
      bodyColor: ink,
      displayColor: ink,
      fontFamily: arabic ? MiraFonts.arabic : null,
    );
  }

  static ThemeData build(MiraTokens t, Brightness brightness, {bool arabic = false}) {
    final scheme = colorScheme(t, brightness);
    final text = textTheme(t.ink, arabic: arabic);
    final controlShape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(MiraRadius.md));
    // Mobile: primary actions use the large control height; never below the touch minimum.
    const buttonMin = Size(MiraSize.touchMin, MiraSize.controlLg);
    final labelStyle = arabic
        ? MiraTextStyles.bodyStrong.copyWith(fontFamily: MiraFonts.arabic)
        : MiraTextStyles.bodyStrong;

    OutlineInputBorder inputBorder(Color color, double width) => OutlineInputBorder(
      borderRadius: BorderRadius.circular(MiraRadius.md),
      borderSide: BorderSide(color: color, width: width),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      textTheme: text,
      fontFamily: arabic ? MiraFonts.arabic : MiraFonts.sans,
      scaffoldBackgroundColor: t.surface,
      canvasColor: t.surface,
      dividerColor: t.line,
      focusColor: t.focusRing,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      extensions: <ThemeExtension<dynamic>>[t],
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: t.buttonPrimaryBg,
          foregroundColor: t.buttonPrimaryFg,
          minimumSize: buttonMin,
          shape: controlShape,
          textStyle: labelStyle,
          animationDuration: MiraDuration.fast,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          backgroundColor: t.buttonSecondaryBg,
          foregroundColor: t.buttonSecondaryFg,
          side: BorderSide(color: t.buttonSecondaryBorder),
          minimumSize: buttonMin,
          shape: controlShape,
          textStyle: labelStyle,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: t.ink,
          minimumSize: buttonMin,
          shape: controlShape,
          textStyle: labelStyle,
        ),
      ),
      inputDecorationTheme: InputDecorationThemeData(
        filled: true,
        fillColor: t.inputBg,
        hintStyle: MiraTextStyles.body.copyWith(color: t.inputPlaceholder),
        border: inputBorder(t.inputBorder, 1),
        enabledBorder: inputBorder(t.inputBorder, 1),
        focusedBorder: inputBorder(t.inputBorderFocus, 2),
        errorBorder: inputBorder(t.danger, 1),
        focusedErrorBorder: inputBorder(t.danger, 2),
        errorStyle: MiraTextStyles.caption.copyWith(color: t.danger),
        contentPadding: const EdgeInsetsDirectional.symmetric(
          horizontal: MiraSpace.space4,
          vertical: MiraSpace.space3,
        ),
        constraints: const BoxConstraints(minHeight: MiraSize.controlLg),
      ),
      cardTheme: CardThemeData(
        color: t.surfaceRaised,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(MiraRadius.lg),
          side: BorderSide(color: t.line),
        ),
      ),
      dividerTheme: DividerThemeData(color: t.line, thickness: 1, space: 1),
    );
  }
}
