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
  const streamingRef = useRef(false)
  const historyAbortRef = useRef<AbortController | null>(null)
  const historyRequestIdRef = useRef(0)

  const invalidateHistoryRequests = useCallback(() => {
    historyRequestIdRef.current += 1
    historyAbortRef.current?.abort()
    historyAbortRef.current = null
  }, [])

  const loadHistory = useCallback(async (sid: string) => {
    const requestId = historyRequestIdRef.current + 1
    historyRequestIdRef.current = requestId

    historyAbortRef.current?.abort()
    const abort = new AbortController()
    historyAbortRef.current = abort

    try {
      const history = await getSessionHistory(sid, abort.signal)
      if (historyRequestIdRef.current === requestId && !abort.signal.aborted) {
        setMessages(history)
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        throw err
      }
    } finally {
      if (historyAbortRef.current === abort) {
        historyAbortRef.current = null
      }
    }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
  }, [])

  const abortStream = useCallback(() => {
    abortRef.current?.abort()
    streamingRef.current = false
    setStreaming(false)
  }, [])

  const sendMessage = useCallback(
    async (text: string, sid: string) => {
      // Use ref for the guard so this callback never needs to be recreated.
      if (streamingRef.current) return
      streamingRef.current = true

      // React StrictMode can trigger overlapping history loads during mount.
      // Invalidate all of them before appending the optimistic chat state.
      invalidateHistoryRequests()

      const userMsg: DisplayMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
        sources: null,
        created_at: new Date().toISOString(),
      }
      let assistantId: string = crypto.randomUUID()
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
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          },
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

          // Normalize CRLF → LF so block splitting works regardless of
          // whether the server (sse_starlette) uses \r\n or \n line endings.
          buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

          // Process complete SSE blocks separated by double newlines
          const blocks = buf.split('\n\n')
          buf = blocks.pop() ?? ''

          for (const block of blocks) {
            let event = 'message'
            // Collect all data: lines and join with \n per the SSE spec so
            // that tokens containing newline characters are not truncated.
            const dataLines: string[] = []
            for (const line of block.split('\n')) {
              if (line.startsWith('event: ')) event = line.slice(7).trim()
              else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
            }
            const data = dataLines.join('\n')
            if (!data || data === '[DONE]') continue

            if (event === 'token') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, content: m.content + data } : m,
                ),
              )
            } else if (event === 'message_id') {
              // Replace the temporary frontend UUID with the real DB UUID so
              // feedback requests reference an existing row.
              const realId = data
              setMessages(prev =>
                prev.map(m => (m.id === assistantId ? { ...m, id: realId } : m)),
              )
              assistantId = realId
            } else if (event === 'sources') {
              try {
                const sources: SourceCitation[] = JSON.parse(data)
                setMessages(prev =>
                  prev.map(m => (m.id === assistantId ? { ...m, sources } : m)),
                )
              } catch {
                // ignore malformed sources payload
              }
            } else if (event === 'error') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, content: data || '(erro interno)' } : m,
                ),
              )
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
        streamingRef.current = false
        setStreaming(false)
        abortRef.current = null
      }
    },
    // Stable callback — the streaming guard uses streamingRef, not the state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [invalidateHistoryRequests],
  )

  return { messages, streaming, sendMessage, loadHistory, clearMessages, abortStream }
}
