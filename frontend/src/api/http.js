import { obterEmpresaAtiva } from './empresaAtiva.js'

const METODOS_SEM_ESCRITA = new Set(['GET', 'HEAD', 'OPTIONS'])

function lerCookie(nome) {
  const par = document.cookie.split('; ').find((item) => item.startsWith(`${nome}=`))
  return par ? decodeURIComponent(par.slice(nome.length + 1)) : null
}

/**
 * Cliente HTTP único da SPA. NUNCA lança: devolve `{ ok, status, dados }`.
 *
 * - envia o token CSRF (cookie `csrftoken`) nas escritas;
 * - envia a empresa ativa desta aba em `X-Empresa` (a menos que `semEmpresa`);
 * - `status` 0 indica falha de rede.
 */
export async function http(url, { metodo = 'GET', corpo, cabecalhos = {}, semEmpresa = false } = {}) {
  const headers = { Accept: 'application/json', ...cabecalhos }
  if (!METODOS_SEM_ESCRITA.has(metodo)) {
    const csrf = lerCookie('csrftoken')
    if (csrf) headers['X-CSRFToken'] = csrf
  }
  const empresa = obterEmpresaAtiva()
  if (empresa && !semEmpresa) headers['X-Empresa'] = String(empresa)

  let body
  if (corpo instanceof FormData) {
    body = corpo // envio de arquivo: o navegador define o Content-Type com o limite (boundary)
  } else if (corpo !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(corpo)
  }

  try {
    const resposta = await fetch(url, { method: metodo, headers, body, credentials: 'same-origin' })
    let dados = null
    try {
      dados = await resposta.json()
    } catch {
      // resposta sem corpo JSON (ex.: 204)
    }
    return { ok: resposta.ok, status: resposta.status, dados }
  } catch {
    return { ok: false, status: 0, dados: null }
  }
}

/**
 * Baixa um arquivo binário (por exemplo, o logo) com os mesmos cabeçalhos do `http()`.
 * Um `<img src>` não enviaria o X-Empresa, por isso a imagem é buscada aqui e exibida por URL local.
 * NUNCA lança: devolve `{ ok, status, blob }`.
 */
export async function baixarBinario(url) {
  const headers = {}
  const empresa = obterEmpresaAtiva()
  if (empresa) headers['X-Empresa'] = String(empresa)
  try {
    const resposta = await fetch(url, { method: 'GET', headers, credentials: 'same-origin' })
    return { ok: resposta.ok, status: resposta.status, blob: resposta.ok ? await resposta.blob() : null }
  } catch {
    return { ok: false, status: 0, blob: null }
  }
}
