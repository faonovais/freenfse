import { useEffect, useState } from 'react'
import { empresas } from '../../api/admin.js'
import CabecalhoColuna from '../../components/CabecalhoColuna.jsx'
import Campo from '../../components/Campo.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { useGridLocal } from '../../hooks/useGridLocal.js'
import { useLista } from '../../hooks/useLista.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

function FormEmpresa({ empresa, servicosOficiaisDisponiveis = [], aoSalvar, aoCancelar }) {
  const novo = !empresa.id
  const [razaoSocial, setRazaoSocial] = useState(empresa.razao_social ?? '')
  const [nomeExibicao, setNomeExibicao] = useState(empresa.nome_exibicao ?? '')
  const [cnpj, setCnpj] = useState(empresa.cnpj_formatado ?? '')
  const [servicosOficiais, setServicosOficiais] = useState(empresa.servicos_oficiais ?? [])
  const [servicosAlterados, setServicosAlterados] = useState(false)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)

  const sujo =
    !salvo &&
    (razaoSocial !== (empresa.razao_social ?? '') ||
      nomeExibicao !== (empresa.nome_exibicao ?? '') ||
      (novo && cnpj !== '') ||
      servicosAlterados)
  useFormularioSujo(sujo)

  function alternarServicoOficial(id) {
    setServicosAlterados(true)
    setServicosOficiais((atual) => (atual.includes(id) ? atual.filter((item) => item !== id) : [...atual, id]))
  }

  async function salvar(evento) {
    evento.preventDefault()
    setSalvando(true)
    setErros({})
    setErroGeral('')
    const nomeExibicaoLimpo = nomeExibicao.trim()
    const corpo = novo ? { razao_social: razaoSocial.trim(), cnpj } : { razao_social: razaoSocial.trim() }
    if (novo ? nomeExibicaoLimpo !== '' : nomeExibicaoLimpo !== (empresa.nome_exibicao ?? '')) {
      corpo.nome_exibicao = nomeExibicaoLimpo
    }
    if (novo ? servicosOficiais.length > 0 : servicosAlterados) {
      corpo.servicos_oficiais = servicosOficiais
    }
    const resposta = novo ? await empresas.criar(corpo) : await empresas.alterar(empresa.id, corpo)
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
      aria-label={novo ? 'Nova empresa' : 'Editar empresa'}
      className="mt-4 space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{novo ? 'Nova empresa' : 'Editar empresa'}</h2>
      <Campo
        rotulo="Razão social"
        required
        value={razaoSocial}
        onChange={(evento) => setRazaoSocial(evento.target.value)}
        erro={erros.razao_social}
      />
      <Campo
        rotulo="Nome para exibição"
        value={nomeExibicao}
        onChange={(evento) => setNomeExibicao(evento.target.value)}
        erro={erros.nome_exibicao}
        dica="Opcional. Se preenchido, aparece como nome principal no seletor de empresa."
      />
      <Campo
        rotulo="CNPJ"
        required
        disabled={!novo}
        value={cnpj}
        onChange={(evento) => setCnpj(evento.target.value)}
        erro={erros.cnpj}
        dica={novo ? 'O CNPJ não poderá ser alterado depois. Aceita CNPJ alfanumérico.' : 'O CNPJ não pode ser alterado.'}
      />
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-gray-900 dark:text-gray-100">Serviços oficiais vinculados</legend>
        {servicosOficiaisDisponiveis.length === 0 ? (
          <p className="text-xs text-gray-600 dark:text-gray-400">
            Nenhum serviço oficial cadastrado para vínculo direto ainda.
          </p>
        ) : (
          <div className="max-h-48 space-y-1.5 overflow-y-auto rounded border border-gray-200 p-2.5 dark:border-gray-800">
            {servicosOficiaisDisponiveis.map((servico) => (
              <label key={servico.id} className="flex items-start gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={servicosOficiais.includes(servico.id)}
                  onChange={() => alternarServicoOficial(servico.id)}
                />
                <span>
                  LC 116 <strong>{servico.codigo_tributacao_nacional}</strong> · NBS <strong>{servico.nbs}</strong> ·
                  cClassTrib <strong>{servico.c_class_trib}</strong> · cIndOp{' '}
                  <strong>{servico.codigo_indicador_operacao}</strong>
                  {servico.descricao_item_lc116 ? ` — ${servico.descricao_item_lc116}` : ''}
                </span>
              </label>
            ))}
          </div>
        )}
        {erros.servicos_oficiais && <p className="text-xs text-estado-erro">{erros.servicos_oficiais}</p>}
      </fieldset>
      {erroGeral && Object.keys(erros).length === 0 && (
        <p role="alert" className="text-sm text-estado-erro">
          {erroGeral}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={salvando}>
          {novo ? 'Criar empresa' : 'Salvar'}
        </button>
        <button type="button" className="botao-leve" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

export default function Empresas() {
  const confirmar = useConfirmacao()
  const [filtros, setFiltros] = useState({ busca: '', ativo: '' })
  const [busca, setBusca] = useState('')
  const { itens, carregando, erro, recarregar } = useLista(empresas.listar, filtros)
  const { itensOrdenados, ordenacao, ordenarPor } = useGridLocal(itens, { colunaInicial: 'razao_social' })
  const [edicao, setEdicao] = useState(null)
  const [erroAcao, setErroAcao] = useState('')
  const [servicosOficiaisDisponiveis, setServicosOficiaisDisponiveis] = useState([])

  useEffect(() => {
    let ativo = true
    empresas.servicosOficiais().then((resposta) => {
      if (ativo && resposta.ok && Array.isArray(resposta.dados)) {
        setServicosOficiaisDisponiveis(resposta.dados)
      }
    })
    return () => {
      ativo = false
    }
  }, [])

  async function alternarAtivo(empresa) {
    if (empresa.ativo) {
      const desativar = await confirmar({
        titulo: 'Desativar empresa?',
        mensagem: `Os usuários perdem o acesso a "${empresa.razao_social}" imediatamente. Os dados são mantidos.`,
        variante: 'perigo',
        textoConfirmar: 'Desativar',
      })
      if (!desativar) return
    }
    setErroAcao('')
    const resposta = await empresas.alterar(empresa.id, { ativo: !empresa.ativo })
    if (!resposta.ok) setErroAcao(mensagemErro(resposta))
    recarregar()
  }

  function aoSalvar() {
    setEdicao(null)
    recarregar()
  }

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Empresas</h1>
        <button type="button" className="botao" onClick={() => setEdicao({})}>
          Nova empresa
        </button>
      </div>

      <form
        role="search"
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(evento) => {
          evento.preventDefault()
          setFiltros((atual) => ({ ...atual, busca: busca.trim() }))
        }}
      >
        <div className="w-64">
          <Campo rotulo="Buscar" value={busca} onChange={(evento) => setBusca(evento.target.value)} />
        </div>
        <div className="text-sm">
          <label htmlFor="filtro-situacao-empresa">Situação</label>
          <select
            id="filtro-situacao-empresa"
            className="campo mt-1"
            value={filtros.ativo}
            onChange={(evento) => setFiltros((atual) => ({ ...atual, ativo: evento.target.value }))}
          >
            <option value="">Todas</option>
            <option value="true">Ativas</option>
            <option value="false">Inativas</option>
          </select>
        </div>
        <button type="submit" className="botao-leve">
          Filtrar
        </button>
      </form>

      {edicao && (
        <FormEmpresa
          key={edicao.id ?? 'nova'}
          empresa={edicao}
          servicosOficiaisDisponiveis={servicosOficiaisDisponiveis}
          aoSalvar={aoSalvar}
          aoCancelar={() => setEdicao(null)}
        />
      )}

      {erroAcao && (
        <p role="alert" className="mt-4 text-sm text-estado-erro">
          {erroAcao}
        </p>
      )}
      {erro && (
        <p role="alert" className="mt-4 text-sm text-estado-erro">
          {erro}
        </p>
      )}

      <div className="mt-4 overflow-x-auto rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">Empresas cadastradas</caption>
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <CabecalhoColuna rotulo="Razão social" coluna="razao_social" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Nome para exibição" coluna="nome_exibicao" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="CNPJ" coluna="cnpj" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Situação" coluna="ativo" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <th scope="col" className="px-3 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {carregando && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-gray-600 dark:text-gray-400">
                  Carregando…
                </td>
              </tr>
            )}
            {!carregando && itens.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-gray-600 dark:text-gray-400">
                  Nenhuma empresa encontrada.
                </td>
              </tr>
            )}
            {itensOrdenados.map((empresa) => (
              <tr key={empresa.id} className="border-b border-gray-200 last:border-0 dark:border-gray-800">
                <td className="px-3 py-2">{empresa.razao_social}</td>
                <td className="px-3 py-2">{empresa.nome_exibicao || '—'}</td>
                <td className="px-3 py-2">{empresa.cnpj_formatado}</td>
                <td className={`px-3 py-2 ${empresa.ativo ? 'text-estado-sucesso' : 'text-estado-neutro'}`}>
                  {empresa.ativo ? 'Ativa' : 'Inativa'}
                </td>
                <td className="px-3 py-2">
                  <div className="celula-acoes">
                    <button
                      type="button"
                      className="botao-acao-grid"
                      aria-label={`Editar ${empresa.razao_social}`}
                      onClick={() => setEdicao(empresa)}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="botao-acao-grid"
                      aria-label={`${empresa.ativo ? 'Desativar' : 'Reativar'} ${empresa.razao_social}`}
                      onClick={() => alternarAtivo(empresa)}
                    >
                      {empresa.ativo ? 'Desativar' : 'Reativar'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
