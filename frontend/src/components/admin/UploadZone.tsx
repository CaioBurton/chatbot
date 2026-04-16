import { useRef, useState, type DragEvent, type ChangeEvent } from 'react'
import { API_BASE } from '../../lib/api'

interface FileEntry {
  id: string            // stable UUID per upload attempt — avoids name-collision bugs
  name: string
  progress: number      // 0–100
  status: 'uploading' | 'done' | 'error'
  message?: string
}

interface Props {
  onUploaded: () => void
}

function readToken(): string | null {
  try {
    return localStorage.getItem('propesqi_access_token')
  } catch {
    return null
  }
}

export default function UploadZone({ onUploaded }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  // Tracks nested drag-enter/leave events so the drop-zone highlight
  // doesn't flicker when the cursor passes over child elements.
  const dragCounter = useRef(0)

  const uploadFile = (file: File) => {
    // Use crypto.randomUUID when available, fall back to timestamp+random.
    const id =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`
    const entry: FileEntry = { id, name: file.name, progress: 0, status: 'uploading' }
    setFiles(prev => [...prev, entry])

    // Match by stable id — avoids clobbering a simultaneous upload of a
    // file with the same name.
    const update = (patch: Partial<FileEntry>) =>
      setFiles(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)))

    const xhr = new XMLHttpRequest()
    const token = readToken()

    xhr.upload.onprogress = (e: ProgressEvent) => {
      if (e.lengthComputable) {
        update({ progress: Math.round((e.loaded / e.total) * 100) })
      }
    }

    xhr.onload = () => {
      if (xhr.status === 202) {
        update({ status: 'done', progress: 100, message: 'Enviado com sucesso.' })
        onUploaded()
      } else if (xhr.status === 409) {
        update({ status: 'error', message: 'Arquivo duplicado já existe.' })
      } else if (xhr.status === 415) {
        update({ status: 'error', message: 'Apenas arquivos PDF são aceitos.' })
      } else if (xhr.status === 413) {
        update({ status: 'error', message: 'Arquivo excede o limite de 50 MB.' })
      } else {
        update({ status: 'error', message: `Erro ${xhr.status}.` })
      }
    }

    xhr.onerror = () => {
      update({ status: 'error', message: 'Falha de conexão.' })
    }

    const form = new FormData()
    form.append('file', file)
    xhr.open('POST', `${API_BASE}/documents/upload`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.send(form)
  }

  const handleFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming)
    // Client-side pre-filter: only application/pdf (backend is authoritative)
    for (const f of list) {
      if (f.type !== 'application/pdf') {
        setFiles(prev => [
          ...prev,
          { name: f.name, progress: 0, status: 'error', message: 'Apenas PDF aceito.' },
        ])
        continue
      }
      uploadFile(f)
    }
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    dragCounter.current = 0
    setDragging(false)
    if (e.dataTransfer.files) handleFiles(e.dataTransfer.files)
  }

  const onDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    dragCounter.current++
    setDragging(true)
  }

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }

  const onDragLeave = () => {
    dragCounter.current--
    if (dragCounter.current === 0) setDragging(false)
  }

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) handleFiles(e.target.files)
    // Reset so the same file can be re-selected after an error
    e.target.value = ''
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        role="button"
        tabIndex={0}
        onDrop={onDrop}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        onKeyDown={e => e.key === 'Enter' && inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging
            ? 'border-[#0078d4] bg-[#e3f2fd] dark:bg-[#1a4a6e]/30'
            : 'border-[#ccc] dark:border-[#555] bg-[#fafafa] dark:bg-[#2d2d2d] hover:border-[#0078d4]'
        }`}
      >
        <span className="text-3xl mb-2">📄</span>
        <p className="text-sm text-[#555] dark:text-[#aaa]">
          Arraste PDFs aqui ou{' '}
          <span className="text-[#0078d4] underline">clique para selecionar</span>
        </p>
        <p className="mt-1 text-xs text-[#888] dark:text-[#666]">
          Apenas PDF · máximo 50 MB por arquivo
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          onChange={onChange}
        />
      </div>

      {files.length > 0 && (
        <ul className="flex flex-col gap-2">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="rounded-lg border border-[#ddd] dark:border-[#444] bg-white dark:bg-[#1e1e1e] px-4 py-2"
            >
              <div className="flex items-center justify-between text-sm">
                <span className="max-w-[70%] overflow-hidden text-ellipsis whitespace-nowrap text-[#111] dark:text-[#e8e8e8]">
                  {f.name}
                </span>
                <span
                  className={
                    f.status === 'done'
                      ? 'text-green-600 dark:text-green-400'
                      : f.status === 'error'
                        ? 'text-red-600 dark:text-red-400'
                        : 'text-[#777] dark:text-[#aaa]'
                  }
                >
                  {f.status === 'uploading'
                    ? `${f.progress}%`
                    : f.status === 'done'
                      ? '✓'
                      : '✗'}
                </span>
              </div>

              {f.status === 'uploading' && (
                <div className="mt-1 h-1 w-full overflow-hidden rounded bg-[#eee] dark:bg-[#444]">
                  <div
                    className="h-full rounded bg-[#0078d4] transition-all"
                    style={{ width: `${f.progress}%` }}
                  />
                </div>
              )}

              {f.message && (
                <p
                  className={`mt-1 text-xs ${
                    f.status === 'error'
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-[#555] dark:text-[#aaa]'
                  }`}
                >
                  {f.message}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
