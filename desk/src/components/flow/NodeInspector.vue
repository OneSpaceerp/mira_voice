<script setup lang="ts">
/** Settings of the selected step. Every field, including every link, is a form control. */
import { Plus, Trash2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  Condition,
  ConditionOp,
  FlowDefinition,
  FlowNode,
  NodeType,
  Prompt,
  TimeRange,
  Weekday,
} from '@/api/types'
import { LANGUAGES } from '@/api/types'
import { outputs, target } from '@/flow/nodeTypes'

import NextSelect from './NextSelect.vue'

const props = defineProps<{
  flow: FlowDefinition
  id: string
  prompts: Prompt[]
  problems: string[]
}>()
const emit = defineEmits<{
  update: [node: FlowNode]
  rename: [to: string]
  start: []
  remove: []
  link: [output: string, to: string]
  create: [output: string, type: NodeType]
}>()
const { t } = useI18n()

const node = computed(() => props.flow.nodes[props.id]!)
const isStart = computed(() => props.flow.start === props.id)
/** In the template: which fields to show (a function, so types do not narrow between blocks). */
const is = (...types: NodeType[]) => types.includes(node.value.type)
const draftId = ref(props.id)
watch(
  () => props.id,
  (v) => (draftId.value = v),
)

// shown in help text; kept out of the template, where '}}' would end the expression
const PLACEHOLDER = '{' + '{name}' + '}'
const DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '*', '#']
const DAYS: Weekday[] = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri']
const OPS: ConditionOp[] = ['eq', 'ne', 'gt', 'lt', 'contains', 'empty', 'not_empty']

function set(field: string, value: unknown) {
  const copy: FlowNode = structuredClone(node.value)
  if (value === '' || value === undefined) delete copy[field]
  else copy[field] = value
  emit('update', copy)
}
function num(field: string, event: Event) {
  const v = (event.target as HTMLInputElement).valueAsNumber
  if (!Number.isNaN(v)) set(field, v)
}
const str = (event: Event) => (event.target as HTMLInputElement | HTMLSelectElement).value

// "No end key" is an empty terminator, which must be kept (absent means the default "#")
const terminator = computed(() =>
  node.value.terminator === '' ? 'none' : String(node.value.terminator ?? '#'),
)
function setTerminator(event: Event) {
  const v = str(event)
  emit('update', { ...structuredClone(node.value), terminator: v === 'none' ? '' : v })
}

// ---- menu keys
const options = computed(() => (node.value.options as Record<string, string>) ?? {})
function addOption() {
  const free = DIGITS.find((d) => !(d in options.value))
  if (free) set('options', { ...options.value, [free]: '' })
}
function changeKey(from: string, to: string) {
  if (from === to || to in options.value) return
  const next: Record<string, string> = {}
  for (const [k, v] of Object.entries(options.value)) next[k === from ? to : k] = v
  set('options', next)
}
function removeOption(key: string) {
  const next = { ...options.value }
  delete next[key]
  set('options', next)
}

// ---- opening hours
const weekly = computed(() => (node.value.weekly as TimeRange[]) ?? [])
const holidays = computed(() => (node.value.holidays as string[]) ?? [])
function setRange(i: number, change: Partial<TimeRange>) {
  set(
    'weekly',
    weekly.value.map((r, j) => (j === i ? { ...r, ...change } : r)),
  )
}
function toggleDay(i: number, day: Weekday) {
  const days = weekly.value[i]!.days
  setRange(i, { days: days.includes(day) ? days.filter((d) => d !== day) : [...days, day] })
}

// ---- branch conditions
const conditions = computed(() => (node.value.conditions as Condition[]) ?? [])
function setCondition(i: number, change: Partial<Condition>) {
  set(
    'conditions',
    conditions.value.map((c, j) => (j === i ? { ...c, ...change } : c)),
  )
}

