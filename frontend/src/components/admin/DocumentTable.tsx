import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, Trash2, Pencil, ChevronLeft, ChevronRight, ExternalLink, Search, X } from 'lucide-react'
import { authFetch, API_BASE, type DocumentListItem } from '../../lib/api'
import EditMetadataModal from './EditMetadataModal'

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const DEFAULT_PAGE_SIZE = 20

const DOC_TYPE_FILTER_OPTIONS = [
  { value: '',          label: 'Todos os tipos' },
  { value: 'edital',    label: 'Edital' },
  { value: 'aditivo',   label: 'Aditivo' },
  { value: 'resolucao', label: 'Resolução' },
  { value: 'tutorial',  label: 'Tutorial' },
  { value: 'portaria',  label: 'Portaria' },
  { value: 'relatorio', label: 'Relatório' },
]

const STATUS_FILTER_OPTIONS = [
  { value: '',           label: 'Todos os status' },
  { value: 'active',     label: 'Ativo' },
  { value: 'processing', label: 'Processando' },
  { value: 'error',      label: 'Erro' },
  { value: 'uploaded',   label: 'Enviado' },
]

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
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [editing, setEditing] = useState<DocumentListItem | null>(null)
  const [editalOptions, setEditalOptions] = useState<string[]>([])
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  // Debounce free-text search so it doesn't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => clearTimeout(t)
  }, [searchInput])

  // `silent` is used for the periodic background auto-refresh: it keeps the
  // current rows on screen (no loading skeleton) and swallows transient
  // errors instead of blanking the table, so the table doesn't flash every
  // time the timer ticks.
  const load = useCallback(
    (pageIndex: number, size: number, opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false
      if (!silent) {
        setLoading(true)
        setError(false)
      }
      const skip = pageIndex * size
      const params = new URLSearchParams({ skip: String(skip), limit: String(size + 1) })
      if (typeFilter) params.set('doc_type', typeFilter)
      if (statusFilter) params.set('doc_status', statusFilter)
      if (search) params.set('q', search)
      authFetch(`${API_BASE}/documents?${params.toString()}`)
        .then(res => {
          if (!res.ok) throw new Error('list error')
          return res.json() as Promise<DocumentListItem[]>
        })
        .then(data => {
          setHasMore(data.length > size)
          setDocs(data.slice(0, size))
        })
        .catch(() => {
          if (!silent) setError(true)
        })
        .finally(() => {
          if (!silent) setLoading(false)
        })
    },
    [typeFilter, statusFilter, search],
  )

  // Filters/page size changed -> start over from the first page.
  useEffect(() => {
    setPage(0)
    load(0, pageSize)
  }, [load, pageSize])

  // refreshKey changes on a timer (auto-refresh) or after an action (upload,
  // delete, reindex). Reload the page the user is currently on, silently, so
  // it neither jumps back to page 1 nor flashes a loading/error state over
  // rows that are still valid — skip the very first run since the effect
  // above already loads page 0 on mount.
  const skipNextRefresh = useRef(true)
  useEffect(() => {
    if (skipNextRefresh.current) {
      skipNextRefresh.current = false
      return
    }
    load(page, pageSize, { silent: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  useEffect(() => {
    authFetch(`${API_BASE}/documents?doc_type=edital&limit=100`)
      .then(res => (res.ok ? (res.json() as Promise<DocumentListItem[]>) : []))
      .then(data => setEditalOptions(data.map(d => d.display_name)))
      .catch(() => {})
  }, [refreshKey])

  const changePage = (delta: number) => {
    const next = page + delta
    setPage(next)
    load(next, pageSize)
  }

  const changePageSize = (size: number) => {
    setPageSize(size)
  }

  const handleDelete = (doc: DocumentListItem) => {
    if (!window.confirm(`Excluir "${doc.display_name}"? Esta ação é irreversível.`)) return
    authFetch(`${API_BASE}/documents/${encodeURIComponent(doc.id)}`, { method: 'DELETE' })
      .then(res => {
        if (!res.ok) throw new Error('delete error')
        onChanged()
        load(page, pageSize)
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
        load(page, pageSize)
      })
      .catch(() => alert('Falha ao reindexar documento.'))
  }

  const handleUpdateMetadata = (docType: string, editalRef: string, editalCycle: string) => {
    const doc = editing
    if (!doc) return
    authFetch(`${API_BASE}/documents/${encodeURIComponent(doc.id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_type: docType,
        edital_ref: editalRef || null,
        edital_cycle: editalCycle || null,
      }),
    })
      .then(res => {
        if (!res.ok) throw new Error('update error')
        setEditing(null)
        onChanged()
        load(page, pageSize)
      })
      .catch(() => alert('Falha ao atualizar classificação do documento.'))
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
      {/* Search + filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#a19e96] dark:text-[#6c717a]" />
          <input
            type="text"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Buscar por nome do documento…"
            className="w-full rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] py-2 pl-8 pr-8 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => setSearchInput('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer text-[#a19e96] hover:text-[#1e2128] dark:text-[#6c717a] dark:hover:text-[#eceae7]"
            >
              <X size={13} />
            </button>
          )}
        </div>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-2.5 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
        >
          {DOC_TYPE_FILTER_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-2.5 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
        >
          {STATUS_FILTER_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

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
                  {search || typeFilter || statusFilter
                    ? 'Nenhum documento corresponde aos filtros.'
                    : 'Nenhum documento encontrado.'}
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
                      {doc.status !== 'processing' && (
                        <button
                          type="button"
                          onClick={() => setEditing(doc)}
                          className="flex cursor-pointer items-center gap-1 rounded-[7px] border border-[#6c7078] dark:border-[#9da2aa] px-2 py-[3px] text-[11.5px] text-[#6c7078] dark:text-[#9da2aa] transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a]"
                        >
                          <Pencil size={11} />
                          Editar
                        </button>
                      )}
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
      <div className="flex items-center justify-between gap-3 text-sm text-[#6c7078] dark:text-[#9da2aa]">
        <div className="flex items-center gap-3">
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
        <label className="flex items-center gap-2">
          Itens por página
          <select
            value={pageSize}
            disabled={loading}
            onChange={e => changePageSize(Number(e.target.value))}
            className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-2 py-1 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {PAGE_SIZE_OPTIONS.map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
      </div>

      {editing && (
        <EditMetadataModal
          doc={editing}
          editalOptions={editalOptions}
          onConfirm={handleUpdateMetadata}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  )
}
