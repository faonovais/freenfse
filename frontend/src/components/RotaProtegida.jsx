import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext.jsx'

export const ROTA_2FA = '/seguranca/2fa'

/** Só entra quem está autenticado; quem precisa configurar o 2FA é levado à tela de configuração. */
export default function RotaProtegida() {
  const { carregando, autenticado, mfa } = useAuth()
  const local = useLocation()

  if (carregando) {
    return (
      <p role="status" className="p-8 text-sm">
        Carregando…
      </p>
    )
  }
  if (!autenticado) return <Navigate to="/login" replace />
  if (mfa?.obrigatorio && !mfa.ativo && local.pathname !== ROTA_2FA) {
    return <Navigate to={ROTA_2FA} replace />
  }
  return <Outlet />
}
