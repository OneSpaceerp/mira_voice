/** Shapes of Mira Core's API (core/src/mira_core/api, schemas.py). */

export type Role = 'platform_admin' | 'tenant_admin' | 'supervisor' | 'agent'
export type Language = 'ar' | 'en' | 'fr'
export const LANGUAGES: Language[] = ['ar', 'en', 'fr']

export interface User {
  id: string
  tenant_id: string | null
  email: string
  full_name: string
  role: Role
  locale: Language
}

export interface Tenant {
  id: string
  name: string
  slug: string
  default_locale: Language
  timezone: string
}

export interface Token {
  access_token: string
  token_type: string
  expires_in: number
}

export interface PromptAudio {
  language: Language
  sample_rate: number
  duration_ms: number
  size_bytes: number
  sha256: string
}

export interface Prompt {
  id: string
  tenant_id: string
  name: string
  description: string
  audio: PromptAudio[]
}

export interface FlowReport {
  errors: string[]
  warnings: string[]
}

export interface Flow {
  id: string
  tenant_id: string
  name: string
  description: string
  draft: Partial<FlowDefinition>
  published_version: number | null
  number: string | null
  updated_at: string
  report: FlowReport | null
  config_applied?: boolean | null
}

export interface FlowVersion {
  version: number
  published_at: string
  published_by: string | null
  current: boolean
}

export interface Extension {
  id: string
  number: string
  display_name: string
}

// ---- Mira Flow v1 (core/src/mira_core/flows/schema.py) ----

export type NodeType =
  | 'play'
  | 'menu'
  | 'collect'
  | 'time'
  | 'language'
  | 'set'
  | 'branch'
  | 'http'
  | 'transfer'
  | 'queue'
  | 'voicemail'
  | 'hangup'

export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'
export type ConditionOp = 'eq' | 'ne' | 'gt' | 'lt' | 'contains' | 'empty' | 'not_empty'

export interface TimeRange {
  days: Weekday[]
  from: string
  to: string
}

export interface Condition {
  op: ConditionOp
  value: string
  next: string
}

/** A node as stored in the flow JSON. Fields depend on `type` (see nodeTypes.ts). */
export interface FlowNode {
  type: NodeType
  label?: string
  x?: number
  y?: number
  [field: string]: unknown
}

export interface FlowDefinition {
  schema: 'mira-flow/1'
  start: string
  nodes: Record<string, FlowNode>
}
