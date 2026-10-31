import { afterEach, describe, expect, it, vi } from 'vitest'
import { iniciarLoginSocial } from './auth.js'

afterEach(() => {
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  document.body.innerHTML = ''
})

describe('login social', () => {
  it('envia um formulário POST ao allauth com o provedor, o retorno e o token CSRF', () => {
    document.cookie = 'csrftoken=token-de-teste'
    const enviar = vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {})

    iniciarLoginSocial('google')

    const formulario = document.querySelector('form')
    expect(formulario.method).toBe('post')
    expect(formulario.getAttribute('action')).toBe('/_allauth/browser/v1/auth/provider/redirect')
    const campos = Object.fromEntries(new FormData(formulario))
    expect(campos).toEqual({
      provider: 'google',
      callback_url: '/',
      process: 'login',
      csrfmiddlewaretoken: 'token-de-teste',
    })
    expect(enviar).toHaveBeenCalledTimes(1)
    enviar.mockRestore()
  })
})
