import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import type { DocumentListItem } from '../../lib/api'

const DOC_TYPE_OPTIONS = [
  { value: 'edital',    label: 'Edital' },
  { value: 'aditivo',   label: 'Aditivo' },
  { value: 'resolucao', label: 'Resolução' },
  { value: 'tutorial',  label: 'Tutorial' },
  { value: 'portaria',  label: 'Portaria' },
  { value: 'relatorio', label: 'Relatório' },
]

interface Props {
  doc: DocumentListItem
  onConfirm: (docType: string, editalRef: string, editalCycle: string) => void
  onCancel: () => void
}

export default function EditMetadataModal({ doc, onConfirm, onCancel }: Props) {
  const [docType, setDocType] = useState(doc.doc_type)
  const [editalRef, setEditalRef] = useState(doc.edital_ref ?? '')
  const [editalCycle, setEditalCycle] = useState(doc.edital_cycle ?? '')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onConfirm(docType, editalRef.trim(), editalCycle.trim())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(25,20,12,0.45)] dark:bg-[rgba(0,0,0,0.6)] px-4">
      <div className="w-full max-w-md rounded-[16px] border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#1e2128] dark:text-[#eceae7]">
            Editar classificação
          </h3>
          <button
            type="button"
            onClick={onCancel}
            className="cursor-pointer text-[#a19e96] hover:text-[#1e2128] dark:text-[#6c717a] dark:hover:text-[#eceae7]"
          >
            <X size={16} />
          </button>
        </div>

        <p className="mb-4 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[#6c7078] dark:text-[#9da2aa]">
          Documento: <span className="font-medium text-[#1e2128] dark:text-[#eceae7]">{doc.display_name}</span>
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs text-[#6c7078] dark:text-[#9da2aa]">
            Tipo do documento
            <select
              value={docType}
              onChange={e => setDocType(e.target.value)}
              className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-3 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
            >
              {DOC_TYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>

          {docType === 'aditivo' && (
            <label className="flex flex-col gap-1 text-xs text-[#6c7078] dark:text-[#9da2aa]">
              Edital de referência (opcional)
              <input
                type="text"
                value={editalRef}
                onChange={e => setEditalRef(e.target.value)}
                placeholder="Ex.: Edital PIBIC 2025/2026"
                className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-3 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
              />
            </label>
          )}

          {(docType === 'edital' || docType === 'aditivo') && (
            <label className="flex flex-col gap-1 text-xs text-[#6c7078] dark:text-[#9da2aa]">
              Ciclo do edital (opcional)
              <input
                type="text"
                value={editalCycle}
                onChange={e => setEditalCycle(e.target.value)}
                placeholder="Ex.: 2025/2026"
                className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-3 py-2 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
              />
            </label>
          )}

          <p className="text-xs text-[#a19e96] dark:text-[#6c717a]">
            Salvar reprocessa o documento para que os chunks reflitam a nova classificação.
          </p>

          <div className="mt-1 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="cursor-pointer rounded-lg border border-[#e6e1d5] dark:border-[#33383f] px-3 py-1.5 text-sm text-[#6c7078] dark:text-[#9da2aa] transition-colors hover:bg-[#eae6dc] dark:hover:bg-[#2c313a]"
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="cursor-pointer rounded-lg bg-[#2c4a86] px-3 py-1.5 text-sm text-white transition-colors hover:bg-[#20396a]"
            >
              Salvar e reindexar
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
