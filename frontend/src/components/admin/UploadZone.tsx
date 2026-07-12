import { useEffect, useRef, useState, type DragEvent, type ChangeEvent } from 'react'
import { FileText, CheckCircle2, XCircle, Loader2, UploadCloud } from 'lucide-react'
import { authFetch, API_BASE, type DocumentListItem } from '../../lib/api'
import { generateUUID } from '../../lib/uuid'
import { useIndexingProgress } from '../../hooks/useIndexingProgress'
import UploadMetadataModal from './UploadMetadataModal'

interface FileEntry {
  id: string            // stable UUID per upload attempt — avoids name-collision bugs
  name: string
  progress: number      // 0–100
  status: 'uploading' | 'done' | 'error'
  message?: string
  docId?: string        // document UUID returned by the server after 202
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

// ------------------------------------------------------------------ //
// Per-entry row — extracted so useIndexingProgress can be called     //
// as a hook at the component level (hooks cannot be used inside      //
// array .map() callbacks directly).                                  //
// ------------------------------------------------------------------ //
function FileEntryRow({
  entry,
  onUpdate,
}: {
  entry: FileEntry
  onUpdate: (patch: Partial<FileEntry>) => void
}) {
  const isIndexing = entry.status === 'uploading' && !!entry.docId
  const { events, done, error } = useIndexingProgress(
    isIndexing ? (entry.docId as string) : null,
  )

  // Keep a stable ref to onUpdate so the effect below doesn't re-run every
  // time the parent re-renders (which happens on every progress event).
  const onUpdateRef = useRef(onUpdate)
  onUpdateRef.current = onUpdate

  const notifiedRef = useRef(false)
  useEffect(() => {
    if ((done || error) && !notifiedRef.current) {
      notifiedRef.current = true
      onUpdateRef.current(
        done
          ? { status: 'done', message: 'Indexado com sucesso.' }
          : { status: 'error', message: 'Erro na indexação.' },
      )
    }
  }, [done, error])

  const latestEvent = events[events.length - 1]

  return (
    <li className="rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-4 py-2 animate-fade-in">
      <div className="flex items-center justify-between text-sm">
        <span className="max-w-[70%] overflow-hidden text-ellipsis whitespace-nowrap text-[#1e2128] dark:text-[#eceae7] flex items-center gap-2">
          <FileText size={14} className="shrink-0 text-[#2c4a86] dark:text-[#8596b9]" />
          {entry.name}
        </span>
        <span
          className={
            entry.status === 'done'
              ? 'text-[#1f9a5a] dark:text-[#4cbd82] flex items-center gap-1'
              : entry.status === 'error'
                ? 'text-[#c0392b] dark:text-[#e0685c] flex items-center gap-1'
                : 'text-[#6c7078] dark:text-[#9da2aa] flex items-center gap-1'
          }
        >
          {entry.status === 'uploading' ? (
            isIndexing ? (
              latestEvent ? (
                <><Loader2 size={12} className="animate-spin" />{latestEvent.progress}%</>
              ) : (
                <Loader2 size={12} className="animate-spin" />
              )
            ) : (
              <><Loader2 size={12} className="animate-spin" />{entry.progress}%</>
            )
          ) : entry.status === 'done' ? (
            <CheckCircle2 size={14} />
          ) : (
            <XCircle size={14} />
          )}
        </span>
      </div>

      {/* XHR upload progress bar */}
      {entry.status === 'uploading' && !isIndexing && (
        <div className="mt-1 h-1 w-full overflow-hidden rounded bg-[#f2efe8] dark:bg-[#262b32]">
          <div
            className="h-full rounded bg-[#2c4a86] dark:bg-[#8596b9] transition-all"
            style={{ width: `${entry.progress}%` }}
          />
        </div>
      )}

      {/* Indexing step progress bar */}
      {isIndexing && (
        <div className="mt-1 h-1 w-full overflow-hidden rounded bg-[#f2efe8] dark:bg-[#262b32]">
          <div
            className="h-full rounded bg-[#2c4a86] dark:bg-[#8596b9] transition-all"
            style={{ width: `${latestEvent ? latestEvent.progress : 0}%` }}
          />
        </div>
      )}

      {/* Latest step description */}
      {isIndexing && latestEvent && (
        <p className="mt-1 text-xs text-[#6c7078] dark:text-[#9da2aa]">{latestEvent.detail}</p>
      )}

      {entry.message && (
        <p
          className={`mt-1 text-xs ${
            entry.status === 'error'
              ? 'text-[#c0392b] dark:text-[#e0685c]'
              : 'text-[#6c7078] dark:text-[#9da2aa]'
          }`}
        >
          {entry.message}
        </p>
      )}
    </li>
  )
}

export default function UploadZone({ onUploaded }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [pending, setPending] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [editalOptions, setEditalOptions] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  // Tracks nested drag-enter/leave events so the drop-zone highlight
  // doesn't flicker when the cursor passes over child elements.
  const dragCounter = useRef(0)

  useEffect(() => {
    authFetch(`${API_BASE}/documents?doc_type=edital&limit=100`)
      .then(res => (res.ok ? (res.json() as Promise<DocumentListItem[]>) : []))
      .then(data => setEditalOptions(data.map(d => d.display_name)))
      .catch(() => {})
  }, [])

  const uploadFile = (file: File, displayName: string, sourceUrl: string, docType: string, editalRef: string, editalCycle: string) => {
    const id = generateUUID()
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
        try {
          const doc = JSON.parse(xhr.responseText) as { id: string }
          update({ progress: 100, docId: doc.id })
        } catch {
          update({ status: 'done', progress: 100, message: 'Enviado com sucesso.' })
        }
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
    if (displayName) form.append('display_name', displayName)
    if (sourceUrl) form.append('source_url', sourceUrl)
    form.append('doc_type', docType)
    if (editalRef) form.append('edital_ref', editalRef)
    if (editalCycle) form.append('edital_cycle', editalCycle)
    xhr.open('POST', `${API_BASE}/documents/upload`)
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.send(form)
  }

  const handleFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming)
    // Client-side pre-filter: only application/pdf (backend is authoritative)
    const accepted: File[] = []
    for (const f of list) {
      if (f.type !== 'application/pdf') {
        setFiles(prev => [
          ...prev,
          { id: `err-${Date.now()}-${Math.random()}`, name: f.name, progress: 0, status: 'error', message: 'Apenas PDF aceito.' },
        ])
        continue
      }
      accepted.push(f)
    }
    if (accepted.length > 0) setPending(prev => [...prev, ...accepted])
  }

  const handleModalConfirm = (displayName: string, sourceUrl: string, docType: string, editalRef: string, editalCycle: string) => {
    const [file, ...rest] = pending
    uploadFile(file, displayName, sourceUrl, docType, editalRef, editalCycle)
    setPending(rest)
  }

  const handleModalCancel = () => {
    setPending(prev => prev.slice(1))
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
        className={`flex cursor-pointer flex-col items-center justify-center rounded-[16px] border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging
            ? 'border-[#2c4a86] dark:border-[#8596b9] bg-[#e8edf7] dark:bg-[#182236]'
            : 'border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] hover:border-[#2c4a86] dark:hover:border-[#8596b9]'
        }`}
      >
        <UploadCloud
          size={36}
          className={`mb-2 transition-transform ${dragging ? 'text-[#2c4a86] dark:text-[#8596b9] scale-110' : 'text-[#a19e96] dark:text-[#6c717a]'}`}
        />
        <p className="text-sm text-[#6c7078] dark:text-[#9da2aa]">
          Arraste PDFs aqui ou{' '}
          <span className="text-[#2c4a86] dark:text-[#8596b9] underline">clique para selecionar</span>
        </p>
        <p className="mt-1 text-xs text-[#a19e96] dark:text-[#6c717a]">
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
            <FileEntryRow
              key={`${f.name}-${i}`}
              entry={f}
              onUpdate={patch =>
                setFiles(prev => prev.map(e => (e.id === f.id ? { ...e, ...patch } : e)))
              }
            />
          ))}
        </ul>
      )}

      {pending.length > 0 && (
        <UploadMetadataModal
          fileName={pending[0].name}
          remaining={pending.length - 1}
          editalOptions={editalOptions}
          onConfirm={handleModalConfirm}
          onCancel={handleModalCancel}
        />
      )}
    </div>
  )
}
