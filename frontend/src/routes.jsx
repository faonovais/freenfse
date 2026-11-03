import Layout from './components/Layout.jsx'
import RotaMaster from './components/RotaMaster.jsx'
import RotaProtegida from './components/RotaProtegida.jsx'
import Empresas from './pages/admin/Empresas.jsx'
import Usuarios from './pages/admin/Usuarios.jsx'
import Vinculos from './pages/admin/Vinculos.jsx'
import Pessoas from './pages/cadastros/Pessoas.jsx'
import Servicos from './pages/cadastros/Servicos.jsx'
import Config2FA from './pages/Config2FA.jsx'
import Certificado from './pages/fiscal/Certificado.jsx'
import DetalheNota from './pages/fiscal/DetalheNota.jsx'
import Logo from './pages/fiscal/Logo.jsx'
import NotaForm from './pages/fiscal/NotaForm.jsx'
import Notas from './pages/fiscal/Notas.jsx'
import Parametros from './pages/fiscal/Parametros.jsx'
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
          { path: 'cadastros/pessoas', element: <Pessoas /> },
          { path: 'cadastros/servicos', element: <Servicos /> },
          { path: 'fiscal/notas', element: <Notas /> },
          { path: 'fiscal/notas/nova', element: <NotaForm /> },
          { path: 'fiscal/notas/:id', element: <DetalheNota /> },
          { path: 'fiscal/notas/:id/editar', element: <NotaForm /> },
          { path: 'fiscal/parametros', element: <Parametros /> },
          { path: 'fiscal/certificado', element: <Certificado /> },
          { path: 'fiscal/logo', element: <Logo /> },
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
