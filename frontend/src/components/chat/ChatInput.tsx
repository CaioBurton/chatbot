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
    <div className="px-4 pt-2.5 pb-4 bg-[#fdfcfa] dark:bg-[#16181c] transition-colors">
      <div className="max-w-[720px] mx-auto">
        {/* Card */}
        <div className="bg-white dark:bg-[#1d2126] rounded-[18px] border border-[#e6e1d5] dark:border-[#33383f] shadow-[0_1px_3px_rgba(30,25,15,0.06)] dark:shadow-none">
          <textarea
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Mensagem ChatBot..."
            rows={1}
            className="w-full resize-none px-4 pt-3.5 pb-1.5 rounded-[18px] text-[14.5px] min-h-[52px] max-h-40 overflow-y-auto leading-[1.55] bg-transparent text-[#1e2128] dark:text-[#eceae7] placeholder-[#a19e96] dark:placeholder-[#6c717a] outline-none border-none"
          />
          {/* Bottom action bar */}
          <div className="flex items-center justify-end px-2.5 pb-2.5 pt-1">
            {disabled ? (
              <button
                type="button"
                onClick={onStop}
                className="w-[34px] h-[34px] flex items-center justify-center rounded-full bg-[#c0392b] dark:bg-[#e0685c] text-white hover:opacity-90 transition-opacity active:scale-95"
                title="Parar geração"
              >
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSend}
                disabled={!value.trim()}
                className="w-[34px] h-[34px] flex items-center justify-center rounded-full bg-[#2c4a86] dark:bg-[#8596b9] disabled:bg-[#e6e1d5] dark:disabled:bg-[#33383f] text-white dark:text-[#101317] disabled:text-[#a19e96] cursor-pointer disabled:cursor-not-allowed hover:bg-[#20396a] dark:hover:bg-[#abb7cf] disabled:hover:bg-[#e6e1d5] dark:disabled:hover:bg-[#33383f] transition-colors active:scale-95"
                title="Enviar mensagem"
              >
                <Send size={15} />
              </button>
            )}
          </div>
        </div>

        {/* Disclaimer */}
        <p className="text-center text-[11px] text-[#a19e96] dark:text-[#6c717a] mt-2">
          O ChatBot pode cometer erros. Considere verificar informações importantes.
        </p>
      </div>
    </div>
  )
}
