import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Trash2, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'
import { authFetch, API_BASE, type DocumentListItem } from '../../lib/api'

const PAGE_SIZE = 20

interface Props {
  refreshKey?: number
  onChanged: () => void
}

const STATUS_LABEL: Record<string, string> = {
  active: 'ativo',
  processing: 'processando',
  error: 'erro',
  uploaded: 'enviado',
}

const STATUS_BADGE: Record<string, string> = {
  active:     'bg-[#e3f6ec] text-[#1f9a5a] dark:bg-[#173226] dark:text-[#4cbd82]',
  processing: 'bg-[#fbeee0] text-[#b6691e] dark:bg-[#3a2c1a] dark:text-[#e0a05c]',
  error:      'bg-[#fbeae7] text-[#c0392b] dark:bg-[#3a1f1c] dark:text-[#e0685c]',
  uploaded:   'bg-[#e8edf7] text-[#2c4a86] dark:bg-[#182236] dark:text-[#8596b9]',
}

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_BADGE[status] ?? 'bg-[#f2efe8] text-[#6c7078] dark:bg-[#262b32] dark:text-[#9da2aa]'
  return (
    <span className={`rounded-full px-[9px] py-0.5 text-[11px] font-semibold ${cls}`}>
      {STATUS_LABEL[status] ?? status}
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
      <p className="text-sm text-[#c0392b] dark:text-[#e0685c]">
        Não foi possível carregar os documentos.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-[14px] border border-[#e6e1d5] dark:border-[#33383f]">
        <table className="min-w-full text-[13.5px] text-[#1e2128] dark:text-[#eceae7]">
          <thead>
            <tr className="bg-[#f2efe8] dark:bg-[#262b32]">
              {['Nome', 'Tipo', 'Status', 'Chunks', 'Data', 'Ações'].map(h => (
                <th
                  key={h}
                  className="px-3.5 py-2.5 text-left text-[11px] font-bold uppercase tracking-wide text-[#a19e96] dark:text-[#6c717a]"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[#a19e96] dark:text-[#6c717a]">
                  Carregando…
                </td>
              </tr>
            )}
            {!loading && docs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[#a19e96] dark:text-[#6c717a]">
                  Nenhum documento encontrado.
                </td>
              </tr>
            )}
            {!loading &&
              docs.map(doc => (
                <tr
                  key={doc.id}
                  className="border-t border-[#e6e1d5] dark:border-[#33383f] hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] transition-colors"
                >
                  <td className="max-w-[240px] overflow-hidden text-ellipsis whitespace-nowrap px-3.5 py-2.5">
                    <span className="inline-flex items-center gap-1.5">
                      {doc.display_name}
                      {doc.source_url && (
                        <a
                          href={doc.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={doc.source_url}
                          className="shrink-0 text-[#2c4a86] hover:text-[#20396a] dark:text-[#8596b9] dark:hover:text-[#abb7cf]"
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                    </span>
                  </td>
                  <td className="px-3.5 py-2.5 text-xs text-[#a19e96] dark:text-[#6c717a]">
                    {doc.file_type}
                  </td>
                  <td className="px-3.5 py-2.5">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="px-3.5 py-2.5 tabular-nums text-[#6c7078] dark:text-[#9da2aa]">
                    {doc.total_chunks ?? '—'}
                  </td>
                  <td className="whitespace-nowrap px-3.5 py-2.5 text-xs text-[#a19e96] dark:text-[#6c717a]">
                    {formatDate(doc.created_at)}
                  </td>
                  <td className="px-3.5 py-2.5">
                    <div className="flex gap-1.5">
                      {(doc.status === 'error' || doc.status === 'uploaded') && (
                        <button
                          type="button"
                          onClick={() => handleReindex(doc)}
                          className="flex cursor-pointer items-center gap-1 rounded-[7px] border border-[#2c4a86] dark:border-[#8596b9] px-2 py-[3px] text-[11.5px] text-[#2c4a86] dark:text-[#8596b9] transition-colors hover:bg-[#e8edf7] dark:hover:bg-[#182236]"
                        >
                          <RefreshCw size={11} />
                          Reindexar
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleDelete(doc)}
                        className="flex cursor-pointer items-center gap-1 rounded-[7px] border border-[#c0392b] dark:border-[#e0685c] px-2 py-[3px] text-[11.5px] text-[#c0392b] dark:text-[#e0685c] transition-colors hover:bg-[#fbeae7] dark:hover:bg-[#3a1f1c]"
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
      <div className="flex items-center gap-3 text-sm text-[#6c7078] dark:text-[#9da2aa]">
        <button
          type="button"
          disabled={page === 0 || loading}
          onClick={() => changePage(-1)}
          className="flex cursor-pointer items-center gap-1 rounded-lg border border-[#e6e1d5] dark:border-[#33383f] px-3 py-1 transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft size={14} />
          Anterior
        </button>
        <span>Página {page + 1}</span>
        <button
          type="button"
          disabled={!hasMore || loading}
          onClick={() => changePage(1)}
          className="flex cursor-pointer items-center gap-1 rounded-lg border border-[#e6e1d5] dark:border-[#33383f] px-3 py-1 transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Próxima
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}
