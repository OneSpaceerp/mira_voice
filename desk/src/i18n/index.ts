/**
 * Arabic, English and French are equals (design-system §2). The UI language follows the
 * user's choice (remembered in this browser), else the user's profile, else the browser.
 * Switching sets <html lang dir>, so base.css switches to the Arabic type styles and every
 * logical CSS property mirrors.
 */
import { createI18n } from 'vue-i18n'

import type { Language } from '@/api/types'
import ar from './ar'
import en from './en'
import fr from './fr'

type Schema = typeof en

const STORE_KEY = 'mira.language'

function initial(): Language {
  try {
    const saved = localStorage.getItem(STORE_KEY)
    if (saved === 'ar' || saved === 'en' || saved === 'fr') return saved
  } catch {
    /* storage blocked */
  }
  const browser = (navigator.language || 'en').slice(0, 2)
  return browser === 'ar' || browser === 'fr' ? browser : 'en'
}

export const i18n = createI18n<[Schema], Language, false>({
  legacy: false,
  locale: initial(),
  fallbackLocale: 'en',
  messages: { en, ar, fr },
})

export function applyDocumentLanguage(lang: Language): void {
  document.documentElement.lang = lang
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
}

export function setLanguage(lang: Language, remember = true): void {
  i18n.global.locale.value = lang
  applyDocumentLanguage(lang)
  if (remember) {
    try {
      localStorage.setItem(STORE_KEY, lang)
    } catch {
      /* storage blocked */
    }
  }
}

export function hasChosenLanguage(): boolean {
  try {
    return localStorage.getItem(STORE_KEY) !== null
  } catch {
    return false
  }
}
