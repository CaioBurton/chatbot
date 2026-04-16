import { useState } from 'react'
import { SessionSummary } from '../../lib/api'
import { useTheme } from '../../hooks/useTheme'

const COLLAPSE_KEY = 'propesqi_sidebar_collapsed'

interface Props {
  summaries: SessionSummary[]
  currentSessionId: string | null
  onNewSession: () => void
  onSelectSession: (id: string) => void
}

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === 'true'
  } catch {
    return false
  }
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
  const [collapsed, setCollapsed] = useState<boolean>(loadCollapsed)
  const { theme, toggleTheme } = useTheme()

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      try {
        localStorage.setItem(COLLAPSE_KEY, String(next))
      } catch {
        // Storage unavailable
      }
      return next
    })
  }

  if (collapsed) {
    return (
      <aside className="w-12 border-r border-[#ddd] dark:border-[#444] flex flex-col items-center bg-[#fafafa] dark:bg-[#2d2d2d] shrink-0">
        <div className="py-2 flex flex-col items-center gap-2 w-full">
          <button
            type="button"
            onClick={onNewSession}
            title="Nova conversa"
            className="w-9 h-9 rounded-lg border border-[#0078d4] text-[#0078d4] text-[1.2rem] flex items-center justify-center bg-transparent cursor-pointer"
          >
            +
          </button>
        </div>
        <div className="flex-1" />
        <button
          type="button"
          onClick={toggleCollapsed}
          title="Expandir"
          className="w-9 h-9 rounded-lg text-base flex items-center justify-center bg-transparent border-0 cursor-pointer text-[#111] dark:text-[#e8e8e8] mb-3"
        >
          ›
        </button>
      </aside>
    )
  }

  return (
    <aside className="w-[260px] min-w-[200px] max-w-[320px] border-r border-[#ddd] dark:border-[#444] flex flex-col bg-[#fafafa] dark:bg-[#2d2d2d] shrink-0">
      <div className="p-4 border-b border-[#ddd] dark:border-[#444]">
        <div className="flex justify-between items-center mb-3">
          <h2 className="m-0 text-base font-semibold text-[#111] dark:text-[#e8e8e8]">
            PROPESQI
          </h2>
          <button
            type="button"
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
            className="border-0 bg-transparent cursor-pointer text-[#111] dark:text-[#e8e8e8] text-base p-1 rounded flex items-center justify-center"
          >
            {theme === 'dark' ? '☀' : '🌙'}
          </button>
        </div>
        <button
          type="button"
          onClick={onNewSession}
          className="w-full py-2 rounded-lg border border-[#0078d4] bg-transparent text-[#0078d4] cursor-pointer text-[0.9rem]"
        >
          + Nova conversa
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {summaries.length === 0 && (
          <p className="p-2 opacity-50 text-[0.85rem] m-0 text-[#111] dark:text-[#e8e8e8]">
            Sem conversas anteriores.
          </p>
        )}
        {summaries.map(s => (
          <button
            type="button"
            key={s.session_id}
            onClick={() => onSelectSession(s.session_id)}
            className={`block w-full text-left px-3 py-[0.6rem] rounded-lg border-0 cursor-pointer mb-1 text-[#111] dark:text-[#e8e8e8] ${
              s.session_id === currentSessionId
                ? 'bg-[#e3f2fd] dark:bg-[#1a4a6e]'
                : 'bg-transparent'
            }`}
          >
            <div className="text-[0.85rem] font-medium overflow-hidden text-ellipsis whitespace-nowrap">
              {s.preview ?? '(sem mensagens)'}
            </div>
            <div className="text-[0.75rem] opacity-[0.55] mt-[0.2rem]">
              {formatDate(s.last_activity)}
            </div>
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={toggleCollapsed}
        title="Recolher"
        className="border-0 border-t border-[#ddd] dark:border-[#444] border-solid bg-transparent cursor-pointer py-[0.6rem] px-4 text-[#111] dark:text-[#e8e8e8] text-[0.9rem] text-right w-full"
      >
        ‹
      </button>
    </aside>
  )
}
