import { render } from '@testing-library/react'
import { createMemoryRouter } from 'react-router-dom'
import App from '../App.jsx'
import { rotas } from '../routes.jsx'
import {
  IDENTIDADE_PADRAO,
  instalarApiFalsa,
  respostaEu,
  SESSAO_ANONIMA,
  SESSAO_AUTENTICADA,
  VERSAO_FALSA,
} from './apiFalsa.js'

const BASE = '/_allauth/browser/v1'

/** Rotas mínimas de um usuário logado; `extras` acrescenta/substitui rotas da API falsa. */
export function rotasAutenticado({ eu = respostaEu(), extras = {} } = {}) {
  return {
    [`GET ${BASE}/auth/session`]: SESSAO_AUTENTICADA,
    [`GET ${BASE}/config`]: { status: 200, dados: { data: { socialaccount: { providers: [] } } } },
    'GET /api/eu/': eu,
    'GET /api/versao/': VERSAO_FALSA,
    'GET /api/fiscal/identidade/': IDENTIDADE_PADRAO,
    ...extras,
  }
}

export function rotasAnonimo({ extras = {} } = {}) {
  return {
    [`GET ${BASE}/auth/session`]: SESSAO_ANONIMA,
    [`GET ${BASE}/config`]: { status: 200, dados: { data: { socialaccount: { providers: [] } } } },
    'GET /api/versao/': VERSAO_FALSA,
    ...extras,
  }
}

/** Renderiza a SPA inteira numa rota, com a API falsa instalada. */
export function montarApp({ rota = '/', rotasApi }) {
  const api = instalarApiFalsa(rotasApi)
  const roteador = createMemoryRouter(rotas, { initialEntries: [rota] })
  const resultado = render(<App roteador={roteador} />)
  return { ...api, roteador, ...resultado }
}

export { BASE }
