import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Trash2, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'
import { authFetch, API_BASE, type DocumentListItem } from '../../lib/api'

const PAGE_SIZE = 20

interface Props {
  refreshKey?: number
  onChanged: () => void
}

const STATUS_BADGE: Record<string, string> = {
  active:     'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  processing: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  error:      'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  uploaded:   'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
}

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_BADGE[status] ?? 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

function formatDate(iso: string): string {
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

export default function DocumentTable({ refreshKey, onChanged }: Props) {
  const [docs, setDocs] = useState<DocumentListItem[]>([])
  const [page, setPage] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const load = useCallback(
    (pageIndex: number) => {
      setLoading(true)
      setError(false)
      const skip = pageIndex * PAGE_SIZE
      authFetch(`${API_BASE}/documents?skip=${skip}&limit=${PAGE_SIZE + 1}`)
        .then(res => {
          if (!res.ok) throw new Error('list error')
          return res.json() as Promise<DocumentListItem[]>
        })
        .then(data => {
          setHasMore(data.length > PAGE_SIZE)
          setDocs(data.slice(0, PAGE_SIZE))
        })
        .catch(() => setError(true))
        .finally(() => setLoading(false))
    },
    [],
  )

  useEffect(() => {
    setPage(0)
    load(0)
  }, [refreshKey, load])

  const changePage = (delta: number) => {
    const next = page + delta
    setPage(next)
    load(next)
  }

  const handleDelete = (doc: DocumentListItem) => {
    if (!window.confirm(`Excluir "${doc.display_name}"? Esta ação é irreversível.`)) return
    authFetch(`${API_BASE}/documents/${encodeURIComponent(doc.id)}`, { method: 'DELETE' })
      .then(res => {
        if (!res.ok) throw new Error('delete error')
        onChanged()
        load(page)
      })
      .catch(() => alert('Falha ao excluir documento.'))
  }

  const handleReindex = (doc: DocumentListItem) => {
    authFetch(`${API_BASE}/documents/${encodeURIComponent(doc.id)}/reindex`, {
      method: 'POST',
    })
      .then(res => {
        if (!res.ok) throw new Error('reindex error')
        onChanged()
        load(page)
      })
      .catch(() => alert('Falha ao reindexar documento.'))
  }

  if (error) {
    return (
      <p className="text-sm text-red-500 dark:text-red-400">
        Não foi possível carregar os documentos.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-xl border border-[#ddd] dark:border-[#444]">
        <table className="min-w-full text-sm text-[#111] dark:text-[#e8e8e8]">
          <thead>
            <tr className="border-b border-[#ddd] dark:border-[#444] bg-[#f5f5f5] dark:bg-[#2a2a2a]">
              {['Nome', 'Tipo', 'Status', 'Chunks', 'Data', 'Ações'].map(h => (
                <th
                  key={h}
                  className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[#555] dark:text-[#aaa]"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[#777] dark:text-[#aaa]">
                  Carregando…
                </td>
              </tr>
            )}
            {!loading && docs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[#777] dark:text-[#aaa]">
                  Nenhum documento encontrado.
                </td>
              </tr>
            )}
            {!loading &&
              docs.map(doc => (
                <tr
                  key={doc.id}
                  className="border-b border-[#eee] dark:border-[#383838] last:border-0 hover:bg-[#f9f9f9] dark:hover:bg-[#333]"
                >
                  <td className="max-w-[240px] overflow-hidden text-ellipsis whitespace-nowrap px-4 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      {doc.display_name}
                      {doc.source_url && (
                        <a
                          href={doc.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={doc.source_url}
                          className="text-[#0078d4] hover:text-[#005a9e] shrink-0"
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-[#777] dark:text-[#aaa]">
                    {doc.file_type}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {doc.total_chunks ?? '—'}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap text-xs text-[#777] dark:text-[#aaa]">
                    {formatDate(doc.created_at)}
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex gap-2">
                      {(doc.status === 'error' || doc.status === 'uploaded') && (
                        <button
                          type="button"
                          onClick={() => handleReindex(doc)}
                          className="rounded border border-[#0078d4] px-2 py-0.5 text-xs text-[#0078d4] hover:bg-[#e3f2fd] dark:hover:bg-[#1a4a6e] cursor-pointer flex items-center gap-1 transition-colors"
                        >
                          <RefreshCw size={11} />
                          Reindexar
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDelete(doc)}
                        className="rounded border border-red-400 px-2 py-0.5 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 cursor-pointer flex items-center gap-1 transition-colors"
                      >
                        <Trash2 size={11} />
                        Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center gap-3 text-sm text-[#555] dark:text-[#aaa]">
        <button
          type="button"
          disabled={page === 0 || loading}
          onClick={() => changePage(-1)}
          className="rounded border border-[#ddd] dark:border-[#444] px-3 py-1 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed hover:bg-[#f5f5f5] dark:hover:bg-[#333] flex items-center gap-1 transition-colors"
        >
          <ChevronLeft size={14} />
          Anterior
        </button>
        <span>Página {page + 1}</span>
        <button
          type="button"
          disabled={!hasMore || loading}
          onClick={() => changePage(1)}
          className="rounded border border-[#ddd] dark:border-[#444] px-3 py-1 disabled:opacity-40 cursor-pointer disabled:cursor-not-allowed hover:bg-[#f5f5f5] dark:hover:bg-[#333] flex items-center gap-1 transition-colors"
        >
          Próxima
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}
