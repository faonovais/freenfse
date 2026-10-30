import { afterEach, describe, expect, it, vi } from 'vitest'
import { definirEmpresaAtiva, limparEmpresaAtiva } from './empresaAtiva.js'
import { http } from './http.js'

afterEach(() => {
  limparEmpresaAtiva()
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

function simular(resposta = { ok: true, status: 200, json: async () => ({ a: 1 }) }) {
  const fetchFalso = vi.fn().mockResolvedValue(resposta)
  vi.stubGlobal('fetch', fetchFalso)
  return fetchFalso
}

describe('cliente HTTP', () => {
  it('envia a empresa ativa desta aba em X-Empresa', async () => {
    const fetchFalso = simular()
    definirEmpresaAtiva(3)

    await http('/api/algo/')

    expect(fetchFalso.mock.calls[0][1].headers['X-Empresa']).toBe('3')
  })

  it('não envia X-Empresa quando a chamada é global', async () => {
    const fetchFalso = simular()
    definirEmpresaAtiva(3)

    await http('/api/eu/', { semEmpresa: true })

    expect(fetchFalso.mock.calls[0][1].headers).not.toHaveProperty('X-Empresa')
  })

  it('envia o token CSRF nas escritas e não nas leituras', async () => {
    const fetchFalso = simular()
    document.cookie = 'csrftoken=token-de-teste'

    await http('/api/x/', { metodo: 'POST', corpo: { a: 1 } })
    await http('/api/x/')

    expect(fetchFalso.mock.calls[0][1].headers['X-CSRFToken']).toBe('token-de-teste')
    expect(fetchFalso.mock.calls[0][1].body).toBe('{"a":1}')
    expect(fetchFalso.mock.calls[1][1].headers).not.toHaveProperty('X-CSRFToken')
  })

  it('devolve { ok, status, dados } e usa os cookies da sessão', async () => {
    const fetchFalso = simular()

    const resposta = await http('/api/x/')

    expect(resposta).toEqual({ ok: true, status: 200, dados: { a: 1 } })
    expect(fetchFalso.mock.calls[0][1].credentials).toBe('same-origin')
  })

  it('não lança em falha de rede: devolve status 0', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('sem rede')))

    await expect(http('/api/x/')).resolves.toEqual({ ok: false, status: 0, dados: null })
  })

  it('aceita resposta sem corpo JSON', async () => {
    simular({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error('sem corpo')
      },
    })

    await expect(http('/api/x/', { metodo: 'DELETE' })).resolves.toEqual({ ok: true, status: 204, dados: null })
  })
})
