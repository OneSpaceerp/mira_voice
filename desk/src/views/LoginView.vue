<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { signIn } from '@/session'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await signIn(email.value.trim(), password.value)
    const next = typeof route.query.next === 'string' ? route.query.next : '/flows'
    await router.replace(next.startsWith('/') ? next : '/flows')
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status < 500 ? t('login.failed') : t('login.unreachable')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login">
    <form class="login__card mv-panel" @submit.prevent="submit">
      <div class="login__brand" aria-hidden="true">m</div>
      <h1 class="mv-title">{{ t('login.title') }}</h1>
      <div v-if="error" class="mv-banner mv-banner--danger" role="alert">{{ error }}</div>
      <div class="mv-field">
        <label for="email">{{ t('login.email') }}</label>
        <input
          id="email"
          v-model="email"
          class="mv-input mv-ltr"
          type="email"
          autocomplete="username"
          required
        />
      </div>
      <div class="mv-field">
        <label for="password">{{ t('login.password') }}</label>
        <input
          id="password"
          v-model="password"
          class="mv-input"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>
      <!-- secondary: the brand block is this screen's one red thing (design-system §4) -->
      <button class="mv-btn mv-btn--secondary" type="submit" :disabled="busy">
        {{ t('login.submit') }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-block-size: 100dvh;
  padding: var(--space-6);
  background: var(--surface);
}
.login__card {
  display: grid;
  gap: var(--space-4);
  inline-size: min(100%, 400px);
  padding: var(--space-8);
}
.login__card h1 {
  margin: 0;
}
/* the brand block: the one place in Desk the extruded shadow appears (design-system §6) */
.login__brand {
  display: grid;
  place-items: center;
  inline-size: var(--space-16);
  block-size: var(--space-16);
  border-radius: var(--radius-lg);
  background: var(--mira-red);
  color: var(--on-red);
  box-shadow: var(--shadow-extrude);
  font: var(--type-display-l-weight) var(--type-display-l-size) / 1 var(--font-display);
}
</style>
