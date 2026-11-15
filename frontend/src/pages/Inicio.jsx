import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { notas } from '../api/fiscal.js'
import PainelColapsavel from '../components/PainelColapsavel.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'
import { formatarDataHora } from '../utils/formatar.js'
import { dinheiro } from './fiscal/situacoes.js'

export default function Inicio() {
  const { usuario, empresaAtiva, temPermissao } = useAuth()
  const [estadoResumo, setEstadoResumo] = useState(null)

  const empresaId = empresaAtiva?.id ?? null
  const podeConsultar = Boolean(empresaAtiva && temPermissao('nfse.consultar'))

  useEffect(() => {
    if (!empresaId || !podeConsultar) return undefined
    let ativo = true
    notas.dashboard().then((resposta) => {
      if (!ativo) return
      setEstadoResumo(resposta.ok ? { empresaId, dados: resposta.dados } : null)
    })
    return () => {
      ativo = false
    }
  }, [empresaId, podeConsultar])

  if (!empresaAtiva) {
    return (
      <section>
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Início</h1>
        <p role="status" className="mt-4 text-sm">
          Você ainda não tem acesso a nenhuma empresa.{' '}
          {usuario.is_master ? (
            <>
              Cadastre uma em <Link className="text-accent underline" to="/admin/empresas">Empresas</Link>.
            </>
          ) : (
            'Peça ao administrador do sistema para liberar o seu acesso.'
          )}
        </p>
      </section>
    )
  }

  const resumo = podeConsultar && estadoResumo?.empresaId === empresaId ? estadoResumo.dados : null
  const servicos = resumo?.servicos_mais_utilizados ?? []
  const ultimasNotas = resumo?.ultimas_notas ?? []
  const maxQuantidade = Math.max(...servicos.map((item) => item.quantidade), 1)

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Início</h1>
      <p className="mt-2 text-sm">
        Você está operando <strong>{empresaAtiva.razao_social}</strong> ({empresaAtiva.cnpj_formatado}) com o perfil{' '}
        <strong>{empresaAtiva.perfil}</strong>.
      </p>

      {podeConsultar && resumo && (
        <section aria-labelledby="titulo-resumo-dashboard" className="mt-6 space-y-6">
          <h2 id="titulo-resumo-dashboard" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Resumo dos últimos 30 dias
          </h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded border border-gray-200 p-4 dark:border-gray-800">
              <p className="text-xs text-gray-600 dark:text-gray-400">NFS-e emitidas (30 dias)</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
                {resumo.quantidade_emitidas}
              </p>
            </div>
            <div className="rounded border border-gray-200 p-4 dark:border-gray-800">
              <p className="text-xs text-gray-600 dark:text-gray-400">Valor total dos serviços (30 dias)</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
                {dinheiro(resumo.valor_total_servicos)}
              </p>
            </div>
          </div>

          <div className="rounded border border-gray-200 p-4 dark:border-gray-800">
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">Serviços mais utilizados</h3>
            {servicos.length === 0 ? (
              <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">
                Nenhuma NFS-e emitida nos últimos 30 dias.
              </p>
            ) : (
              <ul aria-label="Serviços mais utilizados" className="mt-4 space-y-3">
                {servicos.map((item, indice) => {
                  const percentual = Math.max(8, Math.round((item.quantidade / maxQuantidade) * 100))
                  return (
                    <li key={item.servico}>
                      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                        <span className="font-medium text-gray-900 dark:text-gray-100">{item.servico}</span>
                        <span className="tabular-nums text-gray-600 dark:text-gray-400">
                          {item.quantidade} {item.quantidade === 1 ? 'nota' : 'notas'} · {dinheiro(item.valor_total)}
                        </span>
                      </div>
                      <div className="mt-1.5 h-3 w-full overflow-hidden rounded bg-gray-100 dark:bg-gray-800">
                        <div
                          className="h-full rounded transition-all"
                          style={{
                            width: `${percentual}%`,
                            backgroundColor: `var(--color-data-${(indice % 6) + 1})`,
                          }}
                        />
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="rounded border border-gray-200 p-4 dark:border-gray-800">
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">Últimas NFS-e emitidas</h3>
            {ultimasNotas.length === 0 ? (
              <p className="mt-3 text-sm text-gray-600 dark:text-gray-400">
                Nenhuma NFS-e emitida nos últimos 30 dias.
              </p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Últimas NFS-e emitidas</caption>
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-800">
                      <th scope="col" className="p-2">Série</th>
                      <th scope="col" className="p-2">Número DPS</th>
                      <th scope="col" className="p-2">Número NFS-e</th>
                      <th scope="col" className="p-2">Data de emissão</th>
                      <th scope="col" className="p-2">Tomador</th>
                      <th scope="col" className="p-2 text-right">Valor do serviço</th>
                      <th scope="col" className="p-2 text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ultimasNotas.map((nota) => (
                      <tr key={nota.id} className="border-b border-gray-100 dark:border-gray-900">
                        <td className="p-2 tabular-nums">{nota.serie || '—'}</td>
                        <td className="p-2 tabular-nums">{nota.numero_dps ?? '—'}</td>
                        <td className="p-2 tabular-nums">{nota.numero_nfse || '—'}</td>
                        <td className="p-2 whitespace-nowrap">{formatarDataHora(nota.emitida_em)}</td>
                        <td className="p-2">{nota.tomador_nome || '—'}</td>
                        <td className="p-2 text-right whitespace-nowrap tabular-nums">
                          {dinheiro(nota.valor_servico)}
                        </td>
                        <td className="p-2 text-right whitespace-nowrap">
                          <Link className="text-accent underline" to={`/notas/${nota.id}`}>
                            Abrir nota
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      <div className="mt-6">
        <PainelColapsavel titulo="Suas permissões nesta empresa">
          <ul aria-label="Permissões" className="grid gap-1 text-sm sm:grid-cols-2">
            {empresaAtiva.permissoes.map((permissao) => (
              <li key={permissao}>
                <code>{permissao}</code>
              </li>
            ))}
          </ul>
        </PainelColapsavel>
      </div>
    </section>
  )
}
