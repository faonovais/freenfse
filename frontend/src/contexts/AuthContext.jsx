import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '../api/auth.js'
import { definirEmpresaAtiva, limparEmpresaAtiva, obterEmpresaAtiva } from '../api/empresaAtiva.js'
import { mensagemErro } from '../utils/erros.js'

const AuthContext = createContext(null)

const VAZIO = { carregando: true, usuario: null, mfa: null, empresas: [], mfaPendente: false }

function escolherEmpresa(empresas, preferida) {
  if (empresas.some((empresa) => empresa.id === preferida)) return preferida
  return empresas[0]?.id ?? null
}

/**
 * Usuário logado, empresas que ele pode operar e a empresa ativa DESTA ABA.
 * A empresa ativa vive em sessionStorage e segue no cabeçalho X-Empresa (ver api/http.js).
 */
export function AuthProvider({ children }) {
  const [estado, setEstado] = useState(VAZIO)
  const [empresaId, setEmpresaId] = useState(obterEmpresaAtiva)

  const carregar = useCallback(async () => {
    const situacao = await api.sessao() // também emite o cookie CSRF
    if (situacao.status !== 200) {
      limparEmpresaAtiva()
      setEmpresaId(null)
      // Após o login social de quem tem 2FA, o servidor mantém a sessão anônima com o
      // segundo fator pendente: a tela de login deve pedir o código, não a senha.
      const fluxos = situacao.dados?.data?.flows ?? []
      const mfaPendente = fluxos.some((fluxo) => fluxo.id === 'mfa_authenticate' && fluxo.is_pending)
      setEstado({ ...VAZIO, carregando: false, mfaPendente })
      return
    }
    const resposta = await api.eu()
    if (!resposta.ok) {
      setEstado({ ...VAZIO, carregando: false })
      return
    }
    const { empresas, mfa, ...usuario } = resposta.dados
    const escolhida = escolherEmpresa(empresas, obterEmpresaAtiva())
    if (escolhida) definirEmpresaAtiva(escolhida)
    else limparEmpresaAtiva()
    setEmpresaId(escolhida)
    setEstado({ carregando: false, usuario, mfa, empresas, mfaPendente: false })
  }, [])

  useEffect(() => {
    // Consulta inicial da sessão; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  const entrar = useCallback(
    async (email, senha) => {
      const resposta = await api.entrar(email, senha)
      if (resposta.ok) {
        await carregar()
        return { ok: true }
      }
      const fluxos = resposta.dados?.data?.flows ?? []
      if (resposta.status === 401 && fluxos.some((fluxo) => fluxo.id === 'mfa_authenticate')) {
        return { ok: false, etapa: '2fa' }
      }
      return { ok: false, erro: mensagemErro(resposta, 'Não foi possível entrar.') }
    },
    [carregar],
  )

  const autenticar2fa = useCallback(
    async (codigo) => {
      const resposta = await api.autenticar2fa(codigo)
      if (resposta.ok) {
        await carregar()
        return { ok: true }
      }
      return { ok: false, erro: mensagemErro(resposta, 'Código inválido.') }
    },
    [carregar],
  )

  const sair = useCallback(async () => {
    await api.sair()
    limparEmpresaAtiva()
    setEmpresaId(null)
    setEstado({ ...VAZIO, carregando: false })
  }, [])

  const trocarEmpresa = useCallback((id) => {
    definirEmpresaAtiva(id)
    setEmpresaId(id)
  }, [])

  const empresaAtiva = useMemo(
    () => estado.empresas.find((empresa) => empresa.id === empresaId) ?? null,
    [estado.empresas, empresaId],
  )

  const valor = useMemo(
    () => ({
      ...estado,
      autenticado: estado.usuario !== null,
      empresaAtiva,
      recarregar: carregar,
      entrar,
      autenticar2fa,
      sair,
      trocarEmpresa,
      temPermissao: (nome) => empresaAtiva?.permissoes.includes(nome) ?? false,
    }),
    [estado, empresaAtiva, carregar, entrar, autenticar2fa, sair, trocarEmpresa],
  )

  return <AuthContext value={valor}>{children}</AuthContext>
}

export function useAuth() {
  const contexto = useContext(AuthContext)
  if (!contexto) throw new Error('useAuth precisa estar dentro de <AuthProvider>.')
  return contexto
}
