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
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap gap-2.5">
        <button
          type="button"
          disabled={loadingPending || loadingAll}
          onClick={() => reindex('pending').catch(console.error)}
          className="flex cursor-pointer items-center gap-1.5 rounded-[10px] border-[1.5px] border-[#2c4a86] dark:border-[#8596b9] bg-transparent px-4 py-[9px] text-[13.5px] font-semibold text-[#2c4a86] dark:text-[#8596b9] transition-colors hover:bg-[#e8edf7] dark:hover:bg-[#182236] disabled:cursor-not-allowed disabled:opacity-50"
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
            className="flex cursor-pointer items-center gap-1.5 rounded-[10px] border-[1.5px] border-[#c0392b] dark:border-[#e0685c] bg-transparent px-4 py-[9px] text-[13.5px] font-semibold text-[#c0392b] dark:text-[#e0685c] transition-colors hover:bg-[#fbeae7] dark:hover:bg-[#3a1f1c] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <AlertTriangle size={14} />Reindexação total
          </button>
        ) : (
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-sm text-[#c0392b] dark:text-[#e0685c]">
              Apaga todos os vetores. Confirmar?
            </span>
            <button
              type="button"
              disabled={loadingAll}
              onClick={() => { setConfirmAll(false); reindex('all').catch(console.error) }}
              className="flex cursor-pointer items-center gap-1.5 rounded-[9px] border-0 bg-[#c0392b] px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#a8321f] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingAll ? <Loader2 size={14} className="animate-spin" /> : null}
              Sim, reindexar
            </button>
            <button
              type="button"
              onClick={() => setConfirmAll(false)}
              className="cursor-pointer rounded-[9px] border border-[#e6e1d5] dark:border-[#33383f] bg-transparent px-3.5 py-2 text-sm text-[#6c7078] dark:text-[#9da2aa] transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a]"
            >
              Cancelar
            </button>
          </div>
        )}
      </div>

      {result && (
        <p className="text-sm text-[#1f9a5a] dark:text-[#4cbd82]">{result}</p>
      )}
      {error && (
        <p className="text-sm text-[#c0392b] dark:text-[#e0685c]">{error}</p>
      )}
    </div>
  )
}
