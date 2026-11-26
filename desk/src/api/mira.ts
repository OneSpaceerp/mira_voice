/** Typed calls for the screens of this app (flows, prompts, extensions). */
import { api, request } from '@/api/http'
import type { Extension, Flow, FlowDefinition, FlowVersion, Language, Prompt } from '@/api/types'
import { session, tenantQuery } from '@/session'

function withTenant<T extends object>(body: T): T & { tenant_id?: string } {
  return session.user?.role === 'platform_admin' && session.tenantId
    ? { ...body, tenant_id: session.tenantId }
    : body
}

export const flows = {
  list: () => api.get<Flow[]>(`/flows${tenantQuery()}`),
  get: (id: string) => api.get<Flow>(`/flows/${id}`),
  create: (name: string, number: string | null) =>
    api.post<Flow>('/flows', withTenant({ name, number: number || null })),
  saveDraft: (id: string, draft: FlowDefinition) => api.put<Flow>(`/flows/${id}`, { draft }),
  rename: (id: string, name: string, number: string | null) =>
    api.put<Flow>(`/flows/${id}`, { name, number: number || null }),
  publish: (id: string) => api.post<Flow>(`/flows/${id}/publish`),
  versions: (id: string) => api.get<FlowVersion[]>(`/flows/${id}/versions`),
  rollback: (id: string, version: number) => api.post<Flow>(`/flows/${id}/rollback`, { version }),
  editVersion: (id: string, version: number) =>
    api.post<Flow>(`/flows/${id}/versions/${version}/edit`),
  remove: (id: string) => api.delete(`/flows/${id}`),
}

export const prompts = {
  list: () => api.get<Prompt[]>(`/prompts${tenantQuery()}`),
  create: (name: string) => api.post<Prompt>('/prompts', withTenant({ name })),
  upload: (id: string, language: Language, file: Blob) =>
    request<Prompt>('PUT', `/prompts/${id}/audio/${language}`, file, {
      headers: { 'Content-Type': 'audio/wav' },
    }),
  audio: (id: string, language: Language) =>
    request<Blob>('GET', `/prompts/${id}/audio/${language}`),
  removeAudio: (id: string, language: Language) => api.delete(`/prompts/${id}/audio/${language}`),
  remove: (id: string) => api.delete(`/prompts/${id}`),
}

export const extensions = {
  list: () => api.get<Extension[]>(`/extensions${tenantQuery()}`),
}
