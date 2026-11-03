import { consulta } from './consulta.js'
import { http } from './http.js'

// Rotas de empresa: o X-Empresa da aba vai em todas as chamadas (ver http.js).
const BASE = '/api/agendamentos'

/** Listas dos formulários: frequências, modelos ativos, responsáveis possíveis, variáveis do texto. */
export const opcoes = () => http(`${BASE}/opcoes/`)

/** Modelos de NFS-e: a nota de referência de onde saem os rascunhos. */
export const modelos = {
  listar: () => http(`${BASE}/modelos/`),
  obter: (id) => http(`${BASE}/modelos/${id}/`),
  criar: (corpo) => http(`${BASE}/modelos/`, { metodo: 'POST', corpo }),
  alterar: (id, corpo) => http(`${BASE}/modelos/${id}/`, { metodo: 'PATCH', corpo }),
  /** Mostra como ficaria um rascunho gerado hoje (sem gravar nada). */
  previa: (id) => http(`${BASE}/modelos/${id}/previa/`, { metodo: 'POST' }),
  /** Cria agora um rascunho com a cópia dos dados do modelo. Não emite nada. */
  gerarRascunho: (id) => http(`${BASE}/modelos/${id}/gerar-rascunho/`, { metodo: 'POST' }),
}

/** Agendamentos: repetem um modelo e geram rascunhos para aprovação. */
export const agendamentos = {
  listar: () => http(`${BASE}/agendamentos/`),
  obter: (id) => http(`${BASE}/agendamentos/${id}/`),
  criar: (corpo) => http(`${BASE}/agendamentos/`, { metodo: 'POST', corpo }),
  alterar: (id, corpo) => http(`${BASE}/agendamentos/${id}/`, { metodo: 'PATCH', corpo }),
  suspender: (id, motivo) =>
    http(`${BASE}/agendamentos/${id}/suspender/`, { metodo: 'POST', corpo: { motivo } }),
  reativar: (id) => http(`${BASE}/agendamentos/${id}/reativar/`, { metodo: 'POST' }),
  /** Próximas datas de uma regra, antes de salvar. */
  previaDeDatas: (corpo) =>
    http(`${BASE}/agendamentos/previa-datas/`, { metodo: 'POST', corpo }),
}

/** Histórico do que o dispatcher fez em cada data. */
export const execucoes = {
  listar: (filtros) => http(`${BASE}/execucoes/${consulta(filtros)}`),
}

/** Rascunhos esperando decisão: aprovar (individual ou em lote) ou descartar. */
export const rascunhos = {
  listar: (filtros) => http(`${BASE}/rascunhos/${consulta(filtros)}`),
  aprovar: (ids) => http(`${BASE}/rascunhos/aprovar/`, { metodo: 'POST', corpo: { ids } }),
  descartar: (id, motivo) =>
    http(`${BASE}/rascunhos/${id}/descartar/`, { metodo: 'POST', corpo: { motivo } }),
  /** Situação atual das notas (para acompanhar o lote aprovado). */
  situacao: (ids) => http(`${BASE}/rascunhos/situacao/${consulta({ ids: ids.join(',') })}`),
}
