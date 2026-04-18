import { useEffect, useState } from 'react'
import { Save, Loader2, CheckCircle2 } from 'lucide-react'
import { authFetch, API_BASE } from '../../lib/api'

interface RagConfig {
  id: number
  parent_chunk_tokens: number
  child_chunk_tokens: number
  search_top_k: number
  search_score_threshold: number
  reranker_top_k: number
  reranker_score_threshold: number
  updated_at: string
}

interface ValidationError {
  loc: (string | number)[]
  msg: string
  type: string
}

const FIELDS: {
  key: keyof RagConfig
  label: string
  min: number
  max: number
  step: number
}[] = [
  { key: 'parent_chunk_tokens', label: 'Parent chunk tokens', min: 64, max: 2048, step: 1 },
  { key: 'child_chunk_tokens', label: 'Child chunk tokens', min: 16, max: 512, step: 1 },
  { key: 'search_top_k', label: 'Search top-k', min: 1, max: 100, step: 1 },
  { key: 'search_score_threshold', label: 'Search score threshold', min: 0.0, max: 1.0, step: 0.01 },
  { key: 'reranker_top_k', label: 'Reranker top-k', min: 1, max: 100, step: 1 },
  { key: 'reranker_score_threshold', label: 'Reranker score threshold', min: 0.0, max: 1.0, step: 0.01 },
]

const FIELD_KEYS = new Set<string>(FIELDS.map(f => f.key))

export default function RagParametersPanel() {
  const [config, setConfig] = useState<RagConfig | null>(null)
  const [form, setForm] = useState<Partial<Record<keyof RagConfig, string>>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [globalError, setGlobalError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    authFetch(`${API_BASE}/admin/rag-parameters`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<RagConfig>
      })
      .then(data => {
        setConfig(data)
        const initial: Partial<Record<keyof RagConfig, string>> = {}
        for (const f of FIELDS) {
          initial[f.key] = String(data[f.key])
        }
        setForm(initial)
      })
      .catch(() => setGlobalError('Falha ao carregar parâmetros.'))
  }, [])

  const handleChange = (key: keyof RagConfig, value: string) => {
    setForm(prev => ({ ...prev, [key]: value }))
    setFieldErrors(prev => {
      const next = { ...prev }
      delete next[key]
      return next
    })
    setGlobalError(null)
    setSaved(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    setGlobalError(null)
    setSaving(true)
    setSaved(false)

    const body: Record<string, number> = {}
    for (const f of FIELDS) {
      body[f.key] = Number(form[f.key])
    }

    try {
      const res = await authFetch(`${API_BASE}/admin/rag-parameters`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (res.status === 422) {
        const json = (await res.json()) as { detail: ValidationError[] }
        const errors: Record<string, string> = {}
        const globalMessages: string[] = []
        for (const err of json.detail) {
          const fieldName = err.loc[err.loc.length - 1]
          if (typeof fieldName === 'string' && FIELD_KEYS.has(fieldName)) {
            errors[fieldName] = err.msg
          } else {
            globalMessages.push(err.msg)
          }
        }
        setFieldErrors(errors)
        if (globalMessages.length > 0) setGlobalError(globalMessages.join(' '))
        return
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const updated = (await res.json()) as RagConfig
      setConfig(updated)
      const next: Partial<Record<keyof RagConfig, string>> = {}
      for (const f of FIELDS) {
        next[f.key] = String(updated[f.key])
      }
      setForm(next)
      setSaved(true)
    } catch {
      setGlobalError('Falha ao salvar parâmetros.')
    } finally {
      setSaving(false)
    }
  }

  if (!config && !globalError) {
    return <p className="text-sm text-[#777] dark:text-[#aaa]">Carregando…</p>
  }

  if (globalError && !config) {
    return <p className="text-sm text-red-600 dark:text-red-400">{globalError}</p>
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {FIELDS.map(f => (
          <div key={f.key} className="flex flex-col gap-1">
            <label
              htmlFor={`rag-${f.key}`}
              className="text-sm font-medium text-[#333] dark:text-[#ccc]"
            >
              {f.label}
            </label>
            <input
              id={`rag-${f.key}`}
              type="number"
              min={f.min}
              max={f.max}
              step={f.step}
              value={form[f.key] ?? ''}
              onChange={e => handleChange(f.key, e.target.value)}
              className="rounded-lg border border-[#ccc] dark:border-[#555] bg-white dark:bg-[#2d2d2d] px-3 py-2 text-sm text-[#111] dark:text-[#e8e8e8] focus:outline-none focus:ring-2 focus:ring-[#0078d4]"
            />
            <span className="text-xs text-[#777] dark:text-[#999]">
              {f.min} – {f.max}
            </span>
            {fieldErrors[f.key] && (
              <span className="text-xs text-red-600 dark:text-red-400">
                {fieldErrors[f.key]}
              </span>
            )}
          </div>
        ))}
      </div>

      {globalError && (
        <p className="text-sm text-red-600 dark:text-red-400">{globalError}</p>
      )}

      <div className="flex items-center gap-4">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg border border-[#0078d4] bg-transparent px-4 py-2 text-sm text-[#0078d4] hover:bg-[#e3f2fd] dark:hover:bg-[#1a4a6e] disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
        >
          {saving ? (
            <><Loader2 size={14} className="animate-spin" />Salvando…</>
          ) : (
            <><Save size={14} />Salvar parâmetros</>
          )}
        </button>
        {saved && (
          <span className="text-sm text-green-700 dark:text-green-400 flex items-center gap-1 animate-fade-in">
            <CheckCircle2 size={14} />
            Parâmetros salvos com sucesso.
          </span>
        )}
      </div>

      {config && (
        <p className="text-xs text-[#999] dark:text-[#666]">
          Última atualização: {new Date(config.updated_at).toLocaleString('pt-BR')}
        </p>
      )}
    </form>
  )
}
