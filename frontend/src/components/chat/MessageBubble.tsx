import { useState, useEffect, useRef } from 'react'
import { ThumbsUp, ThumbsDown, Copy, Check } from 'lucide-react'
import { DisplayMessage } from '../../hooks/useChat'
import { submitFeedback } from '../../lib/api'

interface Props {
  message: DisplayMessage
  onFeedback?: (id: string, value: 'up' | 'down') => void
}

export default function MessageBubble({ message, onFeedback }: Props) {
  const [copied, setCopied] = useState(false)
  const [feedbackValue, setFeedbackValue] = useState<'up' | 'down' | null>(null)
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current)
    }
  }, [])

  const isUser = message.role === 'user'
  const hasContent = message.content.length > 0

  const bubbleClasses = isUser
    ? 'bg-[#0078d4] dark:bg-[#1a6db5] text-white'
    : 'bg-[#f0f0f0] dark:bg-[#3a3a3a] text-[#111] dark:text-[#e8e8e8]'

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

  return (
    <div className={`flex mb-3 animate-fade-in ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[70%] py-3 px-4 ${isUser ? 'rounded-[1rem_1rem_0_1rem]' : 'rounded-[1rem_1rem_1rem_0]'} ${bubbleClasses} whitespace-pre-wrap break-words leading-[1.5]`}
      >
        {message.content || (
          <span className="inline-block w-0.5 h-4 bg-current animate-blink" />
        )}

        {!isUser && hasContent && (
          <div className="flex gap-[0.3rem] mt-[0.4rem]">
            <button
              type="button"
              onClick={() => handleFeedback('up')}
              disabled={feedbackValue !== null}
              title="Resposta útil"
              className={`border-0 font-[inherit] p-[0.1rem_0.3rem] rounded text-[0.85rem] text-[#111] dark:text-[#e8e8e8] transition-transform hover:scale-110 active:scale-95 ${feedbackValue === 'up' ? 'bg-[#d4edda] dark:bg-[#2d6a2d]' : 'bg-transparent'}`}
              style={{
                opacity: feedbackValue !== null && feedbackValue !== 'up' ? 0.35 : 1,
                cursor: feedbackValue !== null ? 'default' : 'pointer',
              }}
            >
              <ThumbsUp size={14} />
            </button>
            <button
              type="button"
              onClick={() => handleFeedback('down')}
              disabled={feedbackValue !== null}
              title="Resposta não útil"
              className={`border-0 font-[inherit] p-[0.1rem_0.3rem] rounded text-[0.85rem] text-[#111] dark:text-[#e8e8e8] transition-transform hover:scale-110 active:scale-95 ${feedbackValue === 'down' ? 'bg-[#f8d7da] dark:bg-[#6a2d2d]' : 'bg-transparent'}`}
              style={{
                opacity: feedbackValue !== null && feedbackValue !== 'down' ? 0.35 : 1,
                cursor: feedbackValue !== null ? 'default' : 'pointer',
              }}
            >
              <ThumbsDown size={14} />
            </button>
          </div>
        )}

        {!isUser && hasContent && (
          <div className="flex justify-end mt-[0.3rem]">
            <button
              type="button"
              onClick={handleCopy}
              className="border-0 bg-transparent font-[inherit] cursor-pointer p-[0.1rem_0.3rem] rounded text-[0.72rem] opacity-60 text-[#555] dark:text-[#c0c0c0] flex items-center gap-1 hover:opacity-100 transition-opacity"
            >
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? 'Copiado!' : 'Copiar'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
