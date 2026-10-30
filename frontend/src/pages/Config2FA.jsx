import { QRCodeSVG } from 'qrcode.react'
import { useState } from 'react'
import { ativarTotp, codigosDeRecuperacao, reautenticar, statusTotp } from '../api/auth.js'
import { useAuth } from '../contexts/AuthContext.jsx'
import { mensagemErro } from '../utils/erros.js'

/**
 * Configuração do 2FA por aplicativo (TOTP). Ativar exige confirmar a senha
 * (reautenticação do allauth) e provar que o aplicativo gera códigos válidos.
 */
export default function Config2FA() {
  const { mfa, recarregar } = useAuth()
  const [etapa, setEtapa] = useState('inicio') // inicio | senha | codigo | concluido
  const [segredo, setSegredo] = useState(null)
  const [urlTotp, setUrlTotp] = useState(null)
  const [senha, setSenha] = useState('')
  const [codigo, setCodigo] = useState('')
  const [codigosRecuperacao, setCodigosRecuperacao] = useState([])
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function confirmarSenha(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro('')
    const reautenticacao = await reautenticar(senha)
    if (!reautenticacao.ok) {
      setEnviando(false)
      setErro(mensagemErro(reautenticacao, 'Senha incorreta.'))
      return
    }
    // Sem 2FA, o servidor responde 404 trazendo o segredo e a URL para o QR code.
    const resposta = await statusTotp()
    setEnviando(false)
    const meta = resposta.dados?.meta
    if (!meta?.secret) {
      setErro(mensagemErro(resposta, 'Não foi possível iniciar a configuração.'))
      return
    }
    setSenha('')
    setSegredo(meta.secret)
    setUrlTotp(meta.totp_url ?? null)
    setEtapa('codigo')
  }

  async function confirmarCodigo(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErro('')
    const ativacao = await ativarTotp(codigo.trim())
    if (!ativacao.ok) {
      setEnviando(false)
      setErro(mensagemErro(ativacao, 'Código incorreto.'))
      return
    }
    const recuperacao = await codigosDeRecuperacao()
    setEnviando(false)
    setCodigosRecuperacao(recuperacao.dados?.data?.unused_codes ?? [])
    setSegredo(null)
    setCodigo('')
    setEtapa('concluido')
    await recarregar()
  }

  return (
    <section className="max-w-xl">
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Verificação em duas etapas</h1>
      <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
        Além da senha, o login passa a exigir um código gerado por um aplicativo autenticador no seu celular.
      </p>

      {mfa?.obrigatorio && !mfa.ativo && (
        <p className="mt-4 rounded border border-estado-atencao p-3 text-sm">
          O sistema exige a verificação em duas etapas para a sua conta. Configure-a para continuar.
        </p>
      )}

      {erro && (
        <p role="alert" className="mt-4 rounded border border-estado-erro p-3 text-sm text-estado-erro">
          {erro}
        </p>
      )}

      <div className="mt-6 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        {etapa === 'inicio' && mfa?.ativo && (
          <p role="status">
            Verificação em duas etapas <strong>ativa</strong> nesta conta.
          </p>
        )}

        {etapa === 'inicio' && !mfa?.ativo && (
          <>
            <p role="status">A verificação em duas etapas ainda não está ativa.</p>
            <button type="button" className="botao mt-4" onClick={() => setEtapa('senha')}>
              Configurar
            </button>
          </>
        )}

        {etapa === 'senha' && (
          <form onSubmit={confirmarSenha} className="space-y-3">
            <label className="block text-sm">
              Confirme a sua senha para continuar
              <input
                type="password"
                autoComplete="current-password"
                required
                autoFocus
                className="campo mt-1"
                value={senha}
                onChange={(evento) => setSenha(evento.target.value)}
              />
            </label>
            <p className="text-xs text-gray-600 dark:text-gray-400">
              Se você entra apenas pelo Google e não tem senha, peça ao administrador para definir uma.
            </p>
            <button type="submit" className="botao" disabled={enviando}>
              Continuar
            </button>
          </form>
        )}

        {etapa === 'codigo' && (
          <form onSubmit={confirmarCodigo} className="space-y-3">
            <p className="text-sm">
              1. Leia o QR code com o aplicativo autenticador (ou digite a chave abaixo).
            </p>
            {urlTotp && (
              <div className="inline-block rounded bg-white p-3">
                <QRCodeSVG value={urlTotp} size={160} title="QR code do autenticador" />
              </div>
            )}
            <p className="text-sm">
              Chave: <code className="break-all">{segredo}</code>
            </p>
            <label className="block text-sm">
              2. Informe o código de 6 dígitos que o aplicativo mostra
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                className="campo mt-1"
                value={codigo}
                onChange={(evento) => setCodigo(evento.target.value)}
              />
            </label>
            <button type="submit" className="botao" disabled={enviando}>
              Ativar
            </button>
          </form>
        )}

        {etapa === 'concluido' && (
          <div>
            <p role="status">
              Verificação em duas etapas <strong>ativada</strong>.
            </p>
            {codigosRecuperacao.length > 0 && (
              <>
                <p className="mt-4 text-sm">
                  Guarde estes códigos de recuperação em local seguro. Cada um vale uma única vez e só é mostrado agora.
                </p>
                <ul aria-label="Códigos de recuperação" className="mt-2 grid grid-cols-2 gap-1 text-sm">
                  {codigosRecuperacao.map((item) => (
                    <li key={item}>
                      <code>{item}</code>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
