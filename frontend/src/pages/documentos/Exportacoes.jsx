import { useCallback, useEffect, useRef, useState } from 'react'
import { exportacoes as api } from '../../api/documentos.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarDataHora } from '../../utils/formatar.js'
import { rotuloDaSituacao } from '../fiscal/situacoes.js'

export const INTERVALO_DAS_EXPORTACOES = 3000

const SITUACOES_DA_NOTA = ['autorizada', 'cancelada', 'substituida']
const FILTROS_VAZIOS = { periodo_inicio: '', periodo_fim: '', competencia: '', tomador: '' }
const EM_ANDAMENTO = new Set(['pendente', 'gerando'])

const SELO = {
  pronta: 'border-estado-sucesso',
  falhou: 'border-estado-erro text-estado-erro',
  pendente: 'border-estado-atencao',
  gerando: 'border-estado-atencao',
}

function tamanho(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function baixar(blob, nome) {
  const url = URL.createObjectURL(blob)
  const ancora = document.createElement('a')
  ancora.href = url
  ancora.download = nome
  ancora.click()
  URL.revokeObjectURL(url)
}

function Resumo({ filtros }) {
  const partes = []
  if (filtros.periodo_inicio || filtros.periodo_fim) {
    partes.push(`Emissão de ${filtros.periodo_inicio || '…'} a ${filtros.periodo_fim || '…'}`)
  }
  if (filtros.competencia) partes.push(`Competência ${filtros.competencia}`)
  if (filtros.situacao?.length) partes.push(filtros.situacao.map(rotuloDaSituacao).join(', '))
  if (filtros.tomador) partes.push(`Tomador: ${filtros.tomador}`)
  return <span>{partes.join(' · ') || 'Todas as notas emitidas'}</span>
}

export default function Exportacoes() {
  const [pedidos, setPedidos] = useState(null)
  const [falha, setFalha] = useState('')
  const [campos, setCampos] = useState(FILTROS_VAZIOS)
  const [situacoes, setSituacoes] = useState(SITUACOES_DA_NOTA)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [baixando, setBaixando] = useState(null)
  const [notificacao, setNotificacao] = useState('')
  const anteriores = useRef(null) // situação de cada pedido na leitura anterior

  const carregar = useCallback(async () => {
    const resposta = await api.listar()
    if (!resposta.ok) {
      setFalha(mensagemErro(resposta, 'Não foi possível carregar os downloads em lote.'))
      return
    }
    setFalha('')
    const lista = resposta.dados
    // Aviso na tela quando um pedido que estava em andamento termina.
    if (anteriores.current) {
      const prontos = lista.filter((p) => p.situacao === 'pronta' && EM_ANDAMENTO.has(anteriores.current[p.id]))
      const falhos = lista.filter((p) => p.situacao === 'falhou' && EM_ANDAMENTO.has(anteriores.current[p.id]))
      if (prontos.length) setNotificacao(`O download em lote nº ${prontos[0].id} está pronto para baixar.`)
      else if (falhos.length) setNotificacao(`O download em lote nº ${falhos[0].id} não pôde ser gerado.`)
    }
    anteriores.current = Object.fromEntries(lista.map((p) => [p.id, p.situacao]))
    setPedidos(lista)
  }, [])

  useEffect(() => {
    // Carga inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  const andamento = pedidos?.some((p) => EM_ANDAMENTO.has(p.situacao)) ?? false
  useEffect(() => {
    if (!andamento) return undefined
    const relogio = setInterval(carregar, INTERVALO_DAS_EXPORTACOES)
    return () => clearInterval(relogio)
  }, [andamento, carregar])

  const mudar = (campo) => (evento) => setCampos((atual) => ({ ...atual, [campo]: evento.target.value }))
  const alternarSituacao = (valor) =>
    setSituacoes((atual) => (atual.includes(valor) ? atual.filter((s) => s !== valor) : [...atual, valor]))

  async function solicitar(evento) {
    evento.preventDefault()
    setErros({})
    setErroGeral('')
    setNotificacao('')
    const corpo = Object.fromEntries(Object.entries(campos).filter(([, valor]) => valor))
    if (situacoes.length > 0 && situacoes.length < SITUACOES_DA_NOTA.length) corpo.situacao = situacoes
    setEnviando(true)
    const resposta = await api.criar(corpo)
    setEnviando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta, 'Não foi possível pedir o download em lote.'))
      return
    }
    anteriores.current = { ...(anteriores.current ?? {}), [resposta.dados.id]: resposta.dados.situacao }
    setPedidos((atual) => [resposta.dados, ...(atual ?? [])])
  }

  async function baixarZip(pedido) {
    setBaixando(pedido.id)
    setErroGeral('')
    const resposta = await api.baixar(pedido.id)
    setBaixando(null)
    if (!resposta.ok) {
      setErroGeral(
        resposta.status === 409
          ? 'Este download expirou ou já não está disponível. Peça um novo.'
          : 'Não foi possível baixar o arquivo agora. Tente novamente.',
      )
      return
    }
    baixar(resposta.blob, pedido.nome_download || `notas-${pedido.id}.zip`)
  }

  if (falha && pedidos === null) return <Aviso tipo="erro">{falha}</Aviso>

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Download em lote</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Reúne o XML, o PDF e uma planilha-resumo das notas num único arquivo ZIP. O arquivo é gerado em segundo plano,
        fica disponível por tempo limitado e só pode ser baixado por quem o pediu.
      </p>

      <form
        onSubmit={solicitar}
        aria-label="Pedir download em lote"
        className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Campo
            rotulo="Emitidas de"
            type="date"
            value={campos.periodo_inicio}
            onChange={mudar('periodo_inicio')}
            erro={erros.periodo_inicio}
          />
          <Campo
            rotulo="Emitidas até"
            type="date"
            value={campos.periodo_fim}
            onChange={mudar('periodo_fim')}
            erro={erros.periodo_fim}
          />
          <Campo
            rotulo="Competência"
            type="month"
            value={campos.competencia}
            onChange={mudar('competencia')}
            erro={erros.competencia}
          />
          <Campo rotulo="Tomador" value={campos.tomador} onChange={mudar('tomador')} erro={erros.tomador} dica="Parte do nome ou do documento." />
        </div>

        <fieldset className="space-y-1">
          <legend className="text-sm">
            Situação da nota{' '}
            <BotaoAjuda rotulo="situação das notas no lote">
              Só entram notas que já têm XML: autorizadas, canceladas e substituídas. Deixe todas marcadas para incluir
              todas.
            </BotaoAjuda>
          </legend>
          <div className="flex flex-wrap gap-4">
            {SITUACOES_DA_NOTA.map((situacao) => (
              <label key={situacao} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={situacoes.includes(situacao)} onChange={() => alternarSituacao(situacao)} />
                {rotuloDaSituacao(situacao)}
              </label>
            ))}
          </div>
        </fieldset>

        <Aviso tipo="erro">{erroGeral}</Aviso>
        <button type="submit" className="botao" disabled={enviando}>
          {enviando ? 'Enviando o pedido…' : 'Gerar arquivo ZIP'}
        </button>
      </form>

      <Aviso tipo="sucesso" className="mt-4">
        {notificacao}
      </Aviso>

      <h2 className="mt-6 text-lg text-gray-900 dark:text-gray-100">Seus downloads</h2>
      {pedidos === null ? (
        <p role="status" className="mt-2 text-sm">Carregando…</p>
      ) : pedidos.length === 0 ? (
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">Você ainda não pediu nenhum download em lote.</p>
      ) : (
        <ul aria-label="Downloads em lote" className="mt-2 space-y-2">
          {pedidos.map((pedido) => (
            <li
              key={pedido.id}
              className="rounded border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900"
            >
              <p className="flex flex-wrap items-center gap-2">
                <strong>Lote nº {pedido.id}</strong>
                <span className={`rounded border px-2 py-0.5 text-xs ${SELO[pedido.situacao] ?? 'border-gray-300 dark:border-gray-700'}`}>
                  {pedido.situacao_rotulo}
                </span>
                <span className="text-gray-600 dark:text-gray-400">· pedido em {formatarDataHora(pedido.criado_em)}</span>
              </p>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                <Resumo filtros={pedido.filtros} />
              </p>
              {EM_ANDAMENTO.has(pedido.situacao) && (
                <div className="mt-2">
                  <progress
                    className="w-full"
                    max={pedido.total || 1}
                    value={pedido.processadas}
                    aria-label={`Progresso do lote nº ${pedido.id}`}
                  />
                  <p className="text-xs">
                    {pedido.processadas} de {pedido.total} nota(s) processada(s).
                  </p>
                </div>
              )}
              {pedido.situacao === 'pronta' && (
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    className="botao"
                    disabled={baixando === pedido.id}
                    onClick={() => baixarZip(pedido)}
                  >
                    Baixar ZIP ({tamanho(pedido.tamanho_bytes)})
                  </button>
                  <span className="text-xs text-gray-600 dark:text-gray-400">
                    {pedido.total} nota(s) · disponível até {formatarDataHora(pedido.expira_em)}
                  </span>
                </div>
              )}
              {pedido.situacao === 'expirada' && (
                <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                  O arquivo foi apagado depois do prazo de guarda. Faça um novo pedido, se precisar.
                </p>
              )}
              {pedido.erro && <p className="mt-1 text-estado-erro">{pedido.erro}</p>}
              {pedido.avisos?.length > 0 && (
                <details className="mt-1 text-xs">
                  <summary>{pedido.avisos.length} aviso(s) sobre notas deste lote</summary>
                  <ul className="mt-1 list-disc pl-5">
                    {pedido.avisos.map((aviso) => (
                      <li key={aviso}>{aviso}</li>
                    ))}
                  </ul>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
