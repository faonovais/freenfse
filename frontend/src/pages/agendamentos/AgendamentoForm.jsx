import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { agendamentos as api, opcoes as apiOpcoes } from '../../api/agendamentos.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarData } from '../../utils/formatar.js'
import { dataPorExtenso, NOMES_DOS_MESES, ROTULOS_CURTOS_DOS_DIAS } from './regra.js'

export const ATRASO_DA_PREVIA = 400

const VAZIO = {
  nome: '',
  modelo: '',
  responsavel: '',
  frequencia: 'mensal',
  intervalo: '1',
  dias_semana: [],
  dia_do_mes: '5',
  mes: '1',
  hora: '08:00',
  data_inicio: '', // preenchida com "amanhã" ao abrir um agendamento novo
  fim: 'nunca', // nunca | data | execucoes
  data_fim: '',
  max_execucoes: '',
}

/** Formulário de um agendamento novo: começa amanhã (a data de início não pode ser passada). */
function formularioNovo() {
  const amanha = new Date(Date.now() + 24 * 3600 * 1000)
  const mes = String(amanha.getMonth() + 1).padStart(2, '0')
  const dia = String(amanha.getDate()).padStart(2, '0')
  return { ...VAZIO, data_inicio: `${amanha.getFullYear()}-${mes}-${dia}` }
}

function formularioDe(a) {
  return {
    nome: a.nome,
    modelo: String(a.modelo),
    responsavel: String(a.responsavel),
    frequencia: a.frequencia,
    intervalo: String(a.intervalo),
    dias_semana: a.dias_semana ?? [],
    dia_do_mes: a.dia_do_mes == null ? '5' : String(a.dia_do_mes),
    mes: a.mes == null ? '1' : String(a.mes),
    hora: a.hora,
    data_inicio: a.data_inicio,
    fim: a.data_fim ? 'data' : a.max_execucoes ? 'execucoes' : 'nunca',
    data_fim: a.data_fim ?? '',
    max_execucoes: a.max_execucoes ? String(a.max_execucoes) : '',
  }
}

/** Só os campos que a frequência usa; o resto não vai (e não confunde a validação). */
function regraDe(f) {
  const corpo = { frequencia: f.frequencia, hora: f.hora, data_inicio: f.data_inicio }
  if (['diaria', 'semanal', 'mensal'].includes(f.frequencia)) corpo.intervalo = Number(f.intervalo) || 1
  else corpo.intervalo = 1
  if (f.frequencia === 'semanal') corpo.dias_semana = f.dias_semana
  if (f.frequencia === 'mensal' || f.frequencia === 'anual') corpo.dia_do_mes = Number(f.dia_do_mes) || null
  if (f.frequencia === 'anual') corpo.mes = Number(f.mes) || null
  corpo.data_fim = f.fim === 'data' && f.data_fim ? f.data_fim : null
  corpo.max_execucoes = f.fim === 'execucoes' && f.max_execucoes ? Number(f.max_execucoes) : null
  return corpo
}

function PreviaDeDatas({ previa }) {
  if (!previa) return null
  if (previa.erro) return <Aviso tipo="atencao">{previa.erro}</Aviso>
  return (
    <section aria-label="Próximas datas" className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
      <h3 className="text-base text-gray-900 dark:text-gray-100">Próximas datas</h3>
      {previa.datas.length === 0 ? (
        <p className="text-gray-600 dark:text-gray-400">Com estas datas não haveria nenhuma execução futura.</p>
      ) : (
        <ol className="mt-1 list-decimal space-y-0.5 pl-5">
          {previa.datas.map((d) => (
            <li key={d.instante}>{dataPorExtenso(d, formatarData)}</li>
          ))}
        </ol>
      )}
      {previa.termina && previa.datas.length > 0 && (
        <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">Depois destas datas o agendamento termina.</p>
      )}
    </section>
  )
}

