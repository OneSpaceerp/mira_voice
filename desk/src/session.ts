/** Who is signed in, which tenant they work on, and the theme. One reactive object. */
import { reactive } from 'vue'

import { api, ApiError, getToken, setToken } from '@/api/http'
import type { Tenant, Token, User } from '@/api/types'
import { hasChosenLanguage, setLanguage } from '@/i18n'

export type Theme = 'light' | 'dark' | 'system'

interface Session {
  user: User | null
  tenants: Tenant[]
  /** The tenant being worked on: the user's own, or the platform admin's choice. */
  tenantId: string | null
  theme: Theme
  ready: boolean
}

const THEME_KEY = 'mira.theme'

function storedTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY)
    return t === 'light' || t === 'dark' ? t : 'system'
  } catch {
    return 'system'
  }
}

export const session = reactive<Session>({
  user: null,
  tenants: [],
  tenantId: null,
  theme: storedTheme(),
  ready: false,
})

export function applyTheme(theme: Theme): void {
  session.theme = theme
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  try {
    if (theme === 'system') localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, theme)
  } catch {
    /* storage blocked */
  }
}

/** ?tenant_id=… for API calls that need it (platform admins); '' for tenant users. */
export function tenantQuery(prefix = '?'): string {
  return session.user?.role === 'platform_admin' && session.tenantId
    ? `${prefix}tenant_id=${encodeURIComponent(session.tenantId)}`
    : ''
}

export async function loadSession(): Promise<void> {
  if (!getToken()) {
    session.ready = true
    return
  }
  try {
    session.user = await api.get<User>('/auth/me')
    if (session.user.role === 'platform_admin') {
      session.tenants = await api.get<Tenant[]>('/tenants')
      session.tenantId = session.tenants[0]?.id ?? null
    } else {
      session.tenantId = session.user.tenant_id
    }
    if (!hasChosenLanguage()) setLanguage(session.user.locale, false)
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    setToken(null)
    session.user = null
  } finally {
    session.ready = true
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  const form = new URLSearchParams({ username: email, password })
  const token = await api.post<Token>('/auth/token', form)
  setToken(token.access_token)
  await loadSession()
}

export function signOut(): void {
  setToken(null)
  session.user = null
  session.tenants = []
  session.tenantId = null
}
