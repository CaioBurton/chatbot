import { useState, KeyboardEvent } from 'react'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: Props) {
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
    <div
      style={{
        display: 'flex',
        gap: '0.5rem',
        padding: '0.75rem 1rem',
        borderTop: '1px solid #ddd',
        backgroundColor: '#fff',
      }}
    >
      <textarea
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Digite sua mensagem… (Enter envia, Shift+Enter nova linha)"
        rows={1}
        style={{
          flex: 1,
          resize: 'none',
          padding: '0.5rem 0.75rem',
          borderRadius: '0.5rem',
          border: '1px solid #ccc',
          fontFamily: 'inherit',
          fontSize: '0.9rem',
          minHeight: '2.5rem',
          maxHeight: '8rem',
          overflowY: 'auto',
          lineHeight: 1.5,
        }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        style={{
          padding: '0.5rem 1.25rem',
          borderRadius: '0.5rem',
          border: 'none',
          backgroundColor: disabled || !value.trim() ? '#aaa' : '#0078d4',
          color: '#fff',
          cursor: disabled || !value.trim() ? 'not-allowed' : 'pointer',
          fontFamily: 'inherit',
          fontSize: '0.9rem',
          alignSelf: 'flex-end',
          flexShrink: 0,
        }}
      >
        Enviar
      </button>
    </div>
  )
}
