<script setup lang="ts">
/** Where an output goes: an existing step, or a new step of a chosen type (created and linked
 *  in one go). The keyboard-friendly way to wire a flow. */
import { computed, useId } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FlowDefinition, NodeType } from '@/api/types'
import { NODE_TYPES } from '@/flow/nodeTypes'

const props = defineProps<{
  label: string
  modelValue: string
  flow: FlowDefinition
  self: string
  optional?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  create: [type: NodeType]
}>()
const { t } = useI18n()
const id = useId()

const others = computed(() => Object.keys(props.flow.nodes).filter((n) => n !== props.self))
const missing = computed(() => !!props.modelValue && !props.flow.nodes[props.modelValue])

function change(value: string) {
  if (value.startsWith('new:')) emit('create', value.slice(4) as NodeType)
  else emit('update:modelValue', value)
}
</script>

<template>
  <div class="mv-field">
    <label :for="id">{{ label }}</label>
    <select
      :id="id"
      class="mv-select"
      :value="missing ? '' : modelValue"
      :aria-invalid="!optional && !modelValue ? 'true' : undefined"
      @change="change(($event.target as HTMLSelectElement).value)"
    >
      <option value="">{{ optional ? t('common.none') : t('node.unlinked') }}</option>
      <option v-for="n in others" :key="n" :value="n">
        {{ flow.nodes[n]!.label || n }} · {{ t(`node.types.${flow.nodes[n]!.type}`) }}
      </option>
      <optgroup :label="t('editor.palette')">
        <option v-for="nt in NODE_TYPES" :key="nt.type" :value="`new:${nt.type}`">
          {{ t('node.newStep', { type: t(`node.types.${nt.type}`) }) }}
        </option>
      </optgroup>
    </select>
  </div>
</template>
