import { useEffect, useMemo, useRef, useState } from 'react'
import { configEmail as api } from '../../api/documentos.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

/** Campos que a tela edita (as credenciais ficam de fora: entram só quando digitadas). */
const CAMPOS = [
  'provedor', 'remetente_email', 'remetente_nome', 'smtp_host', 'smtp_porta', 'smtp_seguranca',
  'smtp_usuario', 'graph_tenant_id', 'graph_client_id', 'envio_automatico', 'avisar_cancelamento',
  'anexar_pdf', 'anexar_xml', 'assunto_modelo', 'corpo_modelo',
] // prettier-ignore
const LISTAS = ['copias_fixas', 'emails_alerta']
const SEGREDOS = ['smtp_senha', 'graph_client_secret', 'gmail_conta_servico']

const ROTULO_DO_SEGREDO = {
  smtp_senha: 'a senha do SMTP',
  graph_client_secret: 'o segredo do aplicativo Microsoft',
  gmail_conta_servico: 'a chave da conta de serviço do Google',
}

const emTexto = (lista) => (lista ?? []).join(', ')
const emLista = (texto) =>
  texto
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)

function formularioDe(dados) {
  const f = {}
  for (const campo of CAMPOS) f[campo] = dados[campo] ?? ''
  for (const campo of LISTAS) f[campo] = emTexto(dados[campo])
  for (const campo of SEGREDOS) f[campo] = ''
  return f
}

function lerTexto(arquivo) {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader()
    leitor.onload = () => resolve(String(leitor.result))
    leitor.onerror = () => reject(leitor.error)
    leitor.readAsText(arquivo)
  })
}

/** Credencial: nunca volta do servidor; só se informa o que se quer trocar. */
function CampoSecreto({ campo, rotulo, configurada, valor, aoMudar, erro, podeEditar, aoRemover, ...resto }) {
  return (
    <div className="space-y-1">
      <Campo
        rotulo={rotulo}
        type="password"
        autoComplete="new-password"
        value={valor}
        onChange={(e) => aoMudar(campo, e.target.value)}
        erro={erro}
        placeholder={configurada ? 'Configurada — deixe em branco para manter' : ''}
        dica={configurada ? 'Já há uma credencial guardada (cifrada). Ela nunca é mostrada de volta.' : undefined}
        {...resto}
      />
      {configurada && podeEditar && (
        <button type="button" className="botao-leve text-xs" onClick={() => aoRemover(campo)}>
          Remover {ROTULO_DO_SEGREDO[campo]}
        </button>
      )}
    </div>
  )
}

function EnvioDeTeste({ dados, podeEditar, alterado }) {
  const [destino, setDestino] = useState('')
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento) {
    evento.preventDefault()
    setErro('')
    setResultado(null)
    setEnviando(true)
    const resposta = await api.testar(destino)
    setEnviando(false)
    if (resposta.ok) setResultado(resposta.dados)
    else setErro(mensagemErro(resposta, 'Não foi possível enviar o e-mail de teste.'))
  }

  if (!podeEditar) return null
  const desligado = dados.provedor === 'nenhum'
  return (
    <form
      onSubmit={enviar}
      aria-label="E-mail de teste"
      className="mt-6 space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">
        Enviar e-mail de teste{' '}
        <BotaoAjuda rotulo="e-mail de teste">
          Envia uma mensagem simples com a configuração <strong>salva</strong>, para conferir se o remetente e a
          credencial funcionam antes de enviar notas aos clientes.
        </BotaoAjuda>
      </h2>
      {desligado && <Aviso tipo="atencao">Escolha e salve um provedor de e-mail para poder testar.</Aviso>}
      {alterado && !desligado && (
        <Aviso tipo="atencao">Há alterações não salvas: o teste usa a configuração já gravada.</Aviso>
      )}
      <Campo
        rotulo="Enviar o teste para"
        type="email"
        required
        value={destino}
        onChange={(e) => setDestino(e.target.value)}
      />
      <Aviso tipo="erro">{erro}</Aviso>
      {resultado && (
        <Aviso tipo={resultado.situacao === 'enviado' ? 'sucesso' : 'erro'}>
          {resultado.situacao === 'enviado'
            ? `E-mail de teste enviado para ${resultado.destinatarios.join(', ')}.`
            : `O teste falhou: ${resultado.erro || 'o provedor recusou o envio.'}`}
        </Aviso>
      )}
      <button type="submit" className="botao" disabled={enviando || desligado || !destino}>
        {enviando ? 'Enviando…' : 'Enviar e-mail de teste'}
      </button>
    </form>
  )
}

