const ROTULO_DIRECAO = { asc: 'ascendente', desc: 'descendente' }

/** Cabeçalho de coluna ordenável (use com `useGridLocal`). Informa o estado via aria-sort. */
export default function CabecalhoColuna({ rotulo, coluna, ordenacao, aoOrdenar, className = '' }) {
  const ativa = ordenacao.coluna === coluna
  return (
    <th
      scope="col"
      aria-sort={ativa ? (ordenacao.direcao === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={`px-3 py-2 ${className}`}
    >
      <button
        type="button"
        className="inline-flex items-center gap-1 hover:text-accent"
        title={ativa ? `Ordenado de forma ${ROTULO_DIRECAO[ordenacao.direcao]}` : `Ordenar por ${rotulo}`}
        onClick={() => aoOrdenar(coluna)}
      >
        {rotulo}
        <span aria-hidden="true" className="text-xs">
          {ativa ? (ordenacao.direcao === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  )
}
