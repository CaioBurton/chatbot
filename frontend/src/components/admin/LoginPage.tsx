import { useState, type FormEvent } from 'react'
import { Lock, Loader2 } from 'lucide-react'

interface Props {
  login: (email: string, password: string) => Promise<void>
  onSuccess: () => void
}

export default function LoginPage({ login, onSuccess }: Props) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
      onSuccess()
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      if (status === 401) {
        setError('E-mail ou senha inválidos.')
      } else {
        setError('Erro ao entrar. Tente novamente.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-white dark:bg-[#1e1e1e]">
      <div className="w-full max-w-sm rounded-xl border border-[#ddd] dark:border-[#444] bg-[#fafafa] dark:bg-[#2d2d2d] p-8 shadow-sm">
        <h1 className="mb-6 text-xl font-semibold text-[#111] dark:text-[#e8e8e8] flex items-center gap-2">
          <Lock size={18} className="text-[#0078d4]" />
          Painel de Administração
        </h1>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label
              htmlFor="admin-email"
              className="text-sm text-[#555] dark:text-[#aaa]"
            >
              E-mail
            </label>
            <input
              id="admin-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="rounded-lg border border-[#ddd] dark:border-[#555] bg-white dark:bg-[#1e1e1e] px-3 py-2 text-sm text-[#111] dark:text-[#e8e8e8] outline-none focus:border-[#0078d4]"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label
              htmlFor="admin-password"
              className="text-sm text-[#555] dark:text-[#aaa]"
            >
              Senha
            </label>
            <input
              id="admin-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="rounded-lg border border-[#ddd] dark:border-[#555] bg-white dark:bg-[#1e1e1e] px-3 py-2 text-sm text-[#111] dark:text-[#e8e8e8] outline-none focus:border-[#0078d4]"
            />
          </div>

          {error && (
            <p className="rounded-lg border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-400">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 rounded-lg bg-[#0078d4] px-4 py-2 text-sm font-medium text-white hover:bg-[#006cbe] disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
          >
            {loading ? (
              <><Loader2 size={14} className="animate-spin" />Entrando…</>
            ) : (
              'Entrar'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