export default function ConfigEmail() {
  const confirmar = useConfirmacao()
  const { temPermissao } = useAuth()
  const podeEditar = temPermissao('config.editar')
  const [dados, setDados] = useState(null)
  const [falhaAoCarregar, setFalhaAoCarregar] = useState('')
  const [f, setF] = useState(null)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvo, setSalvo] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [nomeDaChave, setNomeDaChave] = useState('')
  const [reinicio, setReinicio] = useState(0) // limpa o campo de arquivo depois de salvar
  const corpoRef = useRef(null)

  useEffect(() => {
    let ativo = true
    api.obter().then((resposta) => {
      if (!ativo) return
      if (resposta.ok) {
        setDados(resposta.dados)
        setF(formularioDe(resposta.dados))
      } else {
        setFalhaAoCarregar(mensagemErro(resposta, 'Não foi possível carregar a configuração de e-mail.'))
      }
    })
    return () => {
      ativo = false
    }
  }, [])

  const inicial = useMemo(() => (dados ? formularioDe(dados) : null), [dados])
  const alterado = Boolean(f && inicial && JSON.stringify(f) !== JSON.stringify(inicial))
  useFormularioSujo(alterado && !salvo)

  if (falhaAoCarregar) return <Aviso tipo="erro">{falhaAoCarregar}</Aviso>
  if (!dados || !f) return <p role="status" className="text-sm">Carregando…</p>

  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  const marcar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.checked }))
  const mudarSegredo = (campo, valor) => setF((atual) => ({ ...atual, [campo]: valor }))
  const configuradas = dados.credenciais_configuradas
  const provedor = f.provedor

  async function guardar(corpo) {
    setErros({})
    setErroGeral('')
    setSalvando(true)
    const resposta = await api.salvar(corpo)
    setSalvando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return false
    }
    setSalvo(true)
    setDados(resposta.dados)
    setF(formularioDe(resposta.dados))
    setNomeDaChave('')
    setReinicio((atual) => atual + 1)
    setSalvo(false)
    return true
  }

  async function salvar(evento) {
    evento.preventDefault()
    const corpo = { ...f }
    for (const campo of LISTAS) corpo[campo] = emLista(f[campo])
    // Credencial em branco = manter: só vai o que foi digitado agora.
    for (const campo of SEGREDOS) if (!f[campo]) delete corpo[campo]
    corpo.smtp_porta = Number(f.smtp_porta) || undefined
    if (!corpo.smtp_porta) delete corpo.smtp_porta
    await guardar(corpo)
  }

  async function removerSegredo(campo) {
    const seguir = await confirmar({
      titulo: 'Remover a credencial?',
      mensagem: `O sistema deixa de ter ${ROTULO_DO_SEGREDO[campo]}. Os e-mails só voltam a sair depois de informar uma nova.`,
      variante: 'perigo',
      textoConfirmar: 'Remover credencial',
    })
    if (seguir) await guardar({ provedor: dados.provedor, [campo]: null })
  }

  async function escolherChave(evento) {
    const arquivo = evento.target.files[0]
    if (!arquivo) return
    try {
      mudarSegredo('gmail_conta_servico', await lerTexto(arquivo))
      setNomeDaChave(arquivo.name)
    } catch {
      setErros((atual) => ({ ...atual, gmail_conta_servico: 'Não foi possível ler o arquivo.' }))
    }
  }

  function inserirVariavel(nome) {
    const area = corpoRef.current
    const marcador = `{${nome}}`
    setF((atual) => {
      const texto = atual.corpo_modelo
      const inicio = area?.selectionStart ?? texto.length
      const fim = area?.selectionEnd ?? texto.length
      return { ...atual, corpo_modelo: texto.slice(0, inicio) + marcador + texto.slice(fim) }
    })
  }

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">E-mail da empresa</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Por onde as notas são enviadas aos tomadores. As credenciais ficam guardadas cifradas e nunca são mostradas de
        volta; para trocar, digite a nova.
      </p>

      <form
        onSubmit={salvar}
        aria-label="Configuração de e-mail"
        className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <fieldset disabled={!podeEditar} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <CampoSelecao
              rotulo="Provedor de e-mail"
              opcoes={dados.opcoes.provedores}
              value={provedor}
              onChange={mudar('provedor')}
              erro={erros.provedor}
              dica="Nenhum = nenhum e-mail é enviado."
            />
          </div>

          {provedor !== 'nenhum' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo
                rotulo="E-mail do remetente"
                type="email"
                value={f.remetente_email}
                onChange={mudar('remetente_email')}
                erro={erros.remetente_email}
                dica="Endereço de onde as notas saem (precisa existir no provedor)."
              />
              <Campo
                rotulo="Nome do remetente"
                value={f.remetente_nome}
                onChange={mudar('remetente_nome')}
                erro={erros.remetente_nome}
                dica="Aparece para quem recebe. Se vazio, usa a razão social."
              />
            </div>
          )}

          {provedor === 'smtp' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo rotulo="Servidor SMTP" value={f.smtp_host} onChange={mudar('smtp_host')} erro={erros.smtp_host} />
              <Campo
                rotulo="Porta"
                type="number"
                min={1}
                max={65535}
                value={f.smtp_porta}
                onChange={mudar('smtp_porta')}
                erro={erros.smtp_porta}
              />
              <CampoSelecao
                rotulo="Segurança da conexão"
                opcoes={dados.opcoes.seguranca}
                value={f.smtp_seguranca}
                onChange={mudar('smtp_seguranca')}
                erro={erros.smtp_seguranca}
              />
              <Campo rotulo="Usuário" value={f.smtp_usuario} onChange={mudar('smtp_usuario')} erro={erros.smtp_usuario} />
              <CampoSecreto
                campo="smtp_senha"
                rotulo="Senha do SMTP"
                configurada={configuradas.smtp_senha}
                valor={f.smtp_senha}
                aoMudar={mudarSegredo}
                erro={erros.smtp_senha}
                podeEditar={podeEditar}
                aoRemover={removerSegredo}
              />
            </div>
          )}

          {provedor === 'graph' && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo
                rotulo="ID do tenant (diretório)"
                value={f.graph_tenant_id}
                onChange={mudar('graph_tenant_id')}
                erro={erros.graph_tenant_id}
              />
              <Campo
                rotulo="ID do aplicativo (cliente)"
                value={f.graph_client_id}
                onChange={mudar('graph_client_id')}
                erro={erros.graph_client_id}
              />
              <CampoSecreto
                campo="graph_client_secret"
                rotulo="Segredo do aplicativo"
                configurada={configuradas.graph_client_secret}
                valor={f.graph_client_secret}
                aoMudar={mudarSegredo}
                erro={erros.graph_client_secret}
                podeEditar={podeEditar}
                aoRemover={removerSegredo}
              />
              <p className="self-end text-xs text-gray-600 dark:text-gray-400">
                O aplicativo precisa da permissão <code>Mail.Send</code> (aplicativo). Anexos acima de 3 MB não são
                enviados por este provedor.
              </p>
            </div>
          )}

          {provedor === 'gmail' && (
            <div className="space-y-2 text-sm">
              <p>
                <label htmlFor="gmail-chave">Chave JSON da conta de serviço do Google</label>{' '}
                <BotaoAjuda rotulo="conta de serviço do Gmail">
                  Crie uma conta de serviço no Google Cloud, ative a delegação em todo o domínio para o escopo de envio
                  do Gmail e baixe a chave JSON. O remetente acima é a caixa em nome da qual o envio é feito.
                </BotaoAjuda>
              </p>
              <input
                key={reinicio}
                id="gmail-chave"
                type="file"
                accept=".json,application/json"
                className="campo mt-1"
                onChange={escolherChave}
                aria-invalid={erros.gmail_conta_servico ? 'true' : undefined}
              />
              {nomeDaChave && <p className="text-xs">Arquivo carregado: {nomeDaChave} (será enviado ao salvar).</p>}
              {configuradas.gmail_conta_servico && !nomeDaChave && (
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  Já há uma chave guardada (cifrada). Envie outro arquivo só se quiser trocá-la.
                </p>
              )}
              {erros.gmail_conta_servico && <p className="text-xs text-estado-erro">{erros.gmail_conta_servico}</p>}
              {configuradas.gmail_conta_servico && podeEditar && (
                <button type="button" className="botao-leve text-xs" onClick={() => removerSegredo('gmail_conta_servico')}>
                  Remover {ROTULO_DO_SEGREDO.gmail_conta_servico}
                </button>
              )}
            </div>
          )}

          {provedor !== 'nenhum' && (
            <>
              <fieldset className="space-y-2">
                <legend className="text-sm">Quando enviar</legend>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={f.envio_automatico} onChange={marcar('envio_automatico')} />
                  <span>Enviar automaticamente quando a nota for autorizada (padrão: envio manual)</span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={f.avisar_cancelamento} onChange={marcar('avisar_cancelamento')} />
                  <span>Avisar o tomador quando a nota for cancelada</span>
                </label>
              </fieldset>

              <fieldset className="space-y-2">
                <legend className="text-sm">Anexos</legend>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={f.anexar_pdf} onChange={marcar('anexar_pdf')} />
                  <span>Anexar o PDF (DANFSe)</span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" checked={f.anexar_xml} onChange={marcar('anexar_xml')} />
                  <span>Anexar o XML da nota</span>
                </label>
              </fieldset>

              <div className="grid gap-3 sm:grid-cols-2">
                <Campo
                  rotulo="Cópias fixas"
                  value={f.copias_fixas}
                  onChange={mudar('copias_fixas')}
                  erro={erros.copias_fixas}
                  dica="Recebem cópia de todo envio (por exemplo, o financeiro). Separe por vírgula."
                />
                <Campo
                  rotulo="Avisos do sistema (certificado a vencer)"
                  value={f.emails_alerta}
                  onChange={mudar('emails_alerta')}
                  erro={erros.emails_alerta}
                  dica="Quem recebe o alerta de vencimento do certificado. Separe por vírgula."
                />
              </div>

              <div className="space-y-3">
                <Campo
                  rotulo="Assunto da mensagem"
                  value={f.assunto_modelo}
                  onChange={mudar('assunto_modelo')}
                  erro={erros.assunto_modelo}
                />
                <div className="text-sm">
                  <label htmlFor="corpo-modelo">Texto da mensagem</label>
                  <textarea
                    id="corpo-modelo"
                    ref={corpoRef}
                    className="campo mt-1 font-mono"
                    rows={8}
                    value={f.corpo_modelo}
                    onChange={mudar('corpo_modelo')}
                    aria-invalid={erros.corpo_modelo ? 'true' : undefined}
                    aria-describedby="variaveis-do-modelo"
                  />
                  {erros.corpo_modelo && <p className="mt-1 text-xs text-estado-erro">{erros.corpo_modelo}</p>}
                </div>
                <div id="variaveis-do-modelo" className="text-xs">
                  <p className="text-gray-600 dark:text-gray-400">
                    Variáveis disponíveis (clique para inserir no texto). O conteúdo delas é protegido: não executa HTML.
                  </p>
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {Object.entries(dados.variaveis).map(([nome, descricao]) => (
                      <li key={nome}>
                        <button
                          type="button"
                          className="botao-leve text-xs"
                          title={descricao}
                          onClick={() => inserirVariavel(nome)}
                        >
                          {`{${nome}}`}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          )}
        </fieldset>

        <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
        {podeEditar ? (
          <button type="submit" className="botao" disabled={salvando || (!alterado && !SEGREDOS.some((c) => f[c]))}>
            {salvando ? 'Salvando…' : 'Salvar configuração'}
          </button>
        ) : (
          <Aviso>Você pode consultar a configuração de e-mail, mas não alterá-la.</Aviso>
        )}
      </form>

      <EnvioDeTeste dados={dados} podeEditar={podeEditar} alterado={alterado} />
    </section>
  )
}
