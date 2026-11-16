import { useMemo, useState } from 'react'
import { servicosOficiais } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import CabecalhoColuna from '../../components/CabecalhoColuna.jsx'
import Campo from '../../components/Campo.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { useGridLocal } from '../../hooks/useGridLocal.js'
import { useLista } from '../../hooks/useLista.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

const SEM_FILTRO = {}

function formularioDe(item) {
  return {
    codigo_tributacao_nacional: item?.codigo_tributacao_nacional ?? '',
    nbs: item?.nbs ?? '',
    cst_ibs_cbs: item?.cst_ibs_cbs ?? '',
    c_class_trib: item?.c_class_trib ?? '',
    codigo_indicador_operacao: item?.codigo_indicador_operacao ?? '',
    ativo: item?.ativo ?? true,
  }
}

function FormServicoOficial({ item, aoSalvar, aoCancelar }) {
  const novo = !item
  const inicial = useMemo(() => formularioDe(item), [item])
  const [f, setF] = useState(inicial)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const [catalogo, setCatalogo] = useState(null)
  const [consultandoCatalogo, setConsultandoCatalogo] = useState(false)
  const [erroCatalogo, setErroCatalogo] = useState('')

  useFormularioSujo(!salvo && JSON.stringify(f) !== JSON.stringify(inicial))

  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))

  async function consultarCatalogo() {
    setConsultandoCatalogo(true)
    setErroCatalogo('')
    const resposta = await servicosOficiais.catalogo({
      codigo_nacional: f.codigo_tributacao_nacional,
      nbs: f.nbs,
      c_class_trib: f.c_class_trib,
    })
    setConsultandoCatalogo(false)
    if (!resposta.ok) {
      setErroCatalogo(mensagemErro(resposta))
      return
    }
    setCatalogo(resposta.dados)
  }

  async function salvar(evento) {
    evento.preventDefault()
    setSalvando(true)
    setErros({})
    setErroGeral('')
    const resposta = novo
      ? await servicosOficiais.criar(f)
      : await servicosOficiais.alterar(item.id, f)
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
      aria-label={novo ? 'Novo serviço oficial' : 'Editar serviço oficial'}
      className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
        {novo ? 'Novo serviço oficial' : 'Editar serviço oficial'}
      </h3>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Campo
          rotulo="Código de tributação nacional (LC 116)"
          required
          value={f.codigo_tributacao_nacional}
          onChange={mudar('codigo_tributacao_nacional')}
          erro={erros.codigo_tributacao_nacional}
          dica="6 dígitos, por exemplo 01.01.01."
        />
        <Campo
          rotulo="NBS"
          required
          value={f.nbs}
          onChange={mudar('nbs')}
          erro={erros.nbs}
          dica="9 dígitos da NBS compatível com o item LC 116."
        />
        <Campo
          rotulo="Indicador da operação (cIndOp)"
          required
          inputMode="numeric"
          maxLength={6}
          value={f.codigo_indicador_operacao}
          onChange={mudar('codigo_indicador_operacao')}
          erro={erros.codigo_indicador_operacao}
          dica="6 dígitos do Anexo VIII."
        />
        <Campo
          rotulo="CST do IBS/CBS"
          required
          inputMode="numeric"
          maxLength={3}
          value={f.cst_ibs_cbs}
          onChange={mudar('cst_ibs_cbs')}
          erro={erros.cst_ibs_cbs}
          dica="3 dígitos (iguais ao início do cClassTrib)."
        />
        <Campo
          rotulo="Classificação tributária (cClassTrib)"
          required
          inputMode="numeric"
          maxLength={6}
          value={f.c_class_trib}
          onChange={mudar('c_class_trib')}
          erro={erros.c_class_trib}
          dica="6 dígitos da tabela oficial."
        />
      </div>

      <div className="space-y-3 rounded border border-gray-200 p-3 dark:border-gray-800">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-gray-600 dark:text-gray-400">
            Consulte as combinações do Anexo VIII e as classificações aceitas na NFS-e antes de salvar.
          </p>
          <button
            type="button"
            className="botao-leve"
            onClick={consultarCatalogo}
            disabled={consultandoCatalogo}
          >
            {consultandoCatalogo ? 'Consultando catálogo…' : 'Consultar catálogo oficial'}
          </button>
        </div>
        <Aviso tipo="erro">{erroCatalogo}</Aviso>

        {catalogo && (
          <div className="space-y-3 text-xs" aria-label="Resultados do catálogo oficial">
            {catalogo.nbs_opcoes?.length > 0 && (
              <div>
                <p className="font-medium text-gray-800 dark:text-gray-200">NBS previstas no Anexo VIII:</p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {catalogo.nbs_opcoes.slice(0, 12).map((opcao) => (
                    <li key={opcao.nbs}>
                      <button
                        type="button"
                        className="botao-leve"
                        onClick={() => setF((atual) => ({ ...atual, nbs: opcao.nbs }))}
                      >
                        Usar NBS {opcao.nbs}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {catalogo.indicadores?.length > 0 && (
              <div>
                <p className="font-medium text-gray-800 dark:text-gray-200">
                  Indicadores de operação (cIndOp) para item e NBS:
                </p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {catalogo.indicadores.map((ind) => (
                    <li key={ind.codigo} className="flex items-center gap-1">
                      <button
                        type="button"
                        className="botao-leve"
                        onClick={() => setF((atual) => ({ ...atual, codigo_indicador_operacao: ind.codigo }))}
                      >
                        Usar cIndOp {ind.codigo}
                      </button>
                      {ind.local_fornecimento && (
                        <span className="text-gray-600 dark:text-gray-400">({ind.local_fornecimento})</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {catalogo.classificacoes?.length > 0 && (
              <div>
                <p className="font-medium text-gray-800 dark:text-gray-200">
                  Classificações tributárias (cClassTrib) aceitas:
                </p>
                <ul className="mt-1 max-h-40 space-y-1 overflow-y-auto">
                  {catalogo.classificacoes.slice(0, 15).map((itemClass) => (
                    <li key={itemClass.codigo} className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="botao-leve"
                        onClick={() =>
                          setF((atual) => ({
                            ...atual,
                            c_class_trib: itemClass.codigo,
                            cst_ibs_cbs: itemClass.cst,
                          }))
                        }
                      >
                        Usar {itemClass.codigo}
                      </button>
                      <span className="text-gray-700 dark:text-gray-300">
                        CST {itemClass.cst} — {itemClass.descricao}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={salvando}>
          {novo ? 'Cadastrar serviço oficial' : 'Salvar'}
        </button>
        <button type="button" className="botao-leve" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

/**
 * Cadastro e consulta de serviços oficiais (LC 116 + NBS + IBS/CBS) vinculados à empresa.
 */
export default function ServicosOficiais({ embutido = false }) {
  const Titulo = embutido ? 'h2' : 'h1'
  const confirmar = useConfirmacao()
  const { temPermissao } = useAuth()
  const podeEditar = temPermissao('config.editar')
  const [busca, setBusca] = useState('')
  const [filtros, setFiltros] = useState(SEM_FILTRO)
  const { itens, carregando, erro, recarregar } = useLista(servicosOficiais.listar, filtros)
  const { itensOrdenados, ordenacao, ordenarPor } = useGridLocal(itens, {
    colunaInicial: 'codigo_tributacao_nacional',
  })
  const [edicao, setEdicao] = useState(null)
  const [erroAcao, setErroAcao] = useState('')

  async function alternarAtivo(item) {
    if (item.ativo) {
      const desativar = await confirmar({
        titulo: 'Desativar serviço oficial?',
        mensagem: `O vínculo oficial ${item.codigo_tributacao_nacional} (NBS ${item.nbs}) não poderá ser selecionado em novos serviços desta empresa.`,
        variante: 'perigo',
        textoConfirmar: 'Desativar',
      })
      if (!desativar) return
    }
    setErroAcao('')
    const resposta = await servicosOficiais.alterar(item.id, { ativo: !item.ativo })
    if (!resposta.ok) setErroAcao(mensagemErro(resposta))
    recarregar()
  }

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Titulo
            className={
              embutido ? 'text-lg text-gray-900 dark:text-gray-100' : 'text-2xl text-gray-900 dark:text-gray-100'
            }
          >
            Serviços oficiais
          </Titulo>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Combinações oficiais de tributação nacional (LC 116), NBS e classificação IBS/CBS disponíveis para o
            cadastro de serviços da empresa.
          </p>
        </div>
        {podeEditar && (
          <button type="button" className="botao" onClick={() => setEdicao('novo')}>
            Novo serviço oficial
          </button>
        )}
      </div>

      <form
        role="search"
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(evento) => {
          evento.preventDefault()
          setFiltros(busca.trim() ? { busca: busca.trim() } : SEM_FILTRO)
        }}
      >
        <div className="w-64">
          <Campo rotulo="Buscar serviço oficial" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <button type="submit" className="botao-leve">
          Filtrar
        </button>
      </form>

      {edicao && (
        <FormServicoOficial
          key={edicao === 'novo' ? 'novo' : edicao.id}
          item={edicao === 'novo' ? null : edicao}
          aoSalvar={() => {
            setEdicao(null)
            recarregar()
          }}
          aoCancelar={() => setEdicao(null)}
        />
      )}

      <Aviso tipo="erro" className="mt-4">
        {erroAcao || erro}
      </Aviso>

      <div className="mt-4 overflow-x-auto rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Serviços oficiais vinculados</caption>
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <CabecalhoColuna
                rotulo="Código LC 116"
                coluna="codigo_tributacao_nacional"
                ordenacao={ordenacao}
                aoOrdenar={ordenarPor}
              />
              <CabecalhoColuna rotulo="NBS" coluna="nbs" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna
                rotulo="CST / cClassTrib"
                coluna="c_class_trib"
                ordenacao={ordenacao}
                aoOrdenar={ordenarPor}
              />
              <CabecalhoColuna
                rotulo="cIndOp"
                coluna="codigo_indicador_operacao"
                ordenacao={ordenacao}
                aoOrdenar={ordenarPor}
              />
              <CabecalhoColuna rotulo="Situação" coluna="ativo" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              {podeEditar && <th scope="col" className="px-3 py-2 text-right">Ações</th>}
            </tr>
          </thead>
          <tbody>
            {carregando && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-gray-600 dark:text-gray-400">
                  Carregando…
                </td>
              </tr>
            )}
            {!carregando && itens.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-gray-600 dark:text-gray-400">
                  Nenhum serviço oficial vinculado a esta empresa.
                </td>
              </tr>
            )}
            {itensOrdenados.map((item) => (
              <tr key={item.id} className="border-b border-gray-200 last:border-0 dark:border-gray-800">
                <td className="px-3 py-2">
                  <span className="font-medium tabular-nums">{item.codigo_tributacao_nacional}</span>
                  {item.descricao_item_lc116 && (
                    <span className="block text-xs text-gray-600 dark:text-gray-400">{item.descricao_item_lc116}</span>
                  )}
                </td>
                <td className="px-3 py-2 tabular-nums">{item.nbs}</td>
                <td className="px-3 py-2">
                  <span className="tabular-nums">
                    {item.cst_ibs_cbs} / {item.c_class_trib}
                  </span>
                  {item.descricao_class_trib && (
                    <span className="block text-xs text-gray-600 dark:text-gray-400">{item.descricao_class_trib}</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className="tabular-nums">{item.codigo_indicador_operacao}</span>
                  {item.local_fornecimento && (
                    <span className="block text-xs text-gray-600 dark:text-gray-400">{item.local_fornecimento}</span>
                  )}
                </td>
                <td className={`px-3 py-2 ${item.ativo ? 'text-estado-sucesso' : 'text-estado-neutro'}`}>
                  {item.ativo ? 'Ativo' : 'Inativo'}
                </td>
                {podeEditar && (
                  <td className="px-3 py-2">
                    <div className="celula-acoes">
                      <button
                        type="button"
                        className="botao-acao-grid"
                        aria-label={`Editar serviço oficial ${item.codigo_tributacao_nacional} NBS ${item.nbs}`}
                        onClick={() => setEdicao(item)}
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        className="botao-acao-grid"
                        aria-label={`${item.ativo ? 'Desativar' : 'Reativar'} serviço oficial ${item.codigo_tributacao_nacional} NBS ${item.nbs}`}
                        onClick={() => alternarAtivo(item)}
                      >
                        {item.ativo ? 'Desativar' : 'Reativar'}
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
