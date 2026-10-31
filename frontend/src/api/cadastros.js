import { consulta } from './consulta.js'
import { http } from './http.js'

// Rotas de empresa: o X-Empresa da aba vai em todas as chamadas (ver http.js).
const BASE = '/api/cadastros'

const recurso = (nome) => ({
  listar: (filtros) => http(`${BASE}/${nome}/${consulta(filtros)}`),
  obter: (id) => http(`${BASE}/${nome}/${id}/`),
  criar: (corpo) => http(`${BASE}/${nome}/`, { metodo: 'POST', corpo }),
  alterar: (id, corpo) => http(`${BASE}/${nome}/${id}/`, { metodo: 'PATCH', corpo }),
})

export const pessoas = recurso('pessoas')
export const servicos = {
  ...recurso('servicos'),
  vigente: (filtros) => http(`${BASE}/servicos/vigente/${consulta(filtros)}`),
}
export const perfis = {
  listar: () => http(`${BASE}/perfis/`),
  criar: (corpo) => http(`${BASE}/perfis/`, { metodo: 'POST', corpo }),
}

// Copiar cadastro de outra empresa (cópia explícita; não cria vínculo).
export const copia = {
  listarDaOrigem: (empresaOrigem, busca) =>
    http(`${BASE}/copia/pessoas/${consulta({ empresa: empresaOrigem, busca })}`),
  copiar: (corpo) => http(`${BASE}/copia/pessoas/`, { metodo: 'POST', corpo }),
}

// Municípios do IBGE (dado público) para os campos de endereço.
export const municipios = {
  buscar: (busca, uf) => http(`${BASE}/municipios/${consulta({ busca, uf })}`),
  obterPorCodigo: (codigo) => http(`${BASE}/municipios/${consulta({ codigo })}`),
}
