import { useState } from 'react'
import { RefreshCw, AlertTriangle, Loader2 } from 'lucide-react'
import { authFetch, API_BASE } from '../../lib/api'

interface Props {
  onReindexed: () => void
}

export default function ReindexControls({ onReindexed }: Props) {
  const [loadingPending, setLoadingPending] = useState(false)
  const [loadingAll, setLoadingAll] = useState(false)
  const [confirmAll, setConfirmAll] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reindex = async (scope: 'pending' | 'all') => {
    setResult(null)
    setError(null)
    const setter = scope === 'pending' ? setLoadingPending : setLoadingAll
    setter(true)
    try {
      const res = await authFetch(`${API_BASE}/documents/reindex-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as { queued: number }
      setResult(`${data.queued} documento(s) enfileirado(s).`)
      onReindexed()
    } catch {
      setError('Falha ao enfileirar reindexação.')
    } finally {
      setter(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={loadingPending || loadingAll}
          onClick={() => reindex('pending').catch(console.error)}
          className="rounded-lg border border-[#0078d4] bg-transparent px-4 py-2 text-sm text-[#0078d4] hover:bg-[#e3f2fd] dark:hover:bg-[#1a4a6e] disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
        >
          {loadingPending ? (
            <><Loader2 size={14} className="animate-spin" />Enfileirando…</>
          ) : (
            <><RefreshCw size={14} />Reindexar pendentes</>
          )}
        </button>

        {!confirmAll ? (
          <button
            type="button"
            disabled={loadingPending || loadingAll}
            onClick={() => setConfirmAll(true)}
            className="rounded-lg border border-red-500 bg-transparent px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
          >
            <AlertTriangle size={14} />Reindexação total
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-sm text-red-600 dark:text-red-400">
              Apaga todos os vetores. Confirmar?
            </span>
            <button
              type="button"
              disabled={loadingAll}
              onClick={() => { setConfirmAll(false); reindex('all').catch(console.error) }}
              className="rounded-lg border border-red-500 bg-red-500 px-3 py-1.5 text-sm text-white hover:bg-red-600 disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center gap-1.5 transition-colors"
            >
              {loadingAll ? <Loader2 size={14} className="animate-spin" /> : null}
              Sim, reindexar
            </button>
            <button
              type="button"
              onClick={() => setConfirmAll(false)}
              className="rounded-lg border border-gray-400 bg-transparent px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer transition-colors"
            >
              Cancelar
            </button>
          </div>
        )}
      </div>

      {result && (
        <p className="text-sm text-green-700 dark:text-green-400">{result}</p>
      )}
      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
    </div>
  )
}
