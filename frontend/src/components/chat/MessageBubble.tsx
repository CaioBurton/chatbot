import { useState, useEffect, useRef } from 'react'
import { ThumbsUp, ThumbsDown, Copy, Check } from 'lucide-react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { DisplayMessage } from '../../hooks/useChat'
import { submitFeedback } from '../../lib/api'

interface Props {
  message: DisplayMessage
  onFeedback?: (id: string, value: 'up' | 'down') => void
}

const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 mb-2 last:mb-0 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 last:mb-0 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="leading-snug">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[#2c4a86] dark:text-[#8596b9] underline hover:opacity-80"
    >
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h1 className="text-lg font-bold mt-1 mb-2 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-bold mt-1 mb-2 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-bold mt-1 mb-1 first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="text-sm font-semibold mt-1 mb-1 first:mt-0">{children}</h4>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-[#ccc] dark:border-[#666] pl-3 italic opacity-90 mb-2 last:mb-0">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-[#ccc] dark:border-[#555] my-2" />,
  pre: ({ children }) => (
    <pre className="bg-black/[0.06] dark:bg-white/10 rounded-md p-2 mb-2 last:mb-0 overflow-x-auto text-[0.8rem] font-mono leading-snug">
      {children}
    </pre>
  ),
  code: ({ className, children }) => {
    if (className?.includes('language-')) {
      return <code className={className}>{children}</code>
    }
    return (
      <code className="bg-black/[0.06] dark:bg-white/10 rounded px-1 py-0.5 text-[0.85em] font-mono">
        {children}
      </code>
    )
  },
  table: ({ children }) => (
    <div className="overflow-x-auto mb-2 last:mb-0">
      <table className="border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="border-b border-[#ccc] dark:border-[#555]">{children}</thead>,
  th: ({ children }) => <th className="px-2 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1 border-t border-[#ddd] dark:border-[#4a4a4a]">{children}</td>,
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
    ? 'bg-[#2c4a86] dark:bg-[#8596b9] text-white dark:text-[#101317]'
    : 'bg-[#f2efe8] dark:bg-[#262b32] text-[#1e2128] dark:text-[#eceae7]'

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
    <div className={`flex mb-3.5 animate-fade-in ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[72%] py-[11px] px-4 ${isUser ? 'rounded-[16px_16px_4px_16px] whitespace-pre-wrap' : 'rounded-[4px_16px_16px_16px]'} ${bubbleClasses} break-words leading-[1.55] text-[15px]`}
      >
        {message.content ? (
          isUser ? (
            message.content
          ) : (
            <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {message.content}
            </Markdown>
          )
        ) : (
          <div className="flex gap-1 py-1 px-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-current inline-block animate-pp-bounce" />
            <span className="w-1.5 h-1.5 rounded-full bg-current inline-block animate-pp-bounce [animation-delay:0.15s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-current inline-block animate-pp-bounce [animation-delay:0.3s]" />
          </div>
        )}

        {!isUser && hasContent && (
          <div className="flex gap-[0.3rem] mt-[0.4rem]">
            <button
              type="button"
              onClick={() => handleFeedback('up')}
              disabled={feedbackValue !== null}
              title="Resposta útil"
              className={`border-0 font-[inherit] p-[0.1rem_0.3rem] rounded text-[0.85rem] transition-transform hover:scale-110 active:scale-95 ${feedbackValue === 'up' ? 'bg-[#e8edf7] dark:bg-[#182236] text-[#2c4a86] dark:text-[#8596b9]' : 'bg-transparent text-[#1e2128] dark:text-[#eceae7]'}`}
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
              className={`border-0 font-[inherit] p-[0.1rem_0.3rem] rounded text-[0.85rem] transition-transform hover:scale-110 active:scale-95 ${feedbackValue === 'down' ? 'bg-[#e8edf7] dark:bg-[#182236] text-[#2c4a86] dark:text-[#8596b9]' : 'bg-transparent text-[#1e2128] dark:text-[#eceae7]'}`}
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
              className="border-0 bg-transparent font-[inherit] cursor-pointer p-[0.1rem_0.3rem] rounded text-[11px] text-[#a19e96] dark:text-[#6c717a] flex items-center gap-1 hover:text-[#6c7078] dark:hover:text-[#9da2aa] transition-colors"
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
