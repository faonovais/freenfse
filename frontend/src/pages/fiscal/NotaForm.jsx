import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { pessoas as apiPessoas, servicos as apiServicos } from '../../api/cadastros.js'
import { notas } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import NomeDoMunicipio from '../../components/NomeDoMunicipio.jsx'
import SelectBusca from '../../components/SelectBusca.jsx'
import SeletorMunicipio from '../../components/SeletorMunicipio.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarData, primeiroDiaDoMes } from '../../utils/formatar.js'
import { BloqueiosDeEmissao } from './Notas.jsx'
import { AMBIENTES, dinheiro } from './situacoes.js'

// Calculado a cada abertura da tela (não uma vez na carga do módulo): a aba pode ficar aberta de um mês
// para o outro, e o mês é o de Brasília, que é o que o servidor usa para recusar competência futura.
const vazio = () => ({
  tomador: null,
  servico: null,
  competencia: primeiroDiaDoMes(),
  valor: '',
  desconto_incondicionado: '',
  desconto_condicionado: '',
  deducao_valor: '',
  deducao_percentual: '',
  informacoes: '',
  percentual_simples: '',
  indicador_operacao: '',
  indicador_destinatario: '', // vazio = herda do modelo (se a nota veio de um) ou da empresa
  municipio_prestacao: '', // vazio = herda do modelo (se a nota veio de um) ou o município do emissor
})

function formularioDe(nota) {
  const valores = nota.valores ?? {}
  const complementos = nota.complementos ?? {}
  return {
    tomador: nota.tomador_id ?? null,
    servico: nota.servico_id ?? null,
    competencia: nota.competencia,
    valor: valores.servico ?? '',
    desconto_incondicionado: valores.desconto_incondicionado ?? '',
    desconto_condicionado: valores.desconto_condicionado ?? '',
    deducao_valor: valores.deducao_valor ?? '',
    deducao_percentual: valores.deducao_percentual ?? '',
    informacoes: complementos.informacoes_complementares ?? '',
    percentual_simples: complementos.percentual_total_tributos_simples ?? '',
    // Só o que a PRÓPRIA nota ajustou volta preenchido; o resto continua herdando do modelo ou da empresa.
    indicador_operacao: complementos.ibs_cbs_nota?.codigo_indicador_operacao ?? '',
    indicador_destinatario:
      complementos.ibs_cbs_nota?.indicador_destinatario == null ? '' : String(complementos.ibs_cbs_nota.indicador_destinatario),
    // Idem: só o município que a PRÓPRIA nota informou volta preenchido.
    municipio_prestacao: complementos.municipio_prestacao_nota ?? '',
  }
}

/** Ajuste pontual de IBS/CBS (cIndOp e indDest): `null` = nada a ajustar (valem o serviço e a empresa). */
function ibsCbsDe(f) {
  const ajuste = {}
  if (f.indicador_operacao) ajuste.codigo_indicador_operacao = f.indicador_operacao
  if (f.indicador_destinatario !== '') ajuste.indicador_destinatario = Number(f.indicador_destinatario)
  return Object.keys(ajuste).length > 0 ? ajuste : null
}

/** Corpo da API: campos numéricos vazios vão como nulos. */
function corpoDe(f) {
  const numero = (valor) => (valor === '' ? null : valor)
  return {
    tomador: f.tomador,
    servico: f.servico,
    competencia: f.competencia,
    valores: {
      servico: f.valor,
      desconto_incondicionado: numero(f.desconto_incondicionado),
      desconto_condicionado: numero(f.desconto_condicionado),
      deducao_valor: numero(f.deducao_valor),
      deducao_percentual: numero(f.deducao_percentual),
    },
    informacoes_complementares: f.informacoes,
    percentual_total_tributos_simples: numero(f.percentual_simples),
    ibs_cbs: ibsCbsDe(f),
    codigo_municipio_prestacao: f.municipio_prestacao,
  }
}

