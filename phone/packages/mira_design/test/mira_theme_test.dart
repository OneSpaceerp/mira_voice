import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mira_design/mira_design.dart';

/// WCAG 2.2 contrast ratio.
double contrast(Color a, Color b) {
  double lin(double c) => c <= 0.04045 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4).toDouble();
  double lum(Color c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  final l1 = lum(a), l2 = lum(b);
  return (math.max(l1, l2) + 0.05) / (math.min(l1, l2) + 0.05);
}

void main() {
  group('tokens', () {
    test('brand red is exactly #BE0007 in both themes', () {
      expect(MiraTokens.light.miraRed, const Color(0xFFBE0007));
      expect(MiraTokens.dark.miraRed, const Color(0xFFBE0007));
    });

    test('light and dark differ where the design says they should', () {
      expect(MiraTokens.light.surface, isNot(MiraTokens.dark.surface));
      expect(MiraTokens.light.ink, isNot(MiraTokens.dark.ink));
      // the wallboard is always dark
      expect(MiraTokens.light.wallboardBg, MiraTokens.dark.wallboardBg);
    });

    test('lerp goes from one theme to the other', () {
      const a = MiraTokens.light, b = MiraTokens.dark;
      expect(a.lerp(b, 0).surface, a.surface);
      expect(a.lerp(b, 1).surface, b.surface);
      expect(a.lerp(b, 1).shadowRaised, b.shadowRaised);
      expect(a.lerp(b, 0.25).shadowRaised, a.shadowRaised); // shadows switch at the midpoint
      expect(a.lerp(null, 0.5), same(a));
    });

    test('copyWith replaces only what is given', () {
      final c = MiraTokens.light.copyWith(ink: MiraTokens.dark.ink);
      expect(c.ink, MiraTokens.dark.ink);
      expect(c.surface, MiraTokens.light.surface);
    });

    test('scales match the token file', () {
      expect(MiraSpace.space4, 16);
      expect(MiraRadius.md, 10);
      expect(MiraSize.touchMin, 44);
      expect(MiraSize.callButton, 64);
      expect(MiraDuration.slow, const Duration(milliseconds: 320));
      expect(MiraTextStyles.body.fontSize, 14);
      expect(MiraTextStyles.arBody.fontFamily, MiraFonts.arabic);
      expect(MiraTextStyles.timer.fontFamily, MiraFonts.mono);
    });
  });

  for (final (name, theme, tokens) in [
    ('light', MiraTheme.light(), MiraTokens.light),
    ('dark', MiraTheme.dark(), MiraTokens.dark),
  ]) {
    group('$name theme', () {
      test('carries the tokens and maps the colour scheme as documented', () {
        expect(theme.extension<MiraTokens>(), same(tokens));
        expect(theme.colorScheme.primary, tokens.miraRed);
        expect(theme.colorScheme.surface, tokens.surface);
        expect(theme.colorScheme.error, tokens.danger);
        expect(theme.scaffoldBackgroundColor, tokens.surface);
        expect(theme.useMaterial3, isTrue);
      });

      test('every "on" colour of the scheme is readable (>= 4.5:1)', () {
        final s = theme.colorScheme;
        final pairs = <String, (Color, Color)>{
          'onPrimary/primary': (s.onPrimary, s.primary),
          'onPrimaryContainer/primaryContainer': (s.onPrimaryContainer, s.primaryContainer),
          'onSecondary/secondary': (s.onSecondary, s.secondary),
          'onTertiary/tertiary': (s.onTertiary, s.tertiary),
          'onTertiaryContainer/tertiaryContainer': (s.onTertiaryContainer, s.tertiaryContainer),
          'onError/error': (s.onError, s.error),
          'onErrorContainer/errorContainer': (s.onErrorContainer, s.errorContainer),
          'onSurface/surface': (s.onSurface, s.surface),
          'onSurfaceVariant/surface': (s.onSurfaceVariant, s.surface),
          'onInverseSurface/inverseSurface': (s.onInverseSurface, s.inverseSurface),
        };
        pairs.forEach((label, pair) {
          expect(contrast(pair.$1, pair.$2), greaterThanOrEqualTo(4.5), reason: '$label in $name');
        });
      });

      test('buttons meet the touch minimum', () {
        final min = theme.filledButtonTheme.style!.minimumSize!.resolve({})!;
        expect(min.height, greaterThanOrEqualTo(MiraSize.touchMin));
      });
    });
  }

  test('Arabic theme uses the Arabic family and sizes', () {
    final ar = MiraTheme.light(arabic: true);
    expect(ar.textTheme.bodyMedium!.fontFamily, MiraFonts.arabic);
    expect(ar.textTheme.bodyMedium!.fontSize, MiraTextStyles.arBody.fontSize);
    expect(ar.textTheme.titleLarge!.fontSize, MiraTextStyles.arTitle.fontSize);
  });

  testWidgets('renders a right-to-left screen with Mira widgets', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: MiraTheme.light(arabic: true),
        darkTheme: MiraTheme.dark(arabic: true),
        locale: const Locale('ar'),
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: Scaffold(
            body: Builder(
              builder: (context) {
                final mira = MiraTokens.of(context);
                return Padding(
                  padding: const EdgeInsetsDirectional.all(MiraSpace.space4),
                  child: Column(
                    children: [
                      FilledButton(onPressed: () {}, child: const Text('رد')),
                      // phone numbers stay LTR inside RTL screens
                      const Directionality(
                        textDirection: TextDirection.ltr,
                        child: Text('+20 100 123 4567'),
                      ),
                      Container(
                        key: const Key('answer'),
                        width: MiraSize.callButton,
                        height: MiraSize.callButton,
                        decoration: BoxDecoration(color: mira.callAnswerBg, shape: BoxShape.circle),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
    expect(find.text('رد'), findsOneWidget);
    expect(tester.getSize(find.byKey(const Key('answer'))), const Size(64, 64));
    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button, isNotNull);
    expect(Theme.of(tester.element(find.text('رد'))).colorScheme.primary, MiraTokens.light.miraRed);
  });
}
