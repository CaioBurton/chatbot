import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, FileCheck2 } from 'lucide-react'

interface Props {
  value: string
  onChange: (value: string) => void
  options: string[]
  placeholder?: string
}

/** Styled combobox for picking an indexed edital as the parent reference
 *  of an aditivo. Behaves like a native datalist (filters as you type,
 *  still accepts free text for editais not yet indexed) but matches the
 *  app's own design instead of the browser's unstyled popup. */
export default function EditalRefInput({ value, onChange, options, placeholder }: Props) {
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase()
    if (!q) return options
    return options.filter(opt => opt.toLowerCase().includes(q))
  }, [value, options])

  useEffect(() => {
    if (!open) return
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  useEffect(() => {
    setHighlight(0)
  }, [value, open])

  const selectOption = (opt: string) => {
    onChange(opt)
    setOpen(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      setOpen(true)
      return
    }
    if (!open || filtered.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight(h => (h + 1) % filtered.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight(h => (h - 1 + filtered.length) % filtered.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      selectOption(filtered[highlight])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoComplete="off"
          className="w-full rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] py-2 pl-3 pr-8 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setOpen(o => !o)}
          className="absolute right-0 top-0 flex h-full cursor-pointer items-center px-2 text-[#a19e96] hover:text-[#1e2128] dark:text-[#6c717a] dark:hover:text-[#eceae7]"
        >
          <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] py-1 shadow-lg">
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-xs text-[#a19e96] dark:text-[#6c717a]">
              {options.length === 0 ? 'Nenhum edital indexado ainda.' : 'Nenhum edital corresponde.'}
            </p>
          ) : (
            filtered.map((opt, i) => (
              <button
                key={opt}
                type="button"
                onMouseDown={e => e.preventDefault()}
                onClick={() => selectOption(opt)}
                className={`flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-sm transition-colors ${
                  i === highlight
                    ? 'bg-[#eae6dc] dark:bg-[#2c313a] text-[#1e2128] dark:text-[#eceae7]'
                    : 'text-[#1e2128] dark:text-[#eceae7] hover:bg-[#eae6dc] dark:hover:bg-[#2c313a]'
                }`}
              >
                <FileCheck2 size={12} className="shrink-0 text-[#2c4a86] dark:text-[#8596b9]" />
                <span className="overflow-hidden text-ellipsis whitespace-nowrap">{opt}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
