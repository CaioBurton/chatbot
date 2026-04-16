export const API_BASE = '/api'

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
