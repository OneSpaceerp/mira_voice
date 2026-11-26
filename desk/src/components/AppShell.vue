<script setup lang="ts">
/** Navigation rail (start side: right in Arabic), language, theme and tenant switches. */
import { GitBranch, LogOut, Mic } from 'lucide-vue-next'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { LANGUAGES, type Language } from '@/api/types'
import { setLanguage } from '@/i18n'
import { applyTheme, session, signOut, type Theme } from '@/session'

const { t, locale } = useI18n()
const router = useRouter()
const themes: Theme[] = ['system', 'light', 'dark']
const isPlatform = computed(() => session.user?.role === 'platform_admin')
const themeKey = (th: Theme) =>
  th === 'light' ? 'nav.themeLight' : th === 'dark' ? 'nav.themeDark' : 'nav.themeSystem'

function out() {
  signOut()
  void router.push({ name: 'login' })
}
</script>

<template>
  <div class="shell">
    <a class="mv-skip" href="#main">{{ t('app.skip') }}</a>
    <nav class="rail" :aria-label="t('app.name')">
      <div class="brand" aria-hidden="true">m</div>
      <RouterLink class="rail__link" :to="{ name: 'flows' }">
        <GitBranch :size="20" aria-hidden="true" />
        <span>{{ t('nav.flows') }}</span>
      </RouterLink>
      <RouterLink class="rail__link" :to="{ name: 'prompts' }">
        <Mic :size="20" aria-hidden="true" />
        <span>{{ t('nav.prompts') }}</span>
      </RouterLink>

      <div class="rail__end">
        <label v-if="isPlatform" class="mv-field">
          <span class="mv-field__label">{{ t('nav.tenant') }}</span>
          <select v-model="session.tenantId" class="mv-select">
            <option v-for="tn in session.tenants" :key="tn.id" :value="tn.id">{{ tn.name }}</option>
          </select>
        </label>
        <label class="mv-field">
          <span class="mv-field__label">{{ t('nav.language') }}</span>
          <select
            class="mv-select"
            :value="locale"
            @change="setLanguage(($event.target as HTMLSelectElement).value as Language)"
          >
            <option v-for="l in LANGUAGES" :key="l" :value="l" :lang="l">
              {{ t(`languages.${l}`, {}, { locale: l }) }}
            </option>
          </select>
        </label>
        <label class="mv-field">
          <span class="mv-field__label">{{ t('nav.theme') }}</span>
          <select
            class="mv-select"
            :value="session.theme"
            @change="applyTheme(($event.target as HTMLSelectElement).value as Theme)"
          >
            <option v-for="th in themes" :key="th" :value="th">{{ t(themeKey(th)) }}</option>
          </select>
        </label>
        <button type="button" class="mv-btn mv-btn--quiet" @click="out">
          <LogOut :size="18" aria-hidden="true" class="mirror" />
          {{ t('nav.signOut') }}
        </button>
      </div>
    </nav>
    <main id="main" class="main" tabindex="-1">
      <RouterView :key="session.tenantId ?? ''" />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 232px 1fr;
  min-block-size: 100dvh;
}
.rail {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4);
  background: var(--sidebar);
  border-inline-end: 1px solid var(--line);
}
.brand {
  display: grid;
  place-items: center;
  inline-size: var(--control-lg);
  block-size: var(--control-lg);
  margin-block-end: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--bone);
  color: var(--ink);
  font: var(--type-heading-weight) var(--type-heading-size) / 1 var(--font-display);
}
.rail__link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-block-size: var(--control-md);
  padding-inline: var(--space-3);
  border-radius: var(--radius-md);
  color: var(--ink);
  text-decoration: none;
  font: var(--type-label-weight) var(--type-label-size) / var(--type-label-line)
    var(--type-label-family);
}
.rail__link:hover {
  background: var(--surface-sunken);
}
.rail__link.router-link-active {
  background: var(--state-hold-soft);
}
.rail__end {
  margin-block-start: auto;
  display: grid;
  gap: var(--space-3);
}
.main {
  min-inline-size: 0;
  outline: none;
}
:dir(rtl) .mirror {
  transform: scaleX(-1);
}
</style>
