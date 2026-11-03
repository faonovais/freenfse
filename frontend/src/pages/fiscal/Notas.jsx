import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { notas } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useLista } from '../../hooks/useLista.js'
import { formatarData, formatarDataHora } from '../../utils/formatar.js'
import { AMBIENTES, SITUACOES, dinheiro, rotuloDaSituacao, seloDaSituacao } from './situacoes.js'

const FILTROS_VAZIOS = { periodo_inicio: '', periodo_fim: '', situacao: '', tomador: '', numero: '' }
const TAMANHO = 25

/** Bloqueios que impedem de emitir, cada um com o caminho para resolver. */
export function BloqueiosDeEmissao({ prontidao }) {
  if (!prontidao || prontidao.pronta) return null
  return (
    <section aria-label="Pendências para emitir" className="space-y-2">
      {prontidao.bloqueios.map((bloqueio) => (
        <Aviso key={bloqueio.codigo} tipo="atencao">
          {bloqueio.mensagem}{' '}
          <Link className="underline" to={bloqueio.tela}>
            Resolver
          </Link>
        </Aviso>
      ))}
    </section>
  )
}

export default function Notas() {
  const { temPermissao } = useAuth()
  const navegar = useNavigate()
  const [prontidao, setProntidao] = useState(null)
  const [campos, setCampos] = useState(FILTROS_VAZIOS)
  const [filtros, setFiltros] = useState({ ...FILTROS_VAZIOS, pagina: 1 })

  useEffect(() => {
    let ativo = true
    notas.prontidao().then((resposta) => {
      if (ativo && resposta.ok) setProntidao(resposta.dados)
    })
    return () => {
      ativo = false
    }
  }, [])

  // A API pagina com `page`; a tela fala em `pagina`.
  const consultaApi = useMemo(() => {
    const { pagina, ...resto } = filtros
    return { ...resto, page: pagina, tamanho: TAMANHO }
  }, [filtros])
  const { itens, total, carregando, erro } = useLista(notas.listar, consultaApi)

  const mudar = (campo) => (evento) => setCampos((atual) => ({ ...atual, [campo]: evento.target.value }))
  const aplicar = (evento) => {
    evento.preventDefault()
    setFiltros({ ...campos, pagina: 1 })
  }
  const limpar = () => {
    setCampos(FILTROS_VAZIOS)
    setFiltros({ ...FILTROS_VAZIOS, pagina: 1 })
  }
  const paginas = Math.max(1, Math.ceil(total / TAMANHO))
  const podeEmitir = temPermissao('nfse.emitir') && Boolean(prontidao?.pronta)

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl text-gray-900 dark:text-gray-100">Notas fiscais (NFS-e)</h1>
          {prontidao && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Ambiente: {AMBIENTES[prontidao.ambiente] ?? prontidao.ambiente} · Leiaute em uso: {prontidao.leiaute_descricao}
            </p>
          )}
        </div>
        {temPermissao('nfse.emitir') && (
          <button type="button" className="botao" disabled={!podeEmitir} onClick={() => navegar('/fiscal/notas/nova')}>
            Nova nota
          </button>
        )}
      </div>

      <div className="mt-3">
        <BloqueiosDeEmissao prontidao={prontidao} />
      </div>

      <form
        onSubmit={aplicar}
        aria-label="Filtros das notas"
        className="mt-4 grid gap-3 rounded border border-gray-200 p-4 sm:grid-cols-2 lg:grid-cols-5 dark:border-gray-800"
      >
        <Campo rotulo="Competência de" type="date" value={campos.periodo_inicio} onChange={mudar('periodo_inicio')} />
        <Campo rotulo="Competência até" type="date" value={campos.periodo_fim} onChange={mudar('periodo_fim')} />
        <CampoSelecao
          rotulo="Situação"
          vazio="Todas"
          opcoes={SITUACOES.map((s) => ({ valor: s.valor, rotulo: s.rotulo }))}
          value={campos.situacao}
          onChange={mudar('situacao')}
        />
        <Campo rotulo="Tomador (nome ou CNPJ/CPF)" value={campos.tomador} onChange={mudar('tomador')} />
        <Campo rotulo="Número da nota" value={campos.numero} onChange={mudar('numero')} />
        <div className="flex gap-2 sm:col-span-2 lg:col-span-5">
          <button type="submit" className="botao">
            Filtrar
          </button>
          <button type="button" className="botao-leve" onClick={limpar}>
            Limpar filtros
          </button>
        </div>
      </form>

      <Aviso tipo="erro" className="mt-4">
        {erro}
      </Aviso>
      {carregando && <p className="mt-4 text-sm">Carregando as notas…</p>}
      {!carregando && !erro && itens.length === 0 && (
        <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">Nenhuma nota encontrada com estes filtros.</p>
      )}
      {itens.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table aria-label="Notas fiscais" className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800">
                <th className="p-2">Número</th>
                <th className="p-2">Competência</th>
                <th className="p-2">Tomador</th>
                <th className="p-2 text-right">Valor</th>
                <th className="p-2">Situação</th>
                <th className="p-2">Emitida em</th>
              </tr>
            </thead>
            <tbody>
              {itens.map((nota) => (
                <tr key={nota.id} className="border-b border-gray-100 dark:border-gray-900">
                  <td className="p-2">
                    <Link className="underline" to={`/fiscal/notas/${nota.id}`}>
                      {nota.numero_nfse ? `Nº ${nota.numero_nfse}` : nota.numero_dps ? `DPS ${nota.numero_dps}` : 'Rascunho'}
                    </Link>
                  </td>
                  <td className="p-2">{formatarData(nota.competencia)}</td>
                  <td className="p-2">
                    {nota.tomador_nome}
                    <span className="block text-xs text-gray-600 dark:text-gray-400">{nota.tomador_documento}</span>
                  </td>
                  <td className="p-2 text-right">{dinheiro(nota.valor_servico)}</td>
                  <td className="p-2">
                    <span className={`rounded border px-2 py-0.5 text-xs ${seloDaSituacao(nota.situacao)}`}>
                      {rotuloDaSituacao(nota.situacao)}
                    </span>
                  </td>
                  <td className="p-2">{formatarDataHora(nota.emitida_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > TAMANHO && (
        <nav aria-label="Páginas" className="mt-3 flex items-center gap-3 text-sm">
          <button
            type="button"
            className="botao-leve"
            disabled={filtros.pagina <= 1}
            onClick={() => setFiltros((f) => ({ ...f, pagina: f.pagina - 1 }))}
          >
            Anterior
          </button>
          <span>
            Página {filtros.pagina} de {paginas}
          </span>
          <button
            type="button"
            className="botao-leve"
            disabled={filtros.pagina >= paginas}
            onClick={() => setFiltros((f) => ({ ...f, pagina: f.pagina + 1 }))}
          >
            Próxima
          </button>
        </nav>
      )}
    </div>
  )
}
