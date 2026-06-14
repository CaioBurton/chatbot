import { useState, KeyboardEvent } from 'react'
import { Send, Square, Plus } from 'lucide-react'

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
    <div className="px-4 pb-4 pt-2 bg-[#fafafa] dark:bg-[#1e1e1e]">
      <div className="max-w-3xl mx-auto">
        {/* Card */}
        <div className="bg-white dark:bg-[#2d2d2d] rounded-2xl border border-[#e0d9d0] dark:border-[#444] shadow-sm">
          <textarea
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Mensagem ChatBot..."
            rows={1}
            className="w-full resize-none px-4 pt-4 pb-2 rounded-2xl text-[0.9rem] min-h-[52px] max-h-40 overflow-y-auto leading-[1.6] bg-transparent text-[#111] dark:text-[#e8e8e8] placeholder-[#aaa] dark:placeholder-[#666] outline-none border-none"
          />
          {/* Bottom action bar */}
          <div className="flex items-center justify-between px-3 pb-3 pt-1">
            <button
              type="button"
              className="w-8 h-8 flex items-center justify-center rounded-full text-[#888] dark:text-[#aaa] hover:bg-[#f0f0f0] dark:hover:bg-[#3a3a3a] transition-colors"
              title="Anexar arquivo"
            >
              <Plus size={18} />
            </button>

            {disabled ? (
              <button
                type="button"
                onClick={onStop}
                className="w-9 h-9 flex items-center justify-center rounded-full bg-[#c0392b] text-white hover:bg-[#a93226] transition-colors active:scale-95"
                title="Parar geração"
              >
                <Square size={15} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSend}
                disabled={!value.trim()}
                className="w-9 h-9 flex items-center justify-center rounded-full bg-[#0078d4] disabled:bg-[#ddd] dark:disabled:bg-[#555] text-white cursor-pointer disabled:cursor-not-allowed hover:bg-[#006ab8] disabled:hover:bg-[#ddd] dark:disabled:hover:bg-[#555] transition-colors active:scale-95"
                title="Enviar mensagem"
              >
                <Send size={15} />
              </button>
            )}
          </div>
        </div>

        {/* Disclaimer */}
        <p className="text-center text-[0.72rem] text-[#aaa] dark:text-[#666] mt-2">
          O ChatBot pode cometer erros. Considere verificar informações importantes.
        </p>
      </div>
    </div>
  )
}
