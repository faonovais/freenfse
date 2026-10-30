import Layout from './components/Layout.jsx'
import RotaMaster from './components/RotaMaster.jsx'
import RotaProtegida from './components/RotaProtegida.jsx'
import Empresas from './pages/admin/Empresas.jsx'
import Usuarios from './pages/admin/Usuarios.jsx'
import Vinculos from './pages/admin/Vinculos.jsx'
import Config2FA from './pages/Config2FA.jsx'
import Inicio from './pages/Inicio.jsx'
import Login from './pages/Login.jsx'
import NaoEncontrada from './pages/NaoEncontrada.jsx'

export const rotas = [
  { path: '/login', element: <Login /> },
  {
    element: <RotaProtegida />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <Inicio /> },
          { path: 'seguranca/2fa', element: <Config2FA /> },
          {
            element: <RotaMaster />,
            children: [
              { path: 'admin/empresas', element: <Empresas /> },
              { path: 'admin/usuarios', element: <Usuarios /> },
              { path: 'admin/vinculos', element: <Vinculos /> },
            ],
          },
          { path: '*', element: <NaoEncontrada /> },
        ],
      },
    ],
  },
]
