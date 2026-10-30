import { useTema } from '../contexts/TemaContext.jsx'

const propriedades = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

const OPCOES = [
  {
    modo: 'claro',
    rotulo: 'Tema claro',
    icone: (
      <svg {...propriedades}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    ),
  },
  {
    modo: 'escuro',
    rotulo: 'Tema escuro',
    icone: (
      <svg {...propriedades}>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    ),
  },
  {
    modo: 'sistema',
    rotulo: 'Tema do sistema',
    icone: (
      <svg {...propriedades}>
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
      </svg>
    ),
  },
]

/** Três botões (sol, lua, monitor) para escolher o tema. */
export default function SeletorTema() {
  const { modo, definirModo } = useTema()
  return (
    <div role="group" aria-label="Tema da interface" className="flex gap-1">
      {OPCOES.map((opcao) => (
        <button
          key={opcao.modo}
          type="button"
          title={opcao.rotulo}
          aria-label={opcao.rotulo}
          aria-pressed={modo === opcao.modo}
          onClick={() => definirModo(opcao.modo)}
          className={`botao-leve flex items-center justify-center ${modo === opcao.modo ? 'border-accent text-accent' : ''}`}
        >
          {opcao.icone}
        </button>
      ))}
    </div>
  )
}
