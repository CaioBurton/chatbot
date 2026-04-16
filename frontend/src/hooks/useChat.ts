import { useState, useCallback, useRef } from 'react'
import { getSessionHistory, SourceCitation, API_BASE } from '../lib/api'

export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: SourceCitation[] | null
  created_at: string
}

export function useChat() {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const loadHistory = useCallback(async (sid: string) => {
    const history = await getSessionHistory(sid)
    setMessages(history)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  const sendMessage = useCallback(
    async (text: string, sid: string) => {
      if (streaming) return

      const userMsg: DisplayMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        sources: null,
        created_at: new Date().toISOString(),
      }
      const assistantId = crypto.randomUUID()
      const assistantPlaceholder: DisplayMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        sources: null,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, userMsg, assistantPlaceholder])
      setStreaming(true)

      const abort = new AbortController()
      abortRef.current = abort

      try {
        const res = await fetch(`${API_BASE}/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid, message: text }),
          signal: abort.signal,
        })

        if (!res.ok || !res.body) {
          throw new Error(`Stream failed: ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buf += decoder.decode(value, { stream: true })

          // Process complete SSE blocks separated by double newlines
          const blocks = buf.split('\n\n')
          buf = blocks.pop() ?? ''

          for (const block of blocks) {
            let event = 'message'
            let data = ''
            for (const line of block.split('\n')) {
              if (line.startsWith('event: ')) event = line.slice(7).trim()
              else if (line.startsWith('data: ')) data = line.slice(6)
            }
            if (!data || data === '[DONE]') continue

            if (event === 'token') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, content: m.content + data } : m,
                ),
              )
            } else if (event === 'sources') {
              try {
                const sources: SourceCitation[] = JSON.parse(data)
                setMessages(prev =>
                  prev.map(m => (m.id === assistantId ? { ...m, sources } : m)),
                )
              } catch {
                // ignore malformed sources payload
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          console.error('Stream error:', err)
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? {
                    ...m,
                    content:
                      m.content
                        ? m.content + '\n\n*(erro na transmissão — resposta incompleta)*'
                        : '(erro na resposta)',
                  }
                : m,
            ),
          )
        }
      } finally {
        setStreaming(false)
        abortRef.current = null
      }
    },
    [streaming],
  )

  return { messages, streaming, sendMessage, loadHistory, clearMessages }
}
