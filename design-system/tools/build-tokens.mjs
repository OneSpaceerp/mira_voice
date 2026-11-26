#!/usr/bin/env node
// Mira Voice — design token build. ONE source: design-system/tokens.json.
//
//   node design-system/tools/build-tokens.mjs           write all generated files
//   node design-system/tools/build-tokens.mjs --check   fail if any generated file is out of date
//
// Generates:
//   design-system/tokens.css                      CSS custom properties (light, dark, follow-OS)
//   desk/src/styles/tokens.css                    same file, for Mira Desk (Vue)
//   desk/src/styles/tokens.ts                     typed token names + helpers for Vue/TS code
//   phone/packages/mira_design/lib/src/mira_tokens.g.dart   Flutter ThemeExtension + constants
//
// No dependencies (Node >= 20). Colour maths: OKLCH -> sRGB per CSS Color 4; contrast per WCAG 2.2.

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const PRIMITIVE_FAMILIES = ['red', 'green', 'amber', 'blue', 'clay', 'neutral']

// ---------------------------------------------------------------- loading / resolving

export function loadTokens(path = join(ROOT, 'design-system/tokens.json')) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

export const isPrimitive = (name) => PRIMITIVE_FAMILIES.includes(name.split('-')[0])

/** Colour tokens split into primitives (one value) and themed tokens ({light, dark}). */
export function colorTables(tokens) {
  const all = new Map(tokens.color.tokens.map((t) => [t.name, t]))
  const primitives = tokens.color.tokens.filter((t) => isPrimitive(t.name))
  // Semantic tokens carry {light, dark}; component tokens usually one reference ("{mira-red}")
  // that follows the theme through what it points to. Normalise both to {light, dark}.
  const themed = tokens.color.tokens
    .filter((t) => !isPrimitive(t.name))
    .map((t) => {
      if (typeof t.value === 'string') return { ...t, value: { light: t.value, dark: t.value }, perTheme: false }
      if (!('light' in t.value) || !('dark' in t.value)) {
        throw new Error(`token ${t.name}: expected a value or {light, dark}, got ${JSON.stringify(t.value)}`)
      }
      return { ...t, perTheme: true }
    })
  for (const t of primitives) {
    if (typeof t.value !== 'string') throw new Error(`primitive ${t.name} must be a single value`)
  }
  return { all, primitives, themed }
}

/** Follow {references} until a literal value; throws on unknown names and cycles. */
export function resolveColor(all, value, theme, seen = []) {
  if (typeof value === 'object') value = value[theme]
  const ref = /^\{([a-z0-9-]+)\}$/.exec(value)
  if (!ref) return value
  const name = ref[1]
  if (seen.includes(name)) throw new Error(`reference cycle: ${[...seen, name].join(' -> ')}`)
  const target = all.get(name)
  if (!target) throw new Error(`unknown token reference {${name}}`)
  return resolveColor(all, target.value, theme, [...seen, name])
}

// ---------------------------------------------------------------- colour maths

/** "oklch(50.4% 0.206 28.5)" -> [r, g, b] in 0..1 (gamut-clipped). */
export function oklchToSrgb(css) {
  const m = /^oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)$/.exec(css)
  if (!m) throw new Error(`not an oklch() colour: ${css}`)
  const L = Number(m[1]) / 100
  const C = Number(m[2])
  const h = (Number(m[3]) * Math.PI) / 180
  const a = C * Math.cos(h)
  const b = C * Math.sin(h)
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const mm = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  const lin = [
    4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s,
  ]
  return lin.map((c) => {
    const v = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.max(c, 0) ** (1 / 2.4) - 0.055
    return Math.min(1, Math.max(0, v))
  })
}

export const toHex = (rgb) =>
  '#' + rgb.map((c) => Math.round(c * 255).toString(16).padStart(2, '0')).join('').toUpperCase()

