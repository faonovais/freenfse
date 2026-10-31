import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ConfirmacaoProvider, useConfirmacao } from './ConfirmacaoContext.jsx'

afterEach(cleanup)

function Chamador({ opcoes, aoResponder }) {
  const confirmar = useConfirmacao()
  return (
    <button type="button" onClick={() => confirmar(opcoes).then(aoResponder)}>
      abrir
    </button>
  )
}

function montar(opcoes = { titulo: 'Excluir?', mensagem: 'Não dá para desfazer.' }) {
  const respostas = []
  render(
    <ConfirmacaoProvider>
      <Chamador opcoes={opcoes} aoResponder={(valor) => respostas.push(valor)} />
    </ConfirmacaoProvider>,
  )
  return respostas
}

describe('confirmar()', () => {
  it('abre um diálogo acessível e resolve true ao confirmar', async () => {
    const respostas = montar()

    fireEvent.click(screen.getByText('abrir'))
    const dialogo = screen.getByRole('dialog', { name: 'Excluir?' })
    expect(dialogo).toHaveAttribute('aria-modal', 'true')
    expect(dialogo).toHaveAccessibleDescription('Não dá para desfazer.')
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))

    await waitFor(() => expect(respostas).toEqual([true]))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('resolve false ao cancelar, com o botão e com a tecla Escape', async () => {
    const respostas = montar()

    fireEvent.click(screen.getByText('abrir'))
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    fireEvent.click(screen.getByText('abrir'))
    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(respostas).toEqual([false, false]))
  })

  it('foca o botão de cancelar (a opção segura) ao abrir', async () => {
    montar()

    fireEvent.click(screen.getByText('abrir'))

    expect(screen.getByRole('button', { name: 'Cancelar' })).toHaveFocus()
  })

  it('na variante de perigo, só habilita o botão depois de digitar o texto exigido', async () => {
    const respostas = montar({
      titulo: 'Desativar?',
      variante: 'perigo',
      textoConfirmar: 'Desativar',
      textoDigitado: 'ALFA',
    })

    fireEvent.click(screen.getByText('abrir'))
    const botao = screen.getByRole('button', { name: 'Desativar' })
    expect(botao).toBeDisabled()
    expect(botao).toHaveClass('botao-perigo')
    fireEvent.change(screen.getByLabelText(/Digite/), { target: { value: 'alfa' } })
    expect(botao).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Digite/), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText(/Digite/), { target: { value: 'ALFA' } })
    expect(botao).toBeEnabled()
    fireEvent.click(botao)

    await waitFor(() => expect(respostas).toEqual([true]))
  })

  it('um pedido novo cancela o anterior', async () => {
    const respostas = []
    function DoisPedidos() {
      const confirmar = useConfirmacao()
      return (
        <>
          <button type="button" onClick={() => confirmar({ titulo: 'Primeiro' }).then((v) => respostas.push(['1', v]))}>
            um
          </button>
          <button type="button" onClick={() => confirmar({ titulo: 'Segundo' }).then((v) => respostas.push(['2', v]))}>
            dois
          </button>
        </>
      )
    }
    render(
      <ConfirmacaoProvider>
        <DoisPedidos />
      </ConfirmacaoProvider>,
    )

    // O diálogo aberto cobre a tela; o segundo pedido chega por outra via (programática).
    fireEvent.click(screen.getByText('um'))
    screen.getByText('dois').click()

    await waitFor(() => expect(respostas).toEqual([['1', false]]))
    expect(screen.getByRole('dialog', { name: 'Segundo' })).toBeInTheDocument()
  })

  it('falha com mensagem clara fora do provedor', () => {
    function Solto() {
      useConfirmacao()
      return null
    }

    expect(() => render(<Solto />)).toThrow(/ConfirmacaoProvider/)
  })
})
