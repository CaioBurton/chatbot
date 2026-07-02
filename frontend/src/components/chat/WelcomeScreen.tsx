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
    <div className="m-auto max-w-[640px] w-full px-3 text-center animate-fade-in">
      <img src={propesqiLogo} alt="" className="w-[72px] h-[72px] rounded-full mx-auto mb-5" />
      <h1 className="font-serif font-semibold text-[26px] text-[#1e2128] dark:text-[#eceae7] mb-2.5">
        Como posso ajudar?
      </h1>
      <p className="text-[14.5px] leading-[1.6] text-[#6c7078] dark:text-[#9da2aa] mb-7 mx-auto max-w-[480px]">
        Sou o assistente virtual da PROPESQI/UFPI. Posso responder dúvidas sobre
        editais, bolsas, prazos e procedimentos da Pró-Reitoria de Pesquisa e Inovação.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => onSend(s)}
            className="flex items-start gap-2 text-left rounded-xl border border-[#e6e1d5] dark:border-[#33383f] bg-white dark:bg-[#1d2126] px-3.5 py-3 text-[13.5px] leading-[1.4] text-[#1e2128] dark:text-[#eceae7] hover:border-[#2c4a86] dark:hover:border-[#8596b9] hover:bg-[#e8edf7] dark:hover:bg-[#182236] cursor-pointer transition-colors"
          >
            <span className="text-[#2c4a86] dark:text-[#8596b9] shrink-0">›</span>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
