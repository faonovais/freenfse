import { afterEach, describe, expect, it, vi } from 'vitest'
import { definirEmpresaAtiva, limparEmpresaAtiva } from './empresaAtiva.js'
import { baixarBinario, http } from './http.js'

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

  it('envia arquivos (FormData) sem fixar o Content-Type, para o navegador incluir o boundary', async () => {
    const fetchFalso = simular()
    const formulario = new FormData()
    formulario.append('arquivo', new File(['x'], 'logo.png'))

    await http('/api/fiscal/logo/claro/', { metodo: 'PUT', corpo: formulario })

    const opcoes = fetchFalso.mock.calls[0][1]
    expect(opcoes.body).toBe(formulario)
    expect(opcoes.headers).not.toHaveProperty('Content-Type')
  })
})

describe('baixarBinario', () => {
  it('baixa o arquivo com o X-Empresa da aba e devolve o blob', async () => {
    const blob = new Blob(['x'])
    const fetchFalso = simular({ ok: true, status: 200, blob: async () => blob })
    definirEmpresaAtiva(8)

    const resposta = await baixarBinario('/api/fiscal/logo/claro/')

    expect(resposta).toEqual({ ok: true, status: 200, blob })
    expect(fetchFalso.mock.calls[0][1].headers['X-Empresa']).toBe('8')
  })

  it('devolve ok=false sem blob quando o servidor recusa, e status 0 sem rede', async () => {
    simular({ ok: false, status: 404, blob: async () => new Blob([]) })
    expect(await baixarBinario('/x')).toEqual({ ok: false, status: 404, blob: null })

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('sem rede')))
    expect(await baixarBinario('/x')).toEqual({ ok: false, status: 0, blob: null })
  })
})
