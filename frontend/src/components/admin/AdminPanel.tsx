import { useCallback, useEffect, useRef, useState } from 'react'
import { LogOut, RefreshCw, Sun, Moon } from 'lucide-react'
import StatsBar from './StatsBar'
import UploadZone from './UploadZone'
import DocumentTable from './DocumentTable'
import RagParametersPanel from './RagParametersPanel'
import ReindexControls from './ReindexControls'
import { useTheme } from '../../hooks/useTheme'
import propesqiMark from '../../images/propesqi_perfil azul 2.png'

const AUTO_REFRESH_INTERVAL_MS = 15_000

type AdminTab = 'documentos' | 'parametros'

const TABS: { key: AdminTab; label: string }[] = [
  { key: 'documentos', label: 'Documentos' },
  { key: 'parametros', label: 'Parâmetros RAG' },
]

interface Props {
  logout: () => void
  onBack: () => void
}

export default function AdminPanel({ logout, onBack }: Props) {
  // Incrementing this key causes stats and table to re-fetch
  const [refreshKey, setRefreshKey] = useState(0)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(() => new Date())
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [tab, setTab] = useState<AdminTab>('documentos')
  const refreshingTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { theme, toggleTheme } = useTheme()

  const refresh = useCallback(() => {
    setIsRefreshing(true)
    setRefreshKey((k: number) => k + 1)
    setLastRefreshed(new Date())
    // Clear the "refreshing" spinner after a short delay
    if (refreshingTimer.current) clearTimeout(refreshingTimer.current)
    refreshingTimer.current = setTimeout(() => setIsRefreshing(false), 800)
  }, [])

  // Auto-refresh every AUTO_REFRESH_INTERVAL_MS
  useEffect(() => {
    const id = setInterval(refresh, AUTO_REFRESH_INTERVAL_MS)
    return () => {
      clearInterval(id)
      if (refreshingTimer.current) clearTimeout(refreshingTimer.current)
    }
  }, [refresh])

  const handleLogout = () => {
    logout()
    onBack()
  }

  const formattedTime = lastRefreshed.toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#fdfcfa] dark:bg-[#16181c] text-[#1e2128] dark:text-[#eceae7] transition-colors">
      {/* Top bar */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e6e1d5] dark:border-[#33383f] bg-[#f7f4ee] dark:bg-[#111316] px-6 py-3.5 shrink-0">
        <div className="flex min-w-0 items-center gap-3.5">
          <img
            src={propesqiMark}
            alt="PROPESQI"
            className="h-9 w-9 shrink-0 rounded-full object-cover"
          />
          <div className="min-w-0">
            <div className="whitespace-nowrap font-serif text-[15.5px] font-semibold text-[#1e2128] dark:text-[#eceae7]">
              Painel de Administração
            </div>
            <button
              type="button"
              onClick={onBack}
              className="flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 text-xs font-semibold text-[#2c4a86] dark:text-[#8596b9] hover:underline"
            >
              ‹ Voltar ao chat
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-[18px]">
          <div className="flex items-center gap-2 text-xs text-[#a19e96] dark:text-[#6c717a]">
            <RefreshCw size={12} className={isRefreshing ? 'animate-spin' : ''} />
            <span>Atualizado às {formattedTime}</span>
            <button
              type="button"
              onClick={refresh}
              disabled={isRefreshing}
              className="cursor-pointer rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-transparent px-2.5 py-1 text-xs text-[#6c7078] dark:text-[#9da2aa] transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Atualizar
            </button>
          </div>
          <button
            type="button"
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-[#6c7078] dark:text-[#9da2aa] transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a]"
          >
            {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="flex cursor-pointer items-center gap-1.5 border-0 bg-transparent text-[12.5px] font-semibold text-[#6c7078] dark:text-[#9da2aa] transition-colors hover:text-[#c0392b] dark:hover:text-[#e0685c]"
          >
            <LogOut size={14} />
            Sair
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="flex shrink-0 gap-0 overflow-x-auto border-b border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-6 pt-2.5">
        {TABS.map(t => {
          const active = tab === t.key
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`mr-[22px] cursor-pointer whitespace-nowrap border-0 border-b-2 bg-transparent px-1 py-2.5 text-[13.5px] font-semibold transition-colors ${
                active
                  ? 'border-[#2c4a86] text-[#2c4a86] dark:border-[#8596b9] dark:text-[#8596b9]'
                  : 'border-transparent text-[#6c7078] dark:text-[#9da2aa]'
              }`}
            >
              {t.label}
            </button>
          )
        })}
      </nav>

      {/* Scrollable content */}
      <main className="flex-1 overflow-y-auto p-6">
        {tab === 'documentos' && (
          <div className="flex flex-col gap-[22px] animate-fade-in">
            <section>
              <h2 className="mb-3.5 font-serif text-base font-semibold">
                Estatísticas
              </h2>
              <StatsBar refreshKey={refreshKey} />
            </section>

            <section>
              <h2 className="mb-3.5 font-serif text-base font-semibold">
                Enviar documentos
              </h2>
              <UploadZone onUploaded={refresh} />
            </section>

            <section>
              <h2 className="mb-3.5 font-serif text-base font-semibold">
                Documentos
              </h2>
              <DocumentTable refreshKey={refreshKey} onChanged={refresh} />
            </section>

            <section>
              <h2 className="mb-3.5 font-serif text-base font-semibold">
                Reindexação
              </h2>
              <div className="rounded-[14px] border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] p-5">
                <ReindexControls onReindexed={refresh} />
              </div>
            </section>
          </div>
        )}

        {tab === 'parametros' && (
          <div className="mx-auto w-full max-w-[840px] animate-fade-in">
            <RagParametersPanel />
          </div>
        )}
      </main>
    </div>
  )
}
