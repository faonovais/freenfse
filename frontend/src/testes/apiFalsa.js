import { vi } from 'vitest'

// JSON vira objeto; envio de arquivo (FormData) vira { campo: valor|File }.
function corpoDe(corpo) {
  if (!corpo) return undefined
  if (corpo instanceof FormData) return Object.fromEntries(corpo.entries())
  return JSON.parse(corpo)
}

/**
 * API falsa para os testes: `rotas` mapeia "MÉTODO /caminho" (sem query) para uma resposta
 * `{ status, dados }` ou para uma função `(chamada) => { status, dados }`.
 * Devolve o `fetch` falso e a lista de chamadas feitas (com cabeçalhos e corpo).
 */
export function instalarApiFalsa(rotas) {
  const chamadas = []
  const fetchFalso = vi.fn(async (url, opcoes = {}) => {
    const metodo = opcoes.method ?? 'GET'
    const caminho = String(url).split('?')[0]
    const chamada = {
      metodo,
      url: String(url),
      caminho,
      cabecalhos: opcoes.headers ?? {},
      corpo: corpoDe(opcoes.body),
    }
    chamadas.push(chamada)
    const tratador = rotas[`${metodo} ${caminho}`]
    const resposta = typeof tratador === 'function' ? tratador(chamada) : (tratador ?? { status: 404, dados: null })
    return {
      ok: resposta.status < 400,
      status: resposta.status,
      json: async () => resposta.dados,
      blob: async () => resposta.blob,
    }
  })
  vi.stubGlobal('fetch', fetchFalso)
  return { fetchFalso, chamadas }
}

export const EMPRESA_A = {
  id: 1,
  razao_social: 'Empresa Alfa Ltda',
  cnpj: '11222333000181',
  cnpj_formatado: '11.222.333/0001-81',
  perfil: 'administrador',
  permissoes: ['nfse.consultar', 'nfse.emitir'],
}

export const EMPRESA_B = {
  id: 2,
  razao_social: 'Empresa Beta S.A.',
  cnpj: '11444777000161',
  cnpj_formatado: '11.444.777/0001-61',
  perfil: 'consulta',
  permissoes: ['nfse.consultar'],
}

export function respostaEu({ master = false, empresas = [EMPRESA_A, EMPRESA_B], mfa = { ativo: true, obrigatorio: false } } = {}) {
  return {
    status: 200,
    dados: { id: 7, email: 'ana@example.com', nome: 'Ana', is_master: master, mfa, empresas },
  }
}

export const SESSAO_AUTENTICADA = { status: 200, dados: { status: 200, meta: { is_authenticated: true } } }
export const SESSAO_ANONIMA = { status: 401, dados: { status: 401, meta: { is_authenticated: false } } }
export const IDENTIDADE_PADRAO = {
  status: 200,
  dados: {
    ambiente: 'producao',
    ambiente_rotulo: 'Produção (notas com valor fiscal)',
    logo: {},
    certificado: { existe: true, vencido: false, dias_para_vencer: 200, faixa_alerta: null },
  },
}
export const VERSAO_FALSA = { status: 200, dados: { versao: '9.9.9' } }

/** Empresa em que o usuário tem todas as permissões de cadastro e de configuração. */
export const EMPRESA_ADMIN = {
  ...EMPRESA_A,
  perfil: 'administrador',
  permissoes: ['nfse.consultar', 'cadastro.consultar', 'cadastro.editar', 'config.consultar', 'config.editar'],
}

/** Empresa em que o usuário só consulta (cadastros e configuração). */
export const EMPRESA_SO_CONSULTA = {
  ...EMPRESA_B,
  perfil: 'consulta',
  permissoes: ['nfse.consultar', 'cadastro.consultar', 'config.consultar'],
}
