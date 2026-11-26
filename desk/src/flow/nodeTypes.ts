/**
 * The Mira Flow node types as the builder sees them: their stripe colour (design-system
 * §3 "Mira Flow"), their outputs (the links they can have) and a new node's starting fields.
 * Keep in step with core/src/mira_core/flows/schema.py.
 */
import type { Condition, FlowNode, NodeType } from '@/api/types'

/** Stripe colours per design-system/3-product-patterns.md ("Mira Flow"). */
export type Stripe = 'hold' | 'live' | 'offline' | 'ink' | 'ringing'

export interface NodeTypeInfo {
  type: NodeType
  stripe: Stripe
  /** Ends the flow (no outputs). */
  terminal: boolean
}

export const NODE_TYPES: NodeTypeInfo[] = [
  { type: 'play', stripe: 'hold', terminal: false },
  { type: 'menu', stripe: 'hold', terminal: false },
  { type: 'collect', stripe: 'hold', terminal: false },
  { type: 'time', stripe: 'ringing', terminal: false },
  { type: 'language', stripe: 'hold', terminal: false },
  { type: 'set', stripe: 'ink', terminal: false },
  { type: 'branch', stripe: 'ink', terminal: false },
  { type: 'http', stripe: 'ink', terminal: false },
  { type: 'transfer', stripe: 'live', terminal: true },
  { type: 'queue', stripe: 'live', terminal: true },
  { type: 'voicemail', stripe: 'offline', terminal: true },
  { type: 'hangup', stripe: 'offline', terminal: true },
]

export function typeInfo(type: NodeType): NodeTypeInfo {
  const info = NODE_TYPES.find((t) => t.type === type)
  if (!info) throw new Error(`unknown node type ${type}`)
  return info
}

/**
 * One output of a node: which field holds the link, and how the canvas labels it.
 * `key` doubles as the Vue Flow source-handle id.
 *   field: a top-level field (next, invalid_next…), or option:<digit> / condition:<index>.
 */
export interface Output {
  key: string
  /** i18n key for the label, or a literal (menu digits). */
  label: string
  literal?: boolean
  optional?: boolean
}

const SIMPLE: Record<string, Output[]> = {
  play: [{ key: 'next', label: 'out.next' }],
  language: [{ key: 'next', label: 'out.next' }],
  set: [{ key: 'next', label: 'out.next' }],
  collect: [
    { key: 'next', label: 'out.done' },
    { key: 'timeout_next', label: 'out.timeout' },
  ],
  time: [
    { key: 'open_next', label: 'out.open' },
    { key: 'closed_next', label: 'out.closed' },
  ],
  http: [
    { key: 'next', label: 'out.ok' },
    { key: 'error_next', label: 'out.error' },
  ],
}

export function outputs(node: FlowNode): Output[] {
  if (node.type === 'menu') {
    const options = Object.keys((node.options as Record<string, string>) ?? {})
      .sort()
      .map((digit) => ({ key: `option:${digit}`, label: digit, literal: true }))
    return [
      ...options,
      { key: 'invalid_next', label: 'out.invalid' },
      { key: 'timeout_next', label: 'out.timeout', optional: true },
    ]
  }
  if (node.type === 'branch') {
    const conditions = ((node.conditions as Condition[]) ?? []).map((_, i) => ({
      key: `condition:${i}`,
      label: String(i + 1),
      literal: true,
    }))
    return [...conditions, { key: 'default_next', label: 'out.otherwise' }]
  }
  return SIMPLE[node.type] ?? []
}

/** The node id an output points to ('' when not linked yet). */
export function target(node: FlowNode, key: string): string {
  if (key.startsWith('option:')) {
    return ((node.options as Record<string, string>) ?? {})[key.slice(7)] ?? ''
  }
  if (key.startsWith('condition:')) {
    return ((node.conditions as Condition[]) ?? [])[Number(key.slice(10))]?.next ?? ''
  }
  return (node[key] as string | undefined) ?? ''
}

/** A copy of `node` with that output pointing to `to` ('' unlinks an optional output). */
export function link(node: FlowNode, key: string, to: string): FlowNode {
  const copy: FlowNode = structuredClone(node)
  if (key.startsWith('option:')) {
    copy.options = { ...(copy.options as Record<string, string> | undefined), [key.slice(7)]: to }
  } else if (key.startsWith('condition:')) {
    const list = [...((copy.conditions as Condition[]) ?? [])]
    const i = Number(key.slice(10))
    if (list[i]) list[i] = { ...list[i], next: to }
    copy.conditions = list
  } else if (to) {
    copy[key] = to
  } else {
    delete copy[key]
  }
  return copy
}

/** Starting fields of a new node (valid once its links and prompt are chosen). */
export function newNode(type: NodeType): FlowNode {
  switch (type) {
    case 'menu':
      return {
        type,
        prompt: '',
        options: { '1': '' },
        timeout_seconds: 5,
        retries: 2,
        invalid_next: '',
      }
    case 'collect':
      return {
        type,
        prompt: '',
        variable: 'account',
        min_digits: 1,
        max_digits: 16,
        terminator: '#',
        timeout_seconds: 8,
        next: '',
        timeout_next: '',
      }
    case 'time':
      return {
        type,
        weekly: [{ days: ['sun', 'mon', 'tue', 'wed', 'thu'], from: '09:00', to: '17:00' }],
        holidays: [],
        open_next: '',
        closed_next: '',
      }
    case 'language':
      return { type, language: 'ar', next: '' }
    case 'set':
      return { type, variable: 'note', value: '', next: '' }
    case 'branch':
      return {
        type,
        variable: 'vip',
        conditions: [{ op: 'eq', value: '1', next: '' }],
        default_next: '',
      }
    case 'http':
      return {
        type,
        method: 'GET',
        url: 'https://',
        headers: {},
        body: {},
        timeout_seconds: 3,
        extract: {},
        next: '',
        error_next: '',
      }
    case 'transfer':
      return { type, number: '' }
    case 'queue':
      return { type, queue: '' }
    case 'voicemail':
      return { type, mailbox: '', max_seconds: 120 }
    case 'hangup':
      return { type }
    default:
      return { type, prompt: '', next: '' }
  }
}
