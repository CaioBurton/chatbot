import { useState, KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
  onStop?: () => void
}

export default function ChatInput({ onSend, disabled, onStop }: Props) {
  const [value, setValue] = useState('')

  const handleSend = () => {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex gap-2 px-4 py-3 border-t border-[#ddd] dark:border-[#444] bg-white dark:bg-[#2d2d2d]">
      <textarea
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Digite sua mensagem… (Enter envia, Shift+Enter nova linha)"
        rows={1}
        className="flex-1 resize-none py-2 px-3 rounded-lg border border-[#ccc] dark:border-[#555] text-[0.9rem] min-h-10 max-h-32 overflow-y-auto leading-[1.5] bg-white dark:bg-[#3a3a3a] text-[#111] dark:text-[#e8e8e8]"
      />
      {disabled ? (
        <button
          type="button"
          onClick={onStop}
          className="py-2 px-4 rounded-lg border-0 bg-[#c0392b] text-white cursor-pointer text-[0.9rem] self-end shrink-0 flex items-center gap-2 hover:bg-[#a93226] transition-colors active:scale-95"
        >
          <Square size={14} fill="currentColor" />
          Parar
        </button>
      ) : (
        <button
          type="button"
          onClick={handleSend}
          disabled={!value.trim()}
          className="py-2 px-4 rounded-lg border-0 bg-[#0078d4] disabled:bg-[#aaa] text-white cursor-pointer disabled:cursor-not-allowed text-[0.9rem] self-end shrink-0 flex items-center gap-2 hover:bg-[#006cbe] disabled:hover:bg-[#aaa] transition-colors active:scale-95"
        >
          <Send size={14} />
          Enviar
        </button>
      )}
    </div>
  )
}
