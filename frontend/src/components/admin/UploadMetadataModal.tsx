import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'

interface Props {
  fileName: string
  remaining: number
  onConfirm: (displayName: string, sourceUrl: string) => void
  onCancel: () => void
}

export default function UploadMetadataModal({ fileName, remaining, onConfirm, onCancel }: Props) {
  const [displayName, setDisplayName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    onConfirm(displayName.trim(), sourceUrl.trim())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-md rounded-xl border border-[#ddd] dark:border-[#444] bg-white dark:bg-[#1e1e1e] p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#111] dark:text-[#e8e8e8]">
            Detalhes do documento
          </h3>
          <button
            type="button"
            onClick={onCancel}
            className="text-[#777] hover:text-[#111] dark:text-[#aaa] dark:hover:text-[#e8e8e8] cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        <p className="mb-4 overflow-hidden text-ellipsis whitespace-nowrap text-xs text-[#555] dark:text-[#aaa]">
          Arquivo: <span className="font-medium text-[#111] dark:text-[#e8e8e8]">{fileName}</span>
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-xs text-[#555] dark:text-[#aaa]">
            Nome do documento
            <input
              type="text"
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder={fileName}
              autoFocus
              className="rounded-lg border border-[#ccc] dark:border-[#555] bg-[#fafafa] dark:bg-[#2d2d2d] px-3 py-2 text-sm text-[#111] dark:text-[#e8e8e8] outline-none focus:border-[#0078d4]"
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-[#555] dark:text-[#aaa]">
            Link do documento (opcional)
            <input
              type="url"
              value={sourceUrl}
              onChange={e => setSourceUrl(e.target.value)}
              placeholder="https://..."
              className="rounded-lg border border-[#ccc] dark:border-[#555] bg-[#fafafa] dark:bg-[#2d2d2d] px-3 py-2 text-sm text-[#111] dark:text-[#e8e8e8] outline-none focus:border-[#0078d4]"
            />
          </label>

          <p className="text-xs text-[#888] dark:text-[#666]">
            Se o nome não for informado, será usado o nome do arquivo.
            {remaining > 0 && ` ${remaining} arquivo(s) restante(s) na fila.`}
          </p>

          <div className="mt-1 flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg border border-[#ccc] dark:border-[#555] px-3 py-1.5 text-sm text-[#555] dark:text-[#aaa] hover:bg-[#f5f5f5] dark:hover:bg-[#333] cursor-pointer transition-colors"
            >
              Cancelar envio
            </button>
            <button
              type="submit"
              className="rounded-lg bg-[#0078d4] px-3 py-1.5 text-sm text-white hover:bg-[#0063ad] cursor-pointer transition-colors"
            >
              Enviar
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
