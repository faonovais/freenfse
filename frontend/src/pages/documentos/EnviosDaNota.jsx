import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { envios as api } from '../../api/documentos.js'
import Aviso from '../../components/Aviso.jsx'
import Campo from '../../components/Campo.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarDataHora } from '../../utils/formatar.js'

export const INTERVALO_DOS_ENVIOS = 3000

const SELO = {
  enviado: 'border-estado-sucesso',
  falhou: 'border-estado-erro text-estado-erro',
  pendente: 'border-estado-atencao',
}

const PAPEIS = { xml: 'XML da nota', pdf: 'PDF (DANFSe)' }
const emLista = (texto) =>
  texto
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)

function Selo({ situacao, rotulo }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-xs ${SELO[situacao] ?? 'border-gray-300 dark:border-gray-700'}`}>
      {rotulo}
    </span>
  )
}

function rotuloDoPapel(papel) {
  if (PAPEIS[papel]) return PAPEIS[papel]
  const [base, ...resto] = String(papel).split(':')
  return PAPEIS[base] ? `${PAPEIS[base]} (${resto.join(':') || 'evento'})` : papel
}

/**
 * Envios de uma nota: histórico de e-mails e cópia ao Drive, com envio e reenvio manuais.
 * Aparece só para quem pode consultar documentos; os botões, só para quem pode enviar.
 */
export default function EnviosDaNota({ notaId }) {
  const { temPermissao } = useAuth()
  const podeEnviar = temPermissao('documentos.enviar')
  const [dados, setDados] = useState(null)
  const [falha, setFalha] = useState('')
  const [aviso, setAviso] = useState(null) // { tipo, texto }
  const [destinatarios, setDestinatarios] = useState('')
  const [erros, setErros] = useState({})
  const [ocupado, setOcupado] = useState(false)

  const carregar = useCallback(async () => {
    const resposta = await api.daNota(notaId)
    if (resposta.ok) {
      setDados(resposta.dados)
      setFalha('')
    } else {
      setFalha(mensagemErro(resposta, 'Não foi possível carregar os envios da nota.'))
    }
  }, [notaId])

  useEffect(() => {
    // Carga inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  // Enquanto há envio na fila, a seção acompanha sozinha.
  const emFila =
    dados != null && [...dados.emails, ...dados.drive].some((item) => item.situacao === 'pendente')
  useEffect(() => {
    if (!emFila) return undefined
    const relogio = setInterval(carregar, INTERVALO_DOS_ENVIOS)
    return () => clearInterval(relogio)
  }, [emFila, carregar])

  async function executar(acao, sucesso) {
    setOcupado(true)
    setAviso(null)
    setErros({})
    const resposta = await acao()
    setOcupado(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setAviso({ tipo: 'erro', texto: mensagemErro(resposta) })
      return
    }
    setAviso({ tipo: 'sucesso', texto: sucesso })
    await carregar()
  }

  async function enviarEmail(evento) {
    evento.preventDefault()
    const lista = emLista(destinatarios)
    await executar(() => api.enviarEmail(notaId, lista.length ? { destinatarios: lista } : {}), 'E-mail na fila de envio.')
    setDestinatarios('')
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (!dados) return <p role="status" className="text-sm">Carregando os envios…</p>

  return (
    <section
      aria-label="Envios da nota"
      className="space-y-4 rounded border border-gray-200 p-4 dark:border-gray-800"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Envios da nota</h2>
      <Aviso tipo={aviso?.tipo}>{aviso?.texto}</Aviso>

      <div className="space-y-3">
        <h3 className="text-base text-gray-900 dark:text-gray-100">E-mails</h3>
        {!dados.email_configurado && (
          <Aviso tipo="atencao">
            O e-mail da empresa ainda não está configurado.{' '}
            {temPermissao('config.consultar') && (
              <Link className="underline" to="/documentos/email">
                Configurar e-mail
              </Link>
            )}
          </Aviso>
        )}
        {dados.emails.length === 0 ? (
          <p className="text-sm text-gray-600 dark:text-gray-400">Esta nota ainda não foi enviada por e-mail.</p>
        ) : (
          <ul aria-label="Histórico de e-mails" className="space-y-2">
            {dados.emails.map((email) => (
              <li key={email.id} className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
                <p className="flex flex-wrap items-center gap-2">
                  <Selo situacao={email.situacao} rotulo={email.situacao_rotulo} />
                  <span>{email.tipo_rotulo}</span>
                  <span className="text-gray-600 dark:text-gray-400">
                    · {formatarDataHora(email.enviado_em || email.criado_em)}
                  </span>
                </p>
                <p className="mt-1 break-all">Para: {email.destinatarios.join(', ') || '—'}</p>
                {email.copias.length > 0 && <p className="break-all">Cópia: {email.copias.join(', ')}</p>}
                {email.anexos.length > 0 && <p className="text-xs">Anexos: {email.anexos.join(', ')}</p>}
                {email.situacao === 'pendente' && email.tentativas > 0 && (
                  <p className="text-xs">
                    Tentativa {email.tentativas} sem sucesso; nova tentativa em {formatarDataHora(email.proxima_tentativa)}.
                  </p>
                )}
                {email.erro && <p className="mt-1 text-estado-erro">{email.erro}</p>}
                {podeEnviar && email.situacao !== 'pendente' && email.tipo !== 'teste' && (
                  <button
                    type="button"
                    className="botao-leve mt-2"
                    disabled={ocupado}
                    onClick={() => executar(() => api.reenviarEmail(email.id), 'Reenvio na fila.')}
                  >
                    Reenviar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {podeEnviar && dados.email_configurado && (
          <form onSubmit={enviarEmail} aria-label="Enviar por e-mail" className="space-y-2">
            <Campo
              rotulo="Destinatários (opcional)"
              value={destinatarios}
              onChange={(e) => setDestinatarios(e.target.value)}
              erro={erros.destinatarios}
              dica={
                dados.destinatarios_padrao.length
                  ? `Sem preencher, vai para: ${dados.destinatarios_padrao.join(', ')}. Separe vários por vírgula.`
                  : 'O tomador não tem e-mail cadastrado: informe um destinatário. Separe vários por vírgula.'
              }
            />
            <button type="submit" className="botao" disabled={ocupado}>
              Enviar por e-mail
            </button>
          </form>
        )}
      </div>

      <div className="space-y-3">
        <h3 className="text-base text-gray-900 dark:text-gray-100">Google Drive</h3>
        {!dados.drive_ativo && (
          <Aviso>
            A cópia ao Google Drive não está ativa.{' '}
            {temPermissao('config.consultar') && (
              <Link className="underline" to="/documentos/drive">
                Configurar o Drive
              </Link>
            )}
          </Aviso>
        )}
        {dados.drive.length === 0 ? (
          <p className="text-sm text-gray-600 dark:text-gray-400">Nenhum arquivo desta nota foi enviado ao Drive.</p>
        ) : (
          <ul aria-label="Arquivos no Drive" className="space-y-2">
            {dados.drive.map((arquivo) => (
              <li key={arquivo.id} className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
                <p className="flex flex-wrap items-center gap-2">
                  <Selo situacao={arquivo.situacao} rotulo={arquivo.situacao_rotulo} />
                  <span>{rotuloDoPapel(arquivo.papel)}</span>
                  {arquivo.enviado_em && (
                    <span className="text-gray-600 dark:text-gray-400">· {formatarDataHora(arquivo.enviado_em)}</span>
                  )}
                </p>
                {arquivo.caminho && <p className="mt-1 break-all font-mono text-xs">{arquivo.caminho}</p>}
                {arquivo.aviso && <Aviso tipo="atencao" className="mt-1">{arquivo.aviso}</Aviso>}
                {arquivo.erro && <p className="mt-1 text-estado-erro">{arquivo.erro}</p>}
              </li>
            ))}
          </ul>
        )}
        {podeEnviar && dados.drive_ativo && (
          <button
            type="button"
            className="botao-leve"
            disabled={ocupado}
            onClick={() => executar(() => api.reenviarDrive(notaId), 'Cópia ao Drive na fila.')}
          >
            Reenviar ao Drive
          </button>
        )}
      </div>
    </section>
  )
}
