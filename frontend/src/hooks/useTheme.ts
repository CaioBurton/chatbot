import { useState, useCallback, useLayoutEffect } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'propesqi_theme'

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage unavailable (e.g. private browsing with strict settings)
  }
}

function loadTheme(): Theme {
  return readStorage(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

export function useTheme() {
  // useState initializer must be pure (no DOM side effects).
  const [theme, setTheme] = useState<Theme>(loadTheme)

  // useLayoutEffect runs synchronously after commit, before paint — no flash.
  useLayoutEffect(() => {
    applyTheme(theme)
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next: Theme = prev === 'light' ? 'dark' : 'light'
      // localStorage write is idempotent and acceptable inside an updater;
      // no DOM mutation here — that is handled by the useLayoutEffect above.
      writeStorage(STORAGE_KEY, next)
      return next
    })
  }, [])

  return { theme, toggleTheme }
}
