// Textos da regra de recorrência em linguagem simples (a tela nunca mostra "cron").

const DIAS_CURTOS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom']
const DIAS_LONGOS = [
  'segunda-feira',
  'terça-feira',
  'quarta-feira',
  'quinta-feira',
  'sexta-feira',
  'sábado',
  'domingo',
]
const MESES = [
  'janeiro',
  'fevereiro',
  'março',
  'abril',
  'maio',
  'junho',
  'julho',
  'agosto',
  'setembro',
  'outubro',
  'novembro',
  'dezembro',
]

export const NOMES_DOS_DIAS = DIAS_LONGOS
export const ROTULOS_CURTOS_DOS_DIAS = DIAS_CURTOS
export const NOMES_DOS_MESES = MESES

const plural = (n, singular, pluralizado) => (n === 1 ? singular : pluralizado)

/** "Todo dia 5 às 08:00", "A cada 2 semanas (seg, qui) às 08:00"… */
export function resumoDaRegra(a) {
  const hora = `às ${a.hora}`
  const n = a.intervalo ?? 1
  switch (a.frequencia) {
    case 'unica':
      return `Uma única vez, ${hora}`
    case 'diaria':
      return n === 1 ? `Todo dia ${hora}` : `A cada ${n} dias ${hora}`
    case 'semanal': {
      const dias = (a.dias_semana ?? []).map((d) => DIAS_CURTOS[d]).join(', ')
      return n === 1 ? `Toda semana (${dias}) ${hora}` : `A cada ${n} semanas (${dias}) ${hora}`
    }
    case 'mensal':
      return n === 1
        ? `Todo mês, dia ${a.dia_do_mes}, ${hora}`
        : `A cada ${n} meses, dia ${a.dia_do_mes}, ${hora}`
    case 'anual':
      return `Todo ano, ${a.dia_do_mes} de ${MESES[(a.mes ?? 1) - 1]}, ${hora}`
    default:
      return ''
  }
}

/** "Sem fim", "Até 31/12/2026", "Termina após 12 execuções (3 feitas)". */
export function resumoDoFim(a, formatarData) {
  if (a.data_fim) return `Até ${formatarData(a.data_fim)}`
  if (a.max_execucoes) {
    return `Termina após ${a.max_execucoes} ${plural(a.max_execucoes, 'execução', 'execuções')} (${a.execucoes_realizadas ?? 0} ${plural(a.execucoes_realizadas ?? 0, 'feita', 'feitas')})`
  }
  return a.frequencia === 'unica' ? '' : 'Sem data de fim'
}

/** "qui, 05/11/2026 às 08:00" a partir da data ISO e da hora devolvidas pela API. */
export function dataPorExtenso(item, formatarData) {
  const [ano, mes, dia] = item.data.split('-').map(Number)
  const diaDaSemana = DIAS_CURTOS[(new Date(ano, mes - 1, dia).getDay() + 6) % 7]
  return `${diaDaSemana}, ${formatarData(item.data)} às ${item.hora}`
}
