import { http } from './http.js'

/** Consulta a versão da API (GET /api/versao/, rota pública, sem empresa). */
export const buscarVersaoApi = () => http('/api/versao/', { semEmpresa: true })
