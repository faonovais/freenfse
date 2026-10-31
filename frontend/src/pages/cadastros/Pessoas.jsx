import { useMemo, useState } from 'react'
import { copia, perfis as apiPerfis, pessoas } from '../../api/cadastros.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import CabecalhoColuna from '../../components/CabecalhoColuna.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import SelectBusca from '../../components/SelectBusca.jsx'
import SelectMultiBusca from '../../components/SelectMultiBusca.jsx'
import SeletorMunicipio from '../../components/SeletorMunicipio.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { useGridLocal } from '../../hooks/useGridLocal.js'
import { useLista } from '../../hooks/useLista.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

const TIPOS = [
  { valor: 'pf', rotulo: 'Pessoa física (CPF)' },
  { valor: 'pj', rotulo: 'Pessoa jurídica (CNPJ)' },
  { valor: 'estrangeiro', rotulo: 'Estrangeiro (NIF)' },
]
const ROTULO_DO_TIPO = { pf: 'Pessoa física', pj: 'Pessoa jurídica', estrangeiro: 'Estrangeiro' }
const MOTIVOS_SEM_NIF = [
  { valor: '0', rotulo: 'Não informado na nota de origem' },
  { valor: '1', rotulo: 'Dispensado do NIF' },
  { valor: '2', rotulo: 'Não exigência do NIF' },
]
const ENDERECOS = [
  { valor: 'nenhum', rotulo: 'Sem endereço' },
  { valor: 'brasil', rotulo: 'Endereço no Brasil' },
  { valor: 'exterior', rotulo: 'Endereço no exterior' },
]
const FILTRO_INICIAL = { busca: '', tipo: '', ativo: '', page: 1 }

function formularioDe(pessoa) {
  const exterior = Boolean(pessoa?.pais)
  const brasil = Boolean(pessoa?.codigo_municipio || pessoa?.cep)
  return {
    tipo: pessoa?.tipo ?? 'pf',
    documento: pessoa?.documento_formatado ?? '',
    nif: pessoa?.nif ?? '',
    motivo_sem_nif: pessoa?.motivo_sem_nif == null ? '' : String(pessoa.motivo_sem_nif),
    nome: pessoa?.nome ?? '',
    inscricao_municipal: pessoa?.inscricao_municipal ?? '',
    telefone: pessoa?.telefone ?? '',
    emails: (pessoa?.emails_envio ?? []).join(', '),
    endereco: exterior ? 'exterior' : brasil || !pessoa ? 'brasil' : 'nenhum',
    logradouro: pessoa?.logradouro ?? '',
    numero: pessoa?.numero ?? '',
    complemento: pessoa?.complemento ?? '',
    bairro: pessoa?.bairro ?? '',
    cep: pessoa?.cep ?? '',
    codigo_municipio: pessoa?.codigo_municipio ?? '',
    pais: pessoa?.pais ?? '',
    codigo_postal: pessoa?.codigo_postal ?? '',
    cidade: pessoa?.cidade ?? '',
    estado: pessoa?.estado ?? '',
    perfis: pessoa?.perfis ?? [],
    ativo: pessoa?.ativo ?? true,
  }
}

/** Envia só o que vale para o tipo escolhido; o restante vai vazio para limpar sobras. */
function corpoDe(f) {
  const estrangeiro = f.tipo === 'estrangeiro'
  const brasil = f.endereco === 'brasil'
  const exterior = estrangeiro && f.endereco === 'exterior'
  return {
    tipo: f.tipo,
    documento: estrangeiro ? '' : f.documento.trim(),
    nif: estrangeiro && f.motivo_sem_nif === '' ? f.nif.trim() : '',
    motivo_sem_nif: estrangeiro && f.motivo_sem_nif !== '' ? Number(f.motivo_sem_nif) : null,
    nome: f.nome.trim(),
    inscricao_municipal: f.inscricao_municipal.trim(),
    telefone: f.telefone.trim(),
    emails_envio: f.emails.split(/[,;\s]+/).filter(Boolean),
    logradouro: brasil || exterior ? f.logradouro : '',
    numero: brasil || exterior ? f.numero : '',
    complemento: brasil || exterior ? f.complemento : '',
    bairro: brasil || exterior ? f.bairro : '',
    cep: brasil ? f.cep : '',
    codigo_municipio: brasil ? f.codigo_municipio : '',
    pais: exterior ? f.pais : '',
    codigo_postal: exterior ? f.codigo_postal : '',
    cidade: exterior ? f.cidade : '',
    estado: exterior ? f.estado : '',
    perfis: f.perfis,
    ativo: f.ativo,
  }
}

