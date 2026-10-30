import { useState } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext.jsx'
import { ConfirmacaoProvider } from './contexts/ConfirmacaoContext.jsx'
import { TemaProvider } from './contexts/TemaContext.jsx'
import { rotas } from './routes.jsx'

/** Raiz da SPA. Os testes passam um roteador em memória em `roteador`. */
export default function App({ roteador }) {
  const [roteadorDoNavegador] = useState(() => roteador ?? createBrowserRouter(rotas))
  return (
    <TemaProvider>
      <ConfirmacaoProvider>
        <AuthProvider>
          <RouterProvider router={roteadorDoNavegador} />
        </AuthProvider>
      </ConfirmacaoProvider>
    </TemaProvider>
  )
}
