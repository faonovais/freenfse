import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import BotaoAjuda from './BotaoAjuda.jsx'
import CabecalhoColuna from './CabecalhoColuna.jsx'
import PainelColapsavel from './PainelColapsavel.jsx'

afterEach(cleanup)

describe('PainelColapsavel', () => {
  it('abre e recolhe, informando o estado por aria-expanded', () => {
    render(
      <PainelColapsavel titulo="Detalhes">
        <p>conteúdo</p>
      </PainelColapsavel>,
    )
    const botao = screen.getByRole('button', { name: /Detalhes/ })
    expect(botao).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('conteúdo')).toBeVisible()

    fireEvent.click(botao)

    expect(botao).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('conteúdo')).not.toBeVisible()
  })

  it('pode começar recolhido', () => {
    render(
      <PainelColapsavel titulo="Detalhes" abertoInicial={false}>
        <p>conteúdo</p>
      </PainelColapsavel>,
    )

    expect(screen.queryByText('conteúdo')).not.toBeVisible()
  })
})

describe('BotaoAjuda', () => {
  it('mostra e esconde a explicação; Escape e clique fora fecham', () => {
    render(<BotaoAjuda rotulo="perfil">Explica o perfil.</BotaoAjuda>)
    const botao = screen.getByRole('button', { name: 'Ajuda: perfil' })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()

    fireEvent.click(botao)
    expect(screen.getByRole('note')).toHaveTextContent('Explica o perfil.')
    expect(botao).toHaveAttribute('aria-expanded', 'true')

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('note')).not.toBeInTheDocument()

    fireEvent.click(botao)
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })
})

describe('CabecalhoColuna', () => {
  const montar = (ordenacao, aoOrdenar = () => {}) =>
    render(
      <table>
        <thead>
          <tr>
            <CabecalhoColuna rotulo="Nome" coluna="nome" ordenacao={ordenacao} aoOrdenar={aoOrdenar} />
          </tr>
        </thead>
      </table>,
    )

  it.each([
    [{ coluna: 'nome', direcao: 'asc' }, 'ascending'],
    [{ coluna: 'nome', direcao: 'desc' }, 'descending'],
    [{ coluna: 'outra', direcao: 'asc' }, 'none'],
  ])('expõe o estado de ordenação (%j) em aria-sort', (ordenacao, esperado) => {
    montar(ordenacao)

    expect(screen.getByRole('columnheader', { name: /Nome/ })).toHaveAttribute('aria-sort', esperado)
  })

  it('chama aoOrdenar com a coluna ao clicar', () => {
    const chamadas = []
    montar({ coluna: null, direcao: 'asc' }, (coluna) => chamadas.push(coluna))

    fireEvent.click(screen.getByRole('button', { name: /Nome/ }))

    expect(chamadas).toEqual(['nome'])
  })
})
