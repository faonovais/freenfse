import { consulta } from './consulta.js'
import { baixarBinario, http } from './http.js'

const BASE = '/api/fiscal'

/** Ambiente, versões dos logos e situação resumida do certificado (todos os vinculados). */
export const identidade = () => http(`${BASE}/identidade/`)

export const parametros = {
  obter: () => http(`${BASE}/parametros/`),
  alterar: (corpo) => http(`${BASE}/parametros/`, { metodo: 'PATCH', corpo }),
  verificarConvenio: () => http(`${BASE}/parametros/verificar-convenio/`, { metodo: 'POST' }),
}

export const certificado = {
  obter: () => http(`${BASE}/certificado/`),
  /** Envia o .pfx e a senha (multipart). A senha não é guardada em nenhum estado da tela. */
  enviar: ({ arquivo, senha, mesmaRaiz }) => {
    const formulario = new FormData()
    formulario.append('arquivo', arquivo)
    formulario.append('senha', senha)
    formulario.append('mesma_raiz', mesmaRaiz ? 'true' : 'false')
    return http(`${BASE}/certificado/`, { metodo: 'POST', corpo: formulario })
  },
  remover: () => http(`${BASE}/certificado/`, { metodo: 'DELETE' }),
}

export const logo = {
  baixar: (tema) => baixarBinario(`${BASE}/logo/${tema}/`),
  enviar: (tema, arquivo) => {
    const formulario = new FormData()
    formulario.append('arquivo', arquivo)
    return http(`${BASE}/logo/${tema}/`, { metodo: 'PUT', corpo: formulario })
  },
  remover: (tema) => http(`${BASE}/logo/${tema}/`, { metodo: 'DELETE' }),
}

/** Notas fiscais (NFS-e) emitidas pela empresa ativa. */
export const notas = {
  listar: (filtros) => http(`${BASE}/notas/${consulta(filtros)}`),
  obter: (id) => http(`${BASE}/notas/${id}/`),
  /** Diz se a empresa pode emitir e, se não, o que falta (com a tela para resolver). */
  prontidao: () => http(`${BASE}/notas/prontidao/`),
  /** Calcula e valida sem gravar nada: é a conferência antes de enviar. */
  previa: (corpo) => http(`${BASE}/notas/previa/`, { metodo: 'POST', corpo }),
  criar: (corpo) => http(`${BASE}/notas/`, { metodo: 'POST', corpo }),
  alterar: (id, corpo) => http(`${BASE}/notas/${id}/`, { metodo: 'PATCH', corpo }),
  /** Coloca a nota em envio (assíncrono): a tela acompanha a situação. */
  emitir: (id) => http(`${BASE}/notas/${id}/emitir/`, { metodo: 'POST' }),
  consultar: (id) => http(`${BASE}/notas/${id}/consultar/`, { metodo: 'POST' }),
  conferir: (id) => http(`${BASE}/notas/${id}/conferir/`, { metodo: 'POST' }),
  cancelar: (id, corpo) => http(`${BASE}/notas/${id}/cancelar/`, { metodo: 'POST', corpo }),
  substituir: (id, corpo) => http(`${BASE}/notas/${id}/substituir/`, { metodo: 'POST', corpo }),
  baixarXml: (id) => baixarBinario(`${BASE}/notas/${id}/xml/`),
  baixarDanfse: (id) => baixarBinario(`${BASE}/notas/${id}/danfse/`),
}
