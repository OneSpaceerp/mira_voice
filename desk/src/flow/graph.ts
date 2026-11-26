/**
 * Flow JSON <-> what the canvas draws, plus the edits that touch several nodes at once
 * (adding, deleting, renaming). Pure functions: the editor keeps one FlowDefinition and
 * replaces it on every change, so undo and "unsaved" are simple comparisons.
 */
import type { FlowDefinition, FlowNode, NodeType } from '@/api/types'
import { link, newNode, outputs, target } from '@/flow/nodeTypes'

export const NODE_W = 240
export const NODE_H = 96
const GAP_X = 64
const GAP_Y = 72

export function emptyFlow(): FlowDefinition {
  return {
    schema: 'mira-flow/1',
    start: 'welcome',
    nodes: { welcome: { ...newNode('play'), x: 0, y: 0 } },
  }
}

/** A draft from the API may be {} (new flow) or partial: give the editor a whole flow. */
export function normalise(draft: Partial<FlowDefinition> | undefined): FlowDefinition {
  if (!draft || !draft.nodes || !Object.keys(draft.nodes).length) return emptyFlow()
  const flow: FlowDefinition = {
    schema: 'mira-flow/1',
    start: draft.start && draft.nodes[draft.start] ? draft.start : Object.keys(draft.nodes)[0]!,
    nodes: structuredClone(draft.nodes),
  }
  const unplaced = Object.values(flow.nodes).every((n) => !n.x && !n.y)
  return unplaced ? layout(flow) : flow
}

/** Layered layout from the start node (for flows written by hand or by older builders). */
export function layout(flow: FlowDefinition): FlowDefinition {
  const depth = new Map<string, number>([[flow.start, 0]])
  const queue = [flow.start]
  while (queue.length) {
    const id = queue.shift()!
    for (const o of outputs(flow.nodes[id]!)) {
      const to = target(flow.nodes[id]!, o.key)
      if (to && flow.nodes[to] && !depth.has(to)) {
        depth.set(to, depth.get(id)! + 1)
        queue.push(to)
      }
    }
  }
  let extra = Math.max(0, ...depth.values()) + 1
  for (const id of Object.keys(flow.nodes)) if (!depth.has(id)) depth.set(id, extra++)
  const rows = new Map<number, string[]>()
  for (const [id, d] of depth) rows.set(d, [...(rows.get(d) ?? []), id])
  const nodes: Record<string, FlowNode> = {}
  for (const [d, ids] of rows) {
    ids.forEach((id, i) => {
      const offset = (i - (ids.length - 1) / 2) * (NODE_W + GAP_X)
      nodes[id] = { ...flow.nodes[id]!, x: Math.round(offset), y: d * (NODE_H + GAP_Y) }
    })
  }
  return { ...flow, nodes }
}

export function uniqueId(flow: FlowDefinition, type: NodeType): string {
  for (let i = 1; ; i++) {
    const id = `${type}_${i}`
    if (!flow.nodes[id]) return id
  }
}

/** Add a node below `near` (or the lowest node), optionally linking `near`'s output to it. */
export function addNode(
  flow: FlowDefinition,
  type: NodeType,
  near?: { id: string; output?: string },
): { flow: FlowDefinition; id: string } {
  const id = uniqueId(flow, type)
  const anchor = near ? flow.nodes[near.id] : undefined
  const lowest = Math.max(0, ...Object.values(flow.nodes).map((n) => n.y ?? 0))
  const y = anchor ? (anchor.y ?? 0) + NODE_H + GAP_Y : lowest + NODE_H + GAP_Y
  // first free slot on that row, alternating right and left of the anchor, so steps added
  // from the same menu never land on top of each other
  const taken = (x: number) =>
    Object.values(flow.nodes).some(
      (n) => Math.abs((n.x ?? 0) - x) < NODE_W + GAP_X && Math.abs((n.y ?? 0) - y) < NODE_H,
    )
  const base = anchor?.x ?? 0
  let x = base
  for (let i = 1; taken(x) && i < 50; i++) {
    x = base + Math.ceil(i / 2) * (i % 2 ? 1 : -1) * (NODE_W + GAP_X)
  }
  const node: FlowNode = { ...newNode(type), x, y }
  const nodes = { ...flow.nodes, [id]: node }
  if (anchor && near?.output) nodes[near.id] = link(anchor, near.output, id)
  return { flow: { ...flow, nodes }, id }
}

/** Remove a node and every link to it (links become empty, to be chosen again). */
export function removeNode(flow: FlowDefinition, id: string): FlowDefinition {
  if (id === flow.start || !flow.nodes[id]) return flow
  const nodes: Record<string, FlowNode> = {}
  for (const [other, node] of Object.entries(flow.nodes)) {
    if (other === id) continue
    let copy = node
    for (const o of outputs(node)) if (target(node, o.key) === id) copy = link(copy, o.key, '')
    nodes[other] = copy
  }
  return { ...flow, nodes }
}

/** Rename a node id everywhere it is linked from. */
export function renameNode(flow: FlowDefinition, from: string, to: string): FlowDefinition {
  if (from === to || !flow.nodes[from] || flow.nodes[to] || !/^[a-z][a-z0-9_]{0,39}$/.test(to)) {
    return flow
  }
  const nodes: Record<string, FlowNode> = {}
  for (const [id, node] of Object.entries(flow.nodes)) {
    let copy = node
    for (const o of outputs(node)) if (target(node, o.key) === from) copy = link(copy, o.key, to)
    nodes[id === from ? to : id] = copy
  }
  return { ...flow, start: flow.start === from ? to : flow.start, nodes }
}

export function updateNode(flow: FlowDefinition, id: string, node: FlowNode): FlowDefinition {
  return { ...flow, nodes: { ...flow.nodes, [id]: node } }
}

export function moveNode(flow: FlowDefinition, id: string, x: number, y: number): FlowDefinition {
  const node = flow.nodes[id]
  return node ? updateNode(flow, id, { ...node, x: Math.round(x), y: Math.round(y) }) : flow
}

export interface CanvasEdge {
  id: string
  source: string
  sourceHandle: string
  target: string
  label: string
  literal: boolean
}

/** Every link as an edge (dangling links are skipped: the wiring report lists them). */
export function edges(flow: FlowDefinition): CanvasEdge[] {
  const out: CanvasEdge[] = []
  for (const [id, node] of Object.entries(flow.nodes)) {
    for (const o of outputs(node)) {
      const to = target(node, o.key)
      if (to && flow.nodes[to]) {
        out.push({
          id: `${id}:${o.key}`,
          source: id,
          sourceHandle: o.key,
          target: to,
          label: o.label,
          literal: !!o.literal,
        })
      }
    }
  }
  return out
}

/** The JSON the API stores: drop empty optional links, keep everything else as is. */
export function toDraft(flow: FlowDefinition): FlowDefinition {
  const nodes: Record<string, FlowNode> = {}
  for (const [id, node] of Object.entries(flow.nodes)) {
    const copy: FlowNode = { ...node }
    for (const key of ['timeout_next', 'invalid_prompt', 'greeting', 'timezone', 'label']) {
      if (copy[key] === '' || copy[key] === null) delete copy[key]
    }
    nodes[id] = copy
  }
  return { schema: 'mira-flow/1', start: flow.start, nodes }
}

/** Node id named in a report line ("menu: goes to 'x'…" -> "menu"). */
export function nodeOfReport(line: string, flow: FlowDefinition): string | null {
  const id = line.split(':', 1)[0]?.trim() ?? ''
  return flow.nodes[id] ? id : null
}
