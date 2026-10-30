import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { createMemoryRouter, Link, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { ConfirmacaoProvider } from '../contexts/ConfirmacaoContext.jsx'
import { haFormularioSujo, useFormularioSujo } from './useFormularioSujo.js'

afterEach(cleanup)

function Formulario() {
  const [texto, setTexto] = useState('')
  useFormularioSujo(texto !== '')
  return (
    <>
      <input aria-label="texto" value={texto} onChange={(evento) => setTexto(evento.target.value)} />
      <Link to="/outra">ir</Link>
    </>
  )
}

function montar() {
  const roteador = createMemoryRouter(
    [
      { path: '/', element: <Formulario /> },
      { path: '/outra', element: <p>outra tela</p> },
    ],
    { initialEntries: ['/'] },
  )
  render(
    <ConfirmacaoProvider>
      <RouterProvider router={roteador} />
    </ConfirmacaoProvider>,
  )
  return roteador
}

const digitar = (valor) => fireEvent.change(screen.getByLabelText('texto'), { target: { value: valor } })

describe('proteção de formulário alterado', () => {
  it('navega livremente quando o formulário está limpo', async () => {
    montar()

    fireEvent.click(screen.getByText('ir'))

    expect(await screen.findByText('outra tela')).toBeInTheDocument()
    expect(haFormularioSujo()).toBe(false)
  })

  it('pede confirmação ao sair com alterações e permanece se a pessoa cancelar', async () => {
    montar()
    digitar('rascunho')
    expect(haFormularioSujo()).toBe(true)

    fireEvent.click(screen.getByText('ir'))
    const dialogo = await screen.findByRole('dialog', { name: 'Sair sem salvar?' })
    fireEvent.click(screen.getByRole('button', { name: 'Continuar editando' }))

    await waitFor(() => expect(dialogo).not.toBeInTheDocument())
    expect(screen.getByLabelText('texto')).toHaveValue('rascunho')
    expect(screen.queryByText('outra tela')).not.toBeInTheDocument()
  })

  it('sai quando a pessoa confirma o descarte', async () => {
    montar()
    digitar('rascunho')

    fireEvent.click(screen.getByText('ir'))
    await screen.findByRole('dialog', { name: 'Sair sem salvar?' })
    fireEvent.click(screen.getByRole('button', { name: 'Sair sem salvar' }))

    expect(await screen.findByText('outra tela')).toBeInTheDocument()
    expect(haFormularioSujo()).toBe(false)
  })

  it('avisa o navegador ao fechar ou recarregar a aba só enquanto há alterações', () => {
    montar()
    const evento = () => {
      const e = new Event('beforeunload', { cancelable: true })
      act(() => {
        window.dispatchEvent(e)
      })
      return e
    }

    expect(evento().defaultPrevented).toBe(false)
    digitar('rascunho')
    expect(evento().defaultPrevented).toBe(true)
    digitar('')
    expect(evento().defaultPrevented).toBe(false)
  })
})
