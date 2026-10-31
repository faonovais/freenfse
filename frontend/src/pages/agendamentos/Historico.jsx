import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { agendamentos as apiAgendamentos, execucoes as api } from '../../api/agendamentos.js'
import Aviso from '../../components/Aviso.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import { useLista } from '../../hooks/useLista.js'
import { formatarData, formatarDataHora } from '../../utils/formatar.js'
import { Selo } from './Modelos.jsx'

const SITUACOES = [
  { valor: 'gerada', rotulo: 'Rascunho gerado' },
  { valor: 'falhou', rotulo: 'Falhou' },
  { valor: 'perdida', rotulo: 'Não executada (atraso)' },
  { valor: 'suspensa', rotulo: 'Não executada (suspenso)' },
]
const TIPO_DO_SELO = { gerada: 'ok', falhou: 'erro', perdida: 'atencao', suspensa: 'atencao', processando: 'neutro' }

export default function Historico() {
  const [params, setParams] = useSearchParams()
  const [agendamentos, setAgendamentos] = useState([])
  const filtros = useMemo(
    () => ({ agendamento: params.get('agendamento') ?? '', situacao: params.get('situacao') ?? '' }),
    [params],
  )
  const { itens, carregando, erro } = useLista(api.listar, filtros)

  useEffect(() => {
    let ativo = true
    apiAgendamentos.listar().then((r) => ativo && r.ok && setAgendamentos(r.dados))
    return () => {
      ativo = false
    }
  }, [])

  const mudar = (campo) => (evento) => {
    const proximo = new URLSearchParams(params)
    if (evento.target.value) proximo.set(campo, evento.target.value)
    else proximo.delete(campo)
    setParams(proximo)
  }

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Histórico de execuções</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        O que cada agendamento fez em cada data. Uma data que falha ou não é executada <strong>não conta</strong> como execução
        realizada; o agendamento tenta de novo na próxima data.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <CampoSelecao
          rotulo="Agendamento"
          vazio="Todos"
          opcoes={agendamentos.map((a) => ({ valor: String(a.id), rotulo: a.nome }))}
          value={filtros.agendamento}
          onChange={mudar('agendamento')}
        />
        <CampoSelecao rotulo="Situação" vazio="Todas" opcoes={SITUACOES} value={filtros.situacao} onChange={mudar('situacao')} />
      </div>
      <Aviso tipo="erro" className="mt-3">
        {erro}
      </Aviso>
      {carregando ? (
        <p role="status" className="mt-4 text-sm">Carregando…</p>
      ) : itens.length === 0 ? (
        <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">Nenhuma execução registrada.</p>
      ) : (
        <ul aria-label="Execuções" className="mt-4 space-y-2">
          {itens.map((e) => (
            <li key={e.id} className="rounded border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900">
              <p className="flex flex-wrap items-center gap-2">
                <strong>{formatarData(e.data_execucao)}</strong>
                <span>{e.agendamento_nome}</span>
                <Selo tipo={TIPO_DO_SELO[e.situacao]}>{e.situacao_rotulo}</Selo>
                <span className="text-xs text-gray-600 dark:text-gray-400">{formatarDataHora(e.concluido_em)}</span>
              </p>
              {e.erro && <p className="mt-1 text-gray-700 dark:text-gray-300">{e.erro}</p>}
              {e.nfse && (
                <p className="mt-1">
                  <Link className="underline" to={`/fiscal/notas/${e.nfse}`}>
                    Abrir o rascunho
                  </Link>
                  {e.nfse_situacao && e.nfse_situacao !== 'rascunho' ? ` (hoje: ${e.nfse_situacao})` : ''}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
