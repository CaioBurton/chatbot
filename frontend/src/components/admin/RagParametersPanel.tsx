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
  context_top_k: number
  hyde_enabled: boolean
  multiquery_enabled: boolean
  reranker_enabled: boolean
  contextual_compression_enabled: boolean
  parent_child_expansion_enabled: boolean
  llm_provider: 'local' | 'openai' | 'anthropic' | 'gemini'
  llm_model: string
  embedding_provider: 'local' | 'gemini'
  embedding_model: string
  child_chunk_overlap_tokens: number
  active_edital_cycle: string | null
  openai_api_key_configured: boolean
  anthropic_api_key_configured: boolean
  google_api_key_configured: boolean
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
  { key: 'context_top_k', label: 'Context top-k', min: 1, max: 50, step: 1 },
  { key: 'child_chunk_overlap_tokens', label: 'Child chunk overlap tokens', min: 0, max: 511, step: 1 },
]

const TOGGLES: { key: keyof RagConfig; label: string; description: string }[] = [
  {
    key: 'hyde_enabled',
    label: 'HyDE',
    description: 'Gera uma resposta hipotética para melhorar a busca semântica.',
  },
  {
    key: 'multiquery_enabled',
    label: 'Multi-query',
    description: 'Reformula a pergunta em múltiplas variações para ampliar a recuperação.',
  },
  {
    key: 'reranker_enabled',
    label: 'Reranker',
    description: 'Reordena os resultados usando um modelo cross-encoder de alta precisão.',
  },
  {
    key: 'contextual_compression_enabled',
    label: 'Compressão contextual',
    description: 'Extrai apenas os trechos mais relevantes de cada chunk antes de montar o contexto.',
  },
  {
    key: 'parent_child_expansion_enabled',
    label: 'Expansão pai-filho',
    description: 'Substitui chunks filhos pelo chunk pai completo para maior contexto.',
  },
]

const FIELD_KEYS = new Set<string>(FIELDS.map(f => f.key))

