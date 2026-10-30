/**
 * Consulta a versão da API (GET /api/versao/).
 * Retorna { ok, status, dados } — mesmo formato do cliente HTTP que entra na Fase 1.
 */
export async function buscarVersaoApi() {
  try {
    const resposta = await fetch('/api/versao/', { headers: { Accept: 'application/json' } })
    const dados = resposta.ok ? await resposta.json() : null
    return { ok: resposta.ok, status: resposta.status, dados }
  } catch {
    return { ok: false, status: 0, dados: null }
  }
}
