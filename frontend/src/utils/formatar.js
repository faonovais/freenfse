// Formatação de datas e documentos para exibição (pt-BR).

export function formatarData(valor) {
  if (!valor) return '—'
  const [ano, mes, dia] = String(valor).slice(0, 10).split('-')
  return `${dia}/${mes}/${ano}`
}

export function formatarDataHora(valor) {
  if (!valor) return '—'
  const data = new Date(valor)
  if (Number.isNaN(data.getTime())) return '—'
  return data.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}
