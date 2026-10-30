/**
 * Empresa ativa DESTA ABA.
 *
 * Fica em sessionStorage (isolado por aba) e nunca em localStorage nem na sessão do
 * servidor: com duas abas abertas, trocar a empresa numa delas não pode mudar a outra
 * (D10). O servidor recebe a empresa a cada requisição, no cabeçalho X-Empresa.
 */
const CHAVE = 'freenfse-empresa-ativa'

// Reserva em memória para quando o navegador bloqueia o armazenamento.
let emMemoria = null

function armazenamento() {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function obterEmpresaAtiva() {
  const depositario = armazenamento()
  let bruto = emMemoria
  try {
    if (depositario) bruto = depositario.getItem(CHAVE)
  } catch {
    // usa a reserva em memória
  }
  const id = Number(bruto)
  return Number.isInteger(id) && id > 0 ? id : null
}

export function definirEmpresaAtiva(id) {
  emMemoria = String(id)
  try {
    armazenamento()?.setItem(CHAVE, String(id))
  } catch {
    // mantém só em memória
  }
}

export function limparEmpresaAtiva() {
  emMemoria = null
  try {
    armazenamento()?.removeItem(CHAVE)
  } catch {
    // nada a limpar
  }
}
