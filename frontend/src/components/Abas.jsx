import { useRef, useState } from 'react'

/**
 * Navegação em abas acessível (WAI-ARIA Tabs: setas, Home/End, roving tabindex).
 * Mantém no DOM o painel das abas já visitadas via `hidden` para não perder estado.
 */
export default function Abas({ abas, abaInicial, ariaLabel = 'Seções da página' }) {
  const botoesRef = useRef({})
  const idsValidos = abas.map((aba) => aba.id)
  const padrao = idsValidos.includes(abaInicial) ? abaInicial : idsValidos[0]
  const [selecionada, setSelecionada] = useState(padrao)
  const [visitadas, setVisitadas] = useState(() => (padrao ? [padrao] : []))

  if (abas.length === 0) return null

  const abaAtiva = idsValidos.includes(selecionada) ? selecionada : padrao

  function ativarAba(id, focar = false) {
    setSelecionada(id)
    setVisitadas((atuais) => (atuais.includes(id) ? atuais : [...atuais, id]))
    if (focar) {
      botoesRef.current[id]?.focus()
    }
  }

  function aoPressionarTecla(evento, indiceAtual) {
    const ultimo = abas.length - 1
    let proximoIndice = null

    if (evento.key === 'ArrowRight') {
      proximoIndice = indiceAtual === ultimo ? 0 : indiceAtual + 1
    } else if (evento.key === 'ArrowLeft') {
      proximoIndice = indiceAtual === 0 ? ultimo : indiceAtual - 1
    } else if (evento.key === 'Home') {
      proximoIndice = 0
    } else if (evento.key === 'End') {
      proximoIndice = ultimo
    }

    if (proximoIndice === null) return
    evento.preventDefault()
    ativarAba(abas[proximoIndice].id, true)
  }

  return (
    <div>
      <div
        role="tablist"
        aria-label={ariaLabel}
        className="mb-6 flex flex-wrap gap-1 border-b border-gray-200 dark:border-gray-800"
      >
        {abas.map((aba, indice) => {
          const ativa = aba.id === abaAtiva
          return (
            <button
              key={aba.id}
              ref={(elemento) => {
                botoesRef.current[aba.id] = elemento
              }}
              type="button"
              role="tab"
              id={`aba-${aba.id}`}
              aria-selected={ativa}
              aria-controls={`painel-${aba.id}`}
              tabIndex={ativa ? 0 : -1}
              onClick={() => ativarAba(aba.id)}
              onKeyDown={(evento) => aoPressionarTecla(evento, indice)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm transition-colors ${
                ativa
                  ? 'border-accent font-semibold text-accent'
                  : 'border-transparent text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
            >
              {aba.rotulo}
            </button>
          )
        })}
      </div>

      {abas.map((aba) => {
        const ativa = aba.id === abaAtiva
        const renderizar = ativa || visitadas.includes(aba.id)
        if (!renderizar) return null
        return (
          <div key={aba.id} id={`painel-${aba.id}`} role="tabpanel" aria-labelledby={`aba-${aba.id}`} hidden={!ativa}>
            {aba.conteudo}
          </div>
        )
      })}
    </div>
  )
}
