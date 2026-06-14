import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, LogOut, RefreshCw } from 'lucide-react'
import StatsBar from './StatsBar'
import UploadZone from './UploadZone'
import DocumentTable from './DocumentTable'
import RagParametersPanel from './RagParametersPanel'
import ReindexControls from './ReindexControls'
import propesqiLogo from '../../images/propesqi_horizontal azul.png'

const AUTO_REFRESH_INTERVAL_MS = 15_000

interface Props {
  logout: () => void
  onBack: () => void
}

export default function AdminPanel({ logout, onBack }: Props) {
  // Incrementing this key causes stats and table to re-fetch
  const [refreshKey, setRefreshKey] = useState(0)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(() => new Date())
  const [isRefreshing, setIsRefreshing] = useState(false)
  const refreshingTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

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
    <div className="flex h-screen flex-col overflow-hidden bg-white dark:bg-[#1e1e1e] text-[#111] dark:text-[#e8e8e8]">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-[#ddd] dark:border-[#444] bg-[#fafafa] dark:bg-[#2d2d2d] px-6 py-3 shrink-0">
        <div className="flex items-center gap-4">
          <div className="dark:bg-white rounded-md px-2 py-1.5 shrink-0">
            <img
              src={propesqiLogo}
              alt="PROPESQI - Pró-Reitoria de Pesquisa e Inovação"
              className="h-10 w-auto block"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="text-sm text-[#0078d4] hover:underline cursor-pointer bg-transparent border-0 p-0 flex items-center gap-1"
            >
              <ArrowLeft size={14} />
              Voltar ao chat
            </button>
            <h1 className="text-base font-semibold">Painel de Administração</h1>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {/* Last-updated indicator + manual refresh */}
          <div className="flex items-center gap-2 text-xs text-[#777] dark:text-[#aaa]">
            <RefreshCw
              size={12}
              className={isRefreshing ? 'animate-spin text-[#0078d4]' : ''}
            />
            <span>Atualizado às {formattedTime}</span>
            <button
              type="button"
              onClick={refresh}
              disabled={isRefreshing}
              className="rounded border border-[#ddd] dark:border-[#444] px-2 py-0.5 hover:bg-[#eee] dark:hover:bg-[#3a3a3a] disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed transition-colors"
            >
              Atualizar
            </button>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="text-sm text-[#777] dark:text-[#aaa] hover:text-red-600 dark:hover:text-red-400 cursor-pointer bg-transparent border-0 flex items-center gap-1 transition-colors"
          >
            <LogOut size={14} />
            Sair
          </button>
        </div>
      </header>

      {/* Scrollable content */}
      <main className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-8">

        {/* Stats */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Estatísticas
          </h2>
          <div className="rounded-xl border border-[#ddd] dark:border-[#444] p-4">
            <StatsBar refreshKey={refreshKey} />
          </div>
        </section>

        {/* Upload */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Enviar documentos
          </h2>
          <div className="rounded-xl border border-[#ddd] dark:border-[#444] p-4">
            <UploadZone onUploaded={refresh} />
          </div>
        </section>

        {/* Reindex controls */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Reindexação
          </h2>
          <div className="rounded-xl border border-[#ddd] dark:border-[#444] p-4">
            <ReindexControls onReindexed={refresh} />
          </div>
        </section>

        {/* RAG parameters */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Parâmetros RAG
          </h2>
          <div className="rounded-xl border border-[#ddd] dark:border-[#444] p-4">
            <RagParametersPanel />
          </div>
        </section>

        {/* Document list */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Documentos
          </h2>
          <div className="rounded-xl border border-[#ddd] dark:border-[#444] p-4">
            <DocumentTable refreshKey={refreshKey} onChanged={refresh} />
          </div>
        </section>
      </main>
    </div>
  )
}
