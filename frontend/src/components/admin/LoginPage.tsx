import { useState, type FormEvent } from 'react'
import { Loader2, ArrowLeft } from 'lucide-react'
import propesqiMark from '../../images/propesqi_perfil azul 2.png'

interface Props {
  login: (email: string, password: string) => Promise<void>
  onSuccess: () => void
  onBackToChat: () => void
}

export default function LoginPage({ login, onSuccess, onBackToChat }: Props) {
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
    <div className="flex min-h-screen items-center justify-center bg-[#fdfcfa] dark:bg-[#16181c] p-6">
      <div className="w-full max-w-[380px] rounded-[20px] border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-8 pt-9 pb-[30px] shadow-[0_12px_32px_rgba(30,25,15,0.08)] dark:shadow-[0_12px_32px_rgba(0,0,0,0.4)] animate-fade-in">
        <img
          src={propesqiMark}
          alt="PROPESQI"
          className="mx-auto mb-[18px] block h-16 w-16 rounded-full object-cover"
        />
        <h1 className="mb-1 text-center font-serif text-[21px] font-semibold text-[#1e2128] dark:text-[#eceae7]">
          Painel de Administração
        </h1>
        <p className="mb-[26px] text-center text-[13px] text-[#6c7078] dark:text-[#9da2aa]">
          PROPESQI · Pesquisa &amp; Inovação · UFPI
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-[14px]">
          <label className="flex flex-col gap-[5px]">
            <span className="text-[12.5px] font-semibold text-[#6c7078] dark:text-[#9da2aa]">
              E-mail
            </span>
            <input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="seuemail@ufpi.edu.br"
              className="w-full rounded-[11px] border-[1.5px] border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-[13px] py-2.5 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none transition-colors focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
            />
          </label>
          <label className="flex flex-col gap-[5px]">
            <span className="text-[12.5px] font-semibold text-[#6c7078] dark:text-[#9da2aa]">
              Senha
            </span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-[11px] border-[1.5px] border-[#e6e1d5] dark:border-[#33383f] bg-[#fdfcfa] dark:bg-[#16181c] px-[13px] py-2.5 text-sm text-[#1e2128] dark:text-[#eceae7] outline-none transition-colors focus:border-[#2c4a86] dark:focus:border-[#8596b9]"
            />
          </label>

          {error && (
            <p className="m-0 rounded-[10px] border border-[#c0392b] dark:border-[#e0685c] bg-[#fbeae7] dark:bg-[#3a1f1c] px-3 py-[9px] text-[12.5px] text-[#c0392b] dark:text-[#e0685c]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 flex w-full items-center justify-center gap-2 rounded-[11px] bg-[#2c4a86] px-3.5 py-[11px] text-sm font-semibold text-white transition-colors hover:bg-[#20396a] disabled:cursor-not-allowed disabled:opacity-70"
          >
            {loading ? (
              <><Loader2 size={14} className="animate-spin" />Entrando…</>
            ) : (
              'Entrar'
            )}
          </button>
        </form>

        <button
          type="button"
          onClick={onBackToChat}
          className="mt-[18px] flex w-full cursor-pointer items-center justify-center gap-1.5 border-0 bg-transparent p-1 text-[13px] font-semibold text-[#2c4a86] dark:text-[#8596b9] hover:underline"
        >
          <ArrowLeft size={14} />
          Voltar ao chat
        </button>
      </div>
    </div>
  )
}
