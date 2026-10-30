import { useState } from 'react'
import { usuarios } from '../../api/admin.js'
import CabecalhoColuna from '../../components/CabecalhoColuna.jsx'
import Campo from '../../components/Campo.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { useGridLocal } from '../../hooks/useGridLocal.js'
import { useLista } from '../../hooks/useLista.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

function FormUsuario({ usuario, aoSalvar, aoCancelar }) {
  const novo = !usuario.id
  const inicial = { email: usuario.email ?? '', nome: usuario.nome ?? '', is_master: usuario.is_master ?? false }
  const [email, setEmail] = useState(inicial.email)
  const [nome, setNome] = useState(inicial.nome)
  const [isMaster, setIsMaster] = useState(inicial.is_master)
  const [senha, setSenha] = useState('')
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [salvo, setSalvo] = useState(false)

  const sujo =
    !salvo &&
    (email !== inicial.email || nome !== inicial.nome || isMaster !== inicial.is_master || senha !== '')
  useFormularioSujo(sujo)

  async function salvar(evento) {
    evento.preventDefault()
    setSalvando(true)
    setErros({})
    setErroGeral('')
    const corpo = { email: email.trim(), nome: nome.trim(), is_master: isMaster }
    if (senha) corpo.senha = senha
    const resposta = novo ? await usuarios.criar(corpo) : await usuarios.alterar(usuario.id, corpo)
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
      aria-label={novo ? 'Novo usuário' : 'Editar usuário'}
      className="mt-4 space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{novo ? 'Novo usuário' : 'Editar usuário'}</h2>
      <Campo
        rotulo="E-mail"
        type="email"
        required
        value={email}
        onChange={(evento) => setEmail(evento.target.value)}
        erro={erros.email}
      />
      <Campo
        rotulo="Nome"
        value={nome}
        onChange={(evento) => setNome(evento.target.value)}
        erro={erros.nome}
      />
      <Campo
        rotulo={novo ? 'Senha inicial' : 'Nova senha'}
        type="password"
        autoComplete="new-password"
        value={senha}
        onChange={(evento) => setSenha(evento.target.value)}
        erro={erros.senha}
        dica="Opcional para quem entra só pelo Google. Mínimo de 10 caracteres."
      />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={isMaster} onChange={(evento) => setIsMaster(evento.target.checked)} />
        Master (administra o sistema e acessa todas as empresas)
      </label>
      {erros.is_master && <p className="text-xs text-estado-erro">{erros.is_master}</p>}
      {erroGeral && Object.keys(erros).length === 0 && (
        <p role="alert" className="text-sm text-estado-erro">
          {erroGeral}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className="botao" disabled={salvando}>
          {novo ? 'Criar usuário' : 'Salvar'}
        </button>
        <button type="button" className="botao-leve" onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}

export default function Usuarios() {
  const confirmar = useConfirmacao()
  const { usuario: logado } = useAuth()
  const [filtros, setFiltros] = useState({ busca: '' })
  const [busca, setBusca] = useState('')
  const { itens, carregando, erro, recarregar } = useLista(usuarios.listar, filtros)
  const { itensOrdenados, ordenacao, ordenarPor } = useGridLocal(itens, { colunaInicial: 'email' })
  const [edicao, setEdicao] = useState(null)
  const [erroAcao, setErroAcao] = useState('')

  async function alternarAtivo(usuario) {
    if (usuario.is_active) {
      const desativar = await confirmar({
        titulo: 'Desativar usuário?',
        mensagem: `${usuario.email} não conseguirá mais entrar no sistema.`,
        variante: 'perigo',
        textoConfirmar: 'Desativar',
      })
      if (!desativar) return
    }
    setErroAcao('')
    const resposta = await usuarios.alterar(usuario.id, { is_active: !usuario.is_active })
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
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Usuários</h1>
        <button type="button" className="botao" onClick={() => setEdicao({})}>
          Novo usuário
        </button>
      </div>

      <form
        role="search"
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(evento) => {
          evento.preventDefault()
          setFiltros({ busca: busca.trim() })
        }}
      >
        <div className="w-64">
          <Campo rotulo="Buscar" value={busca} onChange={(evento) => setBusca(evento.target.value)} />
        </div>
        <button type="submit" className="botao-leve">
          Filtrar
        </button>
      </form>

      {edicao && (
        <FormUsuario
          key={edicao.id ?? 'novo'}
          usuario={edicao}
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
          <caption className="sr-only">Usuários cadastrados</caption>
          <thead className="border-b border-gray-200 dark:border-gray-800">
            <tr>
              <CabecalhoColuna rotulo="E-mail" coluna="email" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Nome" coluna="nome" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Papel" coluna="is_master" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="2FA" coluna="mfa_ativo" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <CabecalhoColuna rotulo="Situação" coluna="is_active" ordenacao={ordenacao} aoOrdenar={ordenarPor} />
              <th scope="col" className="px-3 py-2 text-right">Ações</th>
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
                  Nenhum usuário encontrado.
                </td>
              </tr>
            )}
            {itensOrdenados.map((usuario) => (
              <tr key={usuario.id} className="border-b border-gray-200 last:border-0 dark:border-gray-800">
                <td className="px-3 py-2">{usuario.email}</td>
                <td className="px-3 py-2">{usuario.nome}</td>
                <td className="px-3 py-2">{usuario.is_master ? 'Master' : 'Usuário'}</td>
                <td className="px-3 py-2">{usuario.mfa_ativo ? 'Ativo' : 'Não configurado'}</td>
                <td
                  className={`px-3 py-2 ${usuario.is_active ? 'text-estado-sucesso' : 'text-estado-neutro'}`}
                >
                  {usuario.is_active ? 'Ativo' : 'Inativo'}
                </td>
                <td className="px-3 py-2">
                  <div className="celula-acoes">
                    <button
                      type="button"
                      className="botao-acao-grid"
                      aria-label={`Editar ${usuario.email}`}
                      onClick={() => setEdicao(usuario)}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="botao-acao-grid"
                      aria-label={`${usuario.is_active ? 'Desativar' : 'Reativar'} ${usuario.email}`}
                      disabled={usuario.id === logado.id}
                      title={usuario.id === logado.id ? 'Você não pode desativar o próprio usuário.' : undefined}
                      onClick={() => alternarAtivo(usuario)}
                    >
                      {usuario.is_active ? 'Desativar' : 'Reativar'}
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
