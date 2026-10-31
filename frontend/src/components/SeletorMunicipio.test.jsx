import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { limparEmpresaAtiva } from '../api/empresaAtiva.js'
import { instalarApiFalsa } from '../testes/apiFalsa.js'
import SeletorMunicipio from './SeletorMunicipio.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  vi.unstubAllGlobals()
})

const BALSAS = { codigo: '2101400', nome: 'Balsas', uf: 'MA' }

function montar({ valor = '', aoMudar = vi.fn(), erro, rotas } = {}) {
  const api = instalarApiFalsa({
    'GET /api/cadastros/municipios/': (chamada) => ({
      status: 200,
      dados: chamada.url.includes('codigo=2101400') || chamada.url.includes('busca=bal') ? [BALSAS] : [],
    }),
    ...rotas,
  })
  render(<SeletorMunicipio rotulo="Município" valor={valor} aoMudar={aoMudar} erro={erro} />)
  return { ...api, aoMudar }
}

const digitar = (texto) => fireEvent.change(screen.getByRole('combobox', { name: 'Município' }), { target: { value: texto } })

describe('SeletorMunicipio', () => {
  it('não consulta o servidor com menos de 2 letras', async () => {
    const { chamadas } = montar()

    digitar('b')
    await new Promise((resolver) => setTimeout(resolver, 400))

    expect(chamadas).toEqual([])
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('busca pelo nome e devolve o código IBGE ao escolher', async () => {
    const { aoMudar, chamadas } = montar()

    digitar('bal')
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Balsas\/MA/ }))

    expect(aoMudar).toHaveBeenCalledWith('2101400')
    expect(chamadas[0].url).toContain('busca=bal')
    expect(screen.getByText(/IBGE 2101400/)).toBeInTheDocument()
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('avisa quando nenhum município é encontrado', async () => {
    montar()

    digitar('zzz')

    expect(await screen.findByText('Nenhum município encontrado')).toBeInTheDocument()
  })

  it('mostra o nome do município que já estava gravado (só o código é guardado)', async () => {
    const { chamadas } = montar({ valor: '2101400' })

    expect(await screen.findByText(/Balsas\/MA/)).toBeInTheDocument()
    expect(chamadas[0].url).toContain('codigo=2101400')
  })

  it('exibe a mensagem de erro ligada ao campo', () => {
    montar({ erro: 'Informe o município.' })

    const campo = screen.getByRole('combobox', { name: 'Município' })
    expect(campo).toHaveAttribute('aria-invalid', 'true')
    expect(campo).toHaveAccessibleDescription('Informe o município.')
  })

  it('o envio da busca leva o X-Empresa da aba', async () => {
    window.sessionStorage.setItem('freenfse-empresa-ativa', '4')
    const { chamadas } = montar()

    digitar('bal')

    await waitFor(() => expect(chamadas.length).toBe(1))
    expect(chamadas[0].cabecalhos['X-Empresa']).toBe('4')
  })
})