const PROVIDER_MODELS: Record<string, string[]> = {
  local: ['gemma3:12b', 'gemma3:4b', 'llama3.2:3b', 'mistral:7b'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229'],
  gemini: ['gemini-2.5-flash-preview-05-20', 'gemini-2.5-pro-preview-06-05', 'gemini-2.0-flash', 'gemini-1.5-pro'],
}

const EMBEDDING_PROVIDER_MODELS: Record<string, string[]> = {
  local: ['bge-m3'],
  gemini: ['gemini-embedding-001'],
}

export default function RagParametersPanel() {
  const [config, setConfig] = useState<RagConfig | null>(null)
  const [form, setForm] = useState<Partial<Record<keyof RagConfig, string>>>({})
  const [toggles, setToggles] = useState<Partial<Record<keyof RagConfig, boolean>>>({})
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [globalError, setGlobalError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [llmProvider, setLlmProvider] = useState<'local' | 'openai' | 'anthropic' | 'gemini'>('local')
  const [llmModel, setLlmModel] = useState<string>('gemma3:12b')
  const [embeddingProvider, setEmbeddingProvider] = useState<'local' | 'gemini'>('local')
  const [embeddingModel, setEmbeddingModel] = useState<string>('bge-m3')
  const [activeEditalCycle, setActiveEditalCycle] = useState<string>('')

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
        const initialToggles: Partial<Record<keyof RagConfig, boolean>> = {}
        for (const t of TOGGLES) {
          initialToggles[t.key] = data[t.key] as boolean
        }
        setToggles(initialToggles)
        setLlmProvider(data.llm_provider ?? 'local')
        setLlmModel(data.llm_model ?? 'gemma3:12b')
        setEmbeddingProvider(data.embedding_provider ?? 'local')
        setEmbeddingModel(data.embedding_model ?? 'bge-m3')
        setActiveEditalCycle(data.active_edital_cycle ?? '')
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

  const handleToggle = (key: keyof RagConfig) => {
    setToggles(prev => ({ ...prev, [key]: !prev[key] }))
    setGlobalError(null)
    setSaved(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    setGlobalError(null)
    setSaving(true)
    setSaved(false)

    const body: Record<string, number | boolean | string | null> = {}
    for (const f of FIELDS) {
      body[f.key] = Number(form[f.key])
    }
    for (const t of TOGGLES) {
      body[t.key] = toggles[t.key] ?? true
    }
    body['llm_provider'] = llmProvider
    body['llm_model'] = llmModel
    body['embedding_provider'] = embeddingProvider
    body['embedding_model'] = embeddingModel
    body['active_edital_cycle'] = activeEditalCycle.trim() || null

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
      const nextToggles: Partial<Record<keyof RagConfig, boolean>> = {}
      for (const t of TOGGLES) {
        nextToggles[t.key] = updated[t.key] as boolean
      }
      setToggles(nextToggles)
      setLlmProvider(updated.llm_provider ?? 'local')
      setLlmModel(updated.llm_model ?? 'gemma3:12b')
      setEmbeddingProvider(updated.embedding_provider ?? 'local')
      setEmbeddingModel(updated.embedding_model ?? 'bge-m3')
      setActiveEditalCycle(updated.active_edital_cycle ?? '')
      setSaved(true)
    } catch {
      setGlobalError('Falha ao salvar parâmetros.')
    } finally {
      setSaving(false)
    }
  }

  if (!config && !globalError) {
    return <p className="text-sm text-[#a19e96] dark:text-[#6c717a]">Carregando…</p>
  }

  if (globalError && !config) {
    return <p className="text-sm text-[#c0392b] dark:text-[#e0685c]">{globalError}</p>
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-[26px]">

      {/* LLM Provider */}
      <div className="flex flex-col gap-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wide text-[#6c7078] dark:text-[#9da2aa]">
          Modelo de linguagem
        </h3>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {(['local', 'openai', 'anthropic', 'gemini'] as const).map(p => {
            const labels: Record<string, string> = { local: 'Local (Ollama)', openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'Google Gemini' }
            const descs: Record<string, string> = {
              local: 'Executa o modelo localmente via Ollama, sem envio de dados externos.',
              openai: 'Usa a API da OpenAI (GPT). Requer OPENAI_API_KEY configurada no servidor.',
              anthropic: 'Usa a API da Anthropic (Claude). Requer ANTHROPIC_API_KEY configurada no servidor.',
              gemini: 'Usa a API do Google Gemini. Requer GOOGLE_API_KEY configurada no servidor.',
            }
            const apiKeyOk = p === 'openai'
              ? config?.openai_api_key_configured
              : p === 'anthropic'
              ? config?.anthropic_api_key_configured
              : p === 'gemini'
              ? config?.google_api_key_configured
              : true
            const active = llmProvider === p
            return (
              <button
                key={p}
                type="button"
                onClick={() => {
                  setLlmProvider(p)
                  setLlmModel(PROVIDER_MODELS[p][0])
                  setSaved(false)
                }}
                className={`flex cursor-pointer flex-col gap-[5px] rounded-xl border-[1.5px] px-[15px] py-[13px] text-left transition-colors ${
                  active
                    ? 'border-[#2c4a86] dark:border-[#8596b9] bg-[#e8edf7] dark:bg-[#182236]'
                    : 'border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126]'
                }`}
              >
                <span className={`text-[13.5px] font-semibold ${
                  active ? 'text-[#2c4a86] dark:text-[#8596b9]' : 'text-[#1e2128] dark:text-[#eceae7]'
                }`}>{labels[p]}</span>
                <span className="text-[11.5px] leading-tight text-[#6c7078] dark:text-[#9da2aa]">{descs[p]}</span>
                {p !== 'local' && (
                  <span className={`mt-1 text-[11px] font-semibold ${
                    apiKeyOk ? 'text-[#1f9a5a] dark:text-[#4cbd82]' : 'text-[#b6691e] dark:text-[#e0a05c]'
                  }`}>
                    {apiKeyOk ? '✓ API key configurada' : '⚠ API key não configurada'}
                  </span>
                )}
              </button>
            )
          })}
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-[#1e2128] dark:text-[#eceae7]">
            Modelo
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              list="llm-model-suggestions"
              value={llmModel}
              onChange={e => { setLlmModel(e.target.value); setSaved(false) }}
              className="min-w-[180px] flex-1 rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-3 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:ring-2 focus:ring-[#2c4a86] dark:focus:ring-[#8596b9]"
              placeholder="Nome do modelo"
            />
            <datalist id="llm-model-suggestions">
              {PROVIDER_MODELS[llmProvider].map(m => <option key={m} value={m} />)}
            </datalist>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            {PROVIDER_MODELS[llmProvider].map(m => (
              <button
                key={m}
                type="button"
                onClick={() => { setLlmModel(m); setSaved(false) }}
                className={`cursor-pointer rounded-full border px-3 py-0.5 text-xs transition-colors ${
                  llmModel === m
                    ? 'border-[#2c4a86] dark:border-[#8596b9] bg-[#2c4a86] dark:bg-[#8596b9] text-white dark:text-[#101317]'
                    : 'border-[#e6e1d5] dark:border-[#33383f] text-[#6c7078] dark:text-[#9da2aa] hover:border-[#2c4a86] hover:text-[#2c4a86] dark:hover:border-[#8596b9] dark:hover:text-[#8596b9]'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Embedding Provider */}
      <div className="flex flex-col gap-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wide text-[#6c7078] dark:text-[#9da2aa]">
          Modelo de embedding
        </h3>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {(['local', 'gemini'] as const).map(p => {
            const labels: Record<string, string> = { local: 'Local (Ollama bge-m3)', gemini: 'Google Gemini' }
            const descs: Record<string, string> = {
              local: 'Gera embeddings localmente via Ollama (bge-m3), sem envio de dados externos.',
              gemini: 'Usa a API de embeddings do Google Gemini. Requer GOOGLE_API_KEY configurada no servidor.',
            }
            const apiKeyOk = p === 'gemini' ? config?.google_api_key_configured : true
            const active = embeddingProvider === p
            return (
              <button
                key={p}
                type="button"
                onClick={() => {
                  setEmbeddingProvider(p)
                  setEmbeddingModel(EMBEDDING_PROVIDER_MODELS[p][0])
                  setSaved(false)
                }}
                className={`flex cursor-pointer flex-col gap-[5px] rounded-xl border-[1.5px] px-[15px] py-[13px] text-left transition-colors ${
                  active
                    ? 'border-[#2c4a86] dark:border-[#8596b9] bg-[#e8edf7] dark:bg-[#182236]'
                    : 'border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126]'
                }`}
              >
                <span className={`text-[13.5px] font-semibold ${
                  active ? 'text-[#2c4a86] dark:text-[#8596b9]' : 'text-[#1e2128] dark:text-[#eceae7]'
                }`}>{labels[p]}</span>
                <span className="text-[11.5px] leading-tight text-[#6c7078] dark:text-[#9da2aa]">{descs[p]}</span>
                {p !== 'local' && (
                  <span className={`mt-1 text-[11px] font-semibold ${
                    apiKeyOk ? 'text-[#1f9a5a] dark:text-[#4cbd82]' : 'text-[#b6691e] dark:text-[#e0a05c]'
                  }`}>
                    {apiKeyOk ? '✓ API key configurada' : '⚠ API key não configurada'}
                  </span>
                )}
              </button>
            )
          })}
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-sm font-medium text-[#1e2128] dark:text-[#eceae7]">
            Modelo
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              list="embedding-model-suggestions"
              value={embeddingModel}
              onChange={e => { setEmbeddingModel(e.target.value); setSaved(false) }}
              className="min-w-[180px] flex-1 rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-3 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:ring-2 focus:ring-[#2c4a86] dark:focus:ring-[#8596b9]"
              placeholder="Nome do modelo"
            />
            <datalist id="embedding-model-suggestions">
              {EMBEDDING_PROVIDER_MODELS[embeddingProvider].map(m => <option key={m} value={m} />)}
            </datalist>
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            {EMBEDDING_PROVIDER_MODELS[embeddingProvider].map(m => (
              <button
                key={m}
                type="button"
                onClick={() => { setEmbeddingModel(m); setSaved(false) }}
                className={`cursor-pointer rounded-full border px-3 py-0.5 text-xs transition-colors ${
                  embeddingModel === m
                    ? 'border-[#2c4a86] dark:border-[#8596b9] bg-[#2c4a86] dark:bg-[#8596b9] text-white dark:text-[#101317]'
                    : 'border-[#e6e1d5] dark:border-[#33383f] text-[#6c7078] dark:text-[#9da2aa] hover:border-[#2c4a86] hover:text-[#2c4a86] dark:hover:border-[#8596b9] dark:hover:text-[#8596b9]'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs leading-tight text-[#b6691e] dark:text-[#e0a05c]">
          ⚠ Ao alterar o modelo de embedding, os documentos já indexados ficam
          incompatíveis com o novo modelo. Após salvar, execute uma "Reindexação total"
          na aba de documentos para reprocessar toda a base.
        </p>
      </div>

      {/* Toggles */}
      <div className="flex flex-col gap-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wide text-[#6c7078] dark:text-[#9da2aa]">
          Técnicas de melhoria do RAG
        </h3>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {TOGGLES.map(t => {
            const enabled = toggles[t.key] ?? true
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => handleToggle(t.key)}
                className={`flex cursor-pointer items-start gap-[11px] rounded-xl border-[1.5px] px-[15px] py-[13px] text-left transition-colors ${
                  enabled
                    ? 'border-[#2c4a86] dark:border-[#8596b9] bg-[#e8edf7] dark:bg-[#182236]'
                    : 'border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126]'
                }`}
              >
                {/* Toggle indicator */}
                <span
                  className={`relative mt-0.5 h-[19px] w-[34px] shrink-0 rounded-full transition-colors ${
                    enabled ? 'bg-[#2c4a86] dark:bg-[#8596b9]' : 'bg-[#e6e1d5] dark:bg-[#33383f]'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-[15px] w-[15px] rounded-full bg-white shadow transition-transform ${
                      enabled ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className={`text-sm font-medium ${enabled ? 'text-[#2c4a86] dark:text-[#8596b9]' : 'text-[#1e2128] dark:text-[#eceae7]'}`}>
                    {t.label}
                  </span>
                  <span className="text-[11.5px] leading-snug text-[#6c7078] dark:text-[#9da2aa]">
                    {t.description}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Numeric parameters */}
      <div className="flex flex-col gap-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wide text-[#6c7078] dark:text-[#9da2aa]">
          Parâmetros numéricos
        </h3>
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          {FIELDS.map(f => (
            <div key={f.key} className="flex flex-col gap-1">
              <label
                htmlFor={`rag-${f.key}`}
                className="text-[12.5px] font-semibold text-[#1e2128] dark:text-[#eceae7]"
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
                className="rounded-[9px] border-[1.5px] border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-[11px] py-2 text-[13px] text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
              />
              <span className="text-[11px] text-[#a19e96] dark:text-[#6c717a]">
                {f.min} – {f.max}
              </span>
              {fieldErrors[f.key] && (
                <span className="text-xs text-[#c0392b] dark:text-[#e0685c]">
                  {fieldErrors[f.key]}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Ciclo do edital ativo */}
      <div className="flex flex-col gap-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wide text-[#6c7078] dark:text-[#9da2aa]">
          Ciclo do edital
        </h3>
        <div className="flex flex-col gap-1">
          <label htmlFor="rag-active-edital-cycle" className="text-[12.5px] font-semibold text-[#1e2128] dark:text-[#eceae7]">
            Ciclo ativo (opcional)
          </label>
          <input
            id="rag-active-edital-cycle"
            type="text"
            value={activeEditalCycle}
            onChange={e => { setActiveEditalCycle(e.target.value); setSaved(false) }}
            placeholder="ex.: 2025/2026 (deixe vazio para não filtrar)"
            className="max-w-xs rounded-[9px] border-[1.5px] border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-[11px] py-2 text-[13px] text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
          />
          <span className="text-[11px] text-[#a19e96] dark:text-[#6c717a]">
            Quando definido, as injeções de contexto pinadas do RAG ignoram chunks de outros ciclos.
            Documentos sem ciclo definido continuam elegíveis.
          </span>
        </div>
      </div>

      {globalError && (
        <p className="text-sm text-[#c0392b] dark:text-[#e0685c]">{globalError}</p>
      )}

      <div className="flex items-center gap-3.5">
        <button
          type="submit"
          disabled={saving}
          className="flex cursor-pointer items-center gap-1.5 rounded-[10px] border-[1.5px] border-[#2c4a86] dark:border-[#8596b9] bg-transparent px-[18px] py-[9px] text-[13.5px] font-semibold text-[#2c4a86] dark:text-[#8596b9] transition-colors hover:bg-[#e8edf7] dark:hover:bg-[#182236] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? (
            <><Loader2 size={14} className="animate-spin" />Salvando…</>
          ) : (
            <><Save size={14} />Salvar parâmetros</>
          )}
        </button>
        {saved && (
          <span className="flex animate-fade-in items-center gap-1 text-sm text-[#1f9a5a] dark:text-[#4cbd82]">
            <CheckCircle2 size={14} />
            Parâmetros salvos com sucesso.
          </span>
        )}
      </div>

      {config && (
        <p className="text-xs text-[#a19e96] dark:text-[#6c717a]">
          Última atualização: {new Date(config.updated_at).toLocaleString('pt-BR')}
        </p>
      )}
    </form>
  )
}
