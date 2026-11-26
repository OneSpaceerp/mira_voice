<script setup lang="ts">
/** One step on the canvas: type stripe, title, a one-line summary, and an output port per
 *  link (labelled). Drawn by Vue Flow; editing happens in the inspector. */
import { Handle, Position } from '@vue-flow/core'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FlowNode, Prompt } from '@/api/types'
import { outputs, typeInfo } from '@/flow/nodeTypes'

const props = defineProps<{
  id: string
  data: { node: FlowNode; isStart: boolean; problems: number; prompts: Prompt[] }
  selected?: boolean
}>()
const { t } = useI18n()

const info = computed(() => typeInfo(props.data.node.type))
const ports = computed(() => outputs(props.data.node))
const summary = computed(() => {
  const n = props.data.node
  const promptName = (id: unknown) => props.data.prompts.find((p) => p.id === id)?.name ?? ''
  switch (n.type) {
    case 'play':
    case 'menu':
    case 'collect':
      return promptName(n.prompt) || t('node.choosePrompt')
    case 'transfer':
    case 'voicemail':
      return String(n.number ?? n.mailbox ?? '')
    case 'language':
      return t(`languages.${String(n.language)}`)
    case 'http':
      try {
        return new URL(String(n.url)).hostname
      } catch {
        return String(n.url ?? '')
      }
    case 'set':
    case 'branch':
      return String(n.variable ?? '')
    default:
      return ''
  }
})
const numeric = computed(() => ['transfer', 'voicemail'].includes(props.data.node.type))
</script>

<template>
  <div
    class="card"
    :class="[
      `card--${info.stripe}`,
      { 'card--start': data.isStart, 'card--problem': data.problems },
    ]"
    :aria-label="`${t(`node.types.${data.node.type}`)} ${id}`"
  >
    <Handle v-if="!data.isStart" type="target" :position="Position.Top" class="port port--in" />
    <div class="card__head">
      <span class="card__type">{{ t(`node.types.${data.node.type}`) }}</span>
      <span v-if="data.isStart" class="card__start">{{ t('editor.start') }}</span>
    </div>
    <div class="card__title mv-ltr">{{ data.node.label || id }}</div>
    <div class="card__summary" :class="{ 'mv-number': numeric }">{{ summary }}</div>
    <div v-if="ports.length" class="card__ports">
      <div v-for="(p, i) in ports" :key="p.key" class="card__port">
        <span class="card__portlabel">{{ p.literal ? p.label : t(p.label) }}</span>
        <Handle
          :id="p.key"
          type="source"
          :position="Position.Bottom"
          class="port port--out"
          :style="{ left: `${((i + 1) / (ports.length + 1)) * 100}%` }"
        />
      </div>
    </div>
    <div v-else class="card__ends">{{ t('node.ends') }}</div>
  </div>
</template>

<style scoped>
.card {
  position: relative;
  inline-size: 240px;
  padding: var(--space-3) var(--space-3) var(--space-2);
  background: var(--surface-raised);
  border: 1px solid var(--line);
  border-block-start: 4px solid var(--stripe);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-raised);
  color: var(--ink);
}
.card--hold {
  --stripe: var(--state-hold);
}
.card--live {
  --stripe: var(--state-live);
}
.card--offline {
  --stripe: var(--state-offline);
}
.card--ringing {
  --stripe: var(--state-ringing);
}
.card--ink {
  --stripe: var(--ink);
}
/* the entry step carries the brand red stripe (design-system §3, Mira Flow) */
.card--start {
  --stripe: var(--mira-red);
}
.card--problem {
  border-color: var(--danger);
}
:global(.vue-flow__node.selected) .card {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.card__head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
}
.card__type,
.card__start,
.card__ends,
.card__portlabel {
  font: var(--type-caption-weight) var(--type-caption-size) / var(--type-caption-line)
    var(--type-caption-family);
  color: var(--ink-muted);
}
/* the red stripe marks the start; the label stays neutral (one red thing per screen) */
.card__start {
  color: var(--ink);
}
.card__title {
  font: var(--type-body-strong-weight) var(--type-body-strong-size) / var(--type-body-strong-line)
    var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card__summary {
  min-block-size: var(--type-body-line);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card__ports {
  display: flex;
  justify-content: space-around;
  margin-block-start: var(--space-2);
  padding-block-start: var(--space-1);
  border-block-start: 1px solid var(--line);
}
.card__port {
  text-align: center;
}
.card__ends {
  margin-block-start: var(--space-2);
}
.port {
  inline-size: var(--space-3);
  block-size: var(--space-3);
  background: var(--surface-raised);
  border: 2px solid var(--line-strong);
}
.port--out {
  border-color: var(--stripe);
}
.card--start .port--out {
  border-color: var(--line-strong);
}
</style>
