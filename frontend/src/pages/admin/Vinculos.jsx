import { useEffect, useState } from 'react'
import { empresas, permissoes as buscarPermissoes, usuarios, vinculos } from '../../api/admin.js'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import CabecalhoColuna from '../../components/CabecalhoColuna.jsx'
import SelectBusca from '../../components/SelectBusca.jsx'
import SelectMultiBusca from '../../components/SelectMultiBusca.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { useGridLocal } from '../../hooks/useGridLocal.js'
import { useLista } from '../../hooks/useLista.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

const SEM_FILTRO = {}
const TODAS = 'todas'
const FILTRO_ATIVOS = { ativo: 'true' }

function iguais(a, b) {
  return a.length === b.length && [...a].sort().every((valor, indice) => valor === [...b].sort()[indice])
}

function opcoesDePermissoes(catalogo) {
  return catalogo.map((permissao) => ({ valor: permissao.nome, rotulo: permissao.nome, detalhe: permissao.descricao }))
}

function FormVinculo({ vinculo, usuariosLista, empresasLista, regras, aoSalvar, aoCancelar }) {
  const novo = !vinculo.id
  const [usuario, setUsuario] = useState(vinculo.usuario ?? null)
  const [empresa, setEmpresa] = useState(vinculo.empresa ?? null)
  const [perfil, setPerfil] = useState(vinculo.perfil ?? 'consulta')
  const [extras, setExtras] = useState(vinculo.permissoes_extras ?? [])
  const [removidas, setRemovidas] = useState(vinculo.permissoes_removidas ?? [])
  const [erro, setErro] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)

  const sujo =
    !salvo &&
    (usuario !== (vinculo.usuario ?? null) ||
      empresa !== (vinculo.empresa ?? null) ||
      perfil !== (vinculo.perfil ?? 'consulta') ||
      !iguais(extras, vinculo.permissoes_extras ?? []) ||
      !iguais(removidas, vinculo.permissoes_removidas ?? []))
  useFormularioSujo(sujo)

  const padraoDoPerfil = regras.perfis.find((item) => item.valor === perfil)?.permissoes ?? []
  // Extra só faz sentido para o que o perfil não dá; remoção só para o que o perfil dá.
  const catalogoExtras = regras.permissoes.filter((item) => !padraoDoPerfil.includes(item.nome))
  const catalogoRemocao = regras.permissoes.filter((item) => padraoDoPerfil.includes(item.nome))

  function trocarPerfil(novoPerfil) {
    setPerfil(novoPerfil)
    const padrao = regras.perfis.find((item) => item.valor === novoPerfil)?.permissoes ?? []
    setExtras((atual) => atual.filter((nome) => !padrao.includes(nome)))
    setRemovidas((atual) => atual.filter((nome) => padrao.includes(nome)))
  }

  async function salvar(evento) {
    evento.preventDefault()
    if (novo && (!usuario || !empresa)) {
      setErro('Escolha o usuário e a empresa.')
      return
    }
    setSalvando(true)
    setErro('')
    const corpo = { perfil, permissoes_extras: extras, permissoes_removidas: removidas }
    const resposta = novo
      ? await vinculos.criar({ ...corpo, usuario, empresa })
      : await vinculos.alterar(vinculo.id, corpo)
    setSalvando(false)
    if (!resposta.ok) {
      const porCampo = errosPorCampo(resposta)
      setErro(Object.keys(porCampo).length > 0 ? Object.values(porCampo).join(' ') : mensagemErro(resposta))
      return
    }
    setSalvo(true)
    aoSalvar()
  }

  return (
    <form
      onSubmit={salvar}
      aria-label={novo ? 'Novo vínculo' : 'Editar vínculo'}
      className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{novo ? 'Novo vínculo' : 'Editar vínculo'}</h2>

      {novo ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="text-sm">
            Usuário
            <SelectBusca
              rotulo="Usuário"
              opcoes={usuariosLista.map((item) => ({ valor: item.id, rotulo: item.email, detalhe: item.nome }))}
              valor={usuario}
              aoMudar={setUsuario}
            />
          </div>
          <div className="text-sm">
            Empresa
            <SelectBusca
              rotulo="Empresa"
              opcoes={empresasLista.map((item) => ({
                valor: item.id,
                rotulo: item.razao_social,
                detalhe: item.cnpj_formatado,
              }))}
              valor={empresa}
              aoMudar={setEmpresa}
            />
          </div>
        </div>
      ) : (
        <p className="text-sm">
          <strong>{vinculo.usuario_email}</strong> em <strong>{vinculo.empresa_razao_social}</strong>
        </p>
      )}

      <div className="text-sm">
        <label htmlFor="vinculo-perfil">Perfil</label>
        <select
          id="vinculo-perfil"
          className="campo mt-1"
          value={perfil}
          onChange={(evento) => trocarPerfil(evento.target.value)}
        >
          {regras.perfis.map((item) => (
            <option key={item.valor} value={item.valor}>
              {item.rotulo}
            </option>
          ))}
        </select>
      </div>

      <div className="text-sm">
        <span>
          Permissões extras (além do perfil){' '}
          <BotaoAjuda rotulo="permissões extras">
            Libera operações que o perfil escolhido não inclui, só para este usuário nesta empresa.
          </BotaoAjuda>
        </span>
        <SelectMultiBusca
          rotulo="Permissões extras"
          placeholder="Nenhuma"
          opcoes={opcoesDePermissoes(catalogoExtras)}
          valores={extras}
          aoMudar={setExtras}
          vazio="Todas as permissões já fazem parte do perfil"
        />
      </div>
      <div className="text-sm">
        <span>
          Permissões removidas (do perfil){' '}
          <BotaoAjuda rotulo="permissões removidas">
            Retira operações que o perfil escolhido incluiria, só para este usuário nesta empresa.
          </BotaoAjuda>
        </span>
        <SelectMultiBusca
          rotulo="Permissões removidas"
          placeholder="Nenhuma"
          opcoes={opcoesDePermissoes(catalogoRemocao)}
          valores={removidas}
          aoMudar={setRemovidas}
          vazio="Este perfil não tem permissões a remover"
        />
      </div>

      {erro && (
        <p role="alert" className="text-sm text-estado-erro">
          {erro}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={salvando}>
          {novo ? 'Conceder acesso' : 'Salvar'}
        </button>
        <button type="button" className="botao-leve" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

export default function Vinculos() {
  const confirmar = useConfirmacao()
  const [filtros, setFiltros] = useState(SEM_FILTRO)
  const { itens, carregando, erro, recarregar } = useLista(vinculos.listar, filtros)
  const { itensOrdenados, ordenacao, ordenarPor } = useGridLocal(itens, {
    colunaInicial: 'usuario_email',
    acessores: { empresa_razao_social: (item) => item.empresa_razao_social },
  })
  const [apoio, setApoio] = useState({ usuarios: [], empresas: [], regras: null })
  const [edicao, setEdicao] = useState(null)
  const [erroAcao, setErroAcao] = useState('')

  // Opções dos seletores e catálogo de permissões, carregados uma vez.
  useEffect(() => {
    let ativo = true
    Promise.all([usuarios.listar(FILTRO_ATIVOS), empresas.listar(FILTRO_ATIVOS), buscarPermissoes()]).then(
      ([listaUsuarios, listaEmpresas, regras]) => {
        if (!ativo) return
        setApoio({
          usuarios: listaUsuarios.ok ? listaUsuarios.dados : [],
          empresas: listaEmpresas.ok ? listaEmpresas.dados : [],
          regras: regras.ok ? regras.dados : null,
        })
      },
    )
    return () => {
      ativo = false
    }
  }, [])

  function filtrarPorEmpresa(id) {
    setFiltros(id === TODAS ? SEM_FILTRO : { empresa: id })
  }

  async function alternarAtivo(vinculo) {
    if (vinculo.ativo) {
      const revogar = await confirmar({
        titulo: 'Revogar acesso?',
        mensagem: `${vinculo.usuario_email} perde o acesso a "${vinculo.empresa_razao_social}" imediatamente.`,
        variante: 'perigo',
        textoConfirmar: 'Revogar acesso',
      })
      if (!revogar) return
    }
    setErroAcao('')
    const resposta = await vinculos.alterar(vinculo.id, { ativo: !vinculo.ativo })
    if (!resposta.ok) setErroAcao(mensagemErro(resposta))
    recarregar()
  }

  function aoSalvar() {
    setEdicao(null)
    recarregar()
  }

  const rotuloPerfil = (valor) => apoio.regras?.perfis.find((item) => item.valor === valor)?.rotulo ?? valor

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Vínculos</h1>
        <button type="button" className="botao" disabled={!apoio.regras} onClick={() => setEdicao({})}>
          Novo vínculo
        </button>
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Define o que cada usuário pode fazer em cada empresa. Sem vínculo ativo, o acesso à empresa é negado.
      </p>

      <div className="mt-4 w-72 max-w-full text-sm">
        Filtrar por empresa
        <SelectBusca
          rotulo="Filtrar por empresa"
          placeholder="Todas as empresas"
          opcoes={[
            { valor: TODAS, rotulo: 'Todas as empresas' },
            ...apoio.empresas.map((item) => ({
              valor: item.id,
              rotulo: item.razao_social,
              detalhe: item.cnpj_formatado,
            })),
          ]}
          valor={filtros.empresa ?? TODAS}
          aoMudar={filtrarPorEmpresa}
        />
      </div>

      {edicao && apoio.regras && (
        <FormVinculo
          key={edicao.id ?? 'novo'}
          vinculo={edicao}
          usuariosLista={apoio.usuarios}
          empresasLista={apoio.empresas}
          regras={apoio.regras}
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
          <caption className="sr-only">Vínculos entre usuários e empresas</caption>
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <CabecalhoColuna rotulo="Usuário" coluna="usuario_email" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Empresa" coluna="empresa_razao_social" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Perfil" coluna="perfil" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
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
                  Nenhum vínculo encontrado.
                </td>
              </tr>
            )}
            {itensOrdenados.map((vinculo) => (
              <tr key={vinculo.id} className="border-b border-gray-200 last:border-0 dark:border-gray-800">
                <td className="px-3 py-2">{vinculo.usuario_email}</td>
                <td className="px-3 py-2">
                  {vinculo.empresa_razao_social}
                  <span className="block text-xs text-gray-600 dark:text-gray-400">{vinculo.empresa_cnpj}</span>
                </td>
                <td className="px-3 py-2">{rotuloPerfil(vinculo.perfil)}</td>
                <td className={`px-3 py-2 ${vinculo.ativo ? 'text-estado-sucesso' : 'text-estado-neutro'}`}>
                  {vinculo.ativo ? 'Ativo' : 'Revogado'}
                </td>
                <td className="px-3 py-2">
                  <div className="celula-acoes">
                    <button
                      type="button"
                      className="botao-acao-grid"
                      disabled={!apoio.regras}
                      aria-label={`Editar vínculo de ${vinculo.usuario_email} em ${vinculo.empresa_razao_social}`}
                      onClick={() => setEdicao(vinculo)}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="botao-acao-grid"
                      aria-label={`${vinculo.ativo ? 'Revogar' : 'Restaurar'} vínculo de ${vinculo.usuario_email} em ${vinculo.empresa_razao_social}`}
                      onClick={() => alternarAtivo(vinculo)}
                    >
                      {vinculo.ativo ? 'Revogar' : 'Restaurar'}
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
