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
