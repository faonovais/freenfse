import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useGridLocal } from './useGridLocal.js'

const ITENS = [
  { id: 1, nome: 'Zélia', idade: 30, ativo: true, apelido: null },
  { id: 2, nome: 'Ana', idade: 5, ativo: false, apelido: 'An' },
  { id: 3, nome: 'élio', idade: 12, ativo: true, apelido: 'Z' },
]
const nomes = (resultado) => resultado.current.itensOrdenados.map((item) => item.nome)

describe('useGridLocal', () => {
  it('mantém a ordem original sem coluna inicial', () => {
    const { result } = renderHook(() => useGridLocal(ITENS))

    expect(nomes(result)).toEqual(['Zélia', 'Ana', 'élio'])
  })

  it('ordena texto ignorando acento e caixa; alterna ascendente/descendente no mesmo clique', () => {
    const { result } = renderHook(() => useGridLocal(ITENS))

    act(() => result.current.ordenarPor('nome'))
    expect(nomes(result)).toEqual(['Ana', 'élio', 'Zélia'])
    expect(result.current.ordenacao).toEqual({ coluna: 'nome', direcao: 'asc' })

    act(() => result.current.ordenarPor('nome'))
    expect(nomes(result)).toEqual(['Zélia', 'élio', 'Ana'])
    expect(result.current.ordenacao.direcao).toBe('desc')
  })

  it('ordena números pelo valor, não pelo texto', () => {
    const { result } = renderHook(() => useGridLocal(ITENS))

    act(() => result.current.ordenarPor('idade'))

    expect(result.current.itensOrdenados.map((item) => item.idade)).toEqual([5, 12, 30])
  })

  it('trocar de coluna recomeça ascendente; valores vazios ficam sempre no fim', () => {
    const { result } = renderHook(() => useGridLocal(ITENS, { colunaInicial: 'nome' }))
    act(() => result.current.ordenarPor('nome')) // desc

    act(() => result.current.ordenarPor('apelido'))
    expect(result.current.ordenacao).toEqual({ coluna: 'apelido', direcao: 'asc' })
    expect(result.current.itensOrdenados.at(-1).apelido).toBeNull()

    act(() => result.current.ordenarPor('apelido')) // desc
    expect(result.current.itensOrdenados.at(-1).apelido).toBeNull()
  })

  it('usa o acessor informado e não altera a lista original', () => {
    const copia = [...ITENS]
    const { result } = renderHook(() =>
      useGridLocal(ITENS, { colunaInicial: 'situacao', acessores: { situacao: (item) => item.ativo } }),
    )

    expect(result.current.itensOrdenados[0].ativo).toBe(false)
    expect(ITENS).toEqual(copia)
  })
})
