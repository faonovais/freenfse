import { describe, expect, it } from 'vitest'
import { errosPorCampo, mensagemErro } from './erros.js'

describe('mensagemErro', () => {
  it('traduz o código do middleware de empresa', () => {
    const resposta = { status: 403, dados: { codigo: 'sem_acesso_a_empresa', detalhe: 'x' } }

    expect(mensagemErro(resposta)).toBe('Você não tem acesso a esta empresa.')
  })

  it('traduz erros do allauth pelo código', () => {
    const resposta = { status: 400, dados: { errors: [{ code: 'email_password_mismatch', message: 'x' }] } }

    expect(mensagemErro(resposta)).toBe('E-mail ou senha incorretos.')
  })

  it('traduz o bloqueio por tentativas de login', () => {
    const resposta = { status: 400, dados: { errors: [{ code: 'too_many_login_attempts', message: 'x' }] } }

    expect(mensagemErro(resposta)).toMatch(/Muitas tentativas/)
  })

  it('usa o detail do DRF e a lista de erros de campo', () => {
    expect(mensagemErro({ status: 403, dados: { detail: 'Sem permissão.' } })).toBe('Sem permissão.')
    expect(mensagemErro({ status: 400, dados: { cnpj: ['CNPJ inválido.'] } })).toBe('CNPJ inválido.')
  })

  it('trata falha de rede e erro de servidor sem expor detalhes', () => {
    expect(mensagemErro({ status: 0, dados: null })).toMatch(/Sem conexão/)
    expect(mensagemErro({ status: 500, dados: { trace: 'segredo' } })).toBe('Erro no servidor. Tente novamente em instantes.')
  })
})

describe('errosPorCampo', () => {
  it('junta as mensagens de cada campo', () => {
    const resposta = { status: 400, dados: { cnpj: ['a', 'b'], razao_social: ['c'] } }

    expect(errosPorCampo(resposta)).toEqual({ cnpj: 'a b', razao_social: 'c' })
  })

  it('ignora erros que não são de campo', () => {
    expect(errosPorCampo({ status: 403, dados: { detail: 'x' } })).toEqual({})
    expect(errosPorCampo({ status: 400, dados: { errors: [] } })).toEqual({})
    expect(errosPorCampo({ status: 0, dados: null })).toEqual({})
  })
})
