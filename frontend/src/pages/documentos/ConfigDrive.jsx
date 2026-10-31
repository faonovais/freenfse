import { useEffect, useMemo, useRef, useState } from 'react'
import { configDrive as api, envios } from '../../api/documentos.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarDataHora } from '../../utils/formatar.js'

const CAMPOS_DE_MODELO = ['modelo_subpastas', 'modelo_arquivo']

function formularioDe(dados) {
  return {
    ativo: dados.ativo,
    pasta_raiz_id: dados.pasta_raiz_id,
    modelo_subpastas: dados.modelo_subpastas,
    modelo_arquivo: dados.modelo_arquivo,
    enviar_automaticamente: dados.enviar_automaticamente,
  }
}

function lerTexto(arquivo) {
  return new Promise((resolve, reject) => {
    const leitor = new FileReader()
    leitor.onload = () => resolve(String(leitor.result))
    leitor.onerror = () => reject(leitor.error)
    leitor.readAsText(arquivo)
  })
}

function PreviaDosModelos({ previa }) {
  if (!previa) return null
  if (previa.erros) {
    return (
      <ul aria-label="Problemas nos modelos" className="space-y-1">
        {previa.erros.map((erro) => (
          <li key={erro} className="rounded border border-estado-erro p-2 text-sm text-estado-erro">
            {erro}
          </li>
        ))}
      </ul>
    )
  }
  if (!previa.previa) return <Aviso>{previa.detalhe}</Aviso>
  return (
    <div aria-label="Como a nota ficaria no Drive" className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
      <p>
        Exemplo com a nota nº {previa.numero_nfse} (data de emissão como referência):
      </p>
      <dl className="mt-2 space-y-1">
        <div>
          <dt className="text-xs text-gray-600 dark:text-gray-400">Pasta</dt>
          <dd className="break-all font-mono">{previa.previa.pasta}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-600 dark:text-gray-400">Arquivos</dt>
          <dd>
            <ul className="font-mono">
              {previa.previa.arquivos.map((arquivo) => (
                <li key={arquivo} className="break-all">
                  {arquivo}
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-600 dark:text-gray-400">XML de um cancelamento</dt>
          <dd className="break-all font-mono">{previa.previa.evento}</dd>
        </div>
      </dl>
    </div>
  )
}

function ReenvioDoPeriodo({ ativo }) {
  const [periodo, setPeriodo] = useState({ periodo_inicio: '', periodo_fim: '' })
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento) {
    evento.preventDefault()
    setErro('')
    setResultado(null)
    setEnviando(true)
    const corpo = Object.fromEntries(Object.entries(periodo).filter(([, valor]) => valor))
    const resposta = await envios.reenviarDrivePeriodo(corpo)
    setEnviando(false)
    if (resposta.ok) setResultado(resposta.dados.enfileiradas)
    else setErro(mensagemErro(resposta, 'Não foi possível reenviar o período.'))
  }

  return (
    <form
      onSubmit={enviar}
      aria-label="Reenviar um período ao Drive"
      className="mt-6 space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">
        Reenviar um período ao Drive{' '}
        <BotaoAjuda rotulo="reenvio por período">
          Copia de novo ao Drive todas as notas emitidas no período (pela data de emissão), com os modelos de caminho
          atuais. Útil depois de mudar os modelos ou de corrigir uma falha de acesso.
        </BotaoAjuda>
      </h2>
      {!ativo && <Aviso tipo="atencao">Ative a cópia ao Drive (e salve) para poder reenviar.</Aviso>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo
          rotulo="De"
          type="date"
          value={periodo.periodo_inicio}
          onChange={(e) => setPeriodo((atual) => ({ ...atual, periodo_inicio: e.target.value }))}
        />
        <Campo
          rotulo="Até"
          type="date"
          value={periodo.periodo_fim}
          onChange={(e) => setPeriodo((atual) => ({ ...atual, periodo_fim: e.target.value }))}
        />
      </div>
      <Aviso tipo="erro">{erro}</Aviso>
      {resultado !== null && (
        <Aviso tipo="sucesso">{`${resultado} nota(s) na fila para o Drive. O resultado aparece no detalhe de cada nota.`}</Aviso>
      )}
      <button type="submit" className="botao-leve" disabled={enviando || !ativo}>
        {enviando ? 'Enviando…' : 'Reenviar notas do período'}
      </button>
    </form>
  )
}

export default function ConfigDrive() {
  const { temPermissao } = useAuth()
  const podeEditar = temPermissao('config.editar')
  const podeReenviar = temPermissao('documentos.enviar')
  const [dados, setDados] = useState(null)
  const [falhaAoCarregar, setFalhaAoCarregar] = useState('')
  const [f, setF] = useState(null)
  const [chave, setChave] = useState('')
  const [nomeDaChave, setNomeDaChave] = useState('')
  const [reinicio, setReinicio] = useState(0)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvo, setSalvo] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [previa, setPrevia] = useState(null)
  const [gerandoPrevia, setGerandoPrevia] = useState(false)
  const ultimoCampo = useRef('modelo_subpastas')

  useEffect(() => {
    let ativo = true
    api.obter().then((resposta) => {
      if (!ativo) return
      if (resposta.ok) {
        setDados(resposta.dados)
        setF(formularioDe(resposta.dados))
      } else {
        setFalhaAoCarregar(mensagemErro(resposta, 'Não foi possível carregar a configuração do Drive.'))
      }
    })
    return () => {
      ativo = false
    }
  }, [])

  const inicial = useMemo(() => (dados ? formularioDe(dados) : null), [dados])
  const alterado = Boolean(f && inicial && (JSON.stringify(f) !== JSON.stringify(inicial) || chave))
  useFormularioSujo(alterado && !salvo)

  if (falhaAoCarregar) return <Aviso tipo="erro">{falhaAoCarregar}</Aviso>
  if (!dados || !f) return <p role="status" className="text-sm">Carregando…</p>

  const mudar = (campo) => (evento) => {
    setPrevia(null)
    setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  }
  const marcar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.checked }))

  async function escolherChave(evento) {
    const arquivo = evento.target.files[0]
    if (!arquivo) return
    try {
      setChave(await lerTexto(arquivo))
      setNomeDaChave(arquivo.name)
    } catch {
      setErros((atual) => ({ ...atual, conta_servico: 'Não foi possível ler o arquivo.' }))
    }
  }

  function inserirVariavel(nome) {
    const campo = ultimoCampo.current
    setPrevia(null)
    setF((atual) => ({ ...atual, [campo]: `${atual[campo]}{${nome}}` }))
  }

  async function salvar(evento) {
    evento.preventDefault()
    setErros({})
    setErroGeral('')
    setSalvando(true)
    const corpo = { ...f }
    if (chave) corpo.conta_servico = chave // em branco = manter a que já está guardada
    const resposta = await api.salvar(corpo)
    setSalvando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return
    }
    setSalvo(true)
    setDados(resposta.dados)
    setF(formularioDe(resposta.dados))
    setChave('')
    setNomeDaChave('')
    setReinicio((atual) => atual + 1)
    setSalvo(false)
  }

  async function verPrevia() {
    setErros((atual) => Object.fromEntries(Object.entries(atual).filter(([c]) => !CAMPOS_DE_MODELO.includes(c))))
    setGerandoPrevia(true)
    const resposta = await api.previa({ modelo_subpastas: f.modelo_subpastas, modelo_arquivo: f.modelo_arquivo })
    setGerandoPrevia(false)
    if (resposta.ok) {
      setPrevia(resposta.dados)
    } else if (resposta.status === 400 && resposta.dados && !resposta.dados.codigo) {
      setPrevia({ erros: Object.values(resposta.dados).flat() })
    } else {
      setPrevia({ erros: [mensagemErro(resposta, 'Não foi possível gerar o exemplo.')] })
    }
  }

  const errosDoModelo = [erros.unicidade].filter(Boolean)

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Google Drive da empresa</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Guarda o XML e o PDF de cada nota numa pasta do Drive, organizada pelos modelos abaixo. A chave da conta de
        serviço fica cifrada e nunca é mostrada de volta.
      </p>

      <form
        onSubmit={salvar}
        aria-label="Configuração do Google Drive"
        className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <fieldset disabled={!podeEditar} className="space-y-4">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={f.ativo} onChange={marcar('ativo')} />
            <span>Copiar as notas ao Google Drive</span>
          </label>

          <div className="space-y-2 text-sm">
            <p>
              <label htmlFor="drive-chave">Chave JSON da conta de serviço do Google</label>{' '}
              <BotaoAjuda rotulo="conta de serviço do Drive">
                Crie uma conta de serviço no Google Cloud, baixe a chave JSON e <strong>compartilhe a pasta raiz</strong>{' '}
                com o e-mail da conta de serviço (permissão de editor). O sistema só enxerga o que for compartilhado com
                ela.
              </BotaoAjuda>
            </p>
            <input
              key={reinicio}
              id="drive-chave"
              type="file"
              accept=".json,application/json"
              className="campo mt-1"
              onChange={escolherChave}
              aria-invalid={erros.conta_servico ? 'true' : undefined}
            />
            {nomeDaChave && <p className="text-xs">Arquivo carregado: {nomeDaChave} (será enviado ao salvar).</p>}
            {dados.conta_servico_configurada && !nomeDaChave && (
              <p className="text-xs text-gray-600 dark:text-gray-400">
                Já há uma chave guardada (cifrada) para <strong>{dados.conta_servico_email || 'a conta de serviço'}</strong>.
                Envie outro arquivo só se quiser trocá-la.
              </p>
            )}
            {erros.conta_servico && <p className="text-xs text-estado-erro">{erros.conta_servico}</p>}
          </div>

          <div className="max-w-xl">
            <Campo
              rotulo="ID da pasta raiz no Drive"
              value={f.pasta_raiz_id}
              onChange={mudar('pasta_raiz_id')}
              erro={erros.pasta_raiz_id}
              dica="É o trecho final do endereço da pasta (drive.google.com/drive/folders/ESTE-TRECHO). Ao salvar, o sistema confere o acesso de escrita."
            />
            {dados.pasta_raiz_nome && (
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                Pasta confirmada: <strong>{dados.pasta_raiz_nome}</strong>
                {dados.validado_em ? ` · conferida em ${formatarDataHora(dados.validado_em)}` : ''}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <h2 className="text-lg text-gray-900 dark:text-gray-100">Onde guardar cada nota</h2>
            <Campo
              rotulo="Modelo das subpastas"
              value={f.modelo_subpastas}
              onChange={mudar('modelo_subpastas')}
              onFocus={() => {
                ultimoCampo.current = 'modelo_subpastas'
              }}
              erro={erros.modelo_subpastas}
              dica="Separe os níveis com “/”. Exemplo: {ano}/{mes}. Vazio = direto na pasta raiz."
            />
            <Campo
              rotulo="Modelo do nome do arquivo"
              value={f.modelo_arquivo}
              onChange={mudar('modelo_arquivo')}
              onFocus={() => {
                ultimoCampo.current = 'modelo_arquivo'
              }}
              erro={erros.modelo_arquivo}
              dica="Sem extensão (.xml e .pdf são acrescentados). Vazio = a chave de acesso da nota."
            />
            {errosDoModelo.map((erro) => (
              <Aviso key={erro} tipo="erro">
                {erro}
              </Aviso>
            ))}
            <div className="text-xs">
              <p className="text-gray-600 dark:text-gray-400">
                Variáveis (clique para inserir no último campo usado). O caminho completo precisa identificar uma única
                nota: use <code>{'{chave}'}</code> ou <code>{'{numero_nfse}'}</code> junto com <code>{'{cnpj_emitente}'}</code>.
              </p>
              <ul className="mt-1 flex flex-wrap gap-2">
                {Object.entries(dados.variaveis).map(([nome, descricao]) => (
                  <li key={nome}>
                    <button type="button" className="botao-leve text-xs" title={descricao} onClick={() => inserirVariavel(nome)}>
                      {`{${nome}}`}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-2">
              <button type="button" className="botao-leve" disabled={gerandoPrevia} onClick={verPrevia}>
                {gerandoPrevia ? 'Gerando…' : 'Ver exemplo com uma nota real'}
              </button>
              <PreviaDosModelos previa={previa} />
            </div>
          </div>

          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={f.enviar_automaticamente} onChange={marcar('enviar_automaticamente')} />
            <span>Copiar automaticamente quando a nota for autorizada ou cancelada</span>
          </label>
        </fieldset>

        <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
        {podeEditar ? (
          <button type="submit" className="botao" disabled={salvando || !alterado}>
            {salvando ? 'Conferindo e salvando…' : 'Salvar configuração'}
          </button>
        ) : (
          <Aviso>Você pode consultar a configuração do Drive, mas não alterá-la.</Aviso>
        )}
      </form>

      {podeReenviar && <ReenvioDoPeriodo ativo={dados.ativo} />}
    </section>
  )
}
