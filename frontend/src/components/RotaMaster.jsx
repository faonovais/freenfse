import { Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext.jsx'

/** Administração global: só o Master. O servidor também recusa (403); isto evita a tela vazia. */
export default function RotaMaster() {
  const { usuario } = useAuth()
  if (!usuario.is_master) {
    return (
      <section>
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Acesso negado</h1>
        <p role="alert" className="mt-2 text-sm">
          Esta área é restrita ao administrador do sistema.
        </p>
      </section>
    )
  }
  return <Outlet />
}
