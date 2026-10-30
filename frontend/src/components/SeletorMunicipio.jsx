import { useEffect, useId, useState } from 'react'
import { municipios } from '../api/cadastros.js'

const ESPERA_DA_BUSCA_MS = 250

/**
 * Escolha de município pelo nome (o usuário não digita o código IBGE). Mostra "Nome/UF" do
 * município escolhido e busca no servidor enquanto digita, a partir de 2 letras.
 */
export default function SeletorMunicipio({ rotulo, valor, aoMudar, erro, dica, obrigatorio = false }) {
  const id = useId()
  const idMensagem = `${id}-mensagem`
  const [escolhido, setEscolhido] = useState(null)
  const [busca, setBusca] = useState('')
  const [resultados, setResultados] = useState([])
  const [aberto, setAberto] = useState(false)

  // Mostra o nome do município já gravado (só temos o código).
  useEffect(() => {
    let ativo = true
    if (!valor) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setEscolhido(null)
      return undefined
    }
    municipios.obterPorCodigo(valor).then((resposta) => {
      if (ativo && resposta.ok && resposta.dados.length > 0) setEscolhido(resposta.dados[0])
    })
    return () => {
      ativo = false
    }
  }, [valor])

  useEffect(() => {
    if (busca.trim().length < 2) return undefined
    let ativo = true
    const temporizador = setTimeout(() => {
      municipios.buscar(busca.trim()).then((resposta) => {
        if (ativo) setResultados(resposta.ok ? resposta.dados : [])
      })
    }, ESPERA_DA_BUSCA_MS)
    return () => {
      ativo = false
      clearTimeout(temporizador)
    }
  }, [busca])

  function escolher(municipio) {
    setEscolhido(municipio)
    setAberto(false)
    setBusca('')
    setResultados([])
    aoMudar(municipio.codigo)
  }

  return (
    <div className="relative text-sm">
      <label htmlFor={id}>{rotulo}</label>
      <input
        id={id}
        role="combobox"
        aria-expanded={aberto}
        aria-autocomplete="list"
        aria-required={obrigatorio || undefined}
        aria-invalid={erro ? 'true' : undefined}
        aria-describedby={erro || dica ? idMensagem : undefined}
        autoComplete="off"
        className="campo mt-1"
        placeholder={escolhido ? `${escolhido.nome}/${escolhido.uf}` : 'Digite o nome do município'}
        value={busca}
        onFocus={() => setAberto(true)}
        onChange={(evento) => {
          setBusca(evento.target.value)
          setAberto(true)
        }}
      />
      {escolhido && !busca && (
        <p className="mt-1 text-xs">
          Selecionado: <strong>{escolhido.nome}/{escolhido.uf}</strong> (IBGE {escolhido.codigo})
        </p>
      )}
      {aberto && busca.trim().length >= 2 && (
        <ul
          role="listbox"
          aria-label={`Municípios encontrados para ${rotulo}`}
          className="absolute z-40 mt-1 max-h-60 w-full overflow-auto rounded border border-gray-200 bg-white shadow dark:border-gray-800 dark:bg-gray-900"
        >
          {resultados.length === 0 && (
            <li className="px-3 py-2 text-gray-600 dark:text-gray-400">Nenhum município encontrado</li>
          )}
          {resultados.map((municipio) => (
            <li
              key={municipio.codigo}
              role="option"
              aria-selected={municipio.codigo === valor}
              className="cursor-pointer px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-800"
              onMouseDown={(evento) => {
                evento.preventDefault()
                escolher(municipio)
              }}
            >
              {municipio.nome}/{municipio.uf}
              <span className="block text-xs text-gray-600 dark:text-gray-400">IBGE {municipio.codigo}</span>
            </li>
          ))}
        </ul>
      )}
      {(erro || dica) && (
        <p id={idMensagem} className={`mt-1 text-xs ${erro ? 'text-estado-erro' : 'text-gray-600 dark:text-gray-400'}`}>
          {erro || dica}
        </p>
      )}
    </div>
  )
}
