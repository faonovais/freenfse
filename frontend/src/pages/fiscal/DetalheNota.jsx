import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { notas } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarData, formatarDataHora } from '../../utils/formatar.js'
import { AMBIENTES, SITUACOES, dinheiro, rotuloDaSituacao, seloDaSituacao } from './situacoes.js'

export const INTERVALO_DE_ACOMPANHAMENTO = 3000

const MOTIVOS_DE_CANCELAMENTO = [
  { valor: '1', rotulo: 'Erro na emissão' },
  { valor: '2', rotulo: 'Serviço não prestado' },
  { valor: '9', rotulo: 'Outros' },
]
const MOTIVOS_DE_SUBSTITUICAO = [
  { valor: '01', rotulo: 'Desenquadramento do Simples Nacional' },
  { valor: '02', rotulo: 'Enquadramento no Simples Nacional' },
  { valor: '03', rotulo: 'Inclusão retroativa de imunidade ou isenção' },
  { valor: '04', rotulo: 'Exclusão retroativa de imunidade ou isenção' },
  { valor: '05', rotulo: 'Rejeição da nota pelo tomador ou intermediário' },
  { valor: '99', rotulo: 'Outros motivos' },
]

function baixar(blob, nome) {
  const url = URL.createObjectURL(blob)
  const ancora = document.createElement('a')
  ancora.href = url
  ancora.download = nome
  ancora.click()
  URL.revokeObjectURL(url)
}

/** Problemas devolvidos pela Sefin: código, o que significa, o que fazer e o texto original. */
function ListaDeErros({ erros }) {
  if (!erros?.length) return null
  return (
    <ul aria-label="Problemas apontados pela Sefin" className="mt-2 space-y-2">
      {erros.map((erro, indice) => (
        <li key={`${erro.codigo}-${indice}`} className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
          <p>
            <strong>Código {erro.codigo || '—'}:</strong> {erro.explicacao}
          </p>
          <p className="mt-1">
            <strong>O que fazer:</strong> {erro.orientacao}
          </p>
          {(erro.descricao_original || erro.complemento) && (
            <details className="mt-1 text-xs text-gray-600 dark:text-gray-400">
              <summary>Texto original da Sefin</summary>
              {erro.descricao_original} {erro.complemento}
            </details>
          )}
        </li>
      ))}
    </ul>
  )
}

function Bloco({ titulo, children }) {
  return (
    <section aria-label={titulo} className="rounded border border-gray-200 p-4 dark:border-gray-800">
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{titulo}</h2>
      <div className="mt-2 text-sm">{children}</div>
    </section>
  )
}

