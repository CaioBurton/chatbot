import { useEffect, useRef } from 'react'
import { DisplayMessage } from '../../hooks/useChat'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'
import WelcomeScreen from './WelcomeScreen'

interface Props {
  messages: DisplayMessage[]
  streaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export default function ChatWindow({ messages, streaming, onSend, onStop }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#fafafa] dark:bg-[#1e1e1e]">
      <div className="flex-1 overflow-y-auto p-4 flex flex-col">
        {messages.length === 0 && <WelcomeScreen onSend={onSend} />}
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={onSend} disabled={streaming} onStop={onStop} />
    </div>
  )
}
