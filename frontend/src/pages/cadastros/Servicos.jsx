import { useMemo, useState } from 'react'
import { servicos } from '../../api/cadastros.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import CabecalhoColuna from '../../components/CabecalhoColuna.jsx'
import Campo from '../../components/Campo.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { useGridLocal } from '../../hooks/useGridLocal.js'
import { useLista } from '../../hooks/useLista.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarData } from '../../utils/formatar.js'

const SEM_FILTRO = {}
const RETENCOES = [
  ['retencao_irrf', 'Retenção de IR (%)'],
  ['retencao_csll', 'Retenção de CSLL (%)'],
  ['retencao_pis', 'Retenção de PIS (%)'],
  ['retencao_cofins', 'Retenção de COFINS (%)'],
  ['retencao_inss', 'Retenção de INSS (%)'],
]

function formularioDe(servico) {
  return {
    nome: servico?.nome ?? '',
    descricao: servico?.descricao ?? '',
    codigo_tributacao_nacional: servico?.codigo_tributacao_nacional ?? '',
    codigo_tributacao_municipal: servico?.codigo_tributacao_municipal ?? '',
    nbs: servico?.nbs ?? '',
    cst_ibs_cbs: servico?.cst_ibs_cbs ?? '',
    c_class_trib: servico?.c_class_trib ?? '',
    aliquota_iss: servico?.aliquota_iss ?? '',
    iss_retido: servico?.iss_retido ?? false,
    ...Object.fromEntries(RETENCOES.map(([campo]) => [campo, servico?.[campo] ?? ''])),
    vigencia_inicio: servico?.vigencia_inicio ?? '',
    vigencia_fim: servico?.vigencia_fim ?? '',
    ativo: servico?.ativo ?? true,
  }
}

/** Campos numéricos vazios vão como nulos; a vigência final vazia significa "sem fim". */
function corpoDe(f) {
  const numero = (valor) => (valor === '' ? null : valor)
  return {
    ...f,
    aliquota_iss: numero(f.aliquota_iss),
    vigencia_fim: f.vigencia_fim || null,
    ...Object.fromEntries(RETENCOES.map(([campo]) => [campo, numero(f[campo])])),
  }
}

