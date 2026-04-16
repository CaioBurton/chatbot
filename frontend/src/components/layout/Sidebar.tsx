import { useState } from 'react'
import type { CSSProperties } from 'react'
import { SessionSummary } from '../../lib/api'
import { Theme } from '../../hooks/useTheme'

const COLLAPSE_KEY = 'propesqi_sidebar_collapsed'

interface Props {
  summaries: SessionSummary[]
  currentSessionId: string | null
  onNewSession: () => void
  onSelectSession: (id: string) => void
  theme: Theme
  toggleTheme: () => void
}

function loadCollapsed(): boolean {
  return localStorage.getItem(COLLAPSE_KEY) === 'true'
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
  theme,
  toggleTheme,
}: Props) {
  const [collapsed, setCollapsed] = useState<boolean>(loadCollapsed)

  const isDark = theme === 'dark'
  const bg = isDark ? '#2d2d2d' : '#fafafa'
  const border = isDark ? '#444' : '#ddd'
  const text = isDark ? '#e8e8e8' : '#111'

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      localStorage.setItem(COLLAPSE_KEY, String(next))
      return next
    })
  }

  const iconBtnStyle: CSSProperties = {
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    color: text,
    fontFamily: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }

  if (collapsed) {
    return (
      <aside
        style={{
          width: '48px',
          borderRight: `1px solid ${border}`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          backgroundColor: bg,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            padding: '0.5rem 0',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
            width: '100%',
          }}
        >
          <button
            onClick={onNewSession}
            title="Nova conversa"
            style={{
              ...iconBtnStyle,
              width: '36px',
              height: '36px',
              borderRadius: '0.5rem',
              border: '1px solid #0078d4',
              color: '#0078d4',
              fontSize: '1.2rem',
            }}
          >
            +
          </button>
        </div>
        <div style={{ flex: 1 }} />
        <button
          onClick={toggleCollapsed}
          title="Expandir"
          style={{
            ...iconBtnStyle,
            width: '36px',
            height: '36px',
            borderRadius: '0.5rem',
            fontSize: '1rem',
            marginBottom: '0.75rem',
          }}
        >
          ›
        </button>
      </aside>
    )
  }

  return (
    <aside
      style={{
        width: '260px',
        minWidth: '200px',
        maxWidth: '320px',
        borderRight: `1px solid ${border}`,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: bg,
        flexShrink: 0,
      }}
    >
      <div
        style={{
          padding: '1rem',
          borderBottom: `1px solid ${border}`,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '0.75rem',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: text }}>
            PROPESQI
          </h2>
          <button
            onClick={toggleTheme}
            title={isDark ? 'Modo claro' : 'Modo escuro'}
            style={{
              ...iconBtnStyle,
              fontSize: '1rem',
              padding: '0.25rem',
              borderRadius: '0.25rem',
            }}
          >
            {isDark ? '☀' : '🌙'}
          </button>
        </div>
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
              color: text,
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
                s.session_id === currentSessionId
                  ? isDark ? '#1a4a6e' : '#e3f2fd'
                  : 'transparent',
              cursor: 'pointer',
              fontFamily: 'inherit',
              marginBottom: '0.25rem',
              color: text,
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

      <button
        onClick={toggleCollapsed}
        title="Recolher"
        style={{
          border: 'none',
          borderTop: `1px solid ${border}`,
          backgroundColor: 'transparent',
          cursor: 'pointer',
          padding: '0.6rem 1rem',
          color: text,
          fontSize: '0.9rem',
          textAlign: 'right',
          fontFamily: 'inherit',
        }}
      >
        ‹
      </button>
    </aside>
  )
}
