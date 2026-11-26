// Tests for the token build:  node --test design-system/tools/
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'

import {
  ROOT,
  buildCss,
  buildDart,
  buildTs,
  colorTables,
  contrast,
  loadTokens,
  oklchToSrgb,
  outputs,
  rgbOf,
  toHex,
} from './build-tokens.mjs'

const tokens = loadTokens()
const { all, primitives, themed } = colorTables(tokens)

// The design tool recorded an sRGB hex for every primitive. Near the edge of the sRGB gamut
// (very saturated reds and ambers) its gamut handling differs from a plain clip by up to
// 2/255 per channel — invisible, but Flutter uses the recorded hex so the brand red is exact.
test('OKLCH -> sRGB matches the hex recorded for every primitive (within 2/255 per channel)', () => {
  let checked = 0
  for (const t of primitives) {
    const m = /#([0-9A-F]{6})/i.exec(t.usage)
    if (!m) continue
    const want = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16))
    const got = oklchToSrgb(t.value).map((c) => Math.round(c * 255))
    for (let i = 0; i < 3; i++) {
      assert.ok(Math.abs(got[i] - want[i]) <= 2, `${t.name}: ${toHex(got.map((c) => c / 255))} != #${m[1]}`)
    }
    checked++
  }
  assert.ok(checked >= 60, `only ${checked} primitives carried a hex note`)
})

test('every semantic and component token resolves in both themes', () => {
  for (const t of themed) {
    for (const theme of ['light', 'dark']) assert.equal(rgbOf(all, t.name, theme).length, 3)
  }
})

test('components never reference primitives directly (rule 1 of the token architecture)', () => {
  const component = themed.filter((t) =>
    /^(button|input|callpanel|call|dialkey|kpi)-/.test(t.name),
  )
  for (const t of component) {
    for (const theme of ['light', 'dark']) {
      const ref = /^\{([a-z0-9-]+)\}$/.exec(t.value[theme])?.[1]
      assert.ok(ref && !/^(red|green|amber|blue|clay|neutral)-/.test(ref), `${t.name} (${theme}) -> ${t.value[theme]}`)
    }
  }
})

// The contrast table in 4-accessibility-and-agent-wellbeing.md is part of the design system.
// Recompute every row from the tokens: the numbers must match and the thresholds must hold.
test('contrast table in the accessibility chapter matches the tokens and passes WCAG', () => {
  const md = readFileSync(join(ROOT, 'design-system/4-accessibility-and-agent-wellbeing.md'), 'utf8')
  const rows = [...md.matchAll(/^\| `([a-z0-9-]+)` \| `([a-z0-9-]+)` \| ([\d.]+):1 \| ([\d.]+):1( ⚠)? \| ([\d.]+):1 \|$/gm)]
  assert.ok(rows.length >= 30, `parsed only ${rows.length} rows`)
  for (const [, fg, bg, light, dark, warn, need] of rows) {
    for (const [theme, documented, allowedBelow] of [
      ['light', light, false],
      ['dark', dark, Boolean(warn)],
    ]) {
      const ratio = contrast(rgbOf(all, fg, theme), rgbOf(all, bg, theme))
      assert.ok(Math.abs(ratio - Number(documented)) < 0.06, `${fg} on ${bg} (${theme}): ${ratio.toFixed(2)} vs documented ${documented}`)
      if (!allowedBelow) assert.ok(ratio >= Number(need), `${fg} on ${bg} (${theme}): ${ratio.toFixed(2)} < ${need}`)
    }
  }
})

test('every text colour used on a filled control passes 4.5:1 (both themes)', () => {
  const pairs = [
    ['button-primary-fg', 'button-primary-bg'],
    ['button-primary-fg', 'button-primary-bg-hover'],
    ['button-secondary-fg', 'button-secondary-bg'],
    ['button-danger-fg', 'button-danger-bg'],
    ['input-fg', 'input-bg'],
    ['call-control-fg', 'call-control-bg'],
    ['call-control-on-fg', 'call-control-on-bg'],
    ['dialkey-fg', 'dialkey-bg'],
    ['kpi-value', 'kpi-bg'],
    ['kpi-label', 'kpi-bg'],
    ['on-red', 'call-answer-bg'],
    ['on-red', 'call-hangup-bg'],
  ]
  for (const [fg, bg] of pairs) {
    for (const theme of ['light', 'dark']) {
      const r = contrast(rgbOf(all, fg, theme), rgbOf(all, bg, theme))
      assert.ok(r >= 4.5, `${fg} on ${bg} (${theme}) = ${r.toFixed(2)}`)
    }
  }
})

