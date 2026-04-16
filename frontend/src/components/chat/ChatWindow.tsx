import { useEffect, useRef } from 'react'
import { DisplayMessage } from '../../hooks/useChat'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'

interface Props {
  messages: DisplayMessage[]
  streaming: boolean
  onSend: (text: string) => void
}

export default function ChatWindow({ messages, streaming, onSend }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

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
        backgroundColor: '#fff',
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
            }}
          >
            <p>Envie uma mensagem para começar.</p>
          </div>
        )}
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={onSend} disabled={streaming} />
    </div>
  )
}
