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
  Menu,
  X,
} from 'lucide-react'
import { SessionSummary } from '../../lib/api'
import { useTheme } from '../../hooks/useTheme'
import { useIsMobile } from '../../hooks/useIsMobile'
import propesqiMark from '../../images/propesqi_perfil azul 2.png'

const COLLAPSE_KEY = 'propesqi_sidebar_collapsed'

interface Props {
  summaries: SessionSummary[]
  currentSessionId: string | null
  onNewSession: () => void
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onAdminClick: () => void
}

interface SessionRow {
  groupLabel: string | null
  summary: SessionSummary
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

function dayGroup(iso: string): string {
  if (!iso) return 'Mais antigas'
  const date = new Date(iso)
  if (isNaN(date.getTime())) return 'Mais antigas'
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000)
  if (diffDays <= 0) return 'Hoje'
  if (diffDays === 1) return 'Ontem'
  if (diffDays <= 7) return 'Últimos 7 dias'
  return 'Mais antigas'
}

function groupSessions(summaries: SessionSummary[]): SessionRow[] {
  const sorted = [...summaries].sort(
    (a, b) => new Date(b.last_activity).getTime() - new Date(a.last_activity).getTime(),
  )
  const rows: SessionRow[] = []
  let lastGroup: string | null = null
  for (const summary of sorted) {
    const group = dayGroup(summary.last_activity)
    rows.push({ groupLabel: group !== lastGroup ? group : null, summary })
    lastGroup = group
  }
  return rows
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
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const isMobile = useIsMobile()
  const visibleSummaries = summaries.filter(s => s.preview !== null)
  const rows = groupSessions(visibleSummaries)

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

  const handleSelect = (id: string) => {
    onSelectSession(id)
    setMobileDrawerOpen(false)
  }

  const handleNewSession = () => {
    onNewSession()
    setMobileDrawerOpen(false)
  }

  const sessionList = (
    <div className="flex-1 overflow-y-auto p-2">
      {rows.length === 0 && (
        <p className="p-2 text-[#a19e96] dark:text-[#6c717a] text-[0.85rem] m-0">
          Sem conversas anteriores.
        </p>
      )}
      {rows.map(({ groupLabel, summary: s }) => (
        <div key={s.session_id}>
          {groupLabel && (
            <div className="px-2 pt-3.5 pb-1.5 text-[11px] font-bold tracking-wider uppercase text-[#a19e96] dark:text-[#6c717a]">
              {groupLabel}
            </div>
          )}
          <div
            className={`group flex items-center rounded-lg mb-0.5 animate-slide-in-left ${
              s.session_id === currentSessionId
                ? 'bg-[#e8edf7] dark:bg-[#182236]'
                : 'bg-transparent hover:bg-[#eae6dc] dark:hover:bg-[#2c313a]'
            } transition-colors`}
          >
            <button
              type="button"
              onClick={() => handleSelect(s.session_id)}
              className="flex-1 text-left px-3 py-[0.6rem] rounded-lg border-0 cursor-pointer bg-transparent text-[#1e2128] dark:text-[#eceae7] min-w-0 flex items-start gap-2"
            >
              <MessageSquare size={14} className="mt-0.5 shrink-0 text-[#a19e96] dark:text-[#6c717a]" />
              <div className="min-w-0">
                <div className="text-[0.85rem] font-medium overflow-hidden text-ellipsis whitespace-nowrap">
                  {s.preview}
                </div>
                <div className="text-[0.72rem] text-[#a19e96] dark:text-[#6c717a] mt-[0.2rem]">
                  {formatDate(s.last_activity)}
                </div>
              </div>
            </button>
            <button
              type="button"
              title="Apagar conversa"
              onClick={e => { e.stopPropagation(); onDeleteSession(s.session_id) }}
              className="opacity-0 group-hover:opacity-100 shrink-0 w-7 h-7 mr-1 rounded border-0 bg-transparent cursor-pointer text-[#a19e96] dark:text-[#6c717a] hover:text-[#c0392b] dark:hover:text-[#e0685c] flex items-center justify-center transition-opacity"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )

  const brandBlock = (onClose?: () => void) => (
    <div className="flex items-center justify-between gap-2 mb-3.5">
      <div className="flex items-center gap-[9px] min-w-0">
        <img src={propesqiMark} alt="PROPESQI" className="w-8 h-8 rounded-full object-cover shrink-0" />
        <div className="min-w-0 leading-[1.15]">
          <div className="font-serif font-semibold text-[14.5px] text-[#1e2128] dark:text-[#eceae7] whitespace-nowrap overflow-hidden text-ellipsis">
            PROPESQI
          </div>
          <div className="text-[10.5px] tracking-[.03em] text-[#a19e96] dark:text-[#6c717a] whitespace-nowrap">
            Pesquisa &amp; Inovação · UFPI
          </div>
        </div>
      </div>
      {onClose ? (
        <button
          type="button"
          onClick={onClose}
          className="w-[30px] h-[30px] rounded-lg border-0 bg-transparent text-[#6c7078] dark:text-[#9da2aa] cursor-pointer flex items-center justify-center shrink-0 hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] transition-colors"
        >
          <X size={16} />
        </button>
      ) : (
        <button
          type="button"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
          className="w-[30px] h-[30px] rounded-lg border-0 bg-transparent text-[#6c7078] dark:text-[#9da2aa] cursor-pointer flex items-center justify-center shrink-0 hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] transition-colors"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      )}
    </div>
  )

  const actionButtons = (
    <>
      <button
        type="button"
        onClick={handleNewSession}
        className="w-full py-[9px] px-3 rounded-[10px] border-[1.5px] border-[#2c4a86] dark:border-[#8596b9] bg-transparent text-[#2c4a86] dark:text-[#8596b9] cursor-pointer text-[13.5px] font-semibold flex items-center justify-center gap-1.5 hover:bg-[#e8edf7] dark:hover:bg-[#182236] transition-colors"
      >
        <Plus size={16} />
        Nova conversa
      </button>
      <button
        type="button"
        onClick={onAdminClick}
        className="mt-2 w-full py-[7px] px-3 rounded-[10px] border border-[#e6e1d5] dark:border-[#33383f] bg-transparent text-[#6c7078] dark:text-[#9da2aa] cursor-pointer text-[12.5px] hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] flex items-center justify-center gap-1.5 transition-colors"
      >
        <Settings size={14} />
        Admin
      </button>
    </>
  )

  // Mobile: fixed top header + slide-in drawer overlay instead of a static aside
  if (isMobile) {
    return (
      <>
        <div className="fixed top-0 left-0 right-0 h-14 flex items-center justify-between px-2.5 bg-[#f7f4ee] dark:bg-[#111316] border-b border-[#e6e1d5] dark:border-[#33383f] z-20">
          <button
            type="button"
            onClick={() => setMobileDrawerOpen(true)}
            className="w-[38px] h-[38px] border-0 bg-transparent text-[#1e2128] dark:text-[#eceae7] text-xl cursor-pointer flex items-center justify-center"
          >
            <Menu size={20} />
          </button>
          <img src={propesqiMark} alt="PROPESQI" className="w-7 h-7 rounded-full object-cover" />
          <button
            type="button"
            onClick={handleNewSession}
            className="w-[38px] h-[38px] border-0 bg-transparent text-[#2c4a86] dark:text-[#8596b9] text-xl cursor-pointer flex items-center justify-center"
          >
            <Plus size={20} />
          </button>
        </div>

        {mobileDrawerOpen && (
          <>
            <div
              onClick={() => setMobileDrawerOpen(false)}
              className="fixed inset-0 bg-[rgba(25,20,12,0.45)] dark:bg-[rgba(0,0,0,0.6)] z-30"
            />
            <aside className="fixed top-0 left-0 bottom-0 w-[82%] max-w-[300px] bg-[#f7f4ee] dark:bg-[#111316] z-40 flex flex-col shadow-[2px_0_24px_rgba(0,0,0,.2)] animate-slide-in-left">
              <div className="p-[16px_14px_14px] border-b border-[#e6e1d5] dark:border-[#33383f]">
                {brandBlock(() => setMobileDrawerOpen(false))}
                {actionButtons}
              </div>
              {sessionList}
            </aside>
          </>
        )}
      </>
    )
  }

  if (collapsed) {
    return (
      <aside className="w-[68px] border-r border-[#e6e1d5] dark:border-[#33383f] flex flex-col items-center bg-[#f7f4ee] dark:bg-[#111316] shrink-0 py-4 gap-2.5 transition-colors">
        <img src={propesqiMark} alt="PROPESQI" className="w-[34px] h-[34px] rounded-full object-cover mb-1.5" />
        <button
          type="button"
          onClick={onNewSession}
          title="Nova conversa"
          className="w-[38px] h-[38px] rounded-[10px] border-[1.5px] border-[#2c4a86] dark:border-[#8596b9] text-[#2c4a86] dark:text-[#8596b9] flex items-center justify-center bg-transparent cursor-pointer hover:bg-[#e8edf7] dark:hover:bg-[#182236] transition-colors"
        >
          <Plus size={18} />
        </button>
        <button
          type="button"
          onClick={onAdminClick}
          title="Administração"
          className="w-9 h-9 rounded-lg border border-[#e6e1d5] dark:border-[#33383f] text-[#6c7078] dark:text-[#9da2aa] flex items-center justify-center bg-transparent cursor-pointer hover:border-[#2c4a86] dark:hover:border-[#8596b9] hover:text-[#2c4a86] dark:hover:text-[#8596b9] transition-colors"
        >
          <Settings size={16} />
        </button>
        <div className="flex-1" />
        <button
          type="button"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
          className="w-[34px] h-[34px] rounded-lg border-0 bg-transparent text-[#6c7078] dark:text-[#9da2aa] cursor-pointer flex items-center justify-center hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] transition-colors"
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <button
          type="button"
          onClick={toggleCollapsed}
          title="Expandir"
          className="w-[34px] h-[34px] rounded-lg flex items-center justify-center bg-transparent border-0 cursor-pointer text-[#6c7078] dark:text-[#9da2aa] mb-1 hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] transition-colors"
        >
          <ChevronRight size={18} />
        </button>
      </aside>
    )
  }

  return (
    <aside className="w-[272px] min-w-[200px] max-w-[320px] border-r border-[#e6e1d5] dark:border-[#33383f] flex flex-col bg-[#f7f4ee] dark:bg-[#111316] shrink-0 transition-colors">
      <div className="p-[18px_16px_14px] border-b border-[#e6e1d5] dark:border-[#33383f]">
        {brandBlock()}
        {actionButtons}
      </div>

      {sessionList}

      <button
        type="button"
        onClick={toggleCollapsed}
        title="Recolher"
        className="border-0 border-t border-[#e6e1d5] dark:border-[#33383f] border-solid bg-transparent cursor-pointer py-[10px] px-4 text-[#6c7078] dark:text-[#9da2aa] text-[13px] w-full flex items-center justify-end gap-1.5 hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] transition-colors"
      >
        Recolher <ChevronLeft size={16} />
      </button>
    </aside>
  )
}
