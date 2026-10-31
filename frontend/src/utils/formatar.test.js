import { describe, expect, it } from 'vitest'
import { formatarData, formatarDataHora } from './formatar.js'

describe('formatarData', () => {
  it('formata datas ISO como dd/mm/aaaa, sem depender do fuso', () => {
    expect(formatarData('2026-07-01')).toBe('01/07/2026')
    expect(formatarData('2027-01-01T00:00:00Z')).toBe('01/01/2027')
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

  it('tolera vazio e valor inválido', () => {
    expect(formatarDataHora(null)).toBe('—')
    expect(formatarDataHora('não é data')).toBe('—')
  })
})
