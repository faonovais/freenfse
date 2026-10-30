/** Monta a query string (`?a=1&b=2`) ignorando valores vazios. */
export function consulta(parametros) {
  const limpos = Object.entries(parametros ?? {}).filter(([, valor]) => valor !== '' && valor != null)
  return limpos.length ? `?${new URLSearchParams(limpos)}` : ''
}
