import { useEffect, useRef } from 'react'
import { DisplayMessage } from '../../hooks/useChat'
import { useIsMobile } from '../../hooks/useIsMobile'
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
  const isMobile = useIsMobile()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-[#fdfcfa] dark:bg-[#16181c] transition-colors">
      <div
        className={`flex-1 overflow-y-auto flex flex-col ${isMobile ? 'pt-[66px] px-3.5 pb-2' : 'pt-[26px] px-6 pb-2'}`}
      >
        {messages.length === 0 && <WelcomeScreen onSend={onSend} />}
        {messages.length > 0 && (
          <div className="max-w-[720px] w-full mx-auto flex flex-col">
            {messages.map(m => (
              <MessageBubble key={m.id} message={m} />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={onSend} disabled={streaming} onStop={onStop} />
    </div>
  )
}
