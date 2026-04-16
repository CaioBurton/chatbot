export const API_BASE = '/api'

// ------------------------------------------------------------------ //
// Shared types                                                        //
// ------------------------------------------------------------------ //

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface DocumentListItem {
  id: string
  original_name: string
  status: string
  file_type: string
  total_chunks: number | null
  created_at: string
}

export interface DocumentStats {
  total: number
  active: number
  processing: number
  error: number
  total_chunks: number
}

export interface SessionResponse {
  session_id: string
}

export interface SourceCitation {
  doc_id: string
  original_name: string
  page_number: number | null
  score: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: SourceCitation[] | null
  created_at: string
}

export interface SessionSummary {
  session_id: string
  created_at: string
  last_activity: string
  preview: string | null
}

export async function createSession(): Promise<SessionResponse> {
  const res = await fetch(`${API_BASE}/chat/sessions`, { method: 'POST' })
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`)
  return res.json() as Promise<SessionResponse>
}

export async function getSessionHistory(sessionId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/history`)
  if (!res.ok) throw new Error(`Failed to fetch history: ${res.status}`)
  return res.json() as Promise<ChatMessage[]>
}

export async function getSessionSummaries(sessionIds: string[]): Promise<SessionSummary[]> {
  if (sessionIds.length === 0) return []
  const params = sessionIds.map(id => `session_ids=${encodeURIComponent(id)}`).join('&')
  const res = await fetch(`${API_BASE}/chat/sessions?${params}`)
  if (!res.ok) throw new Error(`Failed to fetch session summaries: ${res.status}`)
  return res.json() as Promise<SessionSummary[]>
}

export async function submitFeedback(messageId: string, feedback: 'up' | 'down'): Promise<void> {
  const res = await fetch(
    `${API_BASE}/chat/messages/${encodeURIComponent(messageId)}/feedback`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback }),
    },
  )
  if (!res.ok) throw new Error(`Failed to submit feedback: ${res.status}`)
}

// ------------------------------------------------------------------ //
// Auth helpers                                                        //
// ------------------------------------------------------------------ //

const ACCESS_TOKEN_KEY = 'propesqi_access_token'

/** Wraps fetch, injecting the stored Bearer token when present.
 *  Dispatches a 'propesqi:auth-error' CustomEvent on the window when the
 *  server responds with 401 so the App can auto-logout without threading
 *  callbacks through every component.
 */
export function authFetch(url: string, init?: RequestInit): Promise<Response> {
  let token: string | null = null
  try {
    token = localStorage.getItem(ACCESS_TOKEN_KEY)
  } catch {
    // Storage unavailable
  }
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(url, { ...init, headers }).then(res => {
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent('propesqi:auth-error'))
    }
    return res
  })
}

/** POST /api/auth/login — returns tokens on success, throws on error. */
export async function loginApi(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw Object.assign(new Error('Login failed'), { status: res.status, body: text })
  }
  return res.json() as Promise<TokenResponse>
}