// ---- data dip rows (headers, body, extract): objects edited as key/value rows
function rows(field: string): [string, string][] {
  return Object.entries((node.value[field] as Record<string, string>) ?? {})
}
function setRow(field: string, i: number, key: string, value: string) {
  const list = rows(field)
  list[i] = [key, value]
  set(field, Object.fromEntries(list))
}
function addRow(field: string) {
  set(field, { ...Object.fromEntries(rows(field)), [`name_${rows(field).length + 1}`]: '' })
}
function removeRow(field: string, i: number) {
  set(field, Object.fromEntries(rows(field).filter((_, j) => j !== i)))
}

function promptLabel(p: Prompt) {
  const langs = LANGUAGES.filter((l) => p.audio.some((a) => a.language === l))
  return `${p.name} (${langs.map((l) => l.toUpperCase()).join(' · ') || '—'})`
}
const portLabel = (o: { label: string; literal?: boolean }) =>
  o.literal ? `${t('node.key')} ${o.label}` : t(o.label)
const linkLabel = (o: { label: string; literal?: boolean }) =>
  outputs(node.value).length > 1 ? `${t('node.next')} (${portLabel(o)})` : t('node.next')
</script>

<template>
  <aside class="inspector" :aria-label="t(`node.types.${node.type}`)">
    <header class="inspector__head">
      <h2 class="mv-heading">{{ t(`node.types.${node.type}`) }}</h2>
      <button
        type="button"
        class="mv-btn mv-btn--sm mv-btn--danger"
        :disabled="isStart"
        :title="isStart ? t('editor.startCannotDelete') : ''"
        @click="emit('remove')"
      >
        <Trash2 :size="16" aria-hidden="true" />
        {{ t('editor.deleteNode') }}
      </button>
    </header>

    <div v-if="problems.length" class="mv-banner mv-banner--danger" role="status">
      <ul>
        <li v-for="p in problems" :key="p">{{ p }}</li>
      </ul>
    </div>

    <div class="mv-field">
      <label for="node-id">{{ t('node.id') }}</label>
      <input
        id="node-id"
        v-model="draftId"
        class="mv-input mv-input--mono"
        pattern="[a-z][a-z0-9_]{0,39}"
        aria-describedby="node-id-help"
        @change="emit('rename', draftId)"
      />
      <span id="node-id-help" class="mv-field__help">{{ t('node.idHelp') }}</span>
    </div>
    <div class="mv-field">
      <label for="node-label">{{ t('node.label') }} ({{ t('common.optional') }})</label>
      <input
        id="node-label"
        class="mv-input"
        maxlength="80"
        :value="node.label ?? ''"
        @change="set('label', str($event))"
      />
    </div>
    <button
      v-if="!isStart"
      type="button"
      class="mv-btn mv-btn--sm mv-btn--quiet"
      @click="emit('start')"
    >
      {{ t('node.makeStart') }}
    </button>

    <!-- prompt (play, menu, collect) -->
    <div v-if="is('play', 'menu', 'collect')" class="mv-field">
      <label for="node-prompt">{{ t('node.prompt') }}</label>
      <select
        id="node-prompt"
        class="mv-select"
        :value="node.prompt ?? ''"
        :aria-invalid="!node.prompt ? 'true' : undefined"
        @change="set('prompt', str($event))"
      >
        <option value="">{{ t('node.choosePrompt') }}</option>
        <option v-for="p in prompts" :key="p.id" :value="p.id">{{ promptLabel(p) }}</option>
      </select>
    </div>

    <!-- menu -->
    <template v-if="is('menu')">
      <fieldset class="group">
        <legend>{{ t('node.options') }}</legend>
        <div v-for="key in Object.keys(options).sort()" :key="key" class="row">
          <select
            class="mv-select row__key mv-ltr"
            :aria-label="t('node.key')"
            :value="key"
            @change="changeKey(key, str($event))"
          >
            <option v-for="d in DIGITS" :key="d" :value="d" :disabled="d !== key && d in options">
              {{ d }}
            </option>
          </select>
          <NextSelect
            class="row__grow"
            :label="`${t('node.next')} (${t('node.key')} ${key})`"
            :model-value="options[key] ?? ''"
            :flow="flow"
            :self="id"
            @update:model-value="emit('link', `option:${key}`, $event)"
            @create="emit('create', `option:${key}`, $event)"
          />
          <button
            type="button"
            class="mv-btn mv-btn--sm mv-btn--quiet mv-btn--icon row__remove"
            :aria-label="`${t('common.remove')} ${key}`"
            :disabled="Object.keys(options).length <= 1"
            @click="removeOption(key)"
          >
            <Trash2 :size="16" aria-hidden="true" />
          </button>
        </div>
        <button type="button" class="mv-btn mv-btn--sm mv-btn--secondary" @click="addOption">
          <Plus :size="16" aria-hidden="true" />{{ t('node.addOption') }}
        </button>
      </fieldset>
      <div class="pair">
        <div class="mv-field">
          <label for="menu-timeout">{{ t('node.timeout') }} ({{ t('common.seconds') }})</label>
          <input
            id="menu-timeout"
            class="mv-input"
            type="number"
            min="1"
            max="30"
            :value="node.timeout_seconds"
            @change="num('timeout_seconds', $event)"
          />
        </div>
        <div class="mv-field">
          <label for="menu-retries">{{ t('node.retries') }}</label>
          <input
            id="menu-retries"
            class="mv-input"
            type="number"
            min="0"
            max="5"
            :value="node.retries"
            @change="num('retries', $event)"
          />
        </div>
      </div>
      <div class="mv-field">
        <label for="menu-invalid">{{ t('node.invalidPrompt') }} ({{ t('common.optional') }})</label>
        <select
          id="menu-invalid"
          class="mv-select"
          :value="node.invalid_prompt ?? ''"
          @change="set('invalid_prompt', str($event))"
        >
          <option value="">{{ t('common.none') }}</option>
          <option v-for="p in prompts" :key="p.id" :value="p.id">{{ promptLabel(p) }}</option>
        </select>
      </div>
    </template>

    <!-- collect -->
    <template v-if="is('collect')">
      <div class="mv-field">
        <label for="collect-var">{{ t('node.variable') }}</label>
        <input
          id="collect-var"
          class="mv-input mv-input--mono"
          pattern="[a-z][a-z0-9_]{0,31}"
          :value="node.variable"
          @change="set('variable', str($event))"
        />
      </div>
      <div class="pair">
        <div class="mv-field">
          <label for="collect-min">{{ t('node.minDigits') }}</label>
          <input
            id="collect-min"
            class="mv-input"
            type="number"
            min="1"
            max="32"
            :value="node.min_digits"
            @change="num('min_digits', $event)"
          />
        </div>
        <div class="mv-field">
          <label for="collect-max">{{ t('node.maxDigits') }}</label>
          <input
            id="collect-max"
            class="mv-input"
            type="number"
            min="1"
            max="32"
            :value="node.max_digits"
            @change="num('max_digits', $event)"
          />
        </div>
      </div>
      <div class="pair">
        <div class="mv-field">
          <label for="collect-term">{{ t('node.terminator') }}</label>
          <select
            id="collect-term"
            class="mv-select mv-ltr"
            :value="terminator"
            @change="setTerminator($event)"
          >
            <option value="#">#</option>
            <option value="*">*</option>
            <option value="none">{{ t('node.noTerminator') }}</option>
          </select>
        </div>
        <div class="mv-field">
          <label for="collect-timeout">{{ t('node.timeout') }} ({{ t('common.seconds') }})</label>
          <input
            id="collect-timeout"
            class="mv-input"
            type="number"
            min="1"
            max="60"
            :value="node.timeout_seconds"
            @change="num('timeout_seconds', $event)"
          />
        </div>
      </div>
    </template>

    <!-- opening hours -->
    <template v-if="is('time')">
      <div class="mv-field">
        <label for="time-tz">{{ t('node.timezone') }} ({{ t('common.optional') }})</label>
        <input
          id="time-tz"
          class="mv-input mv-ltr"
          placeholder="Africa/Cairo"
          :value="node.timezone ?? ''"
          aria-describedby="time-tz-help"
          @change="set('timezone', str($event))"
        />
        <span id="time-tz-help" class="mv-field__help">{{ t('node.timezoneHelp') }}</span>
      </div>
      <fieldset class="group">
        <legend>{{ t('node.hours') }}</legend>
        <div v-for="(r, i) in weekly" :key="i" class="range">
          <div class="days" role="group" :aria-label="t('node.hours')">
            <button
              v-for="d in DAYS"
              :key="d"
              type="button"
              class="day"
              :aria-pressed="r.days.includes(d)"
              @click="toggleDay(i, d)"
            >
              {{ t(`days.${d}`) }}
            </button>
          </div>
          <div class="pair">
            <div class="mv-field">
              <label :for="`from-${i}`">{{ t('node.from') }}</label>
              <input
                :id="`from-${i}`"
                class="mv-input mv-ltr"
                type="time"
                :value="r.from"
                @change="setRange(i, { from: str($event) })"
              />
            </div>
            <div class="mv-field">
              <label :for="`to-${i}`">{{ t('node.to') }}</label>
              <input
                :id="`to-${i}`"
                class="mv-input mv-ltr"
                type="time"
                :value="r.to"
                @change="setRange(i, { to: str($event) })"
              />
            </div>
          </div>
          <button
            v-if="weekly.length > 1"
            type="button"
            class="mv-btn mv-btn--sm mv-btn--quiet"
            @click="
              set(
                'weekly',
                weekly.filter((_, j) => j !== i),
              )
            "
          >
            {{ t('common.remove') }}
          </button>
        </div>
        <button
          type="button"
          class="mv-btn mv-btn--sm mv-btn--secondary"
          @click="set('weekly', [...weekly, { days: ['sat'], from: '10:00', to: '14:00' }])"
        >
          <Plus :size="16" aria-hidden="true" />{{ t('node.addRange') }}
        </button>
      </fieldset>
      <fieldset class="group">
        <legend>{{ t('node.holidays') }}</legend>
        <div v-for="(h, i) in holidays" :key="i" class="row">
          <input
            class="mv-input mv-ltr row__grow"
            type="date"
            :aria-label="t('node.holidays')"
            :value="h"
            @change="
              set(
                'holidays',
                holidays.map((x, j) => (j === i ? str($event) : x)),
              )
            "
          />
          <button
            type="button"
            class="mv-btn mv-btn--sm mv-btn--quiet mv-btn--icon"
            :aria-label="`${t('common.remove')} ${h}`"
            @click="
              set(
                'holidays',
                holidays.filter((_, j) => j !== i),
              )
            "
          >
            <Trash2 :size="16" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          class="mv-btn mv-btn--sm mv-btn--secondary"
          @click="set('holidays', [...holidays, new Date().toISOString().slice(0, 10)])"
        >
          <Plus :size="16" aria-hidden="true" />{{ t('node.addHoliday') }}
        </button>
      </fieldset>
    </template>

    <!-- language -->
    <div v-if="is('language')" class="mv-field">
      <label for="lang-select">{{ t('node.language') }}</label>
      <select
        id="lang-select"
        class="mv-select"
        :value="node.language"
        @change="set('language', str($event))"
      >
        <option v-for="l in LANGUAGES" :key="l" :value="l">{{ t(`languages.${l}`) }}</option>
      </select>
    </div>

    <!-- set variable -->
    <template v-if="is('set')">
      <div class="mv-field">
        <label for="set-var">{{ t('node.variable') }}</label>
        <input
          id="set-var"
          class="mv-input mv-input--mono"
          :value="node.variable"
          @change="set('variable', str($event))"
        />
      </div>
      <div class="mv-field">
        <label for="set-value">{{ t('node.value') }}</label>
        <input
          id="set-value"
          class="mv-input mv-ltr"
          :value="node.value"
          aria-describedby="set-value-help"
          @change="set('value', str($event))"
        />
        <span id="set-value-help" class="mv-field__help">{{
          t('node.valueHelp', { placeholder: PLACEHOLDER })
        }}</span>
      </div>
    </template>

    <!-- branch -->
    <template v-if="is('branch')">
      <div class="mv-field">
        <label for="branch-var">{{ t('node.variable') }}</label>
        <input
          id="branch-var"
          class="mv-input mv-input--mono"
          :value="node.variable"
          @change="set('variable', str($event))"
        />
      </div>
      <fieldset class="group">
        <legend>{{ t('node.conditions') }}</legend>
        <div v-for="(c, i) in conditions" :key="i" class="condition">
          <div class="pair">
            <select
              class="mv-select"
              :aria-label="t('node.conditions')"
              :value="c.op"
              @change="setCondition(i, { op: str($event) as ConditionOp })"
            >
              <option v-for="op in OPS" :key="op" :value="op">{{ t(`ops.${op}`) }}</option>
            </select>
            <input
              v-if="!['empty', 'not_empty'].includes(c.op)"
              class="mv-input mv-ltr"
              :aria-label="t('node.value')"
              :value="c.value"
              @change="setCondition(i, { value: str($event) })"
            />
          </div>
          <NextSelect
            :label="`${t('node.next')} (${i + 1})`"
            :model-value="c.next"
            :flow="flow"
            :self="id"
            @update:model-value="emit('link', `condition:${i}`, $event)"
            @create="emit('create', `condition:${i}`, $event)"
          />
          <button
            v-if="conditions.length > 1"
            type="button"
            class="mv-btn mv-btn--sm mv-btn--quiet"
            @click="
              set(
                'conditions',
                conditions.filter((_, j) => j !== i),
              )
            "
          >
            {{ t('common.remove') }}
          </button>
        </div>
        <button
          type="button"
          class="mv-btn mv-btn--sm mv-btn--secondary"
          :disabled="conditions.length >= 10"
          @click="set('conditions', [...conditions, { op: 'eq', value: '', next: '' }])"
        >
          <Plus :size="16" aria-hidden="true" />{{ t('node.addCondition') }}
        </button>
      </fieldset>
    </template>

    <!-- data dip -->
    <template v-if="is('http')">
      <div class="pair">
        <div class="mv-field">
          <label for="http-method">{{ t('node.method') }}</label>
          <select
            id="http-method"
            class="mv-select mv-ltr"
            :value="node.method"
            @change="set('method', str($event))"
          >
            <option value="GET">GET</option>
            <option value="POST">POST</option>
          </select>
        </div>
        <div class="mv-field">
          <label for="http-timeout">{{ t('node.timeout') }} ({{ t('common.seconds') }})</label>
          <input
            id="http-timeout"
            class="mv-input"
            type="number"
            min="1"
            max="5"
            step="0.5"
            :value="node.timeout_seconds"
            @change="num('timeout_seconds', $event)"
          />
        </div>
      </div>
      <div class="mv-field">
        <label for="http-url">{{ t('node.url') }}</label>
        <input
          id="http-url"
          class="mv-input mv-input--mono"
          :value="node.url"
          aria-describedby="http-url-help"
          @change="set('url', str($event))"
        />
        <span id="http-url-help" class="mv-field__help">{{ t('node.urlHelp') }}</span>
      </div>
      <fieldset
        v-for="field in ['headers', 'body', 'extract']"
        v-show="field !== 'body' || node.method === 'POST'"
        :key="field"
        class="group"
      >
        <legend>{{ t(`node.${field}`) }}</legend>
        <div v-for="([k, v], i) in rows(field)" :key="i" class="row">
          <input
            class="mv-input mv-input--mono"
            :aria-label="field === 'extract' ? t('node.variable') : t('node.label')"
            :value="k"
            @change="setRow(field, i, str($event), v)"
          />
          <input
            class="mv-input mv-input--mono row__grow"
            :aria-label="field === 'extract' ? t('node.path') : t('node.value')"
            :value="v"
            @change="setRow(field, i, k, str($event))"
          />
          <button
            type="button"
            class="mv-btn mv-btn--sm mv-btn--quiet mv-btn--icon"
            :aria-label="`${t('common.remove')} ${k}`"
            @click="removeRow(field, i)"
          >
            <Trash2 :size="16" aria-hidden="true" />
          </button>
        </div>
        <button type="button" class="mv-btn mv-btn--sm mv-btn--secondary" @click="addRow(field)">
          <Plus :size="16" aria-hidden="true" />{{ t('node.addRow') }}
        </button>
      </fieldset>
    </template>

    <!-- transfer / voicemail / queue -->
    <div v-if="is('transfer')" class="mv-field">
      <label for="transfer-number">{{ t('node.number') }}</label>
      <input
        id="transfer-number"
        class="mv-input mv-input--mono"
        inputmode="tel"
        :value="node.number"
        aria-describedby="transfer-help"
        @change="set('number', str($event))"
      />
      <span id="transfer-help" class="mv-field__help">{{ t('node.numberHelp') }}</span>
    </div>
    <div v-if="is('queue')" class="mv-field">
      <label for="queue-id">{{ t('node.queue') }}</label>
      <input
        id="queue-id"
        class="mv-input mv-input--mono"
        :value="node.queue"
        @change="set('queue', str($event))"
      />
    </div>
    <template v-if="is('voicemail')">
      <div class="mv-field">
        <label for="vm-box">{{ t('node.mailbox') }}</label>
        <input
          id="vm-box"
          class="mv-input mv-input--mono"
          inputmode="numeric"
          :value="node.mailbox"
          @change="set('mailbox', str($event))"
        />
      </div>
      <div class="mv-field">
        <label for="vm-greeting">{{ t('node.greeting') }} ({{ t('common.optional') }})</label>
        <select
          id="vm-greeting"
          class="mv-select"
          :value="node.greeting ?? ''"
          @change="set('greeting', str($event))"
        >
          <option value="">{{ t('common.none') }}</option>
          <option v-for="p in prompts" :key="p.id" :value="p.id">{{ promptLabel(p) }}</option>
        </select>
      </div>
      <div class="mv-field">
        <label for="vm-max">{{ t('node.maxSeconds') }} ({{ t('common.seconds') }})</label>
        <input
          id="vm-max"
          class="mv-input"
          type="number"
          min="5"
          max="600"
          :value="node.max_seconds"
          @change="num('max_seconds', $event)"
        />
      </div>
    </template>

    <!-- links -->
    <div v-if="!is('menu') && !is('branch')" class="links">
      <NextSelect
        v-for="o in outputs(node)"
        :key="o.key"
        :label="linkLabel(o)"
        :model-value="target(node, o.key)"
        :flow="flow"
        :self="id"
        :optional="o.optional"
        @update:model-value="emit('link', o.key, $event)"
        @create="emit('create', o.key, $event)"
      />
    </div>
    <div v-else class="links">
      <NextSelect
        v-for="o in outputs(node).filter((x) => !x.literal)"
        :key="o.key"
        :label="linkLabel(o)"
        :model-value="target(node, o.key)"
        :flow="flow"
        :self="id"
        :optional="o.optional"
        @update:model-value="emit('link', o.key, $event)"
        @create="emit('create', o.key, $event)"
      />
    </div>
  </aside>
