import { useState } from 'react'
import StatsBar from './StatsBar'
import UploadZone from './UploadZone'
import DocumentTable from './DocumentTable'
import RagParametersPanel from './RagParametersPanel'
import ReindexControls from './ReindexControls'

interface Props {
  logout: () => void
  onBack: () => void
}

export default function AdminPanel({ logout, onBack }: Props) {
  // Incrementing this key causes stats and table to re-fetch
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = () => setRefreshKey(k => k + 1)

  const handleLogout = () => {
    logout()
    onBack()
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white dark:bg-[#1e1e1e] text-[#111] dark:text-[#e8e8e8]">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-[#ddd] dark:border-[#444] bg-[#fafafa] dark:bg-[#2d2d2d] px-6 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="text-sm text-[#0078d4] hover:underline cursor-pointer bg-transparent border-0 p-0"
          >
            ← Voltar ao chat
          </button>
          <h1 className="text-base font-semibold">Painel de Administração</h1>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="text-sm text-[#777] dark:text-[#aaa] hover:text-red-600 dark:hover:text-red-400 cursor-pointer bg-transparent border-0"
        >
          Sair
        </button>
      </header>

      {/* Scrollable content */}
      <main className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-8">

        {/* Stats */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Estatísticas
          </h2>
          <StatsBar refreshKey={refreshKey} />
        </section>

        {/* Upload */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Enviar documentos
          </h2>
          <UploadZone onUploaded={refresh} />
        </section>

        {/* Reindex controls */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Reindexação
          </h2>
          <ReindexControls onReindexed={refresh} />
        </section>

        {/* RAG parameters */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Parâmetros RAG
          </h2>
          <RagParametersPanel />
        </section>

        {/* Document list */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]">
            Documentos
          </h2>
          <DocumentTable refreshKey={refreshKey} onChanged={refresh} />
        </section>
      </main>
    </div>
  )
}
