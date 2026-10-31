import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { pessoas as apiPessoas, servicos as apiServicos } from '../../api/cadastros.js'
import { notas } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import SelectBusca from '../../components/SelectBusca.jsx'
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
  indicador_destinatario: '0',
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
    indicador_operacao: complementos.ibs_cbs?.codigo_indicador_operacao ?? '',
    indicador_destinatario: String(complementos.ibs_cbs?.indicador_destinatario ?? 0),
  }
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
    ibs_cbs: f.indicador_operacao
      ? { codigo_indicador_operacao: f.indicador_operacao, indicador_destinatario: Number(f.indicador_destinatario) }
      : null,
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

  const servicoEscolhido = useMemo(() => servicos.find((s) => s.id === f.servico), [servicos, f.servico])
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
    const resposta = await notas.previa(corpoDe(f))
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
          {servicoEscolhido?.cst_ibs_cbs && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo
                rotulo="Indicador da operação (IBS/CBS)"
                value={f.indicador_operacao}
                onChange={mudar('indicador_operacao')}
                erro={erros.ibs_cbs}
                dica="6 dígitos. Em branco: a nota segue sem o grupo de IBS/CBS."
              />
              <div className="text-sm">
                <label htmlFor="nota-destinatario">O destinatário é o próprio tomador?</label>
                <select
                  id="nota-destinatario"
                  className="campo mt-1"
                  value={f.indicador_destinatario}
                  onChange={mudar('indicador_destinatario')}
                >
                  <option value="0">Sim</option>
                  <option value="1">Não</option>
                </select>
              </div>
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
