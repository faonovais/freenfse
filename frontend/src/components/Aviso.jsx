const ESTILOS = {
  erro: 'border-estado-erro text-estado-erro',
  atencao: 'border-estado-atencao',
  sucesso: 'border-estado-sucesso',
  info: 'border-gray-200 dark:border-gray-800',
}

/** Caixa de mensagem. Erros são anunciados na hora (role="alert"); os demais, com cortesia. */
export default function Aviso({ tipo = 'info', children, className = '' }) {
  if (!children) return null
  return (
    <p
      role={tipo === 'erro' ? 'alert' : 'status'}
      className={`rounded border p-3 text-sm ${ESTILOS[tipo]} ${className}`}
    >
      {children}
    </p>
  )
}
