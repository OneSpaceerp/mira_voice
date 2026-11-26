<script setup lang="ts">
import { Pause, Play, Plus, Trash2, Upload } from 'lucide-vue-next'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/http'
import { prompts as promptsApi } from '@/api/mira'
import { LANGUAGES, type Language, type Prompt } from '@/api/types'

const { t } = useI18n()
const list = ref<Prompt[] | null>(null)
const problems = ref<string[]>([])
const creating = ref(false)
const name = ref('')
const playing = ref<string>('') // `${prompt id}:${language}`
const audio = new Audio()
let objectUrl = ''

async function load() {
  try {
    list.value = await promptsApi.list()
  } catch {
    problems.value = [t('common.error')]
  }
}

function fail(e: unknown) {
  problems.value = e instanceof ApiError ? e.lines : [t('common.error')]
}

async function create() {
  problems.value = []
  try {
    await promptsApi.create(name.value.trim())
    name.value = ''
    creating.value = false
    await load()
  } catch (e) {
    fail(e)
  }
}

function recording(p: Prompt, lang: Language) {
  return p.audio.find((a) => a.language === lang)
}

async function upload(p: Prompt, lang: Language, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  problems.value = []
  try {
    await promptsApi.upload(p.id, lang, file)
    await load()
  } catch (e) {
    fail(e)
  }
}

async function play(p: Prompt, lang: Language) {
  const key = `${p.id}:${lang}`
  audio.pause()
  if (playing.value === key) {
    playing.value = ''
    return
  }
  try {
    const blob = await promptsApi.audio(p.id, lang)
    if (objectUrl) URL.revokeObjectURL(objectUrl)
    objectUrl = URL.createObjectURL(blob)
    audio.src = objectUrl
    playing.value = key
    audio.onended = () => (playing.value = '')
    await audio.play()
  } catch (e) {
    playing.value = ''
    fail(e)
  }
}

async function removeAudio(p: Prompt, lang: Language) {
  problems.value = []
  try {
    await promptsApi.removeAudio(p.id, lang)
    await load()
  } catch (e) {
    fail(e)
  }
}

async function remove(p: Prompt) {
  if (!window.confirm(t('prompts.deleteConfirm', { name: p.name }))) return
  problems.value = []
  try {
    await promptsApi.remove(p.id)
    await load()
  } catch (e) {
    problems.value =
      e instanceof ApiError && e.status === 409 ? [t('prompts.inUse')] : [t('common.error')]
  }
}

onMounted(load)
onBeforeUnmount(() => {
  audio.pause()
  if (objectUrl) URL.revokeObjectURL(objectUrl)
})
</script>

<template>
  <div class="mv-page">
    <header class="mv-page__head">
      <h1 class="mv-title">{{ t('prompts.title') }}</h1>
      <button
        v-if="!creating"
        type="button"
        class="mv-btn mv-btn--secondary"
        @click="creating = true"
      >
        <Plus :size="18" aria-hidden="true" />
        {{ t('prompts.new') }}
      </button>
    </header>
    <p class="mv-caption">{{ t('prompts.format') }}</p>

    <form v-if="creating" class="create mv-panel" @submit.prevent="create">
      <div class="mv-field">
        <label for="prompt-name">{{ t('prompts.name') }}</label>
        <input id="prompt-name" v-model="name" class="mv-input" required maxlength="100" />
      </div>
      <div class="create__actions">
        <button type="submit" class="mv-btn mv-btn--secondary">{{ t('common.create') }}</button>
        <button type="button" class="mv-btn mv-btn--quiet" @click="creating = false">
          {{ t('common.cancel') }}
        </button>
      </div>
    </form>

    <div v-if="problems.length" class="mv-banner mv-banner--danger" role="alert">
      <ul>
        <li v-for="line in problems" :key="line">{{ line }}</li>
      </ul>
    </div>

    <p v-if="list === null" class="mv-caption">{{ t('common.loading') }}</p>
    <p v-else-if="!list.length && !creating" class="empty">{{ t('prompts.empty') }}</p>
    <ul v-else class="list">
      <li v-for="p in list" :key="p.id" class="prompt mv-panel">
        <div class="prompt__head">
          <h2 class="mv-heading">{{ p.name }}</h2>
          <button
            type="button"
            class="mv-btn mv-btn--sm mv-btn--danger mv-btn--icon"
            :aria-label="`${t('common.delete')}: ${p.name}`"
            @click="remove(p)"
          >
            <Trash2 :size="16" aria-hidden="true" />
          </button>
        </div>
        <div class="langs">
          <div v-for="lang in LANGUAGES" :key="lang" class="lang">
            <span
              class="mv-chip"
              :class="recording(p, lang) ? 'mv-chip--live' : 'mv-chip--offline'"
            >
              {{ lang.toUpperCase() }}
              <span v-if="recording(p, lang)" class="mv-ltr">
                ·
                {{
                  t('prompts.duration', {
                    seconds: Math.round(recording(p, lang)!.duration_ms / 1000),
                  })
                }}
              </span>
              <span v-else class="mv-visually-hidden">
                {{ t('prompts.missing', { language: t(`languages.${lang}`) }) }}
              </span>
            </span>
            <button
              v-if="recording(p, lang)"
              type="button"
              class="mv-btn mv-btn--sm mv-btn--quiet mv-btn--icon"
              :aria-label="t('prompts.play', { language: t(`languages.${lang}`) })"
              :aria-pressed="playing === `${p.id}:${lang}`"
              @click="play(p, lang)"
            >
              <component
                :is="playing === `${p.id}:${lang}` ? Pause : Play"
                :size="16"
                aria-hidden="true"
              />
            </button>
            <label class="mv-btn mv-btn--sm mv-btn--secondary">
              <Upload :size="16" aria-hidden="true" />
              {{
                t(recording(p, lang) ? 'prompts.replace' : 'prompts.upload', {
                  language: lang.toUpperCase(),
                })
              }}
              <input
                type="file"
                accept=".wav,audio/wav"
                class="mv-visually-hidden"
                @change="upload(p, lang, $event)"
              />
            </label>
            <button
              v-if="recording(p, lang)"
              type="button"
              class="mv-btn mv-btn--sm mv-btn--quiet mv-btn--icon"
              :aria-label="`${t('common.remove')}: ${t(`languages.${lang}`)}`"
              @click="removeAudio(p, lang)"
            >
              <Trash2 :size="14" aria-hidden="true" />
            </button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.create {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-6);
  margin-block: var(--space-4);
  max-inline-size: 480px;
}
.create__actions {
  display: flex;
  gap: var(--space-2);
}
.list {
  list-style: none;
  margin: var(--space-4) 0 0;
  padding: 0;
  display: grid;
  gap: var(--space-3);
}
.prompt {
  padding: var(--space-4) var(--space-6);
  display: grid;
  gap: var(--space-3);
}
.prompt__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.prompt__head h2 {
  margin: 0;
}
.langs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
}
.lang {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.lang label:focus-within {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
.empty {
  color: var(--ink-muted);
}
</style>
