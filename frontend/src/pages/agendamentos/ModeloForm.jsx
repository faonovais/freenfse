import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { modelos as api, opcoes as apiOpcoes } from '../../api/agendamentos.js'
import { pessoas as apiPessoas, servicos as apiServicos } from '../../api/cadastros.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import SelectBusca from '../../components/SelectBusca.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarData } from '../../utils/formatar.js'
import { dinheiro } from '../fiscal/situacoes.js'

const VAZIO = {
  nome: '',
  ativo: true,
  tomador: null,
  servico: null,
  valor: '',
  desconto_incondicionado: '',
  desconto_condicionado: '',
  deducao_valor: '',
  deducao_percentual: '',
  informacoes: '',
  percentual_simples: '',
  competencia_padrao: 'mes_da_execucao',
  email_envio_automatico: '',
  email_avisar_cancelamento: '',
  email_anexar_pdf: '',
  email_anexar_xml: '',
  email_assunto: '',
  email_corpo: '',
  copias_proprias: false,
  email_copias: '',
}

const listaDe = (dados) => (Array.isArray(dados) ? dados : (dados?.results ?? []))
const tristate = (valor) => (valor === null || valor === undefined ? '' : valor ? 'sim' : 'nao')
const deTristate = (valor) => (valor === '' ? null : valor === 'sim')
const comoLista = (texto) =>
  texto
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
const OPCOES_TRI = [
  { valor: 'sim', rotulo: 'Sim' },
  { valor: 'nao', rotulo: 'Não' },
]

function formularioDe(m) {
  const valores = m.valores ?? {}
  return {
    nome: m.nome,
    ativo: m.ativo,
    tomador: m.tomador,
    servico: m.servico,
    valor: valores.servico ?? '',
    desconto_incondicionado: valores.desconto_incondicionado ?? '',
    desconto_condicionado: valores.desconto_condicionado ?? '',
    deducao_valor: valores.deducao_valor ?? '',
    deducao_percentual: valores.deducao_percentual ?? '',
    informacoes: m.informacoes_complementares ?? '',
    percentual_simples: m.percentual_total_tributos_simples ?? '',
    competencia_padrao: m.competencia_padrao,
    email_envio_automatico: tristate(m.email_envio_automatico),
    email_avisar_cancelamento: tristate(m.email_avisar_cancelamento),
    email_anexar_pdf: tristate(m.email_anexar_pdf),
    email_anexar_xml: tristate(m.email_anexar_xml),
    email_assunto: m.email_assunto_modelo ?? '',
    email_corpo: m.email_corpo_modelo ?? '',
    copias_proprias: m.email_copias_fixas !== null && m.email_copias_fixas !== undefined,
    email_copias: (m.email_copias_fixas ?? []).join(', '),
  }
}

function corpoDe(f) {
  const numero = (valor) => (valor === '' ? null : valor)
  return {
    nome: f.nome,
    ativo: f.ativo,
    tomador: f.tomador,
    servico: f.servico,
    valores: {
      servico: f.valor,
      desconto_incondicionado: numero(f.desconto_incondicionado),
      desconto_condicionado: numero(f.desconto_condicionado),
      deducao_valor: numero(f.deducao_valor),
      deducao_percentual: numero(f.deducao_percentual),
    },
    informacoes_complementares: f.informacoes,
    percentual_total_tributos_simples: numero(f.percentual_simples),
    competencia_padrao: f.competencia_padrao,
    email_envio_automatico: deTristate(f.email_envio_automatico),
    email_avisar_cancelamento: deTristate(f.email_avisar_cancelamento),
    email_anexar_pdf: deTristate(f.email_anexar_pdf),
    email_anexar_xml: deTristate(f.email_anexar_xml),
    email_assunto_modelo: f.email_assunto,
    email_corpo_modelo: f.email_corpo,
    email_copias_fixas: f.copias_proprias ? comoLista(f.email_copias) : null,
  }
}