</template>

<style scoped>
.inspector {
  display: grid;
  gap: var(--space-4);
  align-content: start;
  padding: var(--space-4);
  overflow-y: auto;
}
.inspector__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
}
.inspector__head h2 {
  margin: 0;
}
.group {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
}
.group legend {
  padding-inline: var(--space-1);
  font: var(--type-label-weight) var(--type-label-size) / var(--type-label-line)
    var(--type-label-family);
}
.row {
  display: flex;
  gap: var(--space-2);
  align-items: end;
}
.row__key {
  inline-size: var(--space-16);
  flex: none;
}
.row__grow {
  flex: 1;
  min-inline-size: 0;
}
.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}
.range,
.condition {
  display: grid;
  gap: var(--space-2);
  padding-block-end: var(--space-3);
  border-block-end: 1px solid var(--line);
}
.days {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}
.day {
  min-block-size: var(--control-sm);
  padding-inline: var(--space-2);
  border: 1px solid var(--line);
  border-radius: var(--radius-pill);
  background: var(--surface-raised);
  color: var(--ink);
  font: inherit;
  cursor: pointer;
}
.day[aria-pressed='true'] {
  background: var(--state-hold-soft);
  border-color: var(--state-hold);
}
.links {
  display: grid;
  gap: var(--space-3);
  padding-block-start: var(--space-3);
  border-block-start: 1px solid var(--line);
}
</style>
