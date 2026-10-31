import { consulta } from './consulta.js'
import { baixarBinario, http } from './http.js'

// Rotas de empresa: o X-Empresa da aba vai em todas as chamadas (ver http.js).
const BASE = '/api/documentos'

/** Configuração de e-mail da empresa. Credenciais entram, mas nunca voltam. */
export const configEmail = {
  obter: () => http(`${BASE}/config/email/`),
  salvar: (corpo) => http(`${BASE}/config/email/`, { metodo: 'PUT', corpo }),
  testar: (destino) => http(`${BASE}/config/email/teste/`, { metodo: 'POST', corpo: { destino } }),
}

/** Configuração do Google Drive da empresa. */
export const configDrive = {
  obter: () => http(`${BASE}/config/drive/`),
  salvar: (corpo) => http(`${BASE}/config/drive/`, { metodo: 'PUT', corpo }),
  previa: (corpo) => http(`${BASE}/config/drive/previa/`, { metodo: 'POST', corpo }),
}

/** Envios de uma nota: histórico de e-mails, cópia ao Drive e reenvios. */
export const envios = {
  daNota: (id) => http(`${BASE}/notas/${id}/envios/`),
  enviarEmail: (id, corpo) => http(`${BASE}/notas/${id}/email/`, { metodo: 'POST', corpo }),
  reenviarEmail: (id) => http(`${BASE}/envios-email/${id}/reenviar/`, { metodo: 'POST' }),
  reenviarDrive: (id) => http(`${BASE}/notas/${id}/drive/reenviar/`, { metodo: 'POST' }),
  reenviarDrivePeriodo: (corpo) => http(`${BASE}/drive/reenviar-periodo/`, { metodo: 'POST', corpo }),
}

/** Download em lote (ZIP gerado em segundo plano). */
export const exportacoes = {
  listar: (filtros) => http(`${BASE}/exportacoes/${consulta(filtros)}`),
  obter: (id) => http(`${BASE}/exportacoes/${id}/`),
  criar: (corpo) => http(`${BASE}/exportacoes/`, { metodo: 'POST', corpo }),
  baixar: (id) => baixarBinario(`${BASE}/exportacoes/${id}/download/`),
}
