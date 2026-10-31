import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { agendamentos as api } from '../../api/agendamentos.js'
import Aviso from '../../components/Aviso.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { mensagemErro } from '../../utils/erros.js'
import { formatarData, formatarDataHora } from '../../utils/formatar.js'
import { Selo } from './Modelos.jsx'
import { resumoDaRegra, resumoDoFim } from './regra.js'

const TIPO_DO_SELO = { ativo: 'ok', suspenso: 'atencao', encerrado: 'neutro' }

export default function Agendamentos() {
  const { temPermissao } = useAuth()
  const confirmar = useConfirmacao()
  const podeEditar = temPermissao('agendamento.editar')
  const [lista, setLista] = useState(null)
  const [falha, setFalha] = useState('')
  const [aviso, setAviso] = useState(null)

  const carregar = useCallback(async () => {
    const resposta = await api.listar()
    if (resposta.ok) setLista(resposta.dados)
    else setFalha(mensagemErro(resposta, 'Não foi possível carregar os agendamentos.'))
  }, [])

  useEffect(() => {
    // Carga inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  async function executar(acao) {
    setAviso(null)
    const resposta = await acao()
    if (!resposta.ok) {
      const erros = resposta.dados && typeof resposta.dados === 'object' ? Object.values(resposta.dados).flat().join(' ') : ''
      setAviso({ tipo: 'erro', texto: erros || mensagemErro(resposta) })
      return
    }
    await carregar()
  }

  async function suspender(agendamento) {
    const seguir = await confirmar({
      titulo: `Suspender “${agendamento.nome}”?`,
      mensagem:
        'Enquanto estiver suspenso, nenhum rascunho é gerado. Ao reativar, vale só a próxima data futura: ' +
        'as datas que passarem durante a suspensão não são geradas depois.',
      textoConfirmar: 'Suspender',
      textoCancelar: 'Voltar',
    })
    if (seguir) await executar(() => api.suspender(agendamento.id, ''))
  }

  async function reativar(agendamento) {
    const seguir = await confirmar({
      titulo: `Reativar “${agendamento.nome}”?`,
      mensagem: 'O agendamento volta a gerar rascunhos a partir da próxima data futura. Nada atrasado é gerado.',
      textoConfirmar: 'Reativar',
      textoCancelar: 'Voltar',
    })
    if (seguir) await executar(() => api.reativar(agendamento.id))
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (!lista) return <p role="status" className="text-sm">Carregando…</p>

  const suspensos = lista.filter((a) => a.situacao === 'suspenso')
  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Agendamentos</h1>
        {podeEditar && (
          <Link className="botao" to="/agendamentos/novo">
            Novo agendamento
          </Link>
        )}
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Um agendamento repete um modelo de NFS-e e <strong>gera rascunhos</strong> nas datas combinadas: nada é emitido sozinho.
        Quem tem permissão de emitir confere e aprova em <Link className="underline" to="/agendamentos/rascunhos">Rascunhos</Link>.
        Feriados e fins de semana executam normalmente.
      </p>
      {suspensos.length > 0 && (
        <Aviso tipo="atencao" className="mt-3">
          {`${suspensos.length} agendamento(s) suspenso(s): não estão gerando rascunhos.`}
        </Aviso>
      )}
      <Aviso tipo={aviso?.tipo} className="mt-3">
        {aviso?.texto}
      </Aviso>

      {lista.length === 0 ? (
        <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">Nenhum agendamento ainda.</p>
      ) : (
        <ul aria-label="Agendamentos" className="mt-4 space-y-2">
          {lista.map((a) => (
            <li key={a.id} className="rounded border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900">
              <p className="flex flex-wrap items-center gap-2">
                <strong className="text-base text-gray-900 dark:text-gray-100">{a.nome}</strong>
                <Selo tipo={TIPO_DO_SELO[a.situacao]}>{a.situacao_rotulo}</Selo>
              </p>
              <p className="mt-1 text-gray-600 dark:text-gray-400">
                Modelo: {a.modelo_nome} · {resumoDaRegra(a)}
                {resumoDoFim(a, formatarData) ? ` · ${resumoDoFim(a, formatarData)}` : ''}
              </p>
              <p className="text-gray-600 dark:text-gray-400">
                Responsável: {a.responsavel_email} · Próxima execução: {a.proxima_execucao ? formatarDataHora(a.proxima_execucao) : '—'}
              </p>
              {a.motivo_situacao && a.situacao !== 'ativo' && (
                <Aviso tipo={a.situacao === 'suspenso' ? 'atencao' : 'info'} className="mt-2">
                  {a.motivo_situacao}
                </Aviso>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                <Link className="botao-leve" to={`/agendamentos/${a.id}`}>
                  {podeEditar ? 'Editar' : 'Ver'}
                </Link>
                <Link className="botao-leve" to={`/agendamentos/historico?agendamento=${a.id}`}>
                  Histórico
                </Link>
                {podeEditar && a.situacao === 'ativo' && (
                  <button type="button" className="botao-leve" onClick={() => suspender(a)}>
                    Suspender
                  </button>
                )}
                {podeEditar && a.situacao === 'suspenso' && (
                  <button type="button" className="botao" onClick={() => reativar(a)}>
                    Reativar
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
