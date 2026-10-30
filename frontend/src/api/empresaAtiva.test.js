import { afterEach, describe, expect, it } from 'vitest'
import { definirEmpresaAtiva, limparEmpresaAtiva, obterEmpresaAtiva } from './empresaAtiva.js'

afterEach(() => {
  limparEmpresaAtiva()
  window.localStorage.clear()
})

describe('empresa ativa por aba', () => {
  it('guarda a empresa em sessionStorage, nunca em localStorage', () => {
    definirEmpresaAtiva(5)

    expect(obterEmpresaAtiva()).toBe(5)
    expect(window.sessionStorage.getItem('freenfse-empresa-ativa')).toBe('5')
    expect(window.localStorage.length).toBe(0)
  })

  it('limpa a empresa', () => {
    definirEmpresaAtiva(5)
    limparEmpresaAtiva()

    expect(obterEmpresaAtiva()).toBeNull()
  })

  it.each(['abc', '0', '-3', '1.5', ''])('ignora valor inválido %j', (valor) => {
    window.sessionStorage.setItem('freenfse-empresa-ativa', valor)

    expect(obterEmpresaAtiva()).toBeNull()
  })
})
