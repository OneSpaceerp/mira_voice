<script setup lang="ts">
/**
 * The canvas (Vue Flow): steps as cards, links as labelled arrows. Dragging a card moves it;
 * dragging from a port to a card links them — a shortcut only: every link can also be set
 * from the inspector, so the builder works with the keyboard alone (WCAG 2.2, 2.5.7).
 * The canvas keeps left-to-right geometry in every language (flows run top to bottom).
 */
import '@vue-flow/core/dist/style.css'
import '@vue-flow/controls/dist/style.css'

import { Background } from '@vue-flow/background'
import { ControlButton, Controls } from '@vue-flow/controls'
import {
  type Connection,
  MarkerType,
  type NodeDragEvent,
  useVueFlow,
  VueFlow,
} from '@vue-flow/core'
import { Maximize, Minus, Plus } from 'lucide-vue-next'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FlowDefinition, Prompt } from '@/api/types'
import { edges as flowEdges } from '@/flow/graph'

import FlowNodeCard from './FlowNodeCard.vue'

const props = defineProps<{
  flow: FlowDefinition
  selected: string | null
  problems: Record<string, number>
  prompts: Prompt[]
}>()
const emit = defineEmits<{
  select: [id: string | null]
  move: [id: string, x: number, y: number]
  link: [source: string, output: string, target: string]
}>()
const { t } = useI18n()
// our own buttons: Vue Flow's defaults have no accessible name (axe button-name)
const { zoomIn, zoomOut, fitView } = useVueFlow()

const nodes = computed(() =>
  Object.entries(props.flow.nodes).map(([id, node]) => ({
    id,
    type: 'mira',
    position: { x: node.x ?? 0, y: node.y ?? 0 },
    selected: id === props.selected,
    data: {
      node,
      isStart: id === props.flow.start,
      problems: props.problems[id] ?? 0,
      prompts: props.prompts,
    },
  })),
)

const edges = computed(() =>
  flowEdges(props.flow).map((e) => ({
    id: e.id,
    source: e.source,
    sourceHandle: e.sourceHandle,
    target: e.target,
    // 'next' is already written on the port; other outputs keep their label on the line
    label: e.literal ? e.label : e.label === 'out.next' ? undefined : t(e.label),
    markerEnd: MarkerType.ArrowClosed,
    class: e.source === props.selected ? 'edge--active' : '',
  })),
)

function onDragStop(event: NodeDragEvent) {
  for (const node of event.nodes) emit('move', node.id, node.position.x, node.position.y)
}

function onConnect(c: Connection) {
  if (c.source && c.target && c.sourceHandle && c.source !== c.target) {
    emit('link', c.source, c.sourceHandle, c.target)
  }
}
</script>

<template>
  <section class="canvas" dir="ltr" :aria-label="t('editor.canvas')">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :nodes-connectable="true"
      :min-zoom="0.3"
      :max-zoom="1.5"
      :snap-to-grid="true"
      :snap-grid="[8, 8]"
      :delete-key-code="null"
      fit-view-on-init
      @node-click="emit('select', $event.node.id)"
      @pane-click="emit('select', null)"
      @node-drag-stop="onDragStop"
      @connect="onConnect"
    >
      <template #node-mira="nodeProps">
        <FlowNodeCard v-bind="nodeProps" />
      </template>
      <Background :gap="8" :size="1" pattern-color="var(--line)" />
      <Controls :show-zoom="false" :show-fit-view="false" :show-interactive="false">
        <ControlButton
          :aria-label="t('editor.zoomIn')"
          :title="t('editor.zoomIn')"
          @click="zoomIn()"
        >
          <Plus :size="16" aria-hidden="true" />
        </ControlButton>
        <ControlButton
          :aria-label="t('editor.zoomOut')"
          :title="t('editor.zoomOut')"
          @click="zoomOut()"
        >
          <Minus :size="16" aria-hidden="true" />
        </ControlButton>
        <ControlButton
          :aria-label="t('editor.fitView')"
          :title="t('editor.fitView')"
          @click="fitView()"
        >
          <Maximize :size="16" aria-hidden="true" />
        </ControlButton>
      </Controls>
    </VueFlow>
  </section>
</template>

<style scoped>
.canvas {
  position: relative;
  block-size: 100%;
  min-block-size: 480px;
  background: var(--surface-sunken);
}
.canvas :deep(.vue-flow__edge-path) {
  stroke: var(--line-strong);
  stroke-width: 1.5;
}
.canvas :deep(.edge--active .vue-flow__edge-path) {
  stroke: var(--focus-ring);
  stroke-width: 2;
}
.canvas :deep(.vue-flow__edge-textbg) {
  fill: var(--surface-sunken);
}
.canvas :deep(.vue-flow__edge-text) {
  fill: var(--ink-muted);
  font: var(--type-caption-weight) var(--type-caption-size) var(--type-caption-family);
}
.canvas :deep(.vue-flow__controls) {
  box-shadow: var(--shadow-raised);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.canvas :deep(.vue-flow__controls-button) {
  background: var(--surface-raised);
  border-block-end: 1px solid var(--line);
  fill: var(--ink);
  color: var(--ink);
  inline-size: var(--control-sm);
  block-size: var(--control-sm);
}
.canvas :deep(.vue-flow__node) {
  border-radius: var(--radius-lg);
}
.canvas :deep(.vue-flow__node:focus-visible) {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
</style>
