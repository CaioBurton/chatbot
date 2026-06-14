import { useState, useEffect, useCallback } from 'react'
import { createSession, getSessionSummaries, deleteSession as apiDeleteSession, SessionSummary } from '../lib/api'

const STORAGE_KEY = 'propesqi_session_ids'
const MAX_STORED_SESSIONS = 50

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function loadStoredIds(): string[] {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(raw)) return []
    return raw
      .filter((id): id is string => typeof id === 'string' && UUID_RE.test(id))
      .slice(0, MAX_STORED_SESSIONS)
  } catch {
    return []
  }
}

function saveStoredIds(ids: string[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
}

export function useSessions() {
  const [sessionIds, setSessionIds] = useState<string[]>(loadStoredIds)
  const [summaries, setSummaries] = useState<SessionSummary[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const refreshSummaries = useCallback(() => {
    if (sessionIds.length === 0) {
      setSummaries([])
      return
    }
    getSessionSummaries(sessionIds).then(setSummaries).catch(console.error)
  }, [sessionIds])

  // Refresh summaries whenever the list of known session IDs changes
  useEffect(() => {
    refreshSummaries()
  }, [refreshSummaries])

  const addSession = useCallback((id: string) => {
    if (!UUID_RE.test(id)) return
    setSessionIds(prev => {
      if (prev.includes(id)) return prev
      const next = [id, ...prev].slice(0, MAX_STORED_SESSIONS)
      saveStoredIds(next)
      return next
    })
  }, [])

  const startNewSession = useCallback(async (): Promise<string> => {
    setLoading(true)
    try {
      const { session_id } = await createSession()
      addSession(session_id)
      setCurrentSessionId(session_id)
      return session_id
    } finally {
      setLoading(false)
    }
  }, [addSession])

  const switchSession = useCallback((id: string) => {
    setCurrentSessionId(id)
  }, [])

  const removeSession = useCallback(async (id: string) => {
    await apiDeleteSession(id)
    setSessionIds(prev => {
      const next = prev.filter(s => s !== id)
      saveStoredIds(next)
      return next
    })
    setSummaries(prev => prev.filter(s => s.session_id !== id))
    setCurrentSessionId(prev => (prev === id ? null : prev))
  }, [])

  return {
    sessionIds,
    summaries,
    currentSessionId,
    loading,
    addSession,
    startNewSession,
    switchSession,
    removeSession,
    setCurrentSessionId,
    refreshSummaries,
  }
}