/** Any literal colour value used in tokens.json -> [r, g, b, alpha] (0..1). */
export function parseColor(css) {
  if (css.startsWith('oklch(')) return [...oklchToSrgb(css), 1]
  let m = /^#([0-9a-f]{6})$/i.exec(css)
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255).concat(1)
  m = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)$/.exec(css)
  if (m) return [m[1] / 255, m[2] / 255, m[3] / 255, m[4] === undefined ? 1 : Number(m[4])]
  throw new Error(`unsupported colour: ${css}`)
}

export function luminance([r, g, b]) {
  const lin = (c) => {
    const c8 = Math.round(c * 255) / 255 // what the screen actually shows
    return c8 <= 0.04045 ? c8 / 12.92 : ((c8 + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

export function contrast(fg, bg) {
  const [l1, l2] = [luminance(fg), luminance(bg)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

/** The sRGB hex the design tool recorded in a primitive's usage note, e.g. "(#BE0007)". */
export const recordedHex = (token) => /\(#([0-9A-F]{6})\)/i.exec(token?.usage ?? '')?.[1]

/** Resolve a token to the primitive (or literal) it finally points at. */
function resolveToken(all, name, theme, seen = []) {
  const t = all.get(name)
  if (!t) throw new Error(`unknown token ${name}`)
  const v = typeof t.value === 'object' ? t.value[theme] : t.value
  const ref = /^\{([a-z0-9-]+)\}$/.exec(v)?.[1]
  if (!ref) return t
  if (seen.includes(ref)) throw new Error(`reference cycle: ${[...seen, ref].join(' -> ')}`)
  return resolveToken(all, ref, theme, [...seen, ref])
}

/** Resolved sRGB [r, g, b] (0..1) of a token in a theme. Uses the recorded hex of the
 *  primitive when there is one (exact brand colours), else converts the OKLCH value. */
export function rgbOf(all, name, theme) {
  const target = resolveToken(all, name, theme)
  const hex = recordedHex(target)
  if (hex) return parseColor(`#${hex}`).slice(0, 3)
  const v = typeof target.value === 'object' ? target.value[theme] : target.value
  return parseColor(v).slice(0, 3)
}

// ---------------------------------------------------------------- CSS

const HEADER = (what) =>
  `Mira Voice design tokens v2 — ${what}.\n` +
  `GENERATED by design-system/tools/build-tokens.mjs from design-system/tokens.json. Do not edit:\n` +
  `change tokens.json and run \`node design-system/tools/build-tokens.mjs\`.`

const cssRef = (value) => value.replace(/^\{([a-z0-9-]+)\}$/, 'var(--$1)')
const decl = (name, value) => `  --${name}: ${value};`

function typeVars(tokens) {
  const out = []
  for (const [fam, stack] of Object.entries(tokens.type.families)) out.push(decl(`font-${fam}`, stack))
  for (const g of tokens.type.groups) {
    for (const s of g.styles) {
      out.push(decl(`type-${s.name}-family`, `var(--font-${g.family})`))
      out.push(decl(`type-${s.name}-size`, s.fontSize))
      out.push(decl(`type-${s.name}-line`, s.lineHeight))
      out.push(decl(`type-${s.name}-weight`, String(s.fontWeight)))
      out.push(decl(`type-${s.name}-tracking`, s.letterSpacing ?? 'normal'))
    }
  }
  return out
}

function themedDecls(tokens, theme) {
  const { themed } = colorTables(tokens)
  // the dark block only needs tokens whose value differs per theme
  const out = themed.filter((t) => theme === 'light' || t.perTheme).map((t) => decl(t.name, cssRef(t.value[theme])))
  for (const s of tokens.shadow.tokens) {
    if (typeof s.value === 'object') out.push(decl(s.name, s.value[theme]))
  }
  return out
}

export function buildCss(tokens) {
  const { primitives } = colorTables(tokens)
  const scale = (group) => tokens[group].tokens.map((t) => decl(t.name, t.value))
  const constantShadows = tokens.shadow.tokens.filter((s) => typeof s.value === 'string')
  const dark = themedDecls(tokens, 'dark')
  return [
    `/* ${HEADER('CSS custom properties')}`,
    '',
    '   Theme: light by default; dark with <html data-theme="dark">, or automatically when the',
    '   OS is dark and the user has not chosen (data-theme absent). Wallboards always set dark.',
    '   Use semantic and component tokens in components — never primitives (red-600, neutral-50…). */',
    '',
    ':root,',
    '[data-theme="light"] {',
    '  color-scheme: light;',
    '  /* primitives — only for semantic tokens below */',
    ...primitives.map((t) => decl(t.name, t.value)),
    '  /* semantic + component (light) */',
    ...themedDecls(tokens, 'light'),
    ...constantShadows.map((s) => decl(s.name, s.value)),
    '  /* scales */',
    ...scale('spacing'),
    ...scale('radius'),
    ...scale('size'),
    ...scale('duration'),
    ...scale('easing'),
    '  /* typography */',
    ...typeVars(tokens),
    '}',
    '',
    '[data-theme="dark"] {',
    '  color-scheme: dark;',
    ...dark,
    '}',
    '',
    '@media (prefers-color-scheme: dark) {',
    '  :root:not([data-theme]) {',
    '    color-scheme: dark;',
    ...dark.map((l) => '  ' + l),
    '  }',
    '}',
    '',
  ].join('\n')
}

// ---------------------------------------------------------------- TypeScript (Mira Desk)

export function buildTs(tokens) {
  const { themed } = colorTables(tokens)
  const list = (names) => names.map((n) => `  '${n}',`).join('\n')
  const ms = (v) => Number(v.replace('ms', ''))
  return `// ${HEADER('TypeScript names for Mira Desk').split('\n').join('\n// ')}
//
// Components use CSS variables: \`color: var(--ink)\`. This file is for the few places that need a
// token in TypeScript (canvas charts, inline styles, JS animations) — still by name, never by value.

export const colorTokens = [
${list(themed.map((t) => t.name))}
] as const
export type ColorToken = (typeof colorTokens)[number]

export const spaceTokens = [
${list(tokens.spacing.tokens.map((t) => t.name))}
] as const
export type SpaceToken = (typeof spaceTokens)[number]

export const radiusTokens = [
${list(tokens.radius.tokens.map((t) => t.name))}
] as const
export type RadiusToken = (typeof radiusTokens)[number]

export const sizeTokens = [
${list(tokens.size.tokens.map((t) => t.name))}
] as const
export type SizeToken = (typeof sizeTokens)[number]

export const typeStyles = [
${list(tokens.type.groups.flatMap((g) => g.styles.map((s) => s.name)))}
] as const
export type TypeStyle = (typeof typeStyles)[number]

export type Token = ColorToken | SpaceToken | RadiusToken | SizeToken

/** \`var(--name)\` for use in inline styles, e.g. \`{ color: cssVar('state-live') }\`. */
export const cssVar = (name: Token): string => \`var(--\${name})\`

/** Motion durations in milliseconds (for JS-driven animations; respect prefers-reduced-motion). */
export const duration = {
${tokens.duration.tokens.map((t) => `  ${t.name.replace('duration-', '')}: ${ms(t.value)},`).join('\n')}
} as const

/** Chart series colours in order (Mira Pulse); read them as CSS variables at draw time. */
export const chartSeries: readonly ColorToken[] = [
${list(themed.filter((t) => t.name.startsWith('chart-')).map((t) => t.name))}
]
`
}

// ---------------------------------------------------------------- Dart (Mira Phone)

const camel = (name) => name.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase())
const dartColor = ([r, g, b, a = 1]) => {
  const hex = [a, r, g, b].map((c) => Math.round(c * 255).toString(16).padStart(2, '0')).join('').toUpperCase()
  return `Color(0x${hex})`
}

function dartShadows(css) {
  // "0 1px 2px rgba(26,20,20,0.08), 0 4px 12px rgba(...)" -> BoxShadow list
  const parts = css.split(/,(?![^(]*\))/).map((p) => p.trim())
  return (
    '[' +
    parts
      .map((p) => {
        const m = /^(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?(?:\s+(-?[\d.]+)(?:px)?)?\s+(.+)$/.exec(p)
        if (!m) throw new Error(`unsupported shadow: ${p}`)
        const [, x, y, blur, spread = '0', color] = m
        return `BoxShadow(offset: Offset(${x}, ${y}), blurRadius: ${blur}, spreadRadius: ${spread}, color: ${dartColor(parseColor(color))})`
      })
      .join(', ') +
    ']'
  )
}

const fontWeight = (w) => `FontWeight.w${w}`

export function buildDart(tokens) {
  const { all, themed } = colorTables(tokens)
  const colorNames = themed.map((t) => t.name)
  const themedShadows = tokens.shadow.tokens.filter((s) => typeof s.value === 'object')
  const fields = [
    ...colorNames.map((n) => ({ name: camel(n), type: 'Color', doc: all.get(n).usage })),
    ...themedShadows.map((s) => ({ name: camel(s.name), type: 'List<BoxShadow>', doc: s.usage })),
  ]
  const instance = (theme) =>
    [
      ...colorNames.map((n) => `    ${camel(n)}: ${dartColor([...rgbOf(all, n, theme), 1])},`),
      ...themedShadows.map((s) => `    ${camel(s.name)}: ${dartShadows(s.value[theme])},`),
    ].join('\n')
  const px = (v) => Number(String(v).replace('px', ''))
  const families = tokens.type.families
  const familyList = (stack) =>
    stack
      .split(',')
      .map((f) => f.trim().replace(/^"|"$/g, ''))
      .filter((f) => !['system-ui', 'sans-serif', 'monospace', 'ui-monospace'].includes(f))
  const styles = tokens.type.groups.flatMap((g) =>
    g.styles.map((s) => {
      const [first, ...fallback] = familyList(families[g.family])
      const size = px(s.fontSize)
      const tracking = s.letterSpacing && s.letterSpacing.endsWith('em') ? Number(s.letterSpacing.replace('em', '')) * size : 0
      return (
        `  /// ${s.usage}\n` +
        `  static const TextStyle ${camel(s.name)} = TextStyle(fontFamily: '${first}', fontFamilyFallback: ${JSON.stringify(fallback).replaceAll('"', "'")}, ` +
        `fontSize: ${size}, height: ${+(px(s.lineHeight) / size).toFixed(4)}, fontWeight: ${fontWeight(s.fontWeight)}` +
        (tracking ? `, letterSpacing: ${+tracking.toFixed(3)}` : '') +
        ');'
      )
    }),
  )
  const consts = (cls, doc, group, strip, type = 'double', conv = px) =>
    `/// ${doc}\nabstract final class ${cls} {\n` +
    tokens[group].tokens
      .map((t) => {
        const raw = conv(t.value)
        return `  /// ${t.usage}\n  static const ${type} ${camel(t.name.replace(strip, ''))} = ${raw};`
      })
      .join('\n') +
    '\n}\n'
  const brandShadows = tokens.shadow.tokens.filter((s) => typeof s.value === 'string')

  return `// ${HEADER('Flutter (Mira Phone)').split('\n').join('\n// ')}
// ignore_for_file: lines_longer_than_80_chars, public_member_api_docs

import 'package:flutter/material.dart';

/// Mira colour and elevation tokens for one theme. Read with \`MiraTokens.of(context)\`.
/// Semantic and component tokens only — primitives are not exposed to widgets on purpose.
@immutable
class MiraTokens extends ThemeExtension<MiraTokens> {
  const MiraTokens({
${fields.map((f) => `    required this.${f.name},`).join('\n')}
  });

${fields.map((f) => `  /// ${f.doc}\n  final ${f.type} ${f.name};`).join('\n')}

  static const MiraTokens light = MiraTokens(
${instance('light')}
  );

  static const MiraTokens dark = MiraTokens(
${instance('dark')}
  );

  static MiraTokens of(BuildContext context) =>
      Theme.of(context).extension<MiraTokens>() ?? (Theme.of(context).brightness == Brightness.dark ? dark : light);

  @override
  MiraTokens copyWith({
${fields.map((f) => `    ${f.type}? ${f.name},`).join('\n')}
  }) {
    return MiraTokens(
${fields.map((f) => `      ${f.name}: ${f.name} ?? this.${f.name},`).join('\n')}
    );
  }

  /// Colours blend; shadow lists switch at the midpoint (light and dark have a different
  /// number of shadows, and BoxShadow.lerpList would leave a zero-size ghost shadow).
  @override
  MiraTokens lerp(covariant ThemeExtension<MiraTokens>? other, double t) {
    if (other is! MiraTokens) return this;
    return MiraTokens(
${fields
  .map((f) =>
    f.type === 'Color'
      ? `      ${f.name}: Color.lerp(${f.name}, other.${f.name}, t)!,`
      : `      ${f.name}: t < 0.5 ? ${f.name} : other.${f.name},`,
  )
  .join('\n')}
    );
  }
}

${consts('MiraSpace', 'Spacing scale (logical pixels). Eight steps, no more.', 'spacing', '')}
${consts('MiraRadius', 'Corner radii. `pill` = fully rounded.', 'radius', 'radius-')}
${consts('MiraSize', 'Component sizes (logical pixels).', 'size', '')}
/// Motion durations.
abstract final class MiraDuration {
${tokens.duration.tokens.map((t) => `  /// ${t.usage}\n  static const Duration ${camel(t.name.replace('duration-', ''))} = Duration(milliseconds: ${Number(t.value.replace('ms', ''))});`).join('\n')}
}

/// Motion curves.
abstract final class MiraEasing {
${tokens.easing.tokens
  .map((t) => {
    const m = /cubic-bezier\(([^)]+)\)/.exec(t.value)
    return `  /// ${t.usage}\n  static const Cubic ${camel(t.name.replace('ease-', ''))} = Cubic(${m[1]});`
  })
  .join('\n')}
}

/// Font families. Fonts are bundled with the app (OFL-licensed IBM Plex and Archivo).
abstract final class MiraFonts {
${Object.entries(families).map(([k, v]) => `  static const String ${k} = '${familyList(v)[0]}';`).join('\n')}
}

/// Text styles (groups Display, App, Reading, Arabic, Data). Colour comes from the theme.
abstract final class MiraTextStyles {
${styles.join('\n')}
}

/// Brand-only shadows (marketing, login screen) — never in dense product UI.
abstract final class MiraBrandShadows {
${brandShadows.map((s) => `  /// ${s.usage}\n  static const List<BoxShadow> ${camel(s.name.replace('shadow-', ''))} = ${dartShadows(s.value)};`).join('\n')}
}
`
}

// ---------------------------------------------------------------- write / check

export function outputs(tokens = loadTokens()) {
  const css = buildCss(tokens)
  return {
    'design-system/tokens.css': css,
    'desk/src/styles/tokens.css': css,
    'desk/src/styles/tokens.ts': buildTs(tokens),
    'phone/packages/mira_design/lib/src/mira_tokens.g.dart': buildDart(tokens),
  }
}

function main(argv) {
  const check = argv.includes('--check')
  const stale = []
  for (const [rel, content] of Object.entries(outputs())) {
    const path = join(ROOT, rel)
    let current = null
    try {
      current = readFileSync(path, 'utf8')
    } catch {
      /* missing */
    }
    if (current === content) continue
    if (check) {
      stale.push(rel)
    } else {
      mkdirSync(dirname(path), { recursive: true })
      writeFileSync(path, content)
      console.log(`wrote ${rel}`)
    }
  }
  if (check && stale.length) {
    console.error(`Out of date — run node design-system/tools/build-tokens.mjs:\n  ${stale.join('\n  ')}`)
    process.exit(1)
  }
  if (check) console.log('generated token files are up to date')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2))
