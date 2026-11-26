/**
 * Calls to Mira Core's REST API (/api/v1, same origin: the dev server and the HTTPS proxy
 * forward it). The access token lives in sessionStorage, not localStorage: agents share
 * workstations, and closing the tab must end the session (design-system §4, shared PCs).
 */

const TOKEN_KEY = 'mira.token'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
  }

  /** Human-readable lines from FastAPI's `detail` (string, list of strings or {errors}). */
  get lines(): string[] {
    const d = this.detail
    if (typeof d === 'string') return [d]
    if (Array.isArray(d)) return d.map((x) => (typeof x === 'string' ? x : JSON.stringify(x)))
    if (d && typeof d === 'object' && 'errors' in d && Array.isArray(d.errors)) {
      return d.errors.map(String)
    }
    return [this.message]
  }
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) sessionStorage.setItem(TOKEN_KEY, token)
  else sessionStorage.removeItem(TOKEN_KEY)
}

let onUnauthorized: () => void = () => {}
export function whenUnauthorized(handler: () => void): void {
  onUnauthorized = handler
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let payload: BodyInit | undefined
  if (body instanceof Blob || body instanceof URLSearchParams) {
    payload = body
  } else if (body !== undefined) {
    headers.set('Content-Type', 'application/json')
    payload = JSON.stringify(body)
  }
  const r = await fetch(`/api/v1${path}`, { ...init, method, headers, body: payload })
  if (r.status === 401) {
    setToken(null)
    onUnauthorized()
  }
  if (!r.ok) {
    let detail: unknown = r.statusText
    try {
      detail = ((await r.json()) as { detail?: unknown }).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, detail)
  }
  if (r.status === 204) return undefined as T
  const type = r.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? await r.json() : await r.blob()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: (path: string) => request<void>('DELETE', path),
}
