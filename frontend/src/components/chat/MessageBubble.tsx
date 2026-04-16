import { DisplayMessage } from '../../hooks/useChat'

interface Props {
  message: DisplayMessage
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '0.75rem',
      }}
    >
      <div
        style={{
          maxWidth: '70%',
          padding: '0.75rem 1rem',
          borderRadius: isUser ? '1rem 1rem 0 1rem' : '1rem 1rem 1rem 0',
          backgroundColor: isUser ? '#0078d4' : '#f0f0f0',
          color: isUser ? '#fff' : '#111',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          lineHeight: 1.5,
        }}
      >
        {message.content || (
          <span style={{ opacity: 0.4, fontStyle: 'italic' }}>▌</span>
        )}

        {message.sources && message.sources.length > 0 && (
          <div
            style={{
              marginTop: '0.6rem',
              borderTop: '1px solid rgba(0,0,0,0.12)',
              paddingTop: '0.5rem',
              fontSize: '0.78rem',
              color: isUser ? 'rgba(255,255,255,0.85)' : '#444',
            }}
          >
            <strong>Fontes:</strong>
            <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem' }}>
              {message.sources.map((s, i) => (
                <li key={i}>
                  {s.original_name}
                  {s.page_number != null ? ` (p. ${s.page_number})` : ''}
                  {' \u2014 '}
                  {(s.score * 100).toFixed(0)}%
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
