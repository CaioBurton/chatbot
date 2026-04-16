import { useState, KeyboardEvent } from 'react'
import { Theme } from '../../hooks/useTheme'

interface Props {
  onSend: (text: string) => void
  disabled?: boolean
  onStop?: () => void
  theme: Theme
}

export default function ChatInput({ onSend, disabled, onStop, theme }: Props) {
  const [value, setValue] = useState('')
  const isDark = theme === 'dark'

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

  const containerBg = isDark ? '#2d2d2d' : '#fff'
  const containerBorder = isDark ? '#444' : '#ddd'
  const inputBorder = isDark ? '#555' : '#ccc'
  const inputBg = isDark ? '#3a3a3a' : '#fff'
  const inputColor = isDark ? '#e8e8e8' : '#111'

  return (
    <div
      style={{
        display: 'flex',
        gap: '0.5rem',
        padding: '0.75rem 1rem',
        borderTop: `1px solid ${containerBorder}`,
        backgroundColor: containerBg,
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
          border: `1px solid ${inputBorder}`,
          fontFamily: 'inherit',
          fontSize: '0.9rem',
          minHeight: '2.5rem',
          maxHeight: '8rem',
          overflowY: 'auto',
          lineHeight: 1.5,
          backgroundColor: inputBg,
          color: inputColor,
        }}
      />
      {disabled ? (
        <button
          onClick={onStop}
          style={{
            padding: '0.5rem 1.25rem',
            borderRadius: '0.5rem',
            border: 'none',
            backgroundColor: '#c0392b',
            color: '#fff',
            cursor: 'pointer',
            fontFamily: 'inherit',
            fontSize: '0.9rem',
            alignSelf: 'flex-end',
            flexShrink: 0,
          }}
        >
          ⏹ Parar
        </button>
      ) : (
        <button
          onClick={handleSend}
          disabled={!value.trim()}
          style={{
            padding: '0.5rem 1.25rem',
            borderRadius: '0.5rem',
            border: 'none',
            backgroundColor: !value.trim() ? '#aaa' : '#0078d4',
            color: '#fff',
            cursor: !value.trim() ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit',
            fontSize: '0.9rem',
            alignSelf: 'flex-end',
            flexShrink: 0,
          }}
        >
          Enviar
        </button>
      )}
    </div>
  )
}
