// Situações da nota em linguagem simples: o texto é o que informa (a cor só reforça).

export const SITUACOES = [
  { valor: 'rascunho', rotulo: 'Rascunho', ajuda: 'Ainda não foi enviada à Sefin.' },
  { valor: 'enviando', rotulo: 'Enviando à Sefin', ajuda: 'Aguardando a resposta da Sefin.' },
  { valor: 'autorizada', rotulo: 'Autorizada', ajuda: 'Nota válida, emitida pela Sefin.' },
  { valor: 'rejeitada', rotulo: 'Rejeitada', ajuda: 'A Sefin recusou. Corrija e envie de novo.' },
  {
    valor: 'incerta',
    rotulo: 'Resultado incerto',
    ajuda: 'A Sefin não confirmou. O sistema confere sozinho; não emita de novo.',
  },
  { valor: 'cancelada', rotulo: 'Cancelada', ajuda: 'Cancelada na Sefin.' },
  { valor: 'substituida', rotulo: 'Substituída', ajuda: 'Trocada por outra nota.' },
]

const POR_VALOR = Object.fromEntries(SITUACOES.map((s) => [s.valor, s]))

export const rotuloDaSituacao = (valor) => POR_VALOR[valor]?.rotulo ?? valor

const CLASSES = {
  autorizada: 'border-estado-sucesso',
  rejeitada: 'border-estado-erro text-estado-erro',
  incerta: 'border-estado-atencao',
  enviando: 'border-estado-atencao',
}

/** Selo da situação: texto sempre visível, borda colorida como reforço. */
export function seloDaSituacao(valor) {
  return CLASSES[valor] ?? 'border-gray-300 dark:border-gray-700'
}

export const AMBIENTES = {
  producao_restrita: 'Produção restrita (testes, sem valor fiscal)',
  producao: 'Produção (notas com valor fiscal)',
}

export const dinheiro = (valor) =>
  valor == null || valor === ''
    ? '—'
    : Number(valor).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
