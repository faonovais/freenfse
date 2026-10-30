import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SelectBusca from './SelectBusca.jsx'

afterEach(cleanup)

const OPCOES = [
  { valor: 1, rotulo: 'Fazenda São João', detalhe: '11.222.333/0001-81' },
  { valor: 2, rotulo: 'Agrícola Beta', detalhe: '11.444.777/0001-61' },
  { valor: 3, rotulo: 'Comercial Gama', detalhe: '45.723.174/0001-10' },
]

function montar(propriedades = {}) {
  const aoMudar = vi.fn()
  render(<SelectBusca rotulo="Empresa" opcoes={OPCOES} valor={null} aoMudar={aoMudar} {...propriedades} />)
  return aoMudar
}

const abrir = () => fireEvent.click(screen.getByRole('combobox', { name: 'Empresa' }))
const opcoesVisiveis = () => within(screen.getByRole('listbox')).queryAllByRole('option')

describe('SelectBusca', () => {
  it('mostra o placeholder e o rótulo da opção selecionada', () => {
    montar()
    expect(screen.getByRole('combobox', { name: 'Empresa' })).toHaveTextContent('Selecione…')

    cleanup()
    montar({ valor: 2 })
    expect(screen.getByRole('combobox', { name: 'Empresa' })).toHaveTextContent('Agrícola Beta')
  })

  it('lista todas as opções ao abrir', () => {
    montar()

    abrir()

    expect(opcoesVisiveis()).toHaveLength(3)
    expect(screen.getByRole('combobox', { name: 'Empresa' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('filtra sem diferenciar maiúsculas nem acentos', () => {
    montar()
    abrir()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Buscar Empresa' }), { target: { value: 'sao joao' } })

    expect(opcoesVisiveis()).toHaveLength(1)
    expect(opcoesVisiveis()[0]).toHaveTextContent('Fazenda São João')
  })

  it('também filtra pelo detalhe (CNPJ)', () => {
    montar()
    abrir()

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '0001-61' } })

    expect(opcoesVisiveis()).toHaveLength(1)
    expect(opcoesVisiveis()[0]).toHaveTextContent('Agrícola Beta')
  })

  it('avisa quando nada é encontrado', () => {
    montar()
    abrir()

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })

    expect(screen.getByText('Nenhum resultado')).toBeInTheDocument()
  })

  it('seleciona com o clique e fecha a lista', () => {
    const aoMudar = montar()
    abrir()

    fireEvent.mouseDown(screen.getByRole('option', { name: /Comercial Gama/ }))

    expect(aoMudar).toHaveBeenCalledWith(3)
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('seleciona pelo teclado: setas e Enter', () => {
    const aoMudar = montar()
    abrir()
    const busca = screen.getByRole('searchbox')

    fireEvent.keyDown(busca, { key: 'ArrowDown' })
    fireEvent.keyDown(busca, { key: 'ArrowDown' })
    fireEvent.keyDown(busca, { key: 'ArrowUp' })
    fireEvent.keyDown(busca, { key: 'Enter' })

    expect(aoMudar).toHaveBeenCalledWith(2)
  })

  it('Escape fecha sem selecionar', () => {
    const aoMudar = montar()
    abrir()

    fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Escape' })

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(aoMudar).not.toHaveBeenCalled()
  })

  it('clicar fora fecha a lista', () => {
    montar()
    abrir()

    fireEvent.mouseDown(document.body)

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('não dispara aoMudar ao escolher a opção já selecionada', () => {
    const aoMudar = montar({ valor: 1 })
    abrir()

    fireEvent.mouseDown(screen.getByRole('option', { name: /Fazenda São João/ }))

    expect(aoMudar).not.toHaveBeenCalled()
  })

  it('desabilitado não abre', () => {
    montar({ desabilitado: true })

    abrir()

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