// --- CSS ------------------------------------------------------------------------------------

function cssBlocks(css) {
  // { selector -> { --var: value } } for top-level and one level of @media nesting
  const blocks = {}
  const re = /([^{}]+)\{([^{}]*)\}/g
  for (const [, sel, body] of css.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(re)) {
    const vars = {}
    for (const [, k, v] of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);?/g)) vars[k] = v.trim()
    blocks[sel.replace(/\s+/g, ' ').trim()] = vars
  }
  return blocks
}

test('regenerated tokens.css keeps every value of the original v2 file', () => {
  const old = cssBlocks(readFileSync(join(ROOT, 'design-system/tools/test/fixtures/tokens.v2-original.css'), 'utf8'))
  const neu = cssBlocks(buildCss(tokens))
  // the v2 file had three blocks: colours (light), colours (dark), and a second :root with scales
  const oldLight = { ...old[':root,[data-theme=light]'], ...old[':root'] }
  const oldDark = { ...oldLight, ...old['[data-theme=dark]'] }
  const newLight = neu[':root, [data-theme="light"]']
  const newDark = { ...newLight, ...neu['[data-theme="dark"]'] }
  assert.ok(Object.keys(oldLight).length >= 165, `parsed ${Object.keys(oldLight).length} variables`)
  const norm = (v) => v.replace(/\s+/g, ' ').replace(/,\s*/g, ', ')
  for (const [k, v] of Object.entries(oldLight)) assert.equal(norm(newLight[k] ?? 'MISSING'), norm(v), `light ${k}`)
  for (const [k, v] of Object.entries(oldDark)) assert.equal(norm(newDark[k] ?? 'MISSING'), norm(v), `dark ${k}`)
})

test('follow-the-OS dark block equals the explicit dark block', () => {
  const css = buildCss(tokens)
  const explicit = cssBlocks(css)['[data-theme="dark"]']
  const media = /@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme\]\) \{([^}]*)\}/.exec(css)[1]
  const auto = {}
  for (const [, k, v] of media.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) auto[k] = v.trim()
  assert.deepEqual(auto, explicit)
})

test('CSS exposes the type styles the components need', () => {
  const css = buildCss(tokens)
  for (const name of ['title', 'body', 'label', 'caption', 'timer', 'ar-body', 'wallboard-kpi']) {
    for (const part of ['family', 'size', 'line', 'weight', 'tracking']) assert.match(css, new RegExp(`--type-${name}-${part}:`))
  }
})

// --- TypeScript and Dart ----------------------------------------------------------------------

test('TypeScript lists every themed colour token', () => {
  const ts = buildTs(tokens)
  for (const t of themed) assert.match(ts, new RegExp(`'${t.name}',`))
  assert.doesNotMatch(ts, /'red-600'/, 'primitives must not be exposed to components')
})

test('Dart ThemeExtension carries every themed colour, both themes, and no primitives', () => {
  const dart = buildDart(tokens)
  const camel = (n) => n.replace(/-([a-z0-9])/g, (_, c) => c.toUpperCase())
  for (const t of themed) {
    assert.match(dart, new RegExp(`final Color ${camel(t.name)};`))
    assert.equal(dart.match(new RegExp(`^    ${camel(t.name)}: Color\\(0x`, 'gm'))?.length, 2, `${t.name} light+dark`)
  }
  assert.doesNotMatch(dart, /red600|neutral50\b/)
  // mira-red is #BE0007 in both themes (the brand red does not change)
  assert.match(dart, /miraRed: Color\(0xFFBE0007\)/)
})

test('generated files on disk are up to date', () => {
  for (const [rel, content] of Object.entries(outputs(tokens))) {
    assert.equal(readFileSync(join(ROOT, rel), 'utf8'), content, `${rel} is stale — run the build`)
  }
})