function Previa({ previa }) {
  if (!previa.ok) {
    return (
      <Aviso tipo="erro">
        {`Se o rascunho fosse gerado hoje, falharia: ${Object.values(previa.erros).join(' ')}`}
      </Aviso>
    )
  }
  return (
    <section aria-label="Como ficaria o rascunho" className="space-y-2 rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
      <h3 className="text-base text-gray-900 dark:text-gray-100">Um rascunho gerado hoje ficaria assim</h3>
      <dl>
        <p className="flex justify-between gap-4"><dt>Tomador</dt><dd>{previa.tomador}</dd></p>
        <p className="flex justify-between gap-4"><dt>Competência</dt><dd>{formatarData(previa.competencia)}</dd></p>
        <p className="flex justify-between gap-4"><dt>Valor do serviço</dt><dd>{dinheiro(previa.totais.valor_servico)}</dd></p>
        <p className="flex justify-between gap-4"><dt>ISS</dt><dd>{dinheiro(previa.totais.valor_iss)}</dd></p>
        <p className="flex justify-between gap-4"><dt>Valor líquido</dt><dd><strong>{dinheiro(previa.totais.valor_liquido)}</strong></dd></p>
        {previa.informacoes_complementares && (
          <p className="mt-1"><dt className="inline font-medium">Texto na nota: </dt><dd className="inline">{previa.informacoes_complementares}</dd></p>
        )}
      </dl>
      {previa.avisos.map((aviso) => (
        <Aviso key={aviso} tipo="atencao">{aviso}</Aviso>
      ))}
    </section>
  )
}

