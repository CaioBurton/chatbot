import { useState, useCallback, useRef } from 'react'
import { getSessionHistory, SourceCitation, API_BASE } from '../lib/api'
import { generateUUID } from '../lib/uuid'

function splitIntoTypingChunks(text: string): string[] {
  if (text.length <= 4) return [text]

  const targetChunkSize = Math.max(2, Math.min(8, Math.ceil(text.length / 24)))
  const chunks: string[] = []
  let index = 0

  while (index < text.length) {
    let end = Math.min(text.length, index + targetChunkSize)

    while (end < text.length && /[^\s]/.test(text[end - 1]) && /[^\s]/.test(text[end])) {
      end += 1
    }

    chunks.push(text.slice(index, end))
    index = end
  }

  return chunks
}

function wait(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms))
}

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

  const applySseBlock = useCallback(
    async (
      block: string,
      assistantIdsRef: { current: string; placeholder: string },
      signal: AbortSignal,
    ) => {
      let event = 'message'
      const dataLines: string[] = []

      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
      }

      const data = dataLines.join('\n')
      if (!data || data === '[DONE]') return

      const matchesAssistant = (messageId: string) =>
        messageId === assistantIdsRef.placeholder || messageId === assistantIdsRef.current

      const updateAssistant = (
        updater: (message: DisplayMessage) => DisplayMessage,
      ) => {
        setMessages(prev =>
          prev.map(message => {
            if (!matchesAssistant(message.id)) return message
            const nextMessage = updater(message)
            return nextMessage.id === assistantIdsRef.current
              ? nextMessage
              : { ...nextMessage, id: assistantIdsRef.current }
          }),
        )
      }

      if (event === 'token') {
        const chunks = splitIntoTypingChunks(data)
        for (let index = 0; index < chunks.length; index += 1) {
          if (signal.aborted) break

          const chunk = chunks[index]
          updateAssistant(message => ({ ...message, content: message.content + chunk }))

          if (index < chunks.length - 1) {
            await wait(18)
          }
        }
      } else if (event === 'message_id') {
        const realId = data
        assistantIdsRef.current = realId
        updateAssistant(message => ({ ...message, id: realId }))
      } else if (event === 'sources') {
        try {
          const sources: SourceCitation[] = JSON.parse(data)
          updateAssistant(message => ({ ...message, sources }))
        } catch {
          // ignore malformed sources payload
        }
      } else if (event === 'error') {
        updateAssistant(message => ({ ...message, content: data || '(erro interno)' }))
      }
    },
    [],
  )

  const sendMessage = useCallback(
    async (text: string, sid: string) => {
      // Use ref for the guard so this callback never needs to be recreated.
      if (streamingRef.current) return
      streamingRef.current = true

      // React StrictMode can trigger overlapping history loads during mount.
      // Invalidate all of them before appending the optimistic chat state.
      invalidateHistoryRequests()

      const userMsg: DisplayMessage = {
        id: generateUUID(),
        role: 'user',
        content: text,
        sources: null,
        created_at: new Date().toISOString(),
      }
      let assistantId: string = generateUUID()
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
      const assistantIdsRef = {
        current: assistantId,
        placeholder: assistantId,
      }

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
          if (done) {
            buf += decoder.decode()
            break
          }

          // Normalize CRLF → LF so block splitting works regardless of
          // whether the server (sse_starlette) uses \r\n or \n line endings.
          buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

          // Process complete SSE blocks separated by double newlines
          const blocks = buf.split('\n\n')
          buf = blocks.pop() ?? ''

          for (const block of blocks) {
            await applySseBlock(block, assistantIdsRef, abort.signal)
          }
        }

        if (buf.trim()) {
          await applySseBlock(buf, assistantIdsRef, abort.signal)
        }

        assistantId = assistantIdsRef.current
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
