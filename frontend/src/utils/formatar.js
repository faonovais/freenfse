// Formatação de datas e documentos para exibição (pt-BR).

// Datas e horas são sempre mostradas no horário de Brasília, qualquer que seja o fuso do navegador
// (o instante é guardado em UTC; entre 21h e 0h de Brasília o dia UTC já é o seguinte).
const FUSO = 'America/Sao_Paulo'

/** Data `AAAA-MM-DD` (competência, vigência) ou instante com hora (vira a data de Brasília). */
export function formatarData(valor) {
  if (!valor) return '—'
  const texto = String(valor)
  if (texto.length > 10 && texto.includes('T')) {
    const instante = new Date(texto)
    if (Number.isNaN(instante.getTime())) return '—'
    return instante.toLocaleDateString('pt-BR', { timeZone: FUSO })
  }
  const [ano, mes, dia] = texto.slice(0, 10).split('-')
  return `${dia}/${mes}/${ano}`
}

/** Primeiro dia do mês corrente **em Brasília** (`AAAA-MM-01`): a competência que a nota sugere. */
export function primeiroDiaDoMes(agora = new Date()) {
  const partes = new Intl.DateTimeFormat('en-CA', { timeZone: FUSO, year: 'numeric', month: '2-digit' })
    .formatToParts(agora)
  const ano = partes.find((p) => p.type === 'year').value
  const mes = partes.find((p) => p.type === 'month').value
  return `${ano}-${mes}-01`
}

export function formatarDataHora(valor) {
  if (!valor) return '—'
  const data = new Date(valor)
  if (Number.isNaN(data.getTime())) return '—'
  return data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: FUSO })
}
