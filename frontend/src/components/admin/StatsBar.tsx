import { useEffect, useState } from 'react'
import { authFetch, API_BASE, type DocumentStats } from '../../lib/api'

interface Props {
  refreshKey?: number
}

export default function StatsBar({ refreshKey }: Props) {
  const [stats, setStats] = useState<DocumentStats | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    setError(false)
    authFetch(`${API_BASE}/documents/stats`)
      .then(res => {
        if (!res.ok) throw new Error('stats error')
        return res.json() as Promise<DocumentStats>
      })
      .then(setStats)
      .catch(() => setError(true))
  }, [refreshKey])

  if (error) {
    return (
      <p className="text-sm text-red-500 dark:text-red-400">
        Não foi possível carregar as estatísticas.
      </p>
    )
  }

  const cards: Array<{ label: string; value: number | string }> = stats
    ? [
        { label: 'Total', value: stats.total },
        { label: 'Ativos', value: stats.active },
        { label: 'Processando', value: stats.processing },
        { label: 'Erros', value: stats.error },
        { label: 'Chunks', value: stats.total_chunks.toLocaleString('pt-BR') },
      ]
    : []

  return (
    <div className="flex flex-wrap gap-3">
      {stats === null
        ? Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="h-16 w-32 animate-pulse rounded-lg bg-[#eee] dark:bg-[#3a3a3a]"
            />
          ))
        : cards.map(c => (
            <div
              key={c.label}
              className="flex flex-col items-center justify-center rounded-lg border border-[#ddd] dark:border-[#444] bg-[#fafafa] dark:bg-[#2d2d2d] px-5 py-3 min-w-[100px]"
            >
              <span className="text-xl font-semibold text-[#111] dark:text-[#e8e8e8]">
                {c.value}
              </span>
              <span className="text-xs text-[#777] dark:text-[#aaa]">{c.label}</span>
            </div>
          ))}
    </div>
  )
}
