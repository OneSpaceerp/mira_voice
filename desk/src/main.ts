// Self-hosted fonts (design-system §5): Mira Server installs may have no internet.
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans-arabic/400.css'
import '@fontsource/ibm-plex-sans-arabic/500.css'
import '@fontsource/ibm-plex-sans-arabic/600.css'
import '@fontsource/ibm-plex-mono/500.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/app.css'

import { createApp } from 'vue'

import { whenUnauthorized } from '@/api/http'
import { applyDocumentLanguage, i18n } from '@/i18n'
import { router } from '@/router'
import { applyTheme, loadSession, session, signOut } from '@/session'

import App from './App.vue'

applyTheme(session.theme)
applyDocumentLanguage(i18n.global.locale.value)
whenUnauthorized(() => {
  signOut()
  void router.push({ name: 'login' })
})

await loadSession()
createApp(App).use(i18n).use(router).mount('#app')
