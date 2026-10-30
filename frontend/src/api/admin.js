import { http } from './http.js'

const BASE = '/api/admin-global'

function consulta(parametros) {
  const limpos = Object.entries(parametros ?? {}).filter(([, valor]) => valor !== '' && valor != null)
  return limpos.length ? `?${new URLSearchParams(limpos)}` : ''
}

const recurso = (nome) => ({
  listar: (filtros) => http(`${BASE}/${nome}/${consulta(filtros)}`, { semEmpresa: true }),
  criar: (corpo) => http(`${BASE}/${nome}/`, { metodo: 'POST', corpo, semEmpresa: true }),
  alterar: (id, corpo) => http(`${BASE}/${nome}/${id}/`, { metodo: 'PATCH', corpo, semEmpresa: true }),
})

export const empresas = recurso('empresas')
export const usuarios = recurso('usuarios')
export const vinculos = recurso('vinculos')
export const permissoes = () => http(`${BASE}/permissoes/`, { semEmpresa: true })