export default function AgendamentoForm() {
  const { id } = useParams()
  const navegar = useNavigate()
  const { temPermissao } = useAuth()
  const podeEditar = temPermissao('agendamento.editar')
  const [padrao] = useState(formularioNovo)
  const [f, setF] = useState(padrao)
  const [inicial, setInicial] = useState(padrao)
  const [opcoes, setOpcoes] = useState({ modelos: [], responsaveis: [], frequencias: [] })
  const [carregando, setCarregando] = useState(Boolean(id))
  const [falha, setFalha] = useState('')
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvando, setSalvando] = useState(false)
  const [previa, setPrevia] = useState(null)
  const [concluido, setConcluido] = useState(false)

  useEffect(() => {
    let ativo = true
    apiOpcoes().then((r) => ativo && r.ok && setOpcoes(r.dados))
    if (id) {
      api.obter(id).then((r) => {
        if (!ativo) return
        if (r.ok) {
          setF(formularioDe(r.dados))
          setInicial(formularioDe(r.dados))
        } else {
          setFalha(mensagemErro(r, 'Não foi possível abrir o agendamento.'))
        }
        setCarregando(false)
      })
    }
    return () => {
      ativo = false
    }
  }, [id])

  const sujo = useMemo(() => JSON.stringify(f) !== JSON.stringify(inicial), [f, inicial])
  useFormularioSujo(sujo && !concluido)
  useEffect(() => {
    if (concluido && !sujo) navegar('/agendamentos')
  }, [concluido, sujo, navegar])

  // Pré-visualização das próximas datas, um instante depois de a regra mudar.
  const regra = useMemo(() => regraDe(f), [f])
  const chaveDaRegra = JSON.stringify(regra)
  useEffect(() => {
    if (carregando || !regra.data_inicio || !regra.hora) return undefined
    let ativo = true
    const relogio = setTimeout(async () => {
      const resposta = await api.previaDeDatas({ ...regra, quantidade: 6, ...(id ? { agendamento: Number(id) } : {}) })
      if (!ativo) return
      if (resposta.ok) setPrevia(resposta.dados)
      else setPrevia({ erro: Object.values(resposta.dados ?? {}).flat().join(' ') || mensagemErro(resposta) })
    }, ATRASO_DA_PREVIA)
    return () => {
      ativo = false
      clearTimeout(relogio)
    }
    // A regra é recalculada a partir de `f`; `chaveDaRegra` evita refazer a chamada à toa.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaveDaRegra, carregando, id])

  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  const alternarDia = (dia) =>
    setF((atual) => ({
      ...atual,
      dias_semana: atual.dias_semana.includes(dia) ? atual.dias_semana.filter((d) => d !== dia) : [...atual.dias_semana, dia].sort(),
    }))

  async function salvar(evento) {
    evento.preventDefault()
    setErros({})
    setErroGeral('')
    setSalvando(true)
    const corpo = { nome: f.nome, modelo: Number(f.modelo) || undefined, responsavel: Number(f.responsavel) || undefined, ...regra }
    const resposta = id ? await api.alterar(id, corpo) : await api.criar(corpo)
    setSalvando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return
    }
    setInicial(f)
    setConcluido(true)
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (carregando) return <p role="status" className="text-sm">Carregando…</p>

  const usaIntervalo = ['diaria', 'semanal', 'mensal'].includes(f.frequencia)
  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">{id ? 'Agendamento' : 'Novo agendamento'}</h1>
      <form
        onSubmit={salvar}
        aria-label="Agendamento"
        className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <fieldset disabled={!podeEditar} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Campo rotulo="Nome do agendamento" value={f.nome} onChange={mudar('nome')} erro={erros.nome} />
            <CampoSelecao
              rotulo="Modelo de NFS-e"
              vazio="Escolha"
              opcoes={opcoes.modelos.map((m) => ({ valor: String(m.id), rotulo: m.nome }))}
              value={f.modelo}
              onChange={mudar('modelo')}
              erro={erros.modelo}
            />
            <CampoSelecao
              rotulo="Responsável"
              vazio="Escolha"
              opcoes={opcoes.responsaveis.map((r) => ({ valor: String(r.id), rotulo: r.nome || r.email, detalhe: r.email }))}
              value={f.responsavel}
              onChange={mudar('responsavel')}
              erro={erros.responsavel}
              dica="Quem recebe os avisos e aprova os rascunhos. Precisa ter permissão de emitir notas."
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <CampoSelecao
              rotulo="Repete"
              opcoes={opcoes.frequencias}
              value={f.frequencia}
              onChange={mudar('frequencia')}
              erro={erros.frequencia}
            />
            {usaIntervalo && (
              <Campo
                rotulo={`A cada quantos ${f.frequencia === 'diaria' ? 'dias' : f.frequencia === 'semanal' ? 'semanas' : 'meses'}?`}
                type="number"
                min={1}
                value={f.intervalo}
                onChange={mudar('intervalo')}
                erro={erros.intervalo}
                dica="1 = toda vez; 2 = pula uma; e assim por diante, contando a partir da data de início."
              />
            )}
            <Campo rotulo="Hora (Brasília)" type="time" value={f.hora} onChange={mudar('hora')} erro={erros.hora} />
          </div>

          {f.frequencia === 'semanal' && (
            <fieldset className="text-sm">
              <legend>Dias da semana</legend>
              <div className="mt-1 flex flex-wrap gap-3">
                {ROTULOS_CURTOS_DOS_DIAS.map((rotulo, dia) => (
                  <label key={rotulo} className="flex items-center gap-1">
                    <input type="checkbox" checked={f.dias_semana.includes(dia)} onChange={() => alternarDia(dia)} />
                    {rotulo}
                  </label>
                ))}
              </div>
              {erros.dias_semana && <p className="mt-1 text-xs text-estado-erro">{erros.dias_semana}</p>}
            </fieldset>
          )}
          {(f.frequencia === 'mensal' || f.frequencia === 'anual') && (
            <div className="grid gap-3 sm:grid-cols-3">
              {f.frequencia === 'anual' && (
                <CampoSelecao
                  rotulo="Mês"
                  opcoes={NOMES_DOS_MESES.map((nome, i) => ({ valor: String(i + 1), rotulo: nome }))}
                  value={f.mes}
                  onChange={mudar('mes')}
                  erro={erros.mes}
                />
              )}
              <Campo
                rotulo="Dia do mês"
                type="number"
                min={1}
                max={31}
                value={f.dia_do_mes}
                onChange={mudar('dia_do_mes')}
                erro={erros.dia_do_mes}
                dica="Dia 29, 30 ou 31 em mês mais curto vale o último dia do mês. Dia 29/02 em ano comum vale 28/02."
              />
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <Campo rotulo={f.frequencia === 'unica' ? 'Data da execução' : 'Começa em'} type="date" value={f.data_inicio} onChange={mudar('data_inicio')} erro={erros.data_inicio} />
            {f.frequencia !== 'unica' && (
              <fieldset className="text-sm sm:col-span-2">
                <legend>
                  Termina{' '}
                  <BotaoAjuda rotulo="fim do agendamento">
                    Escolha uma forma de terminar: numa data, depois de um número de execuções, ou nunca. Uma data que falhar
                    não conta como execução realizada.
                  </BotaoAjuda>
                </legend>
                <div className="mt-1 flex flex-wrap items-end gap-4">
                  <label className="flex items-center gap-1">
                    <input type="radio" name="fim" checked={f.fim === 'nunca'} onChange={() => setF((a) => ({ ...a, fim: 'nunca' }))} />
                    Nunca
                  </label>
                  <label className="flex items-center gap-1">
                    <input type="radio" name="fim" checked={f.fim === 'data'} onChange={() => setF((a) => ({ ...a, fim: 'data' }))} />
                    Em uma data
                  </label>
                  <label className="flex items-center gap-1">
                    <input type="radio" name="fim" checked={f.fim === 'execucoes'} onChange={() => setF((a) => ({ ...a, fim: 'execucoes' }))} />
                    Após N execuções
                  </label>
                </div>
                {f.fim === 'data' && (
                  <Campo rotulo="Data de fim (inclusive)" type="date" value={f.data_fim} onChange={mudar('data_fim')} erro={erros.data_fim} />
                )}
                {f.fim === 'execucoes' && (
                  <Campo rotulo="Número de execuções" type="number" min={1} value={f.max_execucoes} onChange={mudar('max_execucoes')} erro={erros.max_execucoes} />
                )}
              </fieldset>
            )}
          </div>
        </fieldset>

        <PreviaDeDatas previa={previa} />
        <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
        {erros.geral && <Aviso tipo="erro">{erros.geral}</Aviso>}
        {podeEditar ? (
          <button type="submit" className="botao" disabled={salvando}>
            {salvando ? 'Salvando…' : 'Salvar agendamento'}
          </button>
        ) : (
          <Aviso>Você pode consultar o agendamento, mas não alterá-lo.</Aviso>
        )}
      </form>
    </section>
  )
}
