import { http } from './http.js'

const BASE = '/_allauth/browser/v1'

// Consultar a sessão também faz o servidor emitir o cookie CSRF usado nas escritas.
export const sessao = () => http(`${BASE}/auth/session`, { semEmpresa: true })

export const configuracao = () => http(`${BASE}/config`, { semEmpresa: true })

export const entrar = (email, senha) =>
  http(`${BASE}/auth/login`, { metodo: 'POST', corpo: { email, password: senha }, semEmpresa: true })

export const autenticar2fa = (codigo) =>
  http(`${BASE}/auth/2fa/authenticate`, { metodo: 'POST', corpo: { code: codigo }, semEmpresa: true })

export const sair = () => http(`${BASE}/auth/session`, { metodo: 'DELETE', semEmpresa: true })

export const reautenticar = (senha) =>
  http(`${BASE}/auth/reauthenticate`, { metodo: 'POST', corpo: { password: senha }, semEmpresa: true })

// 2FA por aplicativo (TOTP). Sem 2FA, o GET responde 404 com o segredo em `meta`.
export const statusTotp = () => http(`${BASE}/account/authenticators/totp`, { semEmpresa: true })

export const ativarTotp = (codigo) =>
  http(`${BASE}/account/authenticators/totp`, { metodo: 'POST', corpo: { code: codigo }, semEmpresa: true })

export const codigosDeRecuperacao = () =>
  http(`${BASE}/account/authenticators/recovery-codes`, { semEmpresa: true })

export const eu = () => http('/api/eu/', { semEmpresa: true })

/**
 * Login social: o allauth exige uma navegação de formulário (POST) para o provedor.
 * Depois do consentimento o provedor devolve o usuário para a SPA.
 */
export function iniciarLoginSocial(provedor, documento = document) {
  const cookie = documento.cookie.split('; ').find((item) => item.startsWith('csrftoken='))
  const formulario = documento.createElement('form')
  formulario.method = 'POST'
  formulario.action = `${BASE}/auth/provider/redirect`
  const campos = {
    provider: provedor,
    callback_url: '/',
    process: 'login',
    csrfmiddlewaretoken: cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : '',
  }
  for (const [nome, valor] of Object.entries(campos)) {
    const entrada = documento.createElement('input')
    entrada.type = 'hidden'
    entrada.name = nome
    entrada.value = valor
    formulario.appendChild(entrada)
  }
  documento.body.appendChild(formulario)
  formulario.submit()
}
