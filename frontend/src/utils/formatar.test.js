import { describe, expect, it } from 'vitest'
import { formatarData, formatarDataHora, primeiroDiaDoMes } from './formatar.js'

describe('formatarData', () => {
  it('formata datas ISO como dd/mm/aaaa, sem depender do fuso', () => {
    expect(formatarData('2026-07-01')).toBe('01/07/2026')
  })

  it('instante com hora vira a data de Brasília, em qualquer fuso do navegador (issue #24)', () => {
    // 23:30 de 31/10 em Brasília já é 01/11 em UTC.
    expect(formatarData('2026-11-01T02:30:00Z')).toBe('31/10/2026')
    expect(formatarData('2026-10-31T23:30:00-03:00')).toBe('31/10/2026')
    expect(formatarData('2027-01-01T00:00:00Z')).toBe('31/12/2026')
    expect(formatarData('2026-11-01T03:00:00Z')).toBe('01/11/2026') // meia-noite em Brasília
    expect(formatarData('hoje às 3 da tarde T')).toBe('—')
  })

  it('devolve um traço para valor vazio', () => {
    expect(formatarData(null)).toBe('—')
    expect(formatarData('')).toBe('—')
  })
})

describe('formatarDataHora', () => {
  it('formata data e hora em pt-BR', () => {
    expect(formatarDataHora('2026-10-30T15:00:00Z')).toMatch(/^\d{2}\/\d{2}\/\d{4},? \d{2}:\d{2}$/)
  })

  it('mostra sempre o horário de Brasília, não o do navegador nem o UTC (issue #24)', () => {
    expect(formatarDataHora('2026-11-01T02:30:00Z')).toMatch(/^31\/10\/2026,? 23:30$/)
    expect(formatarDataHora('2026-10-31T23:30:00-03:00')).toMatch(/^31\/10\/2026,? 23:30$/)
    expect(formatarDataHora('2026-11-01T03:00:00Z')).toMatch(/^01\/11\/2026,? 00:00$/)
    expect(formatarDataHora('2026-10-30T15:00:00Z')).toMatch(/^30\/10\/2026,? 12:00$/)
  })

  it('tolera vazio e valor inválido', () => {
    expect(formatarDataHora(null)).toBe('—')
    expect(formatarDataHora('não é data')).toBe('—')
  })
})

describe('primeiroDiaDoMes', () => {
  it('é o primeiro dia do mês de Brasília, mesmo quando em UTC já é o mês seguinte (issue #24)', () => {
    expect(primeiroDiaDoMes(new Date('2026-11-01T02:30:00Z'))).toBe('2026-10-01') // 23:30 de 31/10 em Brasília
    expect(primeiroDiaDoMes(new Date('2026-11-01T02:59:59Z'))).toBe('2026-10-01')
    expect(primeiroDiaDoMes(new Date('2026-11-01T03:00:00Z'))).toBe('2026-11-01') // virou o mês
    expect(primeiroDiaDoMes(new Date('2027-01-01T01:00:00Z'))).toBe('2026-12-01') // virada do ano
    expect(primeiroDiaDoMes(new Date('2026-10-15T12:00:00Z'))).toBe('2026-10-01')
  })
})

describe('ambiente de testes', () => {
  it('roda em UTC (não em Brasília), para expor dependência do fuso do navegador', () => {
    expect(new Date('2026-01-01T12:00:00Z').getHours()).toBe(12)
  })
})
