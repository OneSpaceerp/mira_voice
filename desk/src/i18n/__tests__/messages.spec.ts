/** Arabic, English and French are equals: every key in every language, nothing left empty,
 *  and the same {placeholders} in each translation. */
import { describe, expect, it } from 'vitest'

import ar from '@/i18n/ar'
import en from '@/i18n/en'
import fr from '@/i18n/fr'

type Tree = { [k: string]: string | Tree }

function flatten(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(tree)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'string') out[key] = v
    else Object.assign(out, flatten(v, key))
  }
  return out
}

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()

describe.each([
  ['ar', ar],
  ['fr', fr],
])('%s messages', (_name, messages) => {
  const base = flatten(en as Tree)
  const other = flatten(messages as Tree)

  it('has exactly the English keys', () => {
    expect(Object.keys(other).sort()).toEqual(Object.keys(base).sort())
  })

  it('has no empty strings', () => {
    const empty = Object.entries(other).filter(([, value]) => value.trim() === '')
    expect(empty.map(([key]) => key)).toEqual([])
  })

  it('keeps the same placeholders', () => {
    const differ = Object.entries(base).filter(
      ([key, value]) => placeholders(other[key] ?? '').join() !== placeholders(value).join(),
    )
    expect(differ.map(([key]) => key)).toEqual([])
  })
})

it('Arabic strings are Arabic', () => {
  const arabic = /[؀-ۿ]/
  const exceptions = new Set(['editor.shortcuts', 'prompts.format', 'prompts.duration'])
  const notArabic = Object.entries(flatten(ar as Tree))
    .filter(([key, value]) => !exceptions.has(key) && !arabic.test(value))
    .map(([key]) => key)
  expect(notArabic).toEqual([])
})
