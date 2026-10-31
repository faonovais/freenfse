import { useEffect, useId, useRef, useState } from 'react'

/**
 * Modal de confirmação acessível. Na variante "perigo" o botão fica vermelho; com
 * `textoDigitado`, o botão só habilita depois de a pessoa digitar exatamente o texto.
 */
export default function ModalConfirmacao({
  aberto,
  titulo,
  mensagem,
  textoConfirmar = 'Confirmar',
  textoCancelar = 'Cancelar',
  variante = 'padrao',
  textoDigitado,
  aoConfirmar,
  aoCancelar,
}) {
  const idTitulo = useId()
  const idMensagem = useId()
  const [digitado, setDigitado] = useState('')
  const campoRef = useRef(null)
  const cancelarRef = useRef(null)

  useEffect(() => {
    if (!aberto) return undefined
    ;(textoDigitado ? campoRef.current : cancelarRef.current)?.focus()
    const aoTeclar = (evento) => {
      if (evento.key === 'Escape') aoCancelar()
    }
    document.addEventListener('keydown', aoTeclar)
    return () => document.removeEventListener('keydown', aoTeclar)
  }, [aberto, textoDigitado, aoCancelar])

  if (!aberto) return null

  const liberado = !textoDigitado || digitado === textoDigitado
  const classeConfirmar = variante === 'perigo' ? 'botao-perigo' : 'botao'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(evento) => {
        if (evento.target === evento.currentTarget) aoCancelar()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        aria-describedby={mensagem ? idMensagem : undefined}
        className="w-full max-w-md rounded border border-gray-200 bg-white p-6 dark:border-gray-800 dark:bg-gray-900"
      >
        <h2 id={idTitulo} className="text-lg text-gray-900 dark:text-gray-100">
          {titulo}
        </h2>
        {mensagem && (
          <p id={idMensagem} className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            {mensagem}
          </p>
        )}
        {textoDigitado && (
          <label className="mt-4 block text-sm text-gray-600 dark:text-gray-400">
            Digite <strong>{textoDigitado}</strong> para confirmar
            <input
              ref={campoRef}
              className="campo mt-1"
              value={digitado}
              onChange={(evento) => setDigitado(evento.target.value)}
            />
          </label>
        )}
        <div className="mt-6 flex justify-end gap-2">
          <button ref={cancelarRef} type="button" className="botao-leve" onClick={aoCancelar}>
            {textoCancelar}
          </button>
          <button type="button" className={classeConfirmar} disabled={!liberado} onClick={aoConfirmar}>
            {textoConfirmar}
          </button>
        </div>
      </div>
    </div>
  )
}
