import { useEffect, useId, useMemo, useRef, useState } from 'react'

const semAcento = (texto) =>
  String(texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()

/**
 * Seleção com busca. `opcoes`: [{ valor, rotulo, detalhe? }]. O texto digitado filtra
 * pelo rótulo e pelo detalhe, sem diferenciar maiúsculas nem acentos.
 */
export default function SelectBusca({
  opcoes,
  valor,
  aoMudar,
  rotulo,
  placeholder = 'Selecione…',
  vazio = 'Nenhum resultado',
  desabilitado = false,
}) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [indice, setIndice] = useState(0)
  const idLista = useId()
  const raizRef = useRef(null)

  const selecionada = opcoes.find((opcao) => opcao.valor === valor)
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

  function abrir() {
    setBusca('')
    setIndice(0)
    setAberto(true)
  }

  function escolher(opcao) {
    setAberto(false)
    if (opcao.valor !== valor) aoMudar(opcao.valor)
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
      if (filtradas[indice]) escolher(filtradas[indice])
    } else if (evento.key === 'Escape') {
      setAberto(false)
    }
  }

  return (
    <div ref={raizRef} className="relative">
      <button
        type="button"
        role="combobox"
        aria-label={rotulo}
        aria-haspopup="listbox"
        aria-expanded={aberto}
        aria-controls={aberto ? idLista : undefined}
        disabled={desabilitado}
        onClick={() => (aberto ? setAberto(false) : abrir())}
        className="campo flex items-center justify-between gap-2 text-left disabled:opacity-50"
      >
        <span className={selecionada ? '' : 'text-gray-600 dark:text-gray-400'}>
          {selecionada ? selecionada.rotulo : placeholder}
        </span>
        <span aria-hidden="true">▾</span>
      </button>
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
          <ul id={idLista} role="listbox" aria-label={rotulo} className="max-h-60 overflow-auto">
            {filtradas.length === 0 && (
              <li className="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{vazio}</li>
            )}
            {filtradas.map((opcao, posicao) => (
              <li
                key={opcao.valor}
                role="option"
                aria-selected={opcao.valor === valor}
                onMouseEnter={() => setIndice(posicao)}
                onMouseDown={(evento) => {
                  evento.preventDefault()
                  escolher(opcao)
                }}
                className={`cursor-pointer px-3 py-2 text-sm ${
                  posicao === indice ? 'bg-gray-100 dark:bg-gray-800' : ''
                } ${opcao.valor === valor ? 'text-accent' : ''}`}
              >
                <span>{opcao.rotulo}</span>
                {opcao.detalhe && (
                  <span className="block text-xs text-gray-600 dark:text-gray-400">{opcao.detalhe}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
