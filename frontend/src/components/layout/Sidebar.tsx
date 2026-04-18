import { useState } from 'react'
import {
  Plus,
  Settings,
  ChevronRight,
  ChevronLeft,
  Sun,
  Moon,
  Trash2,
  MessageSquare,
} from 'lucide-react'
import { SessionSummary } from '../../lib/api'
import { useTheme } from '../../hooks/useTheme'

const COLLAPSE_KEY = 'propesqi_sidebar_collapsed'

interface Props {
  summaries: SessionSummary[]
  currentSessionId: string | null
  onNewSession: () => void
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onAdminClick: () => void
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
  onDeleteSession,
  onAdminClick,
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
      <aside className="w-12 border-r border-[#ddd] dark:border-[#444] flex flex-col items-center bg-[#fafafa] dark:bg-[#2d2d2d] shrink-0 transition-all duration-200">
        <div className="py-2 flex flex-col items-center gap-2 w-full">
          <button
            type="button"
            onClick={onNewSession}
            title="Nova conversa"
            className="w-9 h-9 rounded-lg border border-[#0078d4] text-[#0078d4] flex items-center justify-center bg-transparent cursor-pointer hover:bg-[#e3f2fd] dark:hover:bg-[#1a4a6e] transition-colors"
          >
            <Plus size={16} />
          </button>
          <button
            type="button"
            onClick={onAdminClick}
            title="Administração"
            className="w-9 h-9 rounded-lg border border-[#ddd] dark:border-[#555] text-[#555] dark:text-[#aaa] flex items-center justify-center bg-transparent cursor-pointer hover:border-[#0078d4] hover:text-[#0078d4] transition-colors"
          >
            <Settings size={16} />
          </button>
        </div>
        <div className="flex-1" />
        <button
          type="button"
          onClick={toggleCollapsed}
          title="Expandir"
          className="w-9 h-9 rounded-lg flex items-center justify-center bg-transparent border-0 cursor-pointer text-[#111] dark:text-[#e8e8e8] mb-3 hover:bg-[#f0f0f0] dark:hover:bg-[#3a3a3a] transition-colors"
        >
          <ChevronRight size={18} />
        </button>
      </aside>
    )
  }

  return (
    <aside className="w-[260px] min-w-[200px] max-w-[320px] border-r border-[#ddd] dark:border-[#444] flex flex-col bg-[#fafafa] dark:bg-[#2d2d2d] shrink-0 transition-all duration-200">
      <div className="p-4 border-b border-[#ddd] dark:border-[#444]">
        <div className="flex justify-between items-center mb-3">
          <h2 className="m-0 text-base font-semibold text-[#111] dark:text-[#e8e8e8]">
            PROPESQI
          </h2>
          <button
            type="button"
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
            className="border-0 bg-transparent cursor-pointer text-[#111] dark:text-[#e8e8e8] p-1 rounded flex items-center justify-center hover:bg-[#f0f0f0] dark:hover:bg-[#3a3a3a] transition-colors"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </div>
        <button
          type="button"
          onClick={onNewSession}
          className="w-full py-2 rounded-lg border border-[#0078d4] bg-transparent text-[#0078d4] cursor-pointer text-[0.9rem] flex items-center justify-center gap-2 hover:bg-[#e3f2fd] dark:hover:bg-[#1a4a6e] transition-colors"
        >
          <Plus size={15} />
          Nova conversa
        </button>
        <button
          type="button"
          onClick={onAdminClick}
          className="mt-2 w-full py-1.5 rounded-lg border border-[#ddd] dark:border-[#555] bg-transparent text-[#555] dark:text-[#aaa] cursor-pointer text-[0.85rem] hover:border-[#0078d4] hover:text-[#0078d4] flex items-center justify-center gap-2 transition-colors"
        >
          <Settings size={14} />
          Admin
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {summaries.length === 0 && (
          <p className="p-2 opacity-50 text-[0.85rem] m-0 text-[#111] dark:text-[#e8e8e8]">
            Sem conversas anteriores.
          </p>
        )}
        {summaries.map(s => (
          <div
            key={s.session_id}
            className={`group flex items-center rounded-lg mb-1 animate-slide-in-left ${
              s.session_id === currentSessionId
                ? 'bg-[#e3f2fd] dark:bg-[#1a4a6e]'
                : 'bg-transparent hover:bg-[#f0f0f0] dark:hover:bg-[#3a3a3a]'
            } transition-colors`}
          >
            <button
              type="button"
              onClick={() => onSelectSession(s.session_id)}
              className="flex-1 text-left px-3 py-[0.6rem] rounded-lg border-0 cursor-pointer bg-transparent text-[#111] dark:text-[#e8e8e8] min-w-0 flex items-start gap-2"
            >
              <MessageSquare size={14} className="mt-0.5 shrink-0 opacity-50" />
              <div className="min-w-0">
                <div className="text-[0.85rem] font-medium overflow-hidden text-ellipsis whitespace-nowrap">
                  {s.preview ?? '(sem mensagens)'}
                </div>
                <div className="text-[0.75rem] opacity-[0.55] mt-[0.2rem]">
                  {formatDate(s.last_activity)}
                </div>
              </div>
            </button>
            <button
              type="button"
              title="Apagar conversa"
              onClick={e => { e.stopPropagation(); onDeleteSession(s.session_id) }}
              className="opacity-0 group-hover:opacity-100 shrink-0 w-7 h-7 mr-1 rounded border-0 bg-transparent cursor-pointer text-[#888] hover:text-red-500 flex items-center justify-center transition-opacity"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={toggleCollapsed}
        title="Recolher"
        className="border-0 border-t border-[#ddd] dark:border-[#444] border-solid bg-transparent cursor-pointer py-[0.6rem] px-4 text-[#111] dark:text-[#e8e8e8] text-[0.9rem] w-full flex items-center justify-end gap-1 hover:bg-[#f0f0f0] dark:hover:bg-[#3a3a3a] transition-colors"
      >
        <ChevronLeft size={16} />
      </button>
    </aside>
  )
}
