import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import ModalConfirmacao from '../components/ModalConfirmacao.jsx'

const ConfirmacaoContext = createContext(null)

/** Fornece `confirmar(opcoes)`: abre o modal e devolve uma Promise<boolean> (substitui window.confirm). */
export function ConfirmacaoProvider({ children }) {
  const [pedido, setPedido] = useState(null)
  const resolverRef = useRef(null)

  const confirmar = useCallback(
    (opcoes) =>
      new Promise((resolver) => {
        resolverRef.current?.(false) // um pedido novo cancela o anterior
        resolverRef.current = resolver
        setPedido(opcoes)
      }),
    [],
  )

  const encerrar = useCallback((resultado) => {
    resolverRef.current?.(resultado)
    resolverRef.current = null
    setPedido(null)
  }, [])

  const aoConfirmar = useCallback(() => encerrar(true), [encerrar])
  const aoCancelar = useCallback(() => encerrar(false), [encerrar])
  const valor = useMemo(() => confirmar, [confirmar])

  return (
    <ConfirmacaoContext value={valor}>
      {children}
      <ModalConfirmacao
        aberto={pedido !== null}
        {...(pedido ?? {})}
        aoConfirmar={aoConfirmar}
        aoCancelar={aoCancelar}
      />
    </ConfirmacaoContext>
  )
}

export function useConfirmacao() {
  const contexto = useContext(ConfirmacaoContext)
  if (!contexto) throw new Error('useConfirmacao precisa estar dentro de <ConfirmacaoProvider>.')
  return contexto
}
