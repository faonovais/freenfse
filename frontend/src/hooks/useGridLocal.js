import { useMemo, useState } from 'react'

const comparador = new Intl.Collator('pt-BR', { numeric: true, sensitivity: 'base' })

function comparar(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b)
  return comparador.compare(String(a), String(b))
}

/**
 * Ordenação local de uma lista já carregada. `acessores` mapeia o nome da coluna ao
 * valor ordenável de cada item (por padrão, `item[coluna]`). Clicar na coluna ativa
 * alterna ascendente/descendente; outra coluna começa ascendente.
 */
export function useGridLocal(itens, { colunaInicial = null, acessores = {} } = {}) {
  const [ordenacao, setOrdenacao] = useState({ coluna: colunaInicial, direcao: 'asc' })

  const itensOrdenados = useMemo(() => {
    const { coluna, direcao } = ordenacao
    if (!coluna) return itens
    const valor = acessores[coluna] ?? ((item) => item[coluna])
    const sinal = direcao === 'asc' ? 1 : -1
    return [...itens].sort((itemA, itemB) => {
      const a = valor(itemA)
      const b = valor(itemB)
      // Valores vazios ficam sempre no fim, nas duas direções.
      if (a == null || b == null) return (a == null) - (b == null)
      return sinal * comparar(a, b)
    })
    // `acessores` é uma constante do chamador; só ordenação e itens mudam o resultado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itens, ordenacao])

  function ordenarPor(coluna) {
    setOrdenacao((atual) =>
      atual.coluna === coluna
        ? { coluna, direcao: atual.direcao === 'asc' ? 'desc' : 'asc' }
        : { coluna, direcao: 'asc' },
    )
  }

  return { itensOrdenados, ordenacao, ordenarPor }
}