function FormServico({ servico, aoSalvar, aoCancelar }) {
  const novo = !servico
  const inicial = useMemo(() => formularioDe(servico), [servico])
  const [f, setF] = useState(inicial)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  const marcar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.checked }))

  useFormularioSujo(!salvo && JSON.stringify(f) !== JSON.stringify(inicial))

  async function salvar(evento) {
    evento.preventDefault()
    setSalvando(true)
    setErros({})
    setErroGeral('')
    const corpo = corpoDe(f)
    const resposta = novo ? await servicos.criar(corpo) : await servicos.alterar(servico.id, corpo)
    setSalvando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return
    }
    setSalvo(true)
    aoSalvar()
  }

  return (
    <form
      onSubmit={salvar}
      aria-label={novo ? 'Novo serviço' : 'Editar serviço'}
      className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{novo ? 'Novo serviço' : 'Editar serviço'}</h2>

      <Campo rotulo="Nome (uso interno)" required value={f.nome} onChange={mudar('nome')} erro={erros.nome} />
      <div className="text-sm">
        <label htmlFor="servico-descricao">Descrição que sai na nota</label>
        <textarea
          id="servico-descricao"
          className="campo mt-1"
          rows={3}
          required
          maxLength={2000}
          value={f.descricao}
          onChange={mudar('descricao')}
          aria-invalid={erros.descricao ? 'true' : undefined}
        />
        {erros.descricao && <p className="mt-1 text-xs text-estado-erro">{erros.descricao}</p>}
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm">
          Classificação{' '}
          <BotaoAjuda rotulo="classificação do serviço">
            O código nacional (6 dígitos: item, subitem e desdobro da lista de serviços) identifica o serviço na nota. O
            municipal só existe em alguns municípios.
          </BotaoAjuda>
        </legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Campo
            rotulo="Código de tributação nacional"
            required
            value={f.codigo_tributacao_nacional}
            onChange={mudar('codigo_tributacao_nacional')}
            erro={erros.codigo_tributacao_nacional}
            dica="6 dígitos, por exemplo 17.01.01."
          />
          <Campo
            rotulo="Código de tributação municipal"
            value={f.codigo_tributacao_municipal}
            onChange={mudar('codigo_tributacao_municipal')}
            erro={erros.codigo_tributacao_municipal}
            dica="3 dígitos, se o município usar."
          />
          <Campo
            rotulo="NBS"
            value={f.nbs}
            onChange={mudar('nbs')}
            erro={erros.nbs}
            dica="9 dígitos. Obrigatória com IBS/CBS."
          />
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-sm">
          IBS e CBS (reforma tributária){' '}
          <BotaoAjuda rotulo="IBS e CBS">
            São os novos tributos sobre o consumo, em transição de 2026 a 2033. Informe o CST (3 dígitos) e a
            classificação tributária (6 dígitos) juntos, ou deixe os dois em branco.
          </BotaoAjuda>
        </legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="CST do IBS/CBS" value={f.cst_ibs_cbs} onChange={mudar('cst_ibs_cbs')} erro={erros.cst_ibs_cbs} />
          <Campo
            rotulo="Classificação tributária (cClassTrib)"
            value={f.c_class_trib}
            onChange={mudar('c_class_trib')}
            erro={erros.c_class_trib}
          />
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-sm">
          ISS e retenções{' '}
          <BotaoAjuda rotulo="ISS e retenções">
            A alíquota do ISS vai de 0% a 5%. Os percentuais de retenção são o padrão do serviço; o valor é calculado
            na hora de emitir a nota.
          </BotaoAjuda>
        </legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Campo
            rotulo="Alíquota do ISS (%)"
            inputMode="decimal"
            value={f.aliquota_iss}
            onChange={mudar('aliquota_iss')}
            erro={erros.aliquota_iss}
          />
          {RETENCOES.map(([campo, rotulo]) => (
            <Campo key={campo} rotulo={rotulo} inputMode="decimal" value={f[campo]} onChange={mudar(campo)} erro={erros[campo]} />
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.iss_retido} onChange={marcar('iss_retido')} />
          ISS retido pelo tomador
        </label>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-sm">
          Vigência{' '}
          <BotaoAjuda rotulo="vigência">
            Cada cadastro vale por um período. Para mudar a alíquota ou a classificação em uma data, encerre a versão
            atual e cadastre a nova começando no dia seguinte. Versões do mesmo serviço não podem se sobrepor.
          </BotaoAjuda>
        </legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo
            rotulo="Início da vigência"
            type="date"
            required
            value={f.vigencia_inicio}
            onChange={mudar('vigencia_inicio')}
            erro={erros.vigencia_inicio}
          />
          <Campo
            rotulo="Fim da vigência"
            type="date"
            value={f.vigencia_fim}
            onChange={mudar('vigencia_fim')}
            erro={erros.vigencia_fim}
            dica="Deixe em branco se não tem data para acabar."
          />
        </div>
      </fieldset>

      <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={salvando}>
          {novo ? 'Cadastrar serviço' : 'Salvar'}
        </button>
        <button type="button" className="botao-leve" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

function ConsultaVigente() {
  const [codigo, setCodigo] = useState('')
  const [data, setData] = useState('')
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState('')

  async function consultar(evento) {
    evento.preventDefault()
    setResultado(null)
    setErro('')
    const resposta = await servicos.vigente({ codigo_nacional: codigo, data })
    if (resposta.ok) setResultado(resposta.dados)
    else if (resposta.status === 404) setErro(resposta.dados?.detalhe ?? 'Nenhuma versão vigente nesta data.')
    else setErro(mensagemErro(resposta))
  }

  return (
    <section aria-label="Consultar versão vigente" className="mt-4 rounded border border-gray-200 p-4 dark:border-gray-800">
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Qual versão vale em uma data?</h2>
      <form onSubmit={consultar} className="mt-2 flex flex-wrap items-end gap-2">
        <div className="w-48">
          <Campo rotulo="Código nacional" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
        </div>
        <div className="w-44">
          <Campo rotulo="Data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
        </div>
        <button type="submit" className="botao-leve">
          Consultar
        </button>
      </form>
      <Aviso tipo="erro" className="mt-3">{erro}</Aviso>
      {resultado && (
        <p role="status" className="mt-3 text-sm">
          <strong>{resultado.nome}</strong>: ISS {resultado.aliquota_iss ?? '—'}%, vigente de{' '}
          {formatarData(resultado.vigencia_inicio)} a {resultado.vigencia_fim ? formatarData(resultado.vigencia_fim) : 'sem data final'}.
        </p>
      )}
    </section>
  )
}

export default function Servicos() {
  const confirmar = useConfirmacao()
  const { temPermissao, empresaAtiva } = useAuth()
  const podeEditar = temPermissao('cadastro.editar')
  const [busca, setBusca] = useState('')
  const [filtros, setFiltros] = useState(SEM_FILTRO)
  const { itens, carregando, erro, recarregar } = useLista(servicos.listar, filtros)
  const { itensOrdenados, ordenacao, ordenarPor } = useGridLocal(itens, { colunaInicial: 'nome' })
  const [edicao, setEdicao] = useState(null)
  const [erroAcao, setErroAcao] = useState('')

  async function alternarAtivo(servico) {
    if (servico.ativo) {
      const desativar = await confirmar({
        titulo: 'Desativar esta versão do serviço?',
        mensagem: `A versão de ${formatarData(servico.vigencia_inicio)} de "${servico.nome}" deixa de valer para novas notas.`,
        variante: 'perigo',
        textoConfirmar: 'Desativar',
      })
      if (!desativar) return
    }
    setErroAcao('')
    const resposta = await servicos.alterar(servico.id, { ativo: !servico.ativo })
    if (!resposta.ok) setErroAcao(mensagemErro(resposta))
    recarregar()
  }

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Serviços</h1>
        {podeEditar && (
          <button type="button" className="botao" onClick={() => setEdicao('novo')}>
            Novo serviço
          </button>
        )}
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Serviços prestados por <strong>{empresaAtiva?.razao_social}</strong>, com a classificação tributária e o período
        em que cada versão vale.
      </p>

      <form
        role="search"
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(evento) => {
          evento.preventDefault()
          setFiltros(busca.trim() ? { busca: busca.trim() } : SEM_FILTRO)
        }}
      >
        <div className="w-64">
          <Campo rotulo="Buscar por nome ou código" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <button type="submit" className="botao-leve">
          Filtrar
        </button>
      </form>

      {edicao && (
        <FormServico
          key={edicao === 'novo' ? 'novo' : edicao.id}
          servico={edicao === 'novo' ? null : edicao}
          aoSalvar={() => {
            setEdicao(null)
            recarregar()
          }}
          aoCancelar={() => setEdicao(null)}
        />
      )}
      <Aviso tipo="erro" className="mt-4">{erroAcao || erro}</Aviso>

      <div className="mt-4 overflow-x-auto rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Serviços cadastrados</caption>
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <CabecalhoColuna rotulo="Nome" coluna="nome" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Código nacional" coluna="codigo_tributacao_nacional" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="ISS" coluna="aliquota_iss" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Vigência" coluna="vigencia_inicio" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Situação" coluna="ativo" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              {podeEditar && <th scope="col" className="px-3 py-2 text-right">Ações</th>}
            </tr>
          </thead>
          <tbody>
            {carregando && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-gray-600 dark:text-gray-400">Carregando…</td>
              </tr>
            )}
            {!carregando && itens.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-gray-600 dark:text-gray-400">Nenhum serviço encontrado.</td>
              </tr>
            )}
            {itensOrdenados.map((servico) => (
              <tr key={servico.id} className="border-b border-gray-200 last:border-0 dark:border-gray-800">
                <td className="px-3 py-2">{servico.nome}</td>
                <td className="px-3 py-2">
                  {servico.codigo_tributacao_nacional}
                  {servico.codigo_tributacao_municipal && (
                    <span className="block text-xs text-gray-600 dark:text-gray-400">
                      municipal {servico.codigo_tributacao_municipal}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">{servico.aliquota_iss == null ? '—' : `${servico.aliquota_iss}%`}</td>
                <td className="px-3 py-2">
                  {formatarData(servico.vigencia_inicio)} a{' '}
                  {servico.vigencia_fim ? formatarData(servico.vigencia_fim) : 'sem data final'}
                </td>
                <td className={`px-3 py-2 ${servico.ativo ? 'text-estado-sucesso' : 'text-estado-neutro'}`}>
                  {servico.ativo ? 'Ativa' : 'Inativa'}
                </td>
                {podeEditar && (
                  <td className="px-3 py-2">
                    <div className="celula-acoes">
                      <button
                        type="button"
                        className="botao-acao-grid"
                        aria-label={`Editar ${servico.nome} de ${formatarData(servico.vigencia_inicio)}`}
                        onClick={() => setEdicao(servico)}
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        className="botao-acao-grid"
                        aria-label={`${servico.ativo ? 'Desativar' : 'Reativar'} ${servico.nome} de ${formatarData(servico.vigencia_inicio)}`}
                        onClick={() => alternarAtivo(servico)}
                      >
                        {servico.ativo ? 'Desativar' : 'Reativar'}
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConsultaVigente />
    </section>
  )
}
