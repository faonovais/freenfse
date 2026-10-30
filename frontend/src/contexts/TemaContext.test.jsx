import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SeletorTema from '../components/SeletorTema.jsx'
import { CHAVE_TEMA, TemaProvider } from './TemaContext.jsx'

function simularPreferenciaDoSistema(escuro) {
  vi.stubGlobal('matchMedia', (consulta) => ({
    matches: escuro && consulta.includes('dark'),
    media: consulta,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  document.documentElement.classList.remove('dark')
  vi.unstubAllGlobals()
})

describe('tema', () => {
  it('usa a chave freenfse-tema', () => {
    expect(CHAVE_TEMA).toBe('freenfse-tema')
  })

  it('segue o sistema por padrão', () => {
    simularPreferenciaDoSistema(true)

    render(
      <TemaProvider>
        <SeletorTema />
      </TemaProvider>,
    )

    expect(document.documentElement).toHaveClass('dark')
    expect(screen.getByRole('button', { name: 'Tema do sistema' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('aplica a classe .dark e lembra a escolha', async () => {
    simularPreferenciaDoSistema(false)
    render(
      <TemaProvider>
        <SeletorTema />
      </TemaProvider>,
    )
    expect(document.documentElement).not.toHaveClass('dark')

    fireEvent.click(screen.getByRole('button', { name: 'Tema escuro' }))

    expect(document.documentElement).toHaveClass('dark')
    expect(window.localStorage.getItem('freenfse-tema')).toBe('escuro')

    fireEvent.click(screen.getByRole('button', { name: 'Tema claro' }))

    expect(document.documentElement).not.toHaveClass('dark')
    expect(window.localStorage.getItem('freenfse-tema')).toBe('claro')
  })

  it('restaura a escolha salva', () => {
    simularPreferenciaDoSistema(false)
    window.localStorage.setItem('freenfse-tema', 'escuro')

    render(
      <TemaProvider>
        <SeletorTema />
      </TemaProvider>,
    )

    expect(document.documentElement).toHaveClass('dark')
  })

  it('ignora valor salvo inválido', () => {
    simularPreferenciaDoSistema(false)
    window.localStorage.setItem('freenfse-tema', 'roxo')

    render(
      <TemaProvider>
        <SeletorTema />
      </TemaProvider>,
    )

    expect(screen.getByRole('button', { name: 'Tema do sistema' })).toHaveAttribute('aria-pressed', 'true')
  })
})
