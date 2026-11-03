import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { modelos as api } from '../../api/agendamentos.js'
import Aviso from '../../components/Aviso.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { mensagemErro } from '../../utils/erros.js'
import { dinheiro } from '../fiscal/situacoes.js'

export function Selo({ children, tipo = 'neutro' }) {
  const estilos = {
    neutro: 'border-gray-300 dark:border-gray-700',
    ok: 'border-estado-sucesso',
    atencao: 'border-estado-atencao',
    erro: 'border-estado-erro text-estado-erro',
  }
  return <span className={`rounded border px-2 py-0.5 text-xs ${estilos[tipo]}`}>{children}</span>
}

export default function Modelos() {
  const { temPermissao } = useAuth()
  const confirmar = useConfirmacao()
  const navegar = useNavigate()
  const podeEditar = temPermissao('agendamento.editar')
  const podeEmitir = temPermissao('nfse.emitir')
  const [lista, setLista] = useState(null)
  const [falha, setFalha] = useState('')
  const [aviso, setAviso] = useState(null)

  const carregar = useCallback(async () => {
    const resposta = await api.listar()
    if (resposta.ok) setLista(resposta.dados)
    else setFalha(mensagemErro(resposta, 'Não foi possível carregar os modelos.'))
  }, [])

  useEffect(() => {
    // Carga inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    carregar()
  }, [carregar])

  async function gerar(modelo) {
    const seguir = await confirmar({
      titulo: `Gerar um rascunho agora com “${modelo.nome}”?`,
      mensagem:
        'Será criado um rascunho com a cópia dos dados do modelo, com a competência do mês atual. ' +
        'Nada é enviado à Sefin: você confere e aprova depois, em Rascunhos.',
      textoConfirmar: 'Gerar rascunho',
      textoCancelar: 'Voltar',
    })
    if (!seguir) return
    setAviso(null)
    const resposta = await api.gerarRascunho(modelo.id)
    if (resposta.ok) {
      navegar('/agendamentos/rascunhos')
    } else {
      const erros = Object.values(resposta.dados?.erros ?? {}).join(' ')
      setAviso({ tipo: 'erro', texto: erros || mensagemErro(resposta) })
    }
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (!lista) return <p role="status" className="text-sm">Carregando…</p>

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Modelos de NFS-e</h1>
        {podeEditar && (
          <Link className="botao" to="/agendamentos/modelos/novo">
            Novo modelo
          </Link>
        )}
      </div>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Um modelo é a nota de referência: tomador, serviço, valor e texto. Cada rascunho gerado a partir dele recebe uma{' '}
        <strong>cópia</strong> desses dados. Alterar o modelo depois muda só os próximos rascunhos, nunca as notas já criadas.
      </p>
      <Aviso tipo={aviso?.tipo} className="mt-3">
        {aviso?.texto}
      </Aviso>

      {lista.length === 0 ? (
        <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">Nenhum modelo cadastrado ainda.</p>
      ) : (
        <ul aria-label="Modelos" className="mt-4 space-y-2">
          {lista.map((modelo) => (
            <li key={modelo.id} className="rounded border border-gray-200 bg-white p-3 text-sm dark:border-gray-800 dark:bg-gray-900">
              <p className="flex flex-wrap items-center gap-2">
                <strong className="text-base text-gray-900 dark:text-gray-100">{modelo.nome}</strong>
                <Selo tipo={modelo.ativo ? 'ok' : 'neutro'}>{modelo.ativo ? 'Ativo' : 'Inativo'}</Selo>
                {modelo.agendamentos_em_uso > 0 && (
                  <Selo>
                    {modelo.agendamentos_em_uso} agendamento(s) usando
                  </Selo>
                )}
              </p>
              <p className="mt-1 text-gray-600 dark:text-gray-400">
                {modelo.tomador_nome || 'Sem tomador'} · {modelo.servico_nome || 'Sem serviço'} ·{' '}
                {dinheiro(modelo.valores?.servico)}
              </p>
              {Object.keys(modelo.problemas).length > 0 && (
                <Aviso tipo="atencao" className="mt-2">
                  Este modelo não conseguiria gerar um rascunho hoje: {Object.values(modelo.problemas).join(' ')}
                </Aviso>
              )}
              <div className="mt-2 flex flex-wrap gap-2">
                <Link className="botao-leve" to={`/agendamentos/modelos/${modelo.id}`}>
                  {podeEditar ? 'Editar' : 'Ver'}
                </Link>
                {podeEmitir && modelo.ativo && (
                  <button type="button" className="botao-leve" onClick={() => gerar(modelo)}>
                    Gerar rascunho agora
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
