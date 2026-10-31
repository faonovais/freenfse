import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { rascunhos as api } from '../../api/agendamentos.js'
import Aviso from '../../components/Aviso.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarData, formatarDataHora } from '../../utils/formatar.js'
import { dinheiro, rotuloDaSituacao } from '../fiscal/situacoes.js'
import { Selo } from './Modelos.jsx'

export const INTERVALO_DO_LOTE = 3000

function origemDe(origem) {
  if (origem.tipo === 'agendamento') {
    return `Agendamento “${origem.nome}” (${formatarData(origem.data_execucao)})`
  }
  if (origem.tipo === 'modelo') return `Modelo “${origem.nome}”`
  return 'Criado à mão'
}

/** Resultado do lote: o que entrou na fila, o que foi recusado e como cada nota terminou. */
function ResultadoDoLote({ lote, situacoes }) {
  return (
    <section aria-label="Resultado da aprovação" className="mt-4 space-y-2 rounded border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900">
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Resultado da aprovação</h2>
      <p>
        {lote.aceitas} enviado(s) para emissão
        {lote.recusadas > 0 ? ` · ${lote.recusadas} recusado(s)` : ''}. O envio à Sefin é feito um a um; esta lista acompanha
        o resultado.
      </p>
      <ul className="space-y-1">
        {lote.resultados.map((r) => {
          const atual = situacoes[r.id]
          return (
            <li key={r.id} className="flex flex-wrap items-center gap-2">
              <span>Nota {r.id}:</span>
              {!r.ok && <Selo tipo="erro">Recusada</Selo>}
              {r.ok && !atual && <Selo tipo="atencao">Enviando</Selo>}
              {r.ok && atual && (
                <Selo tipo={atual.situacao === 'autorizada' ? 'ok' : atual.situacao === 'enviando' ? 'atencao' : 'erro'}>
                  {atual.situacao_rotulo ?? rotuloDaSituacao(atual.situacao)}
                </Selo>
              )}
              <span className="text-gray-600 dark:text-gray-400">
                {r.ok ? (atual?.numero_nfse ? `NFS-e nº ${atual.numero_nfse}` : (atual?.mensagem ?? '')) : r.mensagem}
              </span>
              {r.ok && atual && !['enviando', 'autorizada'].includes(atual.situacao) && (
                <Link className="underline" to={`/fiscal/notas/${r.id}`}>
                  Ver nota
                </Link>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default function Rascunhos() {
  const { temPermissao } = useAuth()
  const confirmar = useConfirmacao()
  const podeEmitir = temPermissao('nfse.emitir')
  const [dados, setDados] = useState(null)
  const [falha, setFalha] = useState('')
  const [selecionados, setSelecionados] = useState([])
  const [lote, setLote] = useState(null)
  const [situacoes, setSituacoes] = useState({})
  const [aprovando, setAprovando] = useState(false)
  const [aviso, setAviso] = useState('')
  const [descartando, setDescartando] = useState(null)
  const [motivo, setMotivo] = useState('')
  const [erroMotivo, setErroMotivo] = useState('')

  const carregar = useCallback(async () => {
    const resposta = await api.listar()
    if (resposta.ok) setDados(resposta.dados)
    else setFalha(mensagemErro(resposta, 'Não foi possível carregar os rascunhos.'))
  }, [])

  useEffect(() => {
    // Carga inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  // Acompanha as notas aceitas até a Sefin responder (autorizada, rejeitada, incerta…).
  const aceitas = useMemo(() => (lote ? lote.resultados.filter((r) => r.ok).map((r) => r.id) : []), [lote])
  const emEnvio = aceitas.some((id) => !situacoes[id] || situacoes[id].situacao === 'enviando')
  useEffect(() => {
    if (!aceitas.length || !emEnvio) return undefined
    let ativo = true
    const consultar = async () => {
      const resposta = await api.situacao(aceitas)
      if (ativo && resposta.ok) setSituacoes(Object.fromEntries(resposta.dados.map((n) => [n.id, n])))
    }
    const relogio = setInterval(consultar, INTERVALO_DO_LOTE)
    consultar()
    return () => {
      ativo = false
      clearInterval(relogio)
    }
  }, [aceitas, emEnvio])

  const itens = dados?.itens ?? []
  const alternar = (id) =>
    setSelecionados((atual) => (atual.includes(id) ? atual.filter((i) => i !== id) : [...atual, id]))
  const todosMarcados = itens.length > 0 && selecionados.length === itens.length

  async function aprovar(ids) {
    const seguir = await confirmar({
      titulo: ids.length === 1 ? 'Aprovar este rascunho?' : `Aprovar ${ids.length} rascunhos?`,
      mensagem:
        'Cada nota será enviada à Sefin pelo mesmo caminho da emissão manual. Notas autorizadas têm valor fiscal ' +
        'e só podem ser desfeitas por cancelamento. Confira os valores antes de aprovar.',
      textoConfirmar: 'Aprovar e emitir',
      textoCancelar: 'Voltar',
    })
    if (!seguir) return
    setAprovando(true)
    setAviso('')
    const resposta = await api.aprovar(ids)
    setAprovando(false)
    if (!resposta.ok) {
      setAviso(mensagemErro(resposta))
      return
    }
    setLote(resposta.dados)
    setSituacoes({})
    setSelecionados([])
    await carregar()
  }

  async function descartar(evento) {
    evento.preventDefault()
    setErroMotivo('')
    const resposta = await api.descartar(descartando, motivo)
    if (!resposta.ok) {
      setErroMotivo(errosPorCampo(resposta).motivo ?? mensagemErro(resposta))
      return
    }
    setDescartando(null)
    setMotivo('')
    setSelecionados((atual) => atual.filter((i) => i !== descartando))
    await carregar()
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (!dados) return <p role="status" className="text-sm">Carregando…</p>

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Rascunhos de NFS-e</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Rascunhos esperando decisão, inclusive os gerados por agendamento. Nada é emitido nem apagado sozinho: confira, corrija o
        que precisar (valor, competência, texto) e aprove, ou descarte com um motivo.
      </p>
      <Aviso tipo="erro" className="mt-3">
        {aviso}
      </Aviso>

      {itens.length === 0 ? (
        <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">Nenhum rascunho esperando decisão.</p>
      ) : (
        <>
          {podeEmitir && (
            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={todosMarcados}
                  onChange={() => setSelecionados(todosMarcados ? [] : itens.map((i) => i.id))}
                />
                Selecionar todos
              </label>
              <button
                type="button"
                className="botao"
                disabled={!selecionados.length || aprovando}
                onClick={() => aprovar(selecionados)}
              >
                {aprovando ? 'Enviando…' : `Aprovar selecionados (${selecionados.length})`}
              </button>
              <span className="text-gray-600 dark:text-gray-400">
                {dados.total} rascunho(s){dados.total > itens.length ? ` (mostrando ${itens.length})` : ''}
              </span>
            </div>
          )}
          <ul aria-label="Rascunhos" className="mt-3 space-y-2">
            {itens.map((r) => (
              <li key={r.id} className="rounded border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900">
                <div className="flex flex-wrap items-start gap-3">
                  {podeEmitir && (
                    <input
                      type="checkbox"
                      aria-label={`Selecionar rascunho ${r.id}`}
                      checked={selecionados.includes(r.id)}
                      onChange={() => alternar(r.id)}
                      className="mt-1"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p>
                      <strong className="text-base text-gray-900 dark:text-gray-100">{r.tomador_nome}</strong> ·{' '}
                      {dinheiro(r.valor_servico)} · competência {formatarData(r.competencia)}
                    </p>
                    <p className="text-gray-600 dark:text-gray-400">
                      {origemDe(r.origem)} · criado em {formatarDataHora(r.criado_em)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link className="botao-leve" to={`/fiscal/notas/${r.id}`}>
                      Abrir
                    </Link>
                    {podeEmitir && (
                      <>
                        <Link className="botao-leve" to={`/fiscal/notas/${r.id}/editar`}>
                          Editar
                        </Link>
                        <button type="button" className="botao-leve" disabled={aprovando} onClick={() => aprovar([r.id])}>
                          Aprovar
                        </button>
                        <button type="button" className="botao-leve" onClick={() => { setDescartando(r.id); setMotivo(''); setErroMotivo('') }}>
                          Descartar
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {descartando === r.id && (
                  <form onSubmit={descartar} aria-label="Descartar rascunho" className="mt-3 space-y-2 border-t border-gray-200 pt-3 dark:border-gray-800">
                    <label htmlFor={`motivo-${r.id}`}>Por que este rascunho será descartado?</label>
                    <textarea
                      id={`motivo-${r.id}`}
                      className="campo"
                      rows={2}
                      value={motivo}
                      onChange={(e) => setMotivo(e.target.value)}
                      aria-invalid={erroMotivo ? 'true' : undefined}
                    />
                    {erroMotivo && <p className="text-xs text-estado-erro">{erroMotivo}</p>}
                    <div className="flex gap-2">
                      <button type="submit" className="botao-perigo">
                        Descartar rascunho
                      </button>
                      <button type="button" className="botao-leve" onClick={() => setDescartando(null)}>
                        Voltar
                      </button>
                    </div>
                  </form>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {lote && <ResultadoDoLote lote={lote} situacoes={situacoes} />}
    </section>
  )
}
