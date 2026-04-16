import { useEffect, useRef } from 'react'
import { DisplayMessage } from '../../hooks/useChat'
import { Theme } from '../../hooks/useTheme'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'

interface Props {
  messages: DisplayMessage[]
  streaming: boolean
  onSend: (text: string) => void
  onStop: () => void
  theme: Theme
}

export default function ChatWindow({ messages, streaming, onSend, onStop, theme }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const isDark = theme === 'dark'

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        backgroundColor: isDark ? '#1e1e1e' : '#fff',
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '1rem',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              margin: 'auto',
              textAlign: 'center',
              opacity: 0.45,
              fontSize: '0.95rem',
              color: isDark ? '#e8e8e8' : '#111',
            }}
          >
            <p>Envie uma mensagem para começar.</p>
          </div>
        )}
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} theme={theme} />
        ))}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={onSend} disabled={streaming} onStop={onStop} theme={theme} />
    </div>
  )
}
