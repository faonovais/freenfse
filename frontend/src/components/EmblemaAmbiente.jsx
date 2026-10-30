/**
 * Emblema do ambiente da empresa. Só a "produção restrita" (ambiente de teste da
 * Receita) é sinalizada; o ambiente de produção real não leva emblema.
 * O campo `ambiente` da empresa chega na fase de configuração fiscal.
 */
export default function EmblemaAmbiente({ ambiente }) {
  if (ambiente !== 'producao_restrita') return null
  return (
    <span
      role="status"
      className="rounded border border-estado-atencao px-2 py-0.5 text-xs font-semibold text-estado-atencao"
    >
      Produção restrita
    </span>
  )
}
