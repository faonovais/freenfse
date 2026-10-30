import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('mostra a versão da API quando ela responde', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ versao: '9.9.9' }) }),
    )

    render(<App />)

    expect(await screen.findByText('API: v9.9.9')).toBeInTheDocument()
    expect(screen.getByText(`Interface: v${__VERSAO_APP__}`)).toBeInTheDocument()
  })

  it('avisa quando a API está indisponível', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('sem rede')))

    render(<App />)

    expect(await screen.findByText('API indisponível')).toBeInTheDocument()
  })
})
