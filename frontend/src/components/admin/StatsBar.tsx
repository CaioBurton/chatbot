import { useEffect, useState } from 'react'
import { authFetch, API_BASE, type DocumentStats } from '../../lib/api'

interface Props {
  refreshKey?: number
}

export default function StatsBar({ refreshKey }: Props) {
  const [stats, setStats] = useState<DocumentStats | null>(null)
  const [error, setError] = useState(false)
  const [fetching, setFetching] = useState(false)

  useEffect(() => {
    setError(false)
    setFetching(true)
    authFetch(`${API_BASE}/documents/stats`)
      .then(res => {
        if (!res.ok) throw new Error('stats error')
        return res.json() as Promise<DocumentStats>
      })
      .then(setStats)
      .catch(() => setError(true))
      .finally(() => setFetching(false))
  }, [refreshKey])

  if (error) {
    return (
      <p className="text-sm text-[#c0392b] dark:text-[#e0685c]">
        Não foi possível carregar as estatísticas.
      </p>
    )
  }

  const cards: Array<{ label: string; value: number | string; className: string }> = stats
    ? [
        { label: 'Total', value: stats.total, className: 'text-[#1e2128] dark:text-[#eceae7]' },
        { label: 'Ativos', value: stats.active, className: 'text-[#1f9a5a] dark:text-[#4cbd82]' },
        { label: 'Processando', value: stats.processing, className: 'text-[#b6691e] dark:text-[#e0a05c]' },
        { label: 'Erros', value: stats.error, className: 'text-[#c0392b] dark:text-[#e0685c]' },
        { label: 'Chunks', value: stats.total_chunks.toLocaleString('pt-BR'), className: 'text-[#1e2128] dark:text-[#eceae7]' },
      ]
    : []

  return (
    <div className="relative grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {/* Subtle overlay spinner on background re-fetches (stats already loaded) */}
      {fetching && stats !== null && (
        <span className="absolute right-0 -top-5 animate-pulse text-[10px] text-[#a19e96] dark:text-[#6c717a]">
          atualizando…
        </span>
      )}
      {stats === null
        ? Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-[72px] animate-pulse rounded-[14px] bg-[#f2efe8] dark:bg-[#262b32]"
            />
          ))
        : cards.map(c => (
            <div
              key={c.label}
              className="flex flex-col gap-1 rounded-[14px] border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] p-4"
            >
              <span className={`font-serif text-[26px] font-semibold leading-none ${c.className}`}>
                {c.value}
              </span>
              <span className="text-xs text-[#6c7078] dark:text-[#9da2aa]">{c.label}</span>
            </div>
          ))}
    </div>
  )
}
