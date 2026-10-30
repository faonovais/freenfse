import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { limparEmpresaAtiva } from '../api/empresaAtiva.js'
import { respostaEu, SESSAO_AUTENTICADA } from '../testes/apiFalsa.js'
import { BASE, montarApp, rotasAnonimo, rotasAutenticado } from '../testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  vi.restoreAllMocks()
})

const preencher = (email, senha) => {
  fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Senha'), { target: { value: senha } })
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
}

const PROVEDOR_GOOGLE = { id: 'google', name: 'Google' }
const configuracaoCom = (provedores) => ({
  status: 200,
  dados: { data: { socialaccount: { providers: provedores } } },
})

describe('login', () => {
  it('entra com e-mail e senha e abre a aplicação', async () => {
    let logado = false
    const { chamadas } = montarApp({
      rota: '/login',
      rotasApi: {
        ...rotasAnonimo(),
        [`GET ${BASE}/auth/session`]: () => (logado ? SESSAO_AUTENTICADA : { status: 401, dados: {} }),
        [`POST ${BASE}/auth/login`]: () => {
          logado = true
          return { status: 200, dados: {} }
        },
        'GET /api/eu/': respostaEu(),
      },
    })
    await screen.findByLabelText('E-mail')

    preencher('ana@example.com', 'senha-de-teste-123')

    expect(await screen.findByLabelText('Empresa em operação')).toBeInTheDocument()
    const envio = chamadas.find((chamada) => chamada.caminho === `${BASE}/auth/login`)
    expect(envio.corpo).toEqual({ email: 'ana@example.com', password: 'senha-de-teste-123' })
    expect(envio.cabecalhos).not.toHaveProperty('X-Empresa')
  })

  it('mostra erro em linguagem simples quando a senha está errada', async () => {
    montarApp({
      rota: '/login',
      rotasApi: {
        ...rotasAnonimo(),
        [`POST ${BASE}/auth/login`]: {
          status: 400,
          dados: { errors: [{ code: 'email_password_mismatch', message: 'x', param: 'password' }] },
        },
      },
    })
    await screen.findByLabelText('E-mail')

    preencher('ana@example.com', 'errada')

    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
    expect(screen.getByLabelText('E-mail')).toBeInTheDocument()
  })

  it('mostra o aviso de bloqueio por tentativas excessivas', async () => {
    montarApp({
      rota: '/login',
      rotasApi: {
        ...rotasAnonimo(),
        [`POST ${BASE}/auth/login`]: {
          status: 400,
          dados: { errors: [{ code: 'too_many_login_attempts', message: 'x' }] },
        },
      },
    })
    await screen.findByLabelText('E-mail')

    preencher('ana@example.com', 'errada')

    expect(await screen.findByRole('alert')).toHaveTextContent(/Muitas tentativas/)
  })

  it('com 2FA ativo, pede o código e conclui o login com ele', async () => {
    let logado = false
    const { chamadas } = montarApp({
      rota: '/login',
      rotasApi: {
        ...rotasAnonimo(),
        [`GET ${BASE}/auth/session`]: () => (logado ? SESSAO_AUTENTICADA : { status: 401, dados: {} }),
        [`POST ${BASE}/auth/login`]: {
          status: 401,
          dados: { status: 401, data: { flows: [{ id: 'mfa_authenticate' }] } },
        },
        [`POST ${BASE}/auth/2fa/authenticate`]: (chamada) => {
          if (chamada.corpo.code !== '123456') return { status: 400, dados: { errors: [{ code: 'incorrect_code', message: 'x' }] } }
          logado = true
          return { status: 200, dados: {} }
        },
        'GET /api/eu/': respostaEu(),
      },
    })
    await screen.findByLabelText('E-mail')
    preencher('ana@example.com', 'senha-de-teste-123')

    const campo = await screen.findByLabelText('Código de verificação')
    expect(screen.queryByLabelText('Senha')).not.toBeInTheDocument()
    fireEvent.change(campo, { target: { value: '000000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verificar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Código incorreto')

    fireEvent.change(screen.getByLabelText('Código de verificação'), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verificar' }))

    expect(await screen.findByLabelText('Empresa em operação')).toBeInTheDocument()
    expect(chamadas.filter((chamada) => chamada.caminho === `${BASE}/auth/2fa/authenticate`)).toHaveLength(2)
  })

  it('só oferece o botão do Google quando o servidor habilita o provedor', async () => {
    montarApp({ rota: '/login', rotasApi: rotasAnonimo() })
    await screen.findByLabelText('E-mail')
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Entrar com Google' })).not.toBeInTheDocument())

    cleanup()
    montarApp({
      rota: '/login',
      rotasApi: { ...rotasAnonimo(), [`GET ${BASE}/config`]: configuracaoCom([PROVEDOR_GOOGLE]) },
    })

    expect(await screen.findByRole('button', { name: 'Entrar com Google' })).toBeInTheDocument()
  })

  it('o botão do Google inicia o login social por formulário POST', async () => {
    const enviar = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})
    montarApp({
      rota: '/login',
      rotasApi: { ...rotasAnonimo(), [`GET ${BASE}/config`]: configuracaoCom([PROVEDOR_GOOGLE]) },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Entrar com Google' }))

    expect(enviar).toHaveBeenCalledTimes(1)
    const formulario = document.querySelector('form[action$="/auth/provider/redirect"]')
    expect(new FormData(formulario).get('provider')).toBe('google')
  })

  it.each([
    ['nao_cadastrado', /não está cadastrado/],
    ['dominio_nao_permitido', /domínio/],
    ['email_nao_verificado', /não confirmou/],
    ['usuario_inativo', /desativado/],
    ['qualquer_outro', /Não foi possível entrar com o provedor/],
  ])('mostra o motivo da recusa do login social (?erro=%s)', async (motivo, texto) => {
    montarApp({ rota: `/login?erro=${motivo}`, rotasApi: rotasAnonimo() })

    expect(await screen.findByRole('alert')).toHaveTextContent(texto)
  })

  it('não oferece cadastro: o acesso é criado pelo administrador', async () => {
    montarApp({ rota: '/login', rotasApi: rotasAnonimo() })
    await screen.findByLabelText('E-mail')

    expect(screen.queryByText(/criar conta|cadastre-se|registrar/i)).not.toBeInTheDocument()
    expect(screen.getByText(/cadastrados pelo administrador/)).toBeInTheDocument()
  })

  it('quem já está logado não vê o login', async () => {
    const { roteador } = montarApp({ rota: '/login', rotasApi: rotasAutenticado() })

    expect(await screen.findByLabelText('Empresa em operação')).toBeInTheDocument()
    expect(roteador.state.location.pathname).toBe('/')
  })
})
