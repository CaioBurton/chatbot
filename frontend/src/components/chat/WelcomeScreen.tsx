import { MessageSquareText } from 'lucide-react'
import propesqiLogo from '../../images/propesqi_perfil azul 2.png'

interface Props {
  onSend: (text: string) => void
}

const SUGGESTIONS = [
  'Quais são os prazos para submissão de projetos de pesquisa?',
  'Como solicito uma bolsa de iniciação científica (PIBIC)?',
  'Quais editais estão abertos atualmente?',
  'Como envio o relatório final de um projeto de pesquisa?',
]

export default function WelcomeScreen({ onSend }: Props) {
  return (
    <div className="m-auto max-w-2xl w-full px-4 text-center animate-fade-in">
      <img src={propesqiLogo} alt="" className="w-20 h-20 rounded-full mx-auto mb-4" />
      <h1 className="text-xl font-semibold text-[#111] dark:text-[#e8e8e8] mb-2">
        Como posso ajudar?
      </h1>
      <p className="text-sm opacity-60 text-[#111] dark:text-[#e8e8e8] mb-6">
        Sou o assistente virtual da PROPESQI/UFPI. Posso responder dúvidas sobre
        editais, bolsas, prazos e procedimentos da Pró-Reitoria de Pesquisa e Inovação.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => onSend(s)}
            className="flex items-start gap-2 text-left rounded-xl border border-[#ddd] dark:border-[#444] bg-white dark:bg-[#2d2d2d] px-4 py-3 text-sm text-[#111] dark:text-[#e8e8e8] hover:border-[#0078d4] hover:bg-[#e3f2fd] dark:hover:bg-[#1a4a6e] cursor-pointer transition-colors"
          >
            <MessageSquareText size={15} className="mt-0.5 shrink-0 text-[#0078d4]" />
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
