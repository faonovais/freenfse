import { useEffect, useId, useMemo, useRef, useState } from 'react'

const semAcento = (texto) =>
  String(texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()

/**
 * Seleção múltipla com busca. `opcoes`: [{ valor, rotulo, detalhe? }]; `valores`: lista dos
 * valores marcados. A lista continua aberta ao marcar; os itens marcados aparecem como
 * etiquetas removíveis.
 */
export default function SelectMultiBusca({
  opcoes,
  valores,
  aoMudar,
  rotulo,
  placeholder = 'Selecione…',
  vazio = 'Nenhum resultado',
}) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [indice, setIndice] = useState(0)
  const idLista = useId()
  const raizRef = useRef(null)

  const marcadas = opcoes.filter((opcao) => valores.includes(opcao.valor))
  const filtradas = useMemo(() => {
    const termo = semAcento(busca)
    return opcoes.filter((opcao) => semAcento(`${opcao.rotulo} ${opcao.detalhe ?? ''}`).includes(termo))
  }, [opcoes, busca])

  useEffect(() => {
    if (!aberto) return undefined
    const aoClicarFora = (evento) => {
      if (raizRef.current && !raizRef.current.contains(evento.target)) setAberto(false)
    }
    document.addEventListener('mousedown', aoClicarFora)
    return () => document.removeEventListener('mousedown', aoClicarFora)
  }, [aberto])

  function alternar(valor) {
    aoMudar(valores.includes(valor) ? valores.filter((item) => item !== valor) : [...valores, valor])
  }

  function aoTeclar(evento) {
    if (evento.key === 'ArrowDown') {
      evento.preventDefault()
      setIndice((atual) => Math.min(atual + 1, filtradas.length - 1))
    } else if (evento.key === 'ArrowUp') {
      evento.preventDefault()
      setIndice((atual) => Math.max(atual - 1, 0))
    } else if (evento.key === 'Enter') {
      evento.preventDefault()
      if (filtradas[indice]) alternar(filtradas[indice].valor)
    } else if (evento.key === 'Escape') {
      setAberto(false)
    }
  }

  return (
    <div ref={raizRef} className="relative">
      <div className="campo flex flex-wrap items-center gap-1">
        {marcadas.map((opcao) => (
          <span
            key={opcao.valor}
            className="inline-flex items-center gap-1 rounded border border-gray-200 px-2 py-0.5 text-xs dark:border-gray-800"
          >
            {opcao.rotulo}
            <button
              type="button"
              aria-label={`Remover ${opcao.rotulo}`}
              className="hover:text-estado-erro"
              onClick={() => alternar(opcao.valor)}
            >
              ×
            </button>
          </span>
        ))}
        <button
          type="button"
          role="combobox"
          aria-label={rotulo}
          aria-haspopup="listbox"
          aria-expanded={aberto}
          aria-controls={aberto ? idLista : undefined}
          className="min-w-24 flex-1 text-left text-gray-600 dark:text-gray-400"
          onClick={() => {
            setBusca('')
            setIndice(0)
            setAberto((atual) => !atual)
          }}
        >
          {marcadas.length === 0 ? placeholder : 'Adicionar…'}
        </button>
      </div>
      {aberto && (
        <div className="absolute z-40 mt-1 w-full rounded border border-gray-200 bg-white shadow dark:border-gray-800 dark:bg-gray-900">
          <input
            autoFocus
            type="search"
            aria-label={`Buscar ${rotulo}`}
            className="campo rounded-b-none border-0 border-b"
            value={busca}
            onChange={(evento) => {
              setBusca(evento.target.value)
              setIndice(0)
            }}
            onKeyDown={aoTeclar}
          />
          <ul id={idLista} role="listbox" aria-multiselectable="true" aria-label={rotulo} className="max-h-60 overflow-auto">
            {filtradas.length === 0 && (
              <li className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{vazio}</li>
            )}
            {filtradas.map((opcao, posicao) => (
              <li
                key={opcao.valor}
                role="option"
                aria-selected={valores.includes(opcao.valor)}
                onMouseEnter={() => setIndice(posicao)}
                onMouseDown={(evento) => {
                  evento.preventDefault()
                  alternar(opcao.valor)
                }}
                className={`flex cursor-pointer items-start gap-2 px-3 py-2 text-sm ${
                  posicao === indice ? 'bg-gray-100 dark:bg-gray-800' : ''
                }`}
              >
                <span aria-hidden="true">{valores.includes(opcao.valor) ? '☑' : '☐'}</span>
                <span>
                  {opcao.rotulo}
                  {opcao.detalhe && (
                    <span className="block text-xs text-gray-600 dark:text-gray-400">{opcao.detalhe}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