function Linha({ rotulo, children }) {
  return (
    <div className="flex justify-between gap-4 border-b border-gray-100 py-1 dark:border-gray-900">
      <dt>{rotulo}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

const ROTULO_DA_ORIGEM = { nota: 'ajuste desta nota', modelo: 'do modelo', servico: 'do serviço', empresa: 'padrão da empresa' }
const ROTULO_DA_PRESTACAO = { nota: 'informado nesta nota', modelo: 'do modelo', emissor: 'padrão: município do emissor' }

/** O grupo de IBS/CBS como vai na DPS: cada valor com a sua origem (nota, modelo ou empresa) ou por que não vai. */
function IbsCbsNaDps({ ibs, servico }) {
  if (!ibs || (!ibs.na_dps && !servico.cst_ibs_cbs)) return null
  if (!ibs.na_dps) return <Linha rotulo="IBS/CBS na DPS">Não vai na nota. {ibs.motivo}</Linha>
  const origem = (campo) => ROTULO_DA_ORIGEM[ibs.origens?.[campo]] ?? ''
  return (
    <Linha rotulo="IBS/CBS na DPS">
      Indicador da operação {ibs.codigo_indicador_operacao}{' '}
      <span className="text-xs text-gray-600 dark:text-gray-400">({origem('codigo_indicador_operacao')})</span> · destinatário{' '}
      {ibs.indicador_destinatario === 0 ? 'é o próprio tomador' : 'é outra pessoa'}{' '}
      <span className="text-xs text-gray-600 dark:text-gray-400">({origem('indicador_destinatario')})</span> · NBS {ibs.nbs} · CST{' '}
      {ibs.cst} · cClassTrib {ibs.c_class_trib}
    </Linha>
  )
}

/** Se a alíquota do ISS vai na DPS (pAliq) e por quê: a regra do Anexo VI, com o código da Sefin. */
function AliquotaNaDps({ decisao }) {
  if (!decisao) return null
  const regra = decisao.codigo_regra ? ` (regra ${decisao.codigo_regra})` : ''
  const onde = `ISSQN devido no ${decisao.regra_incidencia_descricao}`
  if (decisao.bloqueio) {
    return (
      <Linha rotulo="Alíquota do ISS na DPS">
        <span className="text-estado-erro">Bloqueia o envio{regra}.</span> {decisao.bloqueio}
      </Linha>
    )
  }
  return (
    <Linha rotulo="Alíquota do ISS na DPS">
      {decisao.envia ? 'Vai na nota' : 'Não vai na nota'}
      {regra}. {decisao.explicacao}{' '}
      <span className="text-xs text-gray-600 dark:text-gray-400">
        ({onde}, município <NomeDoMunicipio codigo={decisao.municipio_incidencia} />
        {decisao.origem_prestacao ? `, ${ROTULO_DA_PRESTACAO[decisao.origem_prestacao] ?? ''}` : ''})
      </span>
    </Linha>
  )
}

/** Conferência antes do envio: tudo o que vai na nota, já calculado, e os avisos. */
function Previa({ previa, ambiente, leiauteDescricao }) {
  const t = previa.totais
  return (
    <section aria-label="Conferência da nota" className="mt-4 space-y-3 rounded border border-gray-200 p-4 dark:border-gray-800">
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Confira antes de enviar</h2>
      <dl className="text-sm">
        <Linha rotulo="Tomador">
          {previa.tomador.nome} ({previa.tomador.documento || previa.tomador.nif || 'sem documento'})
        </Linha>
        <Linha rotulo="Serviço">
          {previa.servico.nome} · código {previa.servico.codigo_tributacao_nacional}
        </Linha>
        <Linha rotulo="Descrição na nota">{previa.servico.descricao}</Linha>
        <Linha rotulo="Competência">{formatarData(previa.competencia)}</Linha>
        {previa.complementos?.local_prestacao?.codigo && (
          <Linha rotulo="Município da prestação">
            <NomeDoMunicipio codigo={previa.complementos.local_prestacao.codigo} />{' '}
            <span className="text-xs text-gray-600 dark:text-gray-400">
              ({ROTULO_DA_PRESTACAO[previa.complementos.local_prestacao.origem] ?? ''})
            </span>
          </Linha>
        )}
        <Linha rotulo="Valor do serviço">{dinheiro(t.valor_servico)}</Linha>
        {Number(t.desconto_incondicionado) > 0 && <Linha rotulo="Desconto incondicionado">{dinheiro(t.desconto_incondicionado)}</Linha>}
        {Number(t.deducao) > 0 && <Linha rotulo="Dedução">{dinheiro(t.deducao)}</Linha>}
        <Linha rotulo="Base de cálculo do ISS">{dinheiro(t.base_calculo)}</Linha>
        <Linha rotulo={`ISS (${t.aliquota_iss ?? '0'}%)${t.iss_retido ? ' — retido pelo tomador' : ''}`}>{dinheiro(t.valor_iss)}</Linha>
        {Number(t.retencao_irrf) > 0 && <Linha rotulo="Retenção de IR">{dinheiro(t.retencao_irrf)}</Linha>}
        {Number(t.retencao_csll) > 0 && <Linha rotulo="Retenção de CSLL">{dinheiro(t.retencao_csll)}</Linha>}
        {Number(t.retencao_inss) > 0 && <Linha rotulo="Retenção de INSS">{dinheiro(t.retencao_inss)}</Linha>}
        <Linha rotulo="Valor líquido a receber">
          <strong>{dinheiro(t.valor_liquido)}</strong>
        </Linha>
        <AliquotaNaDps decisao={previa.complementos?.aliquota_issqn} />
        <IbsCbsNaDps ibs={previa.ibs_cbs} servico={previa.servico} />
        <Linha rotulo="Ambiente">{AMBIENTES[ambiente] ?? ambiente}</Linha>
        <Linha rotulo="Leiaute">{leiauteDescricao}</Linha>
      </dl>
      {previa.avisos.map((aviso) => (
        <Aviso key={aviso} tipo="atencao">
          {aviso}
        </Aviso>
      ))}
    </section>
  )
}

export default function NotaForm() {
  const { id } = useParams()
  const navegar = useNavigate()
  const confirmar = useConfirmacao()
  const [f, setF] = useState(vazio)
  const [inicial, setInicial] = useState(f)
  const [pessoas, setPessoas] = useState([])
  const [servicos, setServicos] = useState([])
  const [prontidao, setProntidao] = useState(null)
  const [padroesDoModelo, setPadroesDoModelo] = useState(null) // o que o modelo do rascunho definia
  const [municipioDoModelo, setMunicipioDoModelo] = useState('') // município da prestação que o modelo definia
  const [previa, setPrevia] = useState(null)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [concluido, setConcluido] = useState(false)
  const [destino, setDestino] = useState(null)
  const [carregandoNota, setCarregandoNota] = useState(Boolean(id))

  useFormularioSujo(!concluido && JSON.stringify(f) !== JSON.stringify(inicial))

  // Só navega depois de o formulário deixar de estar "sujo" (senão o bloqueio de saída pergunta).
  useEffect(() => {
    if (destino) navegar(destino)
  }, [destino, navegar])

  useEffect(() => {
    let ativo = true
    notas.prontidao().then((r) => ativo && r.ok && setProntidao(r.dados))
    apiPessoas.listar({ ativo: 'true', tamanho: 200 }).then((r) => {
      if (ativo && r.ok) setPessoas(r.dados.results ?? r.dados)
    })
    return () => {
      ativo = false
    }
  }, [])

  useEffect(() => {
    if (!id) return undefined
    let ativo = true
    notas.obter(id).then((r) => {
      if (!ativo) return
      if (r.ok) {
        const preenchido = formularioDe(r.dados)
        setPadroesDoModelo(r.dados.complementos?.ibs_cbs_modelo ?? null)
        setMunicipioDoModelo(r.dados.complementos?.municipio_prestacao_modelo ?? '')
        setF(preenchido)
        setInicial(preenchido)
      } else {
        setErroGeral(mensagemErro(r, 'Não foi possível abrir a nota.'))
      }
      setCarregandoNota(false)
    })
    return () => {
      ativo = false
    }
  }, [id])

  // Só aparecem os serviços com vigência na competência escolhida.
  useEffect(() => {
    let ativo = true
    apiServicos.listar({ vigente_em: f.competencia, ativo: 'true' }).then((r) => {
      if (ativo && r.ok) setServicos(r.dados.results ?? r.dados)
    })
    return () => {
      ativo = false
    }
  }, [f.competencia])

  // O que a nota herda quando deixa o campo em branco: o cIndOp do modelo (se o rascunho veio de um) ou
  // do serviço; o destinatário, do modelo ou da empresa.
  const empresaIbs = prontidao?.ibs_cbs
  const doModelo = padroesDoModelo ?? {}
  const origemDoDestinatario = doModelo.indicador_destinatario != null ? 'modelo' : 'empresa'
  const destinatarioHerdado = doModelo.indicador_destinatario ?? empresaIbs?.indicador_destinatario ?? 0

  const servicoEscolhido = useMemo(() => servicos.find((s) => s.id === f.servico), [servicos, f.servico])
  const indicadorHerdado = doModelo.codigo_indicador_operacao || servicoEscolhido?.codigo_indicador_operacao || ''
  const origemDoIndicador = doModelo.codigo_indicador_operacao ? 'do modelo' : 'do serviço'
  const mudar = (campo) => (evento) => {
    setPrevia(null)
    setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  }
  const escolher = (campo) => (valor) => {
    setPrevia(null)
    setF((atual) => ({ ...atual, [campo]: valor }))
  }

  async function conferir(evento) {
    evento.preventDefault()
    setOcupado(true)
    setErros({})
    setErroGeral('')
    const resposta = await notas.previa({ ...corpoDe(f), rascunho: id ? Number(id) : null })
    setOcupado(false)
    if (!resposta.ok) {
      setPrevia(null)
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return
    }
    setPrevia(resposta.dados)
  }

  /** Grava (cria ou corrige) o rascunho e devolve o id, ou `null` com o erro na tela. */
  async function gravar() {
    const corpo = corpoDe(f)
    const resposta = id ? await notas.alterar(id, corpo) : await notas.criar(corpo)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return null
    }
    return resposta.dados.id
  }

  async function salvarRascunho() {
    setOcupado(true)
    const notaId = await gravar()
    setOcupado(false)
    if (notaId) {
      setConcluido(true)
      setDestino(`/fiscal/notas/${notaId}`)
    }
  }

  async function emitir() {
    const emProducao = prontidao?.ambiente === 'producao'
    const seguir = await confirmar({
      titulo: emProducao ? 'Emitir nota com valor fiscal?' : 'Enviar a nota de teste?',
      mensagem: emProducao
        ? 'A empresa está em produção: esta nota terá valor fiscal. Depois de autorizada, só se corrige cancelando ou substituindo.'
        : 'A empresa está em produção restrita: esta nota é de teste e não tem valor fiscal.',
      textoConfirmar: 'Emitir nota',
      textoCancelar: 'Voltar',
      variante: emProducao ? 'perigo' : 'padrao',
    })
    if (!seguir) return
    setOcupado(true)
    const notaId = await gravar()
    if (!notaId) {
      setOcupado(false)
      return
    }
    const resposta = await notas.emitir(notaId)
    setOcupado(false)
    setConcluido(true)
    if (!resposta.ok) setErroGeral(mensagemErro(resposta))
    setDestino(`/fiscal/notas/${notaId}`)
  }

  if (carregandoNota) return <p className="text-sm">Carregando a nota…</p>

  const podeEmitir = Boolean(prontidao?.pronta)
  return (
    <div>
      <h1 className="text-xl text-gray-900 dark:text-gray-100">{id ? 'Corrigir nota' : 'Nova nota'}</h1>
      {prontidao && (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Esta nota será emitida em: <strong>{AMBIENTES[prontidao.ambiente] ?? prontidao.ambiente}</strong>
        </p>
      )}
      <div className="mt-3">
        <BloqueiosDeEmissao prontidao={prontidao} />
      </div>

      <form onSubmit={conferir} aria-label="Dados da nota" className="mt-4 space-y-4 rounded border border-gray-200 p-4 dark:border-gray-800">
        <fieldset className="space-y-3">
          <legend className="text-sm">1. Quem contratou o serviço</legend>
          <SelectBusca
            rotulo="Tomador"
            opcoes={pessoas.map((p) => ({ valor: p.id, rotulo: p.nome, detalhe: p.documento_formatado }))}
            valor={f.tomador}
            aoMudar={escolher('tomador')}
            placeholder="Busque pelo nome ou documento"
            vazio="Nenhuma pessoa encontrada. Cadastre em Cadastros › Pessoas."
          />
          {erros.tomador && <p className="text-xs text-estado-erro">{erros.tomador}</p>}
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm">
            2. Serviço prestado{' '}
            <BotaoAjuda rotulo="serviço vigente">
              A lista mostra só os serviços cuja vigência cobre a competência escolhida. Mudar a competência pode mudar os
              serviços disponíveis.
            </BotaoAjuda>
          </legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo
              rotulo="Competência"
              type="date"
              required
              value={f.competencia}
              onChange={mudar('competencia')}
              erro={erros.competencia}
              dica="Mês em que o serviço foi prestado."
            />
            <div>
              <SelectBusca
                rotulo="Serviço"
                opcoes={servicos.map((s) => ({ valor: s.id, rotulo: s.nome, detalhe: s.codigo_tributacao_nacional }))}
                valor={f.servico}
                aoMudar={escolher('servico')}
                placeholder="Escolha o serviço"
                vazio="Nenhum serviço vigente nesta competência."
              />
              {erros.servico && <p className="mt-1 text-xs text-estado-erro">{erros.servico}</p>}
            </div>
          </div>
          <SeletorMunicipio
            rotulo="Município da prestação"
            valor={f.municipio_prestacao}
            aoMudar={escolher('municipio_prestacao')}
            erro={erros.codigo_municipio_prestacao}
            padrao={municipioDoModelo || prontidao?.municipio_prestacao_padrao || null}
            textoDoPadrao={municipioDoModelo ? 'Em branco, vale o do modelo' : 'Em branco, vale o município do emissor'}
            dica="Onde o serviço foi prestado. Só muda a alíquota do ISS nos serviços cujo ISSQN é devido no local da prestação."
          />
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm">3. Valores</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            <Campo
              rotulo="Valor do serviço (R$)"
              inputMode="decimal"
              required
              value={f.valor}
              onChange={mudar('valor')}
              erro={erros['valores.servico']}
            />
            <Campo
              rotulo="Desconto incondicionado (R$)"
              inputMode="decimal"
              value={f.desconto_incondicionado}
              onChange={mudar('desconto_incondicionado')}
              erro={erros['valores.desconto_incondicionado']}
            />
            <Campo
              rotulo="Desconto condicionado (R$)"
              inputMode="decimal"
              value={f.desconto_condicionado}
              onChange={mudar('desconto_condicionado')}
              erro={erros['valores.desconto_condicionado']}
            />
            <Campo
              rotulo="Dedução em valor (R$)"
              inputMode="decimal"
              value={f.deducao_valor}
              onChange={mudar('deducao_valor')}
              erro={erros['valores.deducao_valor']}
            />
            <Campo
              rotulo="Dedução em percentual (%)"
              inputMode="decimal"
              value={f.deducao_percentual}
              onChange={mudar('deducao_percentual')}
              erro={erros['valores.deducao_percentual']}
              dica="Use valor ou percentual, não os dois."
            />
          </div>
          {servicoEscolhido && (
            <p className="text-xs text-gray-600 dark:text-gray-400">
              Do cadastro do serviço: ISS {servicoEscolhido.aliquota_iss ?? '—'}%
              {servicoEscolhido.iss_retido ? ' (retido pelo tomador)' : ''}. As retenções cadastradas entram no cálculo.
            </p>
          )}
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="text-sm">4. Informações opcionais</legend>
          <div className="text-sm">
            <label htmlFor="nota-informacoes">Informações complementares na nota</label>
            <textarea
              id="nota-informacoes"
              className="campo mt-1"
              rows={2}
              maxLength={2000}
              value={f.informacoes}
              onChange={mudar('informacoes')}
            />
          </div>
          <Campo
            rotulo="Percentual aproximado de tributos — Simples Nacional (%)"
            inputMode="decimal"
            value={f.percentual_simples}
            onChange={mudar('percentual_simples')}
            erro={erros.percentual_total_tributos_simples}
            dica="Só para ME/EPP optante pelo Simples. Em branco, a nota segue sem essa informação."
          />
          {servicoEscolhido?.c_class_trib && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo
                rotulo="Ajustar o indicador da operação (IBS/CBS)"
                inputMode="numeric"
                maxLength={6}
                value={f.indicador_operacao}
                onChange={mudar('indicador_operacao')}
                erro={erros.ibs_cbs}
                dica={
                  indicadorHerdado
                    ? `Só para exceções (6 dígitos). Em branco: vale o ${origemDoIndicador} (${indicadorHerdado}). O grupo de IBS/CBS só vai se a classificação do serviço exigir.`
                    : 'O serviço não tem indicador da operação. Complete o cadastro do serviço ou informe aqui (6 dígitos) para esta nota; o grupo só vai se a classificação exigir.'
                }
              />
              <CampoSelecao
                rotulo="O destinatário é o próprio tomador?"
                vazio={`Herdar (${origemDoDestinatario === 'modelo' ? 'do modelo' : 'da empresa'}: ${destinatarioHerdado === 0 ? 'sim' : 'não'})`}
                opcoes={[
                  { valor: '0', rotulo: 'Sim' },
                  { valor: '1', rotulo: 'Não' },
                ]}
                value={f.indicador_destinatario}
                onChange={mudar('indicador_destinatario')}
              />
            </div>
          )}
        </fieldset>

        <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
        <button type="submit" className="botao" disabled={ocupado}>
          Conferir a nota
        </button>
      </form>

      {previa && (
        <>
          <Previa previa={previa} ambiente={prontidao?.ambiente} leiauteDescricao={prontidao?.leiaute_descricao} />
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="botao" disabled={ocupado || !podeEmitir} onClick={emitir}>
              Emitir nota
            </button>
            <button type="button" className="botao-leve" disabled={ocupado} onClick={salvarRascunho}>
              Salvar rascunho
            </button>
          </div>
          {!podeEmitir && (
            <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
              Resolva as pendências acima para liberar a emissão. Você pode salvar o rascunho enquanto isso.
            </p>
          )}
        </>
      )}
    </div>
  )
}
