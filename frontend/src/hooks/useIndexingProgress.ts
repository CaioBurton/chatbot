import { useEffect, useRef, useState } from 'react'

export interface ProgressEvent {
  step: string
  detail: string
  progress: number
}

interface UseIndexingProgressResult {
  events: ProgressEvent[]
  done: boolean
  error: boolean
}

export function useIndexingProgress(docId: string | null): UseIndexingProgressResult {
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!docId) return

    const token = localStorage.getItem('propesqi_access_token')
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/documents/${docId}/progress?token=${encodeURIComponent(token)}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onmessage = (e: MessageEvent) => {
      try {
        const event = JSON.parse(e.data as string) as ProgressEvent
        setEvents(prev => [...prev, event])
        if (event.progress === 100) {
          if (event.step === 'error') {
            setError(true)
          } else {
            setDone(true)
          }
          ws.close()
        }
      } catch {
        // ignore malformed frames
      }
    }

    ws.onerror = () => {
      setError(true)
      ws.close()
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [docId])

  return { events, done, error }
}
