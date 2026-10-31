import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import SelectMultiBusca from './SelectMultiBusca.jsx'

afterEach(cleanup)

const OPCOES = [
  { valor: 'nfse.consultar', rotulo: 'nfse.consultar', detalhe: 'Consultar NFS-e' },
  { valor: 'nfse.emitir', rotulo: 'nfse.emitir', detalhe: 'Emitir NFS-e' },
  { valor: 'cadastro.editar', rotulo: 'cadastro.editar', detalhe: 'Editar cadastros' },
]

function Exemplo({ inicial = [] }) {
  const [valores, setValores] = useState(inicial)
  return (
    <>
      <SelectMultiBusca rotulo="Permissões" opcoes={OPCOES} valores={valores} aoMudar={setValores} placeholder="Nenhuma" />
      <output aria-label="marcadas">{valores.join(',')}</output>
    </>
  )
}

const abrir = () => fireEvent.click(screen.getByRole('combobox', { name: 'Permissões' }))
const marcadas = () => screen.getByLabelText('marcadas').textContent

describe('SelectMultiBusca', () => {
  it('marca vários itens sem fechar a lista e mostra etiquetas removíveis', () => {
    render(<Exemplo />)
    abrir()

    fireEvent.mouseDown(screen.getByRole('option', { name: /nfse.emitir/ }))
    fireEvent.mouseDown(screen.getByRole('option', { name: /cadastro.editar/ }))

    expect(screen.getByRole('listbox')).toHaveAttribute('aria-multiselectable', 'true')
    expect(marcadas()).toBe('nfse.emitir,cadastro.editar')
    expect(screen.getByRole('button', { name: 'Remover nfse.emitir' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /nfse.emitir/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('desmarca ao clicar de novo e pelo botão de remover da etiqueta', () => {
    render(<Exemplo inicial={['nfse.emitir', 'nfse.consultar']} />)

    fireEvent.click(screen.getByRole('button', { name: 'Remover nfse.emitir' }))
    expect(marcadas()).toBe('nfse.consultar')

    abrir()
    fireEvent.mouseDown(screen.getByRole('option', { name: /nfse.consultar/ }))
    expect(marcadas()).toBe('')
  })

  it('filtra pelo rótulo e pelo detalhe, sem diferenciar acentos', () => {
    render(<Exemplo />)
    abrir()

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'EDITAR' } })

    const opcoes = within(screen.getByRole('listbox')).getAllByRole('option')
    expect(opcoes).toHaveLength(1)
    expect(opcoes[0]).toHaveTextContent('cadastro.editar')
  })

  it('marca pelo teclado: setas e Enter; Escape fecha', () => {
    render(<Exemplo />)
    abrir()
    const busca = screen.getByRole('searchbox')

    fireEvent.keyDown(busca, { key: 'ArrowDown' })
    fireEvent.keyDown(busca, { key: 'Enter' })
    expect(marcadas()).toBe('nfse.emitir')

    fireEvent.keyDown(busca, { key: 'Escape' })
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('mostra o placeholder sem seleção e a mensagem de vazio sem resultado', () => {
    render(<Exemplo />)
    expect(screen.getByRole('combobox', { name: 'Permissões' })).toHaveTextContent('Nenhuma')

    abrir()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } })

    expect(screen.getByText('Nenhum resultado')).toBeInTheDocument()
  })
})
