<script setup lang="ts">
/**
 * Mira Flow builder: palette | canvas | inspector, a problems panel and the versions list.
 * The flow is one immutable FlowDefinition (shallowRef) replaced on every edit, so "unsaved"
 * is a comparison with the last saved JSON. Publishing is the screen's one red action.
 */
import { ArrowLeft, History } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, RouterLink } from 'vue-router'

import { ApiError } from '@/api/http'
import { flows as flowsApi, prompts as promptsApi } from '@/api/mira'
import type { Flow, FlowDefinition, FlowNode, FlowVersion, NodeType, Prompt } from '@/api/types'
import FlowCanvas from '@/components/flow/FlowCanvas.vue'
import NodeInspector from '@/components/flow/NodeInspector.vue'
import {
  addNode,
  moveNode,
  nodeOfReport,
  normalise,
  removeNode,
  renameNode,
  toDraft,
  updateNode,
} from '@/flow/graph'
import { link, NODE_TYPES, outputs, target } from '@/flow/nodeTypes'

const props = defineProps<{ id: string }>()
const { t } = useI18n()

const meta = ref<Flow | null>(null)
const flow = shallowRef<FlowDefinition | null>(null)
const savedJson = ref('')
const selected = ref<string | null>(null)
const prompts = ref<Prompt[]>([])
const report = ref<{ errors: string[]; warnings: string[] }>({ errors: [], warnings: [] })
const notice = ref<{ kind: 'ok' | 'danger'; lines: string[] } | null>(null)
const busy = ref<'save' | 'publish' | ''>('')
const versions = ref<FlowVersion[] | null>(null)
const loadError = ref('')

const dirty = computed(
  () => !!flow.value && JSON.stringify(toDraft(flow.value)) !== savedJson.value,
)
const problemsByNode = computed(() => {
  const out: Record<string, number> = {}
  if (flow.value) {
    for (const line of report.value.errors) {
      const id = nodeOfReport(line, flow.value)
      if (id) out[id] = (out[id] ?? 0) + 1
    }
  }
  return out
})
const selectedProblems = computed(() =>
  selected.value && flow.value
    ? report.value.errors.filter((l) => nodeOfReport(l, flow.value!) === selected.value)
    : [],
)

function accept(f: Flow) {
  meta.value = f
  flow.value = normalise(f.draft)
  savedJson.value = JSON.stringify(toDraft(normalise(f.draft)))
  report.value = f.report ?? { errors: [], warnings: [] }
}

async function load() {
  loadError.value = ''
  try {
    const [f, p] = await Promise.all([flowsApi.get(props.id), promptsApi.list()])
    prompts.value = p
    accept(f)
    // a brand-new flow: store its starting step right away so the report has something to say
    if (!f.draft || !Object.keys(f.draft).length) await save()
    selected.value ??= flow.value?.start ?? null
  } catch (e) {
    loadError.value = e instanceof ApiError && e.status === 404 ? e.message : t('common.error')
  }
}

function edit(next: FlowDefinition) {
  flow.value = next
  notice.value = null
}

async function save() {
  if (!flow.value || busy.value) return
  busy.value = 'save'
  try {
    const f = await flowsApi.saveDraft(props.id, toDraft(flow.value))
    meta.value = f
    savedJson.value = JSON.stringify(toDraft(flow.value))
    report.value = f.report ?? { errors: [], warnings: [] }
  } catch (e) {
    notice.value = { kind: 'danger', lines: e instanceof ApiError ? e.lines : [t('common.error')] }
  } finally {
    busy.value = ''
  }
}

async function publish() {
  if (!flow.value) return
  if (dirty.value) await save()
  if (report.value.errors.length) {
    notice.value = { kind: 'danger', lines: [t('editor.publishBlocked'), ...report.value.errors] }
    return
  }
  busy.value = 'publish'
  try {
    const f = await flowsApi.publish(props.id)
    meta.value = f
    notice.value = {
      kind: 'ok',
      lines: [t('editor.publishedOk', { version: f.published_version ?? '' })],
    }
    if (versions.value) versions.value = await flowsApi.versions(props.id)
  } catch (e) {
    notice.value = {
      kind: 'danger',
      lines: [
        t('editor.publishBlocked'),
        ...(e instanceof ApiError ? e.lines : [t('common.error')]),
      ],
    }
  } finally {
    busy.value = ''
  }
}

