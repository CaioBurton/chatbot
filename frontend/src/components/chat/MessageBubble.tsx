import { useState, useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { DisplayMessage } from '../../hooks/useChat'
import { Theme } from '../../hooks/useTheme'
import { submitFeedback } from '../../lib/api'

interface Props {
  message: DisplayMessage
  theme: Theme
  onFeedback?: (id: string, value: 'up' | 'down') => void
}

export default function MessageBubble({ message, theme, onFeedback }: Props) {
  const [copied, setCopied] = useState(false)
  const [feedbackValue, setFeedbackValue] = useState<'up' | 'down' | null>(null)
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current)
    }
  }, [])

  const isUser = message.role === 'user'
  const isDark = theme === 'dark'
  const hasContent = message.content.length > 0

  const bubbleBg = isUser
    ? isDark ? '#1a6db5' : '#0078d4'
    : isDark ? '#3a3a3a' : '#f0f0f0'
  const bubbleColor = isUser ? '#fff' : isDark ? '#e8e8e8' : '#111'

  const handleCopy = () => {
    if (!navigator.clipboard) return
    navigator.clipboard.writeText(message.content).then(() => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current)
      setCopied(true)
      copyTimerRef.current = setTimeout(() => setCopied(false), 1500)
    }).catch(console.error)
  }

  const handleFeedback = (value: 'up' | 'down') => {
    if (feedbackValue !== null) return
    setFeedbackValue(value)
    submitFeedback(message.id, value).catch(console.error)
    onFeedback?.(message.id, value)
  }

  const ghostBtnBase: CSSProperties = {
    border: 'none',
    background: 'transparent',
    fontFamily: 'inherit',
    cursor: 'pointer',
    color: bubbleColor,
    padding: '0.1rem 0.3rem',
    borderRadius: '0.25rem',
  }

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '0.75rem',
      }}
    >
      <div
        style={{
          maxWidth: '70%',
          padding: '0.75rem 1rem',
          borderRadius: isUser ? '1rem 1rem 0 1rem' : '1rem 1rem 1rem 0',
          backgroundColor: bubbleBg,
          color: bubbleColor,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          lineHeight: 1.5,
        }}
      >
        {message.content || (
          <span style={{ opacity: 0.4, fontStyle: 'italic' }}>▌</span>
        )}

        {!isUser && hasContent && (
          <div style={{ display: 'flex', gap: '0.3rem', marginTop: '0.4rem' }}>
            <button
              onClick={() => handleFeedback('up')}
              disabled={feedbackValue !== null}
              title="Resposta útil"
              style={{
                ...ghostBtnBase,
                fontSize: '0.85rem',
                opacity: feedbackValue !== null && feedbackValue !== 'up' ? 0.35 : 1,
                backgroundColor:
                  feedbackValue === 'up'
                    ? isDark ? '#2d6a2d' : '#d4edda'
                    : 'transparent',
                cursor: feedbackValue !== null ? 'default' : 'pointer',
              }}
            >
              👍
            </button>
            <button
              onClick={() => handleFeedback('down')}
              disabled={feedbackValue !== null}
              title="Resposta não útil"
              style={{
                ...ghostBtnBase,
                fontSize: '0.85rem',
                opacity: feedbackValue !== null && feedbackValue !== 'down' ? 0.35 : 1,
                backgroundColor:
                  feedbackValue === 'down'
                    ? isDark ? '#6a2d2d' : '#f8d7da'
                    : 'transparent',
                cursor: feedbackValue !== null ? 'default' : 'pointer',
              }}
            >
              👎
            </button>
          </div>
        )}

        {message.sources && message.sources.length > 0 && (
          <div
            style={{
              marginTop: '0.6rem',
              borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.12)'}`,
              paddingTop: '0.5rem',
              fontSize: '0.78rem',
              color: isUser ? 'rgba(255,255,255,0.85)' : isDark ? '#c0c0c0' : '#444',
            }}
          >
            <strong>Fontes:</strong>
            <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem' }}>
              {message.sources.map((s, i) => (
                <li key={i}>
                  {s.original_name}
                  {s.page_number != null ? ` (p. ${s.page_number})` : ''}
                  {' \u2014 '}
                  {(s.score * 100).toFixed(0)}%
                </li>
              ))}
            </ul>
          </div>
        )}

        {!isUser && hasContent && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.3rem' }}>
            <button
              onClick={handleCopy}
              style={{
                ...ghostBtnBase,
                fontSize: '0.72rem',
                opacity: 0.6,
                color: isDark ? '#c0c0c0' : '#555',
              }}
            >
              {copied ? 'Copiado!' : 'Copiar'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