function Linha({ rotulo, children }) {
  return (
    <div className="flex justify-between gap-4 border-b border-gray-100 py-1 dark:border-gray-900">
      <dt>{rotulo}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

function FormularioDeCancelamento({ nota, aoCancelar, aoFechar }) {
  const confirmar = useConfirmacao()
  const [motivo, setMotivo] = useState('1')
  const [justificativa, setJustificativa] = useState('')
  const [erros, setErros] = useState({})
  const [recusa, setRecusa] = useState(null)
  const [erroGeral, setErroGeral] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento) {
    evento.preventDefault()
    const seguir = await confirmar({
      titulo: `Cancelar a nota ${nota.numero_nfse ? `nº ${nota.numero_nfse}` : ''}?`,
      mensagem:
        'O cancelamento é registrado na Sefin e não pode ser desfeito. A nota só aparece como cancelada aqui depois que a Sefin confirmar.',
      textoConfirmar: 'Cancelar a nota',
      textoCancelar: 'Voltar',
      variante: 'perigo',
    })
    if (!seguir) return
    setEnviando(true)
    setErros({})
    setRecusa(null)
    setErroGeral('')
    const resposta = await notas.cancelar(nota.id, { codigo_motivo: Number(motivo), justificativa })
    setEnviando(false)
    if (resposta.ok) {
      aoCancelar(resposta.dados)
    } else if (resposta.dados?.codigo === 'cancelamento_recusado') {
      setRecusa(resposta.dados)
    } else {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
    }
  }

  return (
    <form onSubmit={enviar} aria-label="Cancelar nota" className="space-y-3 rounded border border-gray-200 p-4 dark:border-gray-800">
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Cancelar esta nota</h2>
      <CampoSelecao
        rotulo="Motivo do cancelamento"
        opcoes={MOTIVOS_DE_CANCELAMENTO}
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        erro={erros.codigo_motivo}
      />
      <div className="text-sm">
        <label htmlFor="cancelamento-justificativa">Justificativa (de 15 a 255 caracteres)</label>
        <textarea
          id="cancelamento-justificativa"
          className="campo mt-1"
          rows={3}
          maxLength={255}
          value={justificativa}
          onChange={(e) => setJustificativa(e.target.value)}
          aria-invalid={erros.justificativa ? 'true' : undefined}
        />
        {erros.justificativa && <p className="mt-1 text-xs text-estado-erro">{erros.justificativa}</p>}
      </div>
      {recusa && (
        <div>
          <Aviso tipo="erro">{`A Sefin recusou o cancelamento. ${recusa.detalhe}`}</Aviso>
          <ListaDeErros erros={recusa.erros} />
        </div>
      )}
      <Aviso tipo="erro">{!recusa && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
      <div className="flex gap-2">
        <button type="submit" className="botao-perigo" disabled={enviando}>
          Cancelar a nota
        </button>
        <button type="button" className="botao-leve" onClick={aoFechar}>
          Voltar
        </button>
      </div>
    </form>
  )
}

function FormularioDeSubstituicao({ nota, aoCriar, aoFechar }) {
  const [motivo, setMotivo] = useState('01')
  const [texto, setTexto] = useState('')
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento) {
    evento.preventDefault()
    setEnviando(true)
    setErros({})
    setErroGeral('')
    const resposta = await notas.substituir(nota.id, { codigo_motivo: motivo, motivo: texto })
    setEnviando(false)
    if (resposta.ok) {
      aoCriar(resposta.dados)
    } else {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
    }
  }

  return (
    <form onSubmit={enviar} aria-label="Emitir nota substituta" className="space-y-3 rounded border border-gray-200 p-4 dark:border-gray-800">
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Emitir nota substituta a partir desta</h2>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Será criado um rascunho com os mesmos dados, para você corrigir e emitir. A nota atual só passa a &quot;substituída&quot;
        quando a Sefin confirmar a nova nota.
      </p>
      <CampoSelecao
        rotulo="Motivo da substituição"
        opcoes={MOTIVOS_DE_SUBSTITUICAO}
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        erro={erros.codigo_motivo}
      />
      <Campo
        rotulo={motivo === '99' ? 'Explique o motivo (de 15 a 255 caracteres)' : 'Explicação (opcional, de 15 a 255 caracteres)'}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        erro={erros.motivo}
      />
      <Aviso tipo="erro">{Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={enviando}>
          Criar rascunho da nota substituta
        </button>
        <button type="button" className="botao-leve" onClick={aoFechar}>
          Voltar
        </button>
      </div>
    </form>
  )
}

export default function DetalheNota() {
  const { id } = useParams()
  const navegar = useNavigate()
  const confirmar = useConfirmacao()
  const [nota, setNota] = useState(null)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [painel, setPainel] = useState(null) // 'cancelar' | 'substituir'
  const [ocupado, setOcupado] = useState(false)

  const carregar = useCallback(async () => {
    const resposta = await notas.obter(id)
    if (resposta.ok) {
      setNota(resposta.dados)
      setErro('')
    } else {
      setErro(mensagemErro(resposta, 'Não foi possível abrir a nota.'))
    }
  }, [id])

  useEffect(() => {
    // Carga inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  // Enquanto a Sefin não responde, a tela acompanha a situação sozinha.
  const enviando = nota?.situacao === 'enviando'
  useEffect(() => {
    if (!enviando) return undefined
    const relogio = setInterval(carregar, INTERVALO_DE_ACOMPANHAMENTO)
    return () => clearInterval(relogio)
  }, [enviando, carregar])

  async function executar(acao, { sucesso } = {}) {
    setOcupado(true)
    setAviso('')
    const resposta = await acao()
    setOcupado(false)
    if (!resposta.ok) {
      setAviso(mensagemErro(resposta))
      return null
    }
    if (resposta.dados?.id) setNota(resposta.dados)
    if (sucesso) setAviso(sucesso)
    return resposta
  }

  async function emitir() {
    const incerta = nota.situacao === 'incerta'
    const seguir = await confirmar({
      titulo: incerta ? 'Tentar enviar de novo?' : 'Enviar a nota à Sefin?',
      mensagem: incerta
        ? 'Antes de enviar, o sistema consulta a Sefin: se a nota já existir, ela é apenas recuperada, sem duplicar.'
        : nota.ambiente === 'producao'
          ? 'A empresa está em produção: a nota terá valor fiscal.'
          : 'A empresa está em produção restrita: a nota é de teste.',
      textoConfirmar: 'Enviar',
      textoCancelar: 'Voltar',
    })
    if (seguir) await executar(() => notas.emitir(nota.id))
  }

  async function baixarArquivo(buscar, nome, abrir = false) {
    setOcupado(true)
    const resposta = await buscar()
    setOcupado(false)
    if (!resposta.ok) {
      setAviso('Não foi possível baixar o arquivo agora. Tente novamente.')
      return
    }
    if (abrir) window.open(URL.createObjectURL(resposta.blob), '_blank')
    else baixar(resposta.blob, nome)
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>
  if (!nota) return <p className="text-sm">Carregando a nota…</p>

  const { acoes, totais } = nota
  const titulo = nota.numero_nfse ? `Nota nº ${nota.numero_nfse}` : nota.numero_dps ? `DPS nº ${nota.numero_dps}` : 'Rascunho de nota'
  const situacao = SITUACOES.find((s) => s.valor === nota.situacao)
  const tipoDoAviso = nota.situacao === 'rejeitada' ? 'erro' : 'atencao'

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm">
          <Link className="underline" to="/fiscal/notas">
            ← Notas fiscais
          </Link>
        </p>
        <h1 className="mt-1 text-xl text-gray-900 dark:text-gray-100">{titulo}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
          <span className={`rounded border px-2 py-0.5 text-xs ${seloDaSituacao(nota.situacao)}`}>
            {rotuloDaSituacao(nota.situacao)}
          </span>
          <span className="text-gray-600 dark:text-gray-400">{situacao?.ajuda}</span>
        </p>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {AMBIENTES[nota.ambiente] ?? nota.ambiente}
          {nota.leiaute_descricao ? ` · Leiaute ${nota.leiaute_descricao}` : ''}
          {nota.substitui ? ` · Substitui a nota nº ${nota.substitui_numero}` : ''}
          {nota.substituta ? ' · Já tem nota substituta' : ''}
        </p>
      </div>

      {enviando && <Aviso tipo="atencao">Enviando à Sefin… esta tela acompanha o resultado sozinha.</Aviso>}
      {nota.mensagem && nota.situacao !== 'autorizada' && <Aviso tipo={tipoDoAviso}>{nota.mensagem}</Aviso>}
      <ListaDeErros erros={nota.erros} />
      <Aviso tipo="info">{aviso}</Aviso>

      <div className="flex flex-wrap gap-2" aria-label="Ações da nota" role="group">
        {acoes.emitir && (
          <button type="button" className="botao" disabled={ocupado} onClick={emitir}>
            {nota.situacao === 'rascunho' ? 'Emitir nota' : nota.situacao === 'incerta' ? 'Tentar enviar de novo' : 'Enviar de novo'}
          </button>
        )}
        {acoes.editar && (
          <Link className="botao-leve" to={`/fiscal/notas/${nota.id}/editar`}>
            Corrigir dados
          </Link>
        )}
        {acoes.conferir && (
          <button type="button" className="botao-leve" disabled={ocupado} onClick={() => executar(() => notas.conferir(nota.id), { sucesso: 'Conferência feita.' })}>
            Conferir agora na Sefin
          </button>
        )}
        {acoes.consultar && (
          <button type="button" className="botao-leve" disabled={ocupado} onClick={() => executar(() => notas.consultar(nota.id), { sucesso: 'Nota atualizada pela Sefin.' })}>
            Atualizar pela Sefin
          </button>
        )}
        {acoes.baixar_xml && (
          <button type="button" className="botao-leve" disabled={ocupado} onClick={() => baixarArquivo(() => notas.baixarXml(nota.id), `nfse-${nota.chave}.xml`)}>
            Baixar XML
          </button>
        )}
        {acoes.danfse && (
          <button type="button" className="botao-leve" disabled={ocupado} onClick={() => baixarArquivo(() => notas.baixarDanfse(nota.id), `danfse-${nota.chave}.pdf`, true)}>
            Abrir DANFSe (PDF)
          </button>
        )}
        {acoes.substituir && (
          <button type="button" className="botao-leve" disabled={ocupado} onClick={() => setPainel('substituir')}>
            Emitir nota substituta a partir desta
          </button>
        )}
        {acoes.cancelar && (
          <button type="button" className="botao-perigo" disabled={ocupado} onClick={() => setPainel('cancelar')}>
            Cancelar nota
          </button>
        )}
      </div>

      {painel === 'cancelar' && (
        <FormularioDeCancelamento
          nota={nota}
          aoCancelar={(atualizada) => {
            setNota(atualizada)
            setPainel(null)
            setAviso('Cancelamento confirmado pela Sefin.')
          }}
          aoFechar={() => setPainel(null)}
        />
      )}
      {painel === 'substituir' && (
        <FormularioDeSubstituicao nota={nota} aoCriar={(rascunho) => navegar(`/fiscal/notas/${rascunho.id}`)} aoFechar={() => setPainel(null)} />
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Bloco titulo="Tomador">
          <dl>
            <Linha rotulo="Nome">{nota.tomador.nome}</Linha>
            <Linha rotulo="Documento">{nota.tomador.documento || nota.tomador.nif || '—'}</Linha>
          </dl>
        </Bloco>
        <Bloco titulo="Serviço">
          <dl>
            <Linha rotulo="Serviço">{nota.servico.nome}</Linha>
            <Linha rotulo="Código nacional">{nota.servico.codigo_tributacao_nacional}</Linha>
            <Linha rotulo="Competência">{formatarData(nota.competencia)}</Linha>
          </dl>
        </Bloco>
        <Bloco titulo="Valores">
          <dl>
            <Linha rotulo="Valor do serviço">{dinheiro(totais.valor_servico)}</Linha>
            <Linha rotulo="Base de cálculo do ISS">{dinheiro(totais.base_calculo)}</Linha>
            <Linha rotulo={`ISS (${totais.aliquota_iss ?? '0'}%)`}>{dinheiro(totais.valor_iss)}</Linha>
            <Linha rotulo="Total de retenções">{dinheiro(totais.total_retencoes)}</Linha>
            <Linha rotulo="Valor líquido">
              <strong>{dinheiro(totais.valor_liquido)}</strong>
            </Linha>
          </dl>
        </Bloco>
        <Bloco titulo="Identificação">
          <dl>
            <Linha rotulo="Série / número da DPS">
              {nota.numero_dps ? `${nota.serie} / ${nota.numero_dps}` : '—'}
            </Linha>
            <Linha rotulo="Chave de acesso">{nota.chave ? <span className="break-all">{nota.chave}</span> : '—'}</Linha>
            <Linha rotulo="Emitida em">{formatarDataHora(nota.emitida_em)}</Linha>
          </dl>
        </Bloco>
      </div>

      <Bloco titulo="Eventos">
        {nota.eventos.length === 0 ? (
          <p className="text-gray-600 dark:text-gray-400">Nenhum evento registrado na Sefin.</p>
        ) : (
          <ul>
            {nota.eventos.map((evento) => (
              <li key={`${evento.tipo_evento}-${evento.registrado_em}`}>
                {evento.rotulo} · {formatarDataHora(evento.registrado_em)}
              </li>
            ))}
          </ul>
        )}
      </Bloco>

      <Bloco titulo="Histórico da nota">
        <ol className="space-y-1">
          {nota.historico.map((passo, indice) => (
            <li key={`${passo.momento}-${indice}`}>
              {formatarDataHora(passo.momento)} · {rotuloDaSituacao(passo.de)} → {rotuloDaSituacao(passo.para)}
              {passo.motivo ? ` (${passo.motivo})` : ''}
            </li>
          ))}
          {nota.historico.length === 0 && <li className="text-gray-600 dark:text-gray-400">Rascunho ainda não enviado.</li>}
        </ol>
      </Bloco>
    </div>
  )
}
