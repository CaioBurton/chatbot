import { SessionSummary } from '../../lib/api'

interface Props {
  summaries: SessionSummary[]
  currentSessionId: string | null
  onNewSession: () => void
  onSelectSession: (id: string) => void
}

function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export default function Sidebar({
  summaries,
  currentSessionId,
  onNewSession,
  onSelectSession,
}: Props) {
  return (
    <aside
      style={{
        width: '260px',
        minWidth: '200px',
        maxWidth: '320px',
        borderRight: '1px solid #ddd',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#fafafa',
        flexShrink: 0,
      }}
    >
      <div
        style={{
          padding: '1rem',
          borderBottom: '1px solid #ddd',
        }}
      >
        <h2 style={{ margin: '0 0 0.75rem', fontSize: '1rem', fontWeight: 600 }}>
          PROPESQI
        </h2>
        <button
          onClick={onNewSession}
          style={{
            width: '100%',
            padding: '0.5rem',
            borderRadius: '0.5rem',
            border: '1px solid #0078d4',
            backgroundColor: 'transparent',
            color: '#0078d4',
            cursor: 'pointer',
            fontFamily: 'inherit',
            fontSize: '0.9rem',
          }}
        >
          + Nova conversa
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem' }}>
        {summaries.length === 0 && (
          <p
            style={{
              padding: '0.5rem',
              opacity: 0.5,
              fontSize: '0.85rem',
              margin: 0,
            }}
          >
            Sem conversas anteriores.
          </p>
        )}
        {summaries.map(s => (
          <button
            key={s.session_id}
            onClick={() => onSelectSession(s.session_id)}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '0.6rem 0.75rem',
              borderRadius: '0.5rem',
              border: 'none',
              backgroundColor:
                s.session_id === currentSessionId ? '#e3f2fd' : 'transparent',
              cursor: 'pointer',
              fontFamily: 'inherit',
              marginBottom: '0.25rem',
            }}
          >
            <div
              style={{
                fontSize: '0.85rem',
                fontWeight: 500,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {s.preview ?? '(sem mensagens)'}
            </div>
            <div
              style={{
                fontSize: '0.75rem',
                opacity: 0.55,
                marginTop: '0.2rem',
              }}
            >
              {formatDate(s.last_activity)}
            </div>
          </button>
        ))}
      </div>
    </aside>
  )
}
