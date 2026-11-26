<script setup lang="ts">
import { Plus } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { flows as flowsApi } from '@/api/mira'
import type { Flow } from '@/api/types'

const { t } = useI18n()
const router = useRouter()
const list = ref<Flow[] | null>(null)
const error = ref('')
const creating = ref(false)
const name = ref('')
const number = ref('')
const createError = ref<string[]>([])

async function load() {
  error.value = ''
  try {
    list.value = await flowsApi.list()
  } catch {
    error.value = t('common.error')
  }
}

async function create() {
  createError.value = []
  try {
    const flow = await flowsApi.create(name.value.trim(), number.value.trim() || null)
    await router.push({ name: 'flow', params: { id: flow.id } })
  } catch (e) {
    createError.value = e instanceof ApiError ? e.lines : [t('common.error')]
  }
}

onMounted(load)
</script>

<template>
  <div class="mv-page">
    <header class="mv-page__head">
      <h1 class="mv-title">{{ t('flows.title') }}</h1>
      <button
        v-if="!creating"
        type="button"
        class="mv-btn mv-btn--secondary"
        @click="creating = true"
      >
        <Plus :size="18" aria-hidden="true" />
        {{ t('flows.new') }}
      </button>
    </header>

    <form v-if="creating" class="create mv-panel" @submit.prevent="create">
      <div class="mv-field">
        <label for="flow-name">{{ t('flows.name') }}</label>
        <input id="flow-name" v-model="name" class="mv-input" required maxlength="100" />
      </div>
      <div class="mv-field">
        <label for="flow-number">{{ t('flows.number') }} ({{ t('common.optional') }})</label>
        <input
          id="flow-number"
          v-model="number"
          class="mv-input mv-input--mono"
          inputmode="numeric"
          pattern="[0-9]{2,16}"
          aria-describedby="flow-number-help"
        />
        <span id="flow-number-help" class="mv-field__help">{{ t('flows.numberHelp') }}</span>
      </div>
      <div v-if="createError.length" class="mv-banner mv-banner--danger" role="alert">
        <ul>
          <li v-for="line in createError" :key="line">{{ line }}</li>
        </ul>
      </div>
      <div class="create__actions">
        <button type="submit" class="mv-btn mv-btn--secondary">{{ t('common.create') }}</button>
        <button type="button" class="mv-btn mv-btn--quiet" @click="creating = false">
          {{ t('common.cancel') }}
        </button>
      </div>
    </form>

    <div v-if="error" class="mv-banner mv-banner--danger" role="alert">
      {{ error }}
      <button type="button" class="mv-btn mv-btn--sm mv-btn--secondary" @click="load">
        {{ t('common.retry') }}
      </button>
    </div>
    <p v-else-if="list === null" class="mv-caption">{{ t('common.loading') }}</p>
    <p v-else-if="!list.length && !creating" class="empty">{{ t('flows.empty') }}</p>
    <ul v-else class="list">
      <li v-for="flow in list" :key="flow.id" class="row mv-panel">
        <div class="row__main">
          <RouterLink class="row__name" :to="{ name: 'flow', params: { id: flow.id } }">
            {{ flow.name }}
          </RouterLink>
          <span v-if="flow.number" class="mv-number">{{ flow.number }}</span>
        </div>
        <span
          class="mv-chip"
          :class="flow.published_version ? 'mv-chip--live' : 'mv-chip--offline'"
        >
          {{
            flow.published_version
              ? t('flows.published', { version: flow.published_version })
              : t('flows.notPublished')
          }}
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.create {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-6);
  margin-block-end: var(--space-6);
  max-inline-size: 480px;
}
.create__actions {
  display: flex;
  gap: var(--space-2);
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--space-2);
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-6);
}
.row__main {
  display: flex;
  align-items: baseline;
  gap: var(--space-4);
}
.row__name {
  color: var(--ink);
  font: var(--type-body-strong-weight) var(--type-body-strong-size) / var(--type-body-strong-line)
    var(--type-body-strong-family);
}
.empty {
  color: var(--ink-muted);
}
</style>