export default function ModeloForm() {
  const { id } = useParams()
  const navegar = useNavigate()
  const { temPermissao } = useAuth()
  const podeEditar = temPermissao('agendamento.editar')
  const [f, setF] = useState(VAZIO)
  const [inicial, setInicial] = useState(VAZIO)
  const [pessoas, setPessoas] = useState([])
  const [servicos, setServicos] = useState([])
  const [variaveis, setVariaveis] = useState({})
  const [carregando, setCarregando] = useState(Boolean(id))
  const [falha, setFalha] = useState('')
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [previa, setPrevia] = useState(null)
  const [concluido, setConcluido] = useState(false)
  const textoRef = useRef(null)

  useEffect(() => {
    let ativo = true
    apiPessoas.listar({ ativo: 'true', tamanho: 200 }).then((r) => ativo && r.ok && setPessoas(listaDe(r.dados)))
    apiServicos.listar({ ativo: 'true', tamanho: 200 }).then((r) => ativo && r.ok && setServicos(listaDe(r.dados)))
    apiOpcoes().then((r) => ativo && r.ok && setVariaveis(r.dados.variaveis_do_texto))
    if (id) {
      api.obter(id).then((r) => {
        if (!ativo) return
        if (r.ok) {
          setF(formularioDe(r.dados))
          setInicial(formularioDe(r.dados))
        } else {
          setFalha(mensagemErro(r, 'Não foi possível abrir o modelo.'))
        }
        setCarregando(false)
      })
    }
    return () => {
      ativo = false
    }
  }, [id])

  const sujo = useMemo(() => JSON.stringify(f) !== JSON.stringify(inicial), [f, inicial])
  useFormularioSujo(sujo && !concluido)
  useEffect(() => {
    if (concluido && !sujo) navegar('/agendamentos/modelos')
  }, [concluido, sujo, navegar])

  const opcoesPessoas = useMemo(
    () => pessoas.map((p) => ({ valor: p.id, rotulo: p.nome, detalhe: p.documento_formatado ?? p.documento })),
    [pessoas],
  )
  const opcoesServicos = useMemo(
    () =>
      servicos.map((s) => ({
        valor: s.id,
        rotulo: s.nome,
        detalhe: `${s.codigo_tributacao_nacional} · desde ${formatarData(s.vigencia_inicio)}${s.vigencia_fim ? ` até ${formatarData(s.vigencia_fim)}` : ''}`,
      })),
    [servicos],
  )

  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  const marcar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.checked }))

  function inserirVariavel(nome) {
    const area = textoRef.current
    setF((atual) => {
      const inicio = area?.selectionStart ?? atual.informacoes.length
      const fim = area?.selectionEnd ?? atual.informacoes.length
      return { ...atual, informacoes: `${atual.informacoes.slice(0, inicio)}{${nome}}${atual.informacoes.slice(fim)}` }
    })
  }

  async function salvar(evento) {
    evento.preventDefault()
    setErros({})
    setErroGeral('')
    setSalvando(true)
    const corpo = corpoDe(f)
    const resposta = id ? await api.alterar(id, corpo) : await api.criar(corpo)
    setSalvando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return
    }
    setInicial(f)
    setConcluido(true)
  }

  async function conferir() {
    setPrevia(null)
    const resposta = await api.previa(id)
    if (resposta.ok) setPrevia(resposta.dados)
    else setErroGeral(mensagemErro(resposta))
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (carregando) return <p role="status" className="text-sm">Carregando…</p>

  const erroValor = erros['valores.servico']
  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">{id ? 'Modelo de NFS-e' : 'Novo modelo de NFS-e'}</h1>
      <form
        onSubmit={salvar}
        aria-label="Modelo de NFS-e"
        className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <fieldset disabled={!podeEditar} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo rotulo="Nome do modelo" value={f.nome} onChange={mudar('nome')} erro={erros.nome} />
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input type="checkbox" checked={f.ativo} onChange={marcar('ativo')} />
              <span>
                Modelo ativo{' '}
                <BotaoAjuda rotulo="modelo ativo">
                  Só modelo ativo gera rascunhos. Um modelo inativo pode ficar incompleto, até você terminar de preenchê-lo.
                </BotaoAjuda>
              </span>
            </label>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <SelectBusca
                rotulo="Tomador"
                opcoes={opcoesPessoas}
                valor={f.tomador}
                aoMudar={(valor) => setF((atual) => ({ ...atual, tomador: valor }))}
                vazio="Nenhuma pessoa encontrada"
              />
              {erros.tomador && <p className="mt-1 text-xs text-estado-erro">{erros.tomador}</p>}
            </div>
            <div>
              <SelectBusca
                rotulo="Serviço"
                opcoes={opcoesServicos}
                valor={f.servico}
                aoMudar={(valor) => setF((atual) => ({ ...atual, servico: valor }))}
                vazio="Nenhum serviço encontrado"
              />
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                A cada rascunho vale a versão do serviço vigente na competência, com o mesmo código de tributação.
              </p>
              {erros.servico && <p className="mt-1 text-xs text-estado-erro">{erros.servico}</p>}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Campo
              rotulo="Valor do serviço (R$)"
              inputMode="decimal"
              value={f.valor}
              onChange={mudar('valor')}
              erro={erroValor}
              dica="O valor pode ser corrigido no rascunho antes de aprovar (não há reajuste automático)."
            />
            <CampoSelecao
              rotulo="Competência do rascunho"
              opcoes={[
                { valor: 'mes_da_execucao', rotulo: 'Mês da execução (padrão)' },
                { valor: 'mes_anterior', rotulo: 'Mês anterior ao da execução' },
              ]}
              value={f.competencia_padrao}
              onChange={mudar('competencia_padrao')}
              erro={erros.competencia_padrao}
              dica="Dá para trocar a competência em cada rascunho."
            />
          </div>

          <details className="text-sm">
            <summary className="cursor-pointer">Descontos e deduções (opcional)</summary>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <Campo rotulo="Desconto incondicionado (R$)" inputMode="decimal" value={f.desconto_incondicionado} onChange={mudar('desconto_incondicionado')} erro={erros['valores.desconto_incondicionado']} />
              <Campo rotulo="Desconto condicionado (R$)" inputMode="decimal" value={f.desconto_condicionado} onChange={mudar('desconto_condicionado')} erro={erros['valores.desconto_condicionado']} />
              <Campo rotulo="Dedução (R$)" inputMode="decimal" value={f.deducao_valor} onChange={mudar('deducao_valor')} erro={erros['valores.deducao_valor']} />
              <Campo rotulo="Dedução (%)" inputMode="decimal" value={f.deducao_percentual} onChange={mudar('deducao_percentual')} erro={erros['valores.deducao_percentual']} />
            </div>
          </details>

          <div className="space-y-1 text-sm">
            <label htmlFor="modelo-informacoes">Informações complementares na nota</label>
            <textarea
              id="modelo-informacoes"
              ref={textoRef}
              className="campo mt-1"
              rows={3}
              value={f.informacoes}
              onChange={mudar('informacoes')}
              aria-invalid={erros.informacoes_complementares ? 'true' : undefined}
            />
            {erros.informacoes_complementares && <p className="text-xs text-estado-erro">{erros.informacoes_complementares}</p>}
            <p className="text-xs text-gray-600 dark:text-gray-400">Variáveis (clique para inserir):</p>
            <ul className="flex flex-wrap gap-2">
              {Object.entries(variaveis).map(([nome, descricao]) => (
                <li key={nome}>
                  <button type="button" className="botao-leve text-xs" title={descricao} onClick={() => inserirVariavel(nome)}>
                    {`{${nome}}`}
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <Campo rotulo="Percentual total de tributos do Simples (%) — opcional" inputMode="decimal" value={f.percentual_simples} onChange={mudar('percentual_simples')} erro={erros.percentual_total_tributos_simples} />

          <details className="text-sm">
            <summary className="cursor-pointer">E-mail das notas deste modelo (opcional)</summary>
            <p className="mt-2 text-xs text-gray-600 dark:text-gray-400">
              Por padrão vale a configuração de e-mail da empresa. Aqui você muda só o que for diferente para as notas deste modelo.
            </p>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <CampoSelecao rotulo="Enviar automaticamente ao autorizar" vazio="Igual à empresa" opcoes={OPCOES_TRI} value={f.email_envio_automatico} onChange={mudar('email_envio_automatico')} />
              <CampoSelecao rotulo="Avisar o tomador no cancelamento" vazio="Igual à empresa" opcoes={OPCOES_TRI} value={f.email_avisar_cancelamento} onChange={mudar('email_avisar_cancelamento')} />
              <CampoSelecao rotulo="Anexar o PDF" vazio="Igual à empresa" opcoes={OPCOES_TRI} value={f.email_anexar_pdf} onChange={mudar('email_anexar_pdf')} />
              <CampoSelecao rotulo="Anexar o XML" vazio="Igual à empresa" opcoes={OPCOES_TRI} value={f.email_anexar_xml} onChange={mudar('email_anexar_xml')} />
              <Campo rotulo="Assunto próprio" value={f.email_assunto} onChange={mudar('email_assunto')} erro={erros.email_assunto_modelo} dica="Vazio = o assunto da empresa." />
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.copias_proprias} onChange={marcar('copias_proprias')} />
                  Usar cópias fixas próprias
                </label>
                {f.copias_proprias && (
                  <Campo rotulo="Cópias fixas deste modelo" value={f.email_copias} onChange={mudar('email_copias')} erro={erros.email_copias_fixas} dica="Separe por vírgula. Vazio = sem cópias." />
                )}
              </div>
            </div>
            <div className="mt-2 text-sm">
              <label htmlFor="modelo-email-corpo">Texto próprio da mensagem</label>
              <textarea id="modelo-email-corpo" className="campo mt-1" rows={4} value={f.email_corpo} onChange={mudar('email_corpo')} aria-invalid={erros.email_corpo_modelo ? 'true' : undefined} />
              {erros.email_corpo_modelo && <p className="mt-1 text-xs text-estado-erro">{erros.email_corpo_modelo}</p>}
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">Vazio = o texto da empresa.</p>
            </div>
          </details>
        </fieldset>

        <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
        {previa && <Previa previa={previa} />}
        <div className="flex flex-wrap gap-2">
          {podeEditar ? (
            <button type="submit" className="botao" disabled={salvando}>
              {salvando ? 'Salvando…' : 'Salvar modelo'}
            </button>
          ) : (
            <Aviso>Você pode consultar o modelo, mas não alterá-lo.</Aviso>
          )}
          {id && (
            <button type="button" className="botao-leve" onClick={conferir} disabled={sujo}>
              Conferir como ficaria hoje
            </button>
          )}
        </div>
        {id && sujo && (
          <p className="text-xs text-gray-600 dark:text-gray-400">Salve o modelo antes de conferir: a conferência usa o que está gravado.</p>
        )}
      </form>
    </section>
  )
}
