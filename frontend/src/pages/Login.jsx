import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { configuracao, iniciarLoginSocial } from '../api/auth.js'
import SeletorTema from '../components/SeletorTema.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'
import { ERROS_SOCIAIS } from '../utils/erros.js'

/** Provedores sociais que o servidor habilitou (a lista vem da configuração do allauth). */
function useProvedores() {
  const [provedores, setProvedores] = useState([])
  useEffect(() => {
    let ativo = true
    configuracao().then((resposta) => {
      if (ativo && resposta.ok) setProvedores(resposta.dados?.data?.socialaccount?.providers ?? [])
    })
    return () => {
      ativo = false
    }
  }, [])
  return provedores
}

export default function Login() {
  const { autenticado, carregando, mfaPendente, entrar, autenticar2fa } = useAuth()
  const [params] = useSearchParams()
  const provedores = useProvedores()
  // Sem escolha local, a etapa vem do servidor: após o login com Google de quem tem 2FA,
  // a sessão fica com o código pendente e a tela já abre pedindo-o.
  const [etapaEscolhida, setEtapaEscolhida] = useState(null)
  const etapa = etapaEscolhida ?? (mfaPendente ? '2fa' : 'credenciais')
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [codigo, setCodigo] = useState('')
  const [erro, setErro] = useState(ERROS_SOCIAIS[params.get('erro')] ?? (params.get('erro') ? ERROS_SOCIAIS.social : ''))
  const [enviando, setEnviando] = useState(false)

  if (!carregando && autenticado) return <Navigate to="/" replace />

  async function enviarCredenciais(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro('')
    const resultado = await entrar(email.trim(), senha)
    setEnviando(false)
    if (resultado.etapa === '2fa') setEtapaEscolhida('2fa')
    else if (!resultado.ok) setErro(resultado.erro)
  }

  async function enviarCodigo(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro('')
    const resultado = await autenticar2fa(codigo.trim())
    setEnviando(false)
    if (!resultado.ok) setErro(resultado.erro)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100 p-4 text-gray-800 dark:bg-[#121212] dark:text-gray-300">
      <section className="w-full max-w-sm rounded border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl text-gray-900 dark:text-gray-100">freenfse</h1>
          <SeletorTema />
        </div>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Acesso restrito a usuários cadastrados pelo administrador.
        </p>

        {erro && (
          <p role="alert" className="mt-4 rounded border border-estado-erro p-3 text-sm text-estado-erro">
            {erro}
          </p>
        )}

        {etapa === 'credenciais' && (
          <>
            {provedores.some((provedor) => provedor.id === 'google') && (
              <button
                type="button"
                className="botao-leve mt-4 w-full py-2"
                onClick={() => iniciarLoginSocial('google')}
              >
                Entrar com Google
              </button>
            )}
            <form onSubmit={enviarCredenciais} className="mt-4 space-y-3">
              <label className="block text-sm">
                E-mail
                <input
                  type="email"
                  autoComplete="username"
                  required
                  className="campo mt-1"
                  value={email}
                  onChange={(evento) => setEmail(evento.target.value)}
                />
              </label>
              <label className="block text-sm">
                Senha
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  className="campo mt-1"
                  value={senha}
                  onChange={(evento) => setSenha(evento.target.value)}
                />
              </label>
              <button type="submit" className="botao w-full" disabled={enviando}>
                Entrar
              </button>
            </form>
          </>
        )}

        {etapa === '2fa' && (
          <form onSubmit={enviarCodigo} className="mt-4 space-y-3">
            <label className="block text-sm">
              Código de verificação
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                autoFocus
                className="campo mt-1"
                value={codigo}
                onChange={(evento) => setCodigo(evento.target.value)}
              />
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400">
              Informe o código do aplicativo autenticador ou um código de recuperação.
            </p>
            <button type="submit" className="botao w-full" disabled={enviando}>
              Verificar
            </button>
            <button
              type="button"
              className="botao-leve w-full"
              onClick={() => {
                setErro('')
                setEtapaEscolhida('credenciais')
              }}
            >
              Voltar ao login
            </button>
          </form>
        )}
      </section>
    </div>
  )
}
