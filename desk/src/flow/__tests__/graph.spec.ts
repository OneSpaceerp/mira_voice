import { describe, expect, it } from 'vitest'

import type { FlowDefinition } from '@/api/types'
import {
  addNode,
  edges,
  layout,
  moveNode,
  nodeOfReport,
  normalise,
  removeNode,
  renameNode,
  toDraft,
} from '@/flow/graph'
import { link, newNode, outputs, target } from '@/flow/nodeTypes'

const P = '7d2ac4b2-0d2f-4c0e-8f7e-1a2b3c4d5e6f'

function sample(): FlowDefinition {
  return {
    schema: 'mira-flow/1',
    start: 'hello',
    nodes: {
      hello: { type: 'play', prompt: P, next: 'menu' },
      menu: { type: 'menu', prompt: P, options: { '1': 'desk', '2': 'bye' }, invalid_next: 'bye' },
      desk: { type: 'transfer', number: '1001' },
      bye: { type: 'hangup' },
    },
  }
}

describe('node outputs', () => {
  it('lists menu keys, then the fallbacks', () => {
    const keys = outputs(sample().nodes.menu!).map((o) => o.key)
    expect(keys).toEqual(['option:1', 'option:2', 'invalid_next', 'timeout_next'])
  })

  it('reads and writes every kind of link', () => {
    const menu = sample().nodes.menu!
    expect(target(menu, 'option:2')).toBe('bye')
    expect(target(link(menu, 'option:2', 'desk'), 'option:2')).toBe('desk')
    const branch = newNode('branch')
    expect(target(link(branch, 'condition:0', 'desk'), 'condition:0')).toBe('desk')
    expect(link(menu, 'timeout_next', '')).not.toHaveProperty('timeout_next')
  })

  it('terminal steps have no outputs', () => {
    expect(outputs(newNode('transfer'))).toEqual([])
    expect(outputs(newNode('hangup'))).toEqual([])
  })
})

describe('graph edits', () => {
  it('draws one edge per link', () => {
    const e = edges(sample())
    expect(e.map((x) => x.id).sort()).toEqual([
      'hello:next',
      'menu:invalid_next',
      'menu:option:1',
      'menu:option:2',
    ])
    expect(e.find((x) => x.id === 'menu:option:1')).toMatchObject({ label: '1', literal: true })
  })

  it('adds a step below and links it', () => {
    const { flow, id } = addNode(sample(), 'voicemail', { id: 'menu', output: 'timeout_next' })
    expect(id).toBe('voicemail_1')
    expect(flow.nodes.menu!.timeout_next).toBe('voicemail_1')
    expect(flow.nodes.voicemail_1!.y).toBeGreaterThan(flow.nodes.menu!.y ?? 0)
  })

  it('steps added from the same parent never overlap', () => {
    let flow = layout(sample())
    const added: string[] = []
    for (const output of ['timeout_next', 'invalid_next', 'option:2']) {
      const r = addNode(flow, 'hangup', { id: 'menu', output })
      flow = r.flow
      added.push(r.id)
    }
    const spots = Object.values(flow.nodes).map((n) => `${n.x},${n.y}`)
    expect(new Set(spots).size).toBe(spots.length)
    const xs = added.map((id) => flow.nodes[id]!.x ?? 0).sort((a, b) => a - b)
    const gaps = xs.slice(1).map((x, i) => x - xs[i]!)
    expect(Math.min(...gaps)).toBeGreaterThanOrEqual(240) // a card's width
  })

  it('deleting a step unlinks everything that pointed to it', () => {
    const flow = removeNode(sample(), 'bye')
    expect(flow.nodes.bye).toBeUndefined()
    expect(flow.nodes.menu!.invalid_next).toBeUndefined()
    expect((flow.nodes.menu!.options as Record<string, string>)['2']).toBe('')
  })

  it('never deletes the start step', () => {
    const f = sample()
    expect(removeNode(f, 'hello')).toBe(f)
  })

  it('renaming follows every link and the start', () => {
    const flow = renameNode(sample(), 'hello', 'welcome')
    expect(flow.start).toBe('welcome')
    const again = renameNode(flow, 'bye', 'goodbye')
    expect((again.nodes.menu!.options as Record<string, string>)['2']).toBe('goodbye')
    expect(again.nodes.menu!.invalid_next).toBe('goodbye')
    // refused: bad id, taken id
    expect(renameNode(again, 'desk', 'Bad-Id')).toBe(again)
    expect(renameNode(again, 'desk', 'goodbye')).toBe(again)
  })

  it('lays out a hand-written flow top to bottom', () => {
    const flow = layout(sample())
    expect(flow.nodes.hello!.y).toBe(0)
    expect(flow.nodes.menu!.y).toBeGreaterThan(0)
    expect(flow.nodes.desk!.y).toBe(flow.nodes.bye!.y)
    expect(flow.nodes.desk!.x).not.toBe(flow.nodes.bye!.x)
  })

  it('normalises an empty draft into a one-step flow', () => {
    const flow = normalise({})
    expect(Object.keys(flow.nodes)).toEqual(['welcome'])
    expect(flow.start).toBe('welcome')
  })

  it('moves to whole pixels', () => {
    expect(moveNode(sample(), 'desk', 10.6, 20.2).nodes.desk).toMatchObject({ x: 11, y: 20 })
  })

  it('drafts drop empty optional fields', () => {
    const f = sample()
    f.nodes.menu!.timeout_next = ''
    f.nodes.menu!.invalid_prompt = ''
    const draft = toDraft(f)
    expect(draft.nodes.menu).not.toHaveProperty('timeout_next')
    expect(draft.nodes.menu).not.toHaveProperty('invalid_prompt')
  })

  it('finds the step a problem line is about', () => {
    expect(nodeOfReport("menu: goes to 'x', which does not exist", sample())).toBe('menu')
    expect(nodeOfReport('flow: something', sample())).toBeNull()
  })
})