async function toggleVersions() {
  versions.value = versions.value ? null : await flowsApi.versions(props.id)
}
async function rollback(v: number) {
  try {
    meta.value = await flowsApi.rollback(props.id, v)
    versions.value = await flowsApi.versions(props.id)
  } catch (e) {
    notice.value = { kind: 'danger', lines: e instanceof ApiError ? e.lines : [t('common.error')] }
  }
}
async function editVersion(v: number) {
  accept(await flowsApi.editVersion(props.id, v))
  selected.value = flow.value?.start ?? null
}

// ---- edits from the canvas, palette and inspector
function onMove(id: string, x: number, y: number) {
  if (flow.value) edit(moveNode(flow.value, id, x, y))
}
function onLink(source: string, output: string, to: string) {
  if (!flow.value) return
  const node = flow.value.nodes[source]
  if (node) edit(updateNode(flow.value, source, link(node, output, to)))
}
function onCreate(source: string, output: string, type: NodeType) {
  if (!flow.value) return
  const r = addNode(flow.value, type, { id: source, output })
  edit(r.flow)
  selected.value = r.id
}
function addFromPalette(type: NodeType) {
  if (!flow.value) return
  const anchor = selected.value
  // link the new step to the selected step's first free output, if it has one
  const anchorNode = anchor ? flow.value.nodes[anchor] : undefined
  const free = anchorNode ? outputs(anchorNode).find((o) => !target(anchorNode, o.key)) : undefined
  const r = addNode(flow.value, type, anchor ? { id: anchor, output: free?.key } : undefined)
  edit(r.flow)
  selected.value = r.id
}
function onUpdate(node: FlowNode) {
  if (flow.value && selected.value) edit(updateNode(flow.value, selected.value, node))
}
function onRename(to: string) {
  if (!flow.value || !selected.value) return
  const next = renameNode(flow.value, selected.value, to)
  if (next !== flow.value) {
    edit(next)
    selected.value = to
  }
}
function onRemove() {
  if (!flow.value || !selected.value) return
  edit(removeNode(flow.value, selected.value))
  selected.value = flow.value.start
}
function onStart() {
  if (flow.value && selected.value) edit({ ...flow.value, start: selected.value })
}
function selectProblem(line: string) {
  if (flow.value) selected.value = nodeOfReport(line, flow.value) ?? selected.value
}

// ---- keyboard: Ctrl+S saves; arrow keys move the selected step (WCAG 2.5.7 alternative)
function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    void save()
    return
  }
  const target = e.target as HTMLElement
  if (
    !flow.value ||
    !selected.value ||
    target.closest('input, select, textarea, [contenteditable]')
  )
    return
  const step = e.shiftKey ? 64 : 8
  const moves: Record<string, [number, number]> = {
    ArrowLeft: [-step, 0],
    ArrowRight: [step, 0],
    ArrowUp: [0, -step],
    ArrowDown: [0, step],
  }
  const d = moves[e.key]
  const node = flow.value.nodes[selected.value]
  if (d && node) {
    e.preventDefault()
    edit(moveNode(flow.value, selected.value, (node.x ?? 0) + d[0], (node.y ?? 0) + d[1]))
  }
}

function beforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) e.preventDefault()
}
onBeforeRouteLeave(() => !dirty.value || window.confirm(t('common.unsaved')))
onMounted(() => {
  void load()
  window.addEventListener('keydown', onKey)
  window.addEventListener('beforeunload', beforeUnload)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<template>
  <div class="editor">
    <header class="bar">
      <RouterLink class="mv-btn mv-btn--quiet mv-btn--sm" :to="{ name: 'flows' }">
        <ArrowLeft :size="16" aria-hidden="true" class="mirror" />
        {{ t('editor.back') }}
      </RouterLink>
      <h1 class="mv-heading bar__title">{{ meta?.name ?? '' }}</h1>
      <span v-if="meta?.number" class="mv-number">{{ meta.number }}</span>
      <span
        v-if="meta"
        class="mv-chip"
        :class="meta.published_version ? 'mv-chip--live' : 'mv-chip--offline'"
      >
        {{
          meta.published_version
            ? t('flows.published', { version: meta.published_version })
            : t('flows.notPublished')
        }}
      </span>
      <span class="bar__state mv-caption" role="status" aria-live="polite">
        {{ busy === 'save' ? t('common.saving') : dirty ? t('common.unsaved') : t('common.saved') }}
      </span>
      <div class="bar__actions">
        <label v-if="flow" class="goto">
          <span class="mv-visually-hidden">{{ t('editor.nothingSelected') }}</span>
          <select
            class="mv-select"
            :value="selected ?? ''"
            @change="selected = ($event.target as HTMLSelectElement).value || null"
          >
            <option v-for="(n, nid) in flow.nodes" :key="nid" :value="nid">
              {{ n.label || nid }} · {{ t(`node.types.${n.type}`) }}
            </option>
          </select>
        </label>
        <button
          type="button"
          class="mv-btn mv-btn--secondary mv-btn--sm"
          :aria-expanded="!!versions"
          @click="toggleVersions"
        >
          <History :size="16" aria-hidden="true" />
          {{ t('editor.versions') }}
        </button>
        <button
          type="button"
          class="mv-btn mv-btn--secondary mv-btn--sm"
          :disabled="!dirty || !!busy"
          @click="save"
        >
          {{ t('common.save') }}
        </button>
        <button
          type="button"
          class="mv-btn mv-btn--primary mv-btn--sm"
          :disabled="!!busy"
          @click="publish"
        >
          {{ busy === 'publish' ? t('editor.publishing') : t('editor.publish') }}
        </button>
      </div>
    </header>

    <div v-if="loadError" class="mv-banner mv-banner--danger" role="alert">{{ loadError }}</div>
    <div
      v-if="notice"
      class="mv-banner notice"
      :class="notice.kind === 'ok' ? 'mv-banner--ok' : 'mv-banner--danger'"
      role="status"
    >
      <ul>
        <li v-for="line in notice.lines" :key="line">
          <button
            v-if="flow && nodeOfReport(line, flow)"
            type="button"
            class="linkish"
            @click="selectProblem(line)"
          >
            {{ line }}
          </button>
          <template v-else>{{ line }}</template>
        </li>
      </ul>
    </div>

    <div v-if="flow" class="body">
      <nav class="palette" :aria-label="t('editor.palette')">
        <h2 class="mv-label">{{ t('editor.palette') }}</h2>
        <p class="mv-caption">{{ t('editor.paletteHelp') }}</p>
        <button
          v-for="nt in NODE_TYPES"
          :key="nt.type"
          type="button"
          class="palette__item"
          :class="`palette__item--${nt.stripe}`"
          @click="addFromPalette(nt.type)"
        >
          {{ t(`node.types.${nt.type}`) }}
        </button>
        <p class="mv-caption palette__tip">{{ t('editor.shortcuts') }}</p>
      </nav>

      <FlowCanvas
        class="stage"
        :flow="flow"
        :selected="selected"
        :problems="problemsByNode"
        :prompts="prompts"
        @select="selected = $event"
        @move="onMove"
        @link="onLink"
      />

      <div class="side">
        <NodeInspector
          v-if="selected && flow.nodes[selected]"
          :key="selected"
          :flow="flow"
          :id="selected"
          :prompts="prompts"
          :problems="selectedProblems"
          @update="onUpdate"
          @rename="onRename"
          @start="onStart"
          @remove="onRemove"
          @link="(output, to) => onLink(selected!, output, to)"
          @create="(output, type) => onCreate(selected!, output, type)"
        />
        <p v-else class="side__empty mv-caption">{{ t('editor.nothingSelected') }}</p>

        <section class="report" :aria-label="t('editor.problems')">
          <h2 class="mv-label">{{ t('editor.problems') }} ({{ report.errors.length }})</h2>
          <p v-if="!report.errors.length && !report.warnings.length" class="mv-caption">
            {{ t('editor.noProblems') }}
          </p>
          <ul class="report__list">
            <li v-for="line in report.errors" :key="line">
              <button type="button" class="linkish report__error" @click="selectProblem(line)">
                {{ line }}
              </button>
            </li>
            <li v-for="line in report.warnings" :key="line" class="mv-caption">
              {{ t('editor.warnings') }}: {{ line }}
            </li>
          </ul>
        </section>

        <section v-if="versions" class="versions" :aria-label="t('editor.versions')">
          <h2 class="mv-label">{{ t('editor.versions') }}</h2>
          <ul class="report__list">
            <li v-for="v in versions" :key="v.version" class="version">
              <span class="mv-number">v{{ v.version }}</span>
              <time class="mv-caption" :datetime="v.published_at">{{
                new Date(v.published_at).toLocaleString()
              }}</time>
              <span v-if="v.current" class="mv-chip mv-chip--live">{{ t('editor.current') }}</span>
              <button
                v-else
                type="button"
                class="mv-btn mv-btn--sm mv-btn--secondary"
                @click="rollback(v.version)"
              >
                {{ t('editor.rollback') }}
              </button>
              <button
                type="button"
                class="mv-btn mv-btn--sm mv-btn--quiet"
                @click="editVersion(v.version)"
              >
                {{ t('editor.editVersion') }}
              </button>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor {
  display: grid;
  grid-template-rows: auto auto 1fr;
  block-size: 100dvh;
}
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-raised);
  border-block-end: 1px solid var(--line);
}
.bar__title {
  margin: 0;
}
.bar__state {
  margin-inline-start: var(--space-2);
}
.bar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-inline-start: auto;
}
.goto .mv-select {
  min-block-size: var(--control-sm);
  max-inline-size: 240px;
}
.notice {
  margin: var(--space-3) var(--space-4) 0;
}
.body {
  grid-row: 3; /* the stretching row, whether or not a notice is shown above */
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr) 360px;
  min-block-size: 0;
}
.palette {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  border-inline-end: 1px solid var(--line);
  overflow-y: auto;
}
.palette h2,
.palette p {
  margin: 0;
}
.palette__item {
  text-align: start;
  min-block-size: var(--control-sm);
  padding-inline: var(--space-3);
  background: var(--surface-raised);
  color: var(--ink);
  border: 1px solid var(--line);
  border-inline-start: 4px solid var(--stripe);
  border-radius: var(--radius-md);
  font: inherit;
  cursor: pointer;
}
.palette__item:hover {
  background: var(--surface-sunken);
}
.palette__item--hold {
  --stripe: var(--state-hold);
}
.palette__item--live {
  --stripe: var(--state-live);
}
.palette__item--offline {
  --stripe: var(--state-offline);
}
.palette__item--ringing {
  --stripe: var(--state-ringing);
}
.palette__item--ink {
  --stripe: var(--ink);
}
.palette__tip {
  margin-block-start: auto;
}
.stage {
  min-block-size: 0;
}
.side {
  display: flex;
  flex-direction: column;
  min-block-size: 0;
  overflow-y: auto;
  background: var(--surface-raised);
  border-inline-start: 1px solid var(--line);
}
.side__empty {
  padding: var(--space-4);
}
.report,
.versions {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-4);
  border-block-start: 1px solid var(--line);
}
.report h2,
.versions h2 {
  margin: 0;
}
.report__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-1);
}
.report__error {
  color: var(--danger);
}
.version {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}
.linkish {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  text-decoration: underline;
  cursor: pointer;
}
:dir(rtl) .mirror {
  transform: scaleX(-1);
}
</style>
