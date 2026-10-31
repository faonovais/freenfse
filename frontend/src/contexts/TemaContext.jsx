import { createContext, useContext, useEffect, useMemo, useState } from 'react'

export const CHAVE_TEMA = 'freenfse-tema'
export const MODOS_DE_TEMA = ['claro', 'escuro', 'sistema']

const TemaContext = createContext(null)

function lerModoSalvo() {
  try {
    const salvo = window.localStorage.getItem(CHAVE_TEMA)
    return MODOS_DE_TEMA.includes(salvo) ? salvo : 'sistema'
  } catch {
    return 'sistema'
  }
}

function sistemaPrefereEscuro() {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** Tema claro, escuro ou do sistema; aplica a classe `.dark` no <html> e lembra a escolha. */
export function TemaProvider({ children }) {
  const [modo, setModo] = useState(lerModoSalvo)
  const [sistemaEscuro, setSistemaEscuro] = useState(sistemaPrefereEscuro)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const consulta = window.matchMedia('(prefers-color-scheme: dark)')
    const aoMudar = (evento) => setSistemaEscuro(evento.matches)
    consulta.addEventListener('change', aoMudar)
    return () => consulta.removeEventListener('change', aoMudar)
  }, [])

  const escuro = modo === 'escuro' || (modo === 'sistema' && sistemaEscuro)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', escuro)
  }, [escuro])

  const valor = useMemo(
    () => ({
      modo,
      escuro,
      definirModo(novo) {
        if (!MODOS_DE_TEMA.includes(novo)) return
        setModo(novo)
        try {
          window.localStorage.setItem(CHAVE_TEMA, novo)
        } catch {
          // sem armazenamento: a escolha vale só nesta sessão
        }
      },
    }),
    [modo, escuro],
  )

  return <TemaContext value={valor}>{children}</TemaContext>
}

export function useTema() {
  const contexto = useContext(TemaContext)
  if (!contexto) throw new Error('useTema precisa estar dentro de <TemaProvider>.')
  return contexto
}
