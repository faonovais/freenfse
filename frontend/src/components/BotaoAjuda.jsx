import { useEffect, useId, useRef, useState } from 'react'

/** Botão "?" que abre uma explicação curta ao lado do campo. Fecha com Escape ou clique fora. */
export default function BotaoAjuda({ rotulo, children }) {
  const [aberto, setAberto] = useState(false)
  const idAjuda = useId()
  const raizRef = useRef(null)

  useEffect(() => {
    if (!aberto) return undefined
    const aoTeclar = (evento) => {
      if (evento.key === 'Escape') setAberto(false)
    }
    const aoClicarFora = (evento) => {
      if (raizRef.current && !raizRef.current.contains(evento.target)) setAberto(false)
    }
    document.addEventListener('keydown', aoTeclar)
    document.addEventListener('mousedown', aoClicarFora)
    return () => {
      document.removeEventListener('keydown', aoTeclar)
      document.removeEventListener('mousedown', aoClicarFora)
    }
  }, [aberto])

  return (
    <span ref={raizRef} className="relative inline-block align-middle">
      <button
        type="button"
        aria-label={`Ajuda: ${rotulo}`}
        aria-expanded={aberto}
        aria-controls={aberto ? idAjuda : undefined}
        className="botao-leve h-6 w-6 rounded-full !p-0 text-xs"
        onClick={() => setAberto((atual) => !atual)}
      >
        ?
      </button>
      {aberto && (
        <span
          id={idAjuda}
          role="note"
          className="absolute left-0 z-40 mt-1 block w-64 rounded border border-gray-200 bg-white p-3 text-xs font-normal text-gray-800 shadow dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300"
        >
          {children}
        </span>
      )}
    </span>
  )
}