function FormPessoa({ pessoa, opcoesDePerfil, aoSalvar, aoCancelar }) {
  const novo = !pessoa
  const inicial = useMemo(() => formularioDe(pessoa), [pessoa])
  const [f, setF] = useState(inicial)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)
  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  const estrangeiro = f.tipo === 'estrangeiro'

  useFormularioSujo(!salvo && JSON.stringify(f) !== JSON.stringify(inicial))

  async function salvar(evento) {
    evento.preventDefault()
    setSalvando(true)
    setErros({})
    setErroGeral('')
    const corpo = corpoDe(f)
    const resposta = novo ? await pessoas.criar(corpo) : await pessoas.alterar(pessoa.id, corpo)
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
      aria-label={novo ? 'Nova pessoa' : 'Editar pessoa'}
      className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{novo ? 'Nova pessoa' : 'Editar pessoa'}</h2>

      <div className="grid gap-3 sm:grid-cols-2">
        <CampoSelecao rotulo="Tipo de pessoa" opcoes={TIPOS} value={f.tipo} onChange={mudar('tipo')} erro={erros.tipo} />
        <Campo rotulo="Nome ou razão social" required value={f.nome} onChange={mudar('nome')} erro={erros.nome} />
      </div>

      {!estrangeiro && (
        <Campo
          rotulo={f.tipo === 'pf' ? 'CPF' : 'CNPJ'}
          required
          value={f.documento}
          onChange={mudar('documento')}
          erro={erros.documento}
          dica="Pode digitar com ou sem pontos e traço."
        />
      )}

      {estrangeiro && (
        <fieldset className="space-y-3">
          <legend className="text-sm">
            Identificação fiscal no exterior{' '}
            <BotaoAjuda rotulo="NIF">
              O NIF é o número de identificação fiscal do estrangeiro no país dele. Se não houver, escolha o motivo.
            </BotaoAjuda>
          </legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo
              rotulo="NIF"
              value={f.nif}
              disabled={f.motivo_sem_nif !== ''}
              onChange={mudar('nif')}
              erro={erros.nif}
            />
            <CampoSelecao
              rotulo="Ou o motivo de não informar o NIF"
              vazio="Vou informar o NIF"
              opcoes={MOTIVOS_SEM_NIF}
              value={f.motivo_sem_nif}
              onChange={mudar('motivo_sem_nif')}
              erro={erros.motivo_sem_nif}
            />
          </div>
        </fieldset>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <Campo
          rotulo="Inscrição municipal"
          value={f.inscricao_municipal}
          onChange={mudar('inscricao_municipal')}
          erro={erros.inscricao_municipal}
        />
        <Campo rotulo="Telefone" value={f.telefone} onChange={mudar('telefone')} erro={erros.telefone} />
        <Campo
          rotulo="E-mails para envio da nota"
          value={f.emails}
          onChange={mudar('emails')}
          erro={erros.emails_envio}
          dica="Separe vários e-mails por vírgula."
        />
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm">
          Endereço{' '}
          <BotaoAjuda rotulo="endereço">
            Para pessoa física ou jurídica do Brasil, o município é obrigatório: a nota fiscal exige o código do IBGE.
          </BotaoAjuda>
        </legend>
        {estrangeiro && (
          <CampoSelecao
            rotulo="Onde fica o endereço"
            opcoes={ENDERECOS}
            value={f.endereco}
            onChange={mudar('endereco')}
          />
        )}
        {f.endereco !== 'nenhum' && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Campo rotulo="Logradouro" value={f.logradouro} onChange={mudar('logradouro')} erro={erros.logradouro} />
            <Campo rotulo="Número" value={f.numero} onChange={mudar('numero')} erro={erros.numero} />
            <Campo rotulo="Complemento" value={f.complemento} onChange={mudar('complemento')} erro={erros.complemento} />
            <Campo rotulo="Bairro" value={f.bairro} onChange={mudar('bairro')} erro={erros.bairro} />
            {f.endereco === 'brasil' && (
              <>
                <Campo rotulo="CEP" value={f.cep} onChange={mudar('cep')} erro={erros.cep} />
                <SeletorMunicipio
                  rotulo="Município"
                  obrigatorio
                  valor={f.codigo_municipio}
                  aoMudar={(codigo) => setF((atual) => ({ ...atual, codigo_municipio: codigo }))}
                  erro={erros.codigo_municipio}
                />
              </>
            )}
            {f.endereco === 'exterior' && (
              <>
                <Campo rotulo="País (código de 2 letras)" maxLength={2} value={f.pais} onChange={mudar('pais')} erro={erros.pais} />
                <Campo rotulo="Código postal" value={f.codigo_postal} onChange={mudar('codigo_postal')} erro={erros.codigo_postal} />
                <Campo rotulo="Cidade" value={f.cidade} onChange={mudar('cidade')} erro={erros.cidade} />
                <Campo rotulo="Estado ou província" value={f.estado} onChange={mudar('estado')} erro={erros.estado} />
              </>
            )}
          </div>
        )}
      </fieldset>

      <div className="text-sm">
        Perfis{' '}
        <BotaoAjuda rotulo="perfis">A mesma pessoa pode ser cliente e fornecedor ao mesmo tempo.</BotaoAjuda>
        <SelectMultiBusca
          rotulo="Perfis"
          placeholder="Nenhum perfil"
          opcoes={opcoesDePerfil}
          valores={f.perfis}
          aoMudar={(valores) => setF((atual) => ({ ...atual, perfis: valores }))}
        />
      </div>

      <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={salvando}>
          {novo ? 'Cadastrar' : 'Salvar'}
        </button>
        <button type="button" className="botao-leve" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

function CopiarDeOutraEmpresa({ origens, aoConcluir, aoFechar }) {
  const confirmar = useConfirmacao()
  const { empresaAtiva } = useAuth()
  const [origem, setOrigem] = useState(null)
  const [lista, setLista] = useState(null)
  const [marcadas, setMarcadas] = useState([])
  const [erro, setErro] = useState('')
  const [resultado, setResultado] = useState(null)
  const [copiando, setCopiando] = useState(false)

  async function escolherOrigem(id) {
    setOrigem(id)
    setLista(null)
    setMarcadas([])
    setResultado(null)
    setErro('')
    const resposta = await copia.listarDaOrigem(id)
    if (resposta.ok) setLista(resposta.dados)
    else setErro(mensagemErro(resposta))
  }

  const alternar = (id) =>
    setMarcadas((atual) => (atual.includes(id) ? atual.filter((item) => item !== id) : [...atual, id]))

  async function copiar() {
    const nomeOrigem = origens.find((empresa) => empresa.id === origem)?.razao_social
    const seguir = await confirmar({
      titulo: 'Copiar cadastros?',
      mensagem:
        `${marcadas.length} pessoa(s) de "${nomeOrigem}" serão copiadas para "${empresaAtiva.razao_social}". ` +
        'É uma cópia: depois, alterar uma não muda a outra.',
      textoConfirmar: 'Copiar',
    })
    if (!seguir) return
    setCopiando(true)
    const resposta = await copia.copiar({ empresa_origem: origem, ids: marcadas })
    setCopiando(false)
    if (!resposta.ok) {
      setErro(mensagemErro(resposta))
      return
    }
    setResultado(resposta.dados)
    setMarcadas([])
    aoConcluir()
  }

  return (
    <section
      aria-label="Copiar de outra empresa"
      className="mt-4 space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">Copiar de outra empresa</h2>
      <p className="text-sm text-gray-600 dark:text-gray-400">
        Traz para <strong>{empresaAtiva.razao_social}</strong> pessoas já cadastradas em outra empresa a que você tem
        acesso. As pessoas copiadas passam a ser independentes das originais.
      </p>
      <div className="w-72 max-w-full text-sm">
        Copiar de
        <SelectBusca
          rotulo="Empresa de origem"
          placeholder="Escolha a empresa"
          opcoes={origens.map((empresa) => ({
            valor: empresa.id,
            rotulo: empresa.razao_social,
            detalhe: empresa.cnpj_formatado,
          }))}
          valor={origem}
          aoMudar={escolherOrigem}
        />
      </div>
      <Aviso tipo="erro">{erro}</Aviso>
      {lista && lista.length === 0 && <Aviso>Esta empresa não tem pessoas ativas para copiar.</Aviso>}
      {lista && lista.length > 0 && (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={marcadas.length === lista.length}
              onChange={(evento) => setMarcadas(evento.target.checked ? lista.map((p) => p.id) : [])}
            />
            Selecionar todas ({lista.length})
          </label>
          <ul aria-label="Pessoas da empresa de origem" className="max-h-64 overflow-auto text-sm">
            {lista.map((pessoa) => (
              <li key={pessoa.id}>
                <label className="flex items-center gap-2 py-1">
                  <input type="checkbox" checked={marcadas.includes(pessoa.id)} onChange={() => alternar(pessoa.id)} />
                  {pessoa.nome}
                  <span className="text-xs text-gray-600 dark:text-gray-400">{ROTULO_DO_TIPO[pessoa.tipo]}</span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      {resultado && (
        <div role="status" className="rounded border border-estado-sucesso p-3 text-sm">
          <p>
            <strong>{resultado.copiadas}</strong> pessoa(s) copiada(s).
          </p>
          {resultado.ignoradas.length > 0 && (
            <>
              <p className="mt-2">Não copiadas:</p>
              <ul className="list-disc pl-5">
                {resultado.ignoradas.map((item) => (
                  <li key={item.id}>
                    {item.nome}: {item.motivo}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <button type="button" className="botao" disabled={marcadas.length === 0 || copiando} onClick={copiar}>
          Copiar selecionadas
        </button>
        <button type="button" className="botao-leve" onClick={aoFechar}>
          Fechar
        </button>
      </div>
    </section>
  )
}

export default function Pessoas() {
  const confirmar = useConfirmacao()
  const { empresas, empresaAtiva, temPermissao } = useAuth()
  const podeEditar = temPermissao('cadastro.editar')
  const [filtros, setFiltros] = useState(FILTRO_INICIAL)
  const [busca, setBusca] = useState('')
  const { itens, total, carregando, erro, recarregar } = useLista(pessoas.listar, filtros)
  const { itensOrdenados, ordenacao, ordenarPor } = useGridLocal(itens, {
    acessores: { documento: (p) => p.documento_formatado || p.nif },
  })
  const perfisCarregados = useLista(apiPerfis.listar, FILTRO_INICIAL)
  const opcoesDePerfil = perfisCarregados.itens.map((p) => ({ valor: p.codigo, rotulo: p.nome }))
  const [edicao, setEdicao] = useState(null) // null | 'nova' | pessoa
  const [copiando, setCopiando] = useState(false)
  const [erroAcao, setErroAcao] = useState('')

  const origens = empresas.filter(
    (empresa) => empresa.id !== empresaAtiva?.id && empresa.permissoes.includes('cadastro.consultar'),
  )
  const paginas = Math.max(1, Math.ceil(total / 25))

  async function alternarAtivo(pessoa) {
    if (pessoa.ativo) {
      const desativar = await confirmar({
        titulo: 'Desativar pessoa?',
        mensagem: `"${pessoa.nome}" deixa de aparecer nas escolhas, mas o histórico é mantido.`,
        variante: 'perigo',
        textoConfirmar: 'Desativar',
      })
      if (!desativar) return
    }
    setErroAcao('')
    const resposta = await pessoas.alterar(pessoa.id, { ativo: !pessoa.ativo })
    if (!resposta.ok) setErroAcao(mensagemErro(resposta))
    recarregar()
  }

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Pessoas</h1>
        {podeEditar && (
          <div className="flex gap-2">
            {origens.length > 0 && (
              <button type="button" className="botao-leve" onClick={() => setCopiando(true)}>
                Copiar de outra empresa
              </button>
            )}
            <button type="button" className="botao" onClick={() => setEdicao('nova')}>
              Nova pessoa
            </button>
          </div>
        )}
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Clientes, fornecedores e intermediários de <strong>{empresaAtiva?.razao_social}</strong>. Cada empresa tem o seu
        próprio cadastro.
      </p>

      <form
        role="search"
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(evento) => {
          evento.preventDefault()
          setFiltros((atual) => ({ ...atual, busca: busca.trim(), page: 1 }))
        }}
      >
        <div className="w-64">
          <Campo rotulo="Buscar por nome ou documento" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <CampoSelecao
          rotulo="Tipo"
          vazio="Todos"
          opcoes={TIPOS}
          value={filtros.tipo}
          onChange={(e) => setFiltros((atual) => ({ ...atual, tipo: e.target.value, page: 1 }))}
        />
        <CampoSelecao
          rotulo="Situação"
          vazio="Todas"
          opcoes={[
            { valor: 'true', rotulo: 'Ativas' },
            { valor: 'false', rotulo: 'Inativas' },
          ]}
          value={filtros.ativo}
          onChange={(e) => setFiltros((atual) => ({ ...atual, ativo: e.target.value, page: 1 }))}
        />
        <button type="submit" className="botao-leve">
          Filtrar
        </button>
      </form>

      {copiando && (
        <CopiarDeOutraEmpresa origens={origens} aoConcluir={recarregar} aoFechar={() => setCopiando(false)} />
      )}
      {edicao && (
        <FormPessoa
          key={edicao === 'nova' ? 'nova' : edicao.id}
          pessoa={edicao === 'nova' ? null : edicao}
          opcoesDePerfil={opcoesDePerfil}
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
          <caption className="sr-only">Pessoas cadastradas</caption>
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <CabecalhoColuna rotulo="Nome" coluna="nome" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Documento" coluna="documento" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Tipo" coluna="tipo" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <th scope="col" className="px-3 py-2">Município</th>
              <th scope="col" className="px-3 py-2">Perfis</th>
              <CabecalhoColuna rotulo="Situação" coluna="ativo" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              {podeEditar && <th scope="col" className="px-3 py-2 text-right">Ações</th>}
            </tr>
          </thead>
          <tbody>
            {carregando && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-gray-600 dark:text-gray-400">Carregando…</td>
              </tr>
            )}
            {!carregando && itens.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-4 text-gray-600 dark:text-gray-400">Nenhuma pessoa encontrada.</td>
              </tr>
            )}
            {itensOrdenados.map((pessoa) => (
              <tr key={pessoa.id} className="border-b border-gray-200 last:border-0 dark:border-gray-800">
                <td className="px-3 py-2">{pessoa.nome}</td>
                <td className="px-3 py-2">{pessoa.documento_formatado || (pessoa.nif ? `NIF ${pessoa.nif}` : '—')}</td>
                <td className="px-3 py-2">{ROTULO_DO_TIPO[pessoa.tipo]}</td>
                <td className="px-3 py-2">{pessoa.municipio_nome || '—'}</td>
                <td className="px-3 py-2">{pessoa.perfis.join(', ') || '—'}</td>
                <td className={`px-3 py-2 ${pessoa.ativo ? 'text-estado-sucesso' : 'text-estado-neutro'}`}>
                  {pessoa.ativo ? 'Ativa' : 'Inativa'}
                </td>
                {podeEditar && (
                  <td className="px-3 py-2">
                    <div className="celula-acoes">
                      <button
                        type="button"
                        className="botao-acao-grid"
                        aria-label={`Editar ${pessoa.nome}`}
                        onClick={() => setEdicao(pessoa)}
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        className="botao-acao-grid"
                        aria-label={`${pessoa.ativo ? 'Desativar' : 'Reativar'} ${pessoa.nome}`}
                        onClick={() => alternarAtivo(pessoa)}
                      >
                        {pessoa.ativo ? 'Desativar' : 'Reativar'}
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {paginas > 1 && (
        <nav aria-label="Páginas" className="mt-3 flex items-center gap-3 text-sm">
          <button
            type="button"
            className="botao-leve"
            disabled={filtros.page <= 1}
            onClick={() => setFiltros((atual) => ({ ...atual, page: atual.page - 1 }))}
          >
            Anterior
          </button>
          <span>
            Página {filtros.page} de {paginas}
          </span>
          <button
            type="button"
            className="botao-leve"
            disabled={filtros.page >= paginas}
            onClick={() => setFiltros((atual) => ({ ...atual, page: atual.page + 1 }))}
          >
            Próxima
          </button>
        </nav>
      )}
    </section>
  )
}
