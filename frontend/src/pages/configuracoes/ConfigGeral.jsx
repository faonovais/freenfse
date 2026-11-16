import { useSearchParams } from 'react-router-dom'
import Abas from '../../components/Abas.jsx'
import Aviso from '../../components/Aviso.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import ConfigDrive from '../documentos/ConfigDrive.jsx'
import ConfigEmail from '../documentos/ConfigEmail.jsx'
import Logo from '../fiscal/Logo.jsx'

/**
 * Configurações gerais da empresa agrupadas em abas (Logo, E-mail, Google Drive).
 */
export default function ConfigGeral() {
  const { temPermissao } = useAuth()
  const [params] = useSearchParams()
  const podeConsultar = temPermissao('config.consultar')

  const abas = podeConsultar
    ? [
        { id: 'logo', rotulo: 'Logo da empresa', conteudo: <Logo embutido /> },
        { id: 'email', rotulo: 'E-mail da empresa', conteudo: <ConfigEmail embutido /> },
        { id: 'drive', rotulo: 'Google Drive', conteudo: <ConfigDrive embutido /> },
      ]
    : []

  return (
    <section>
      <h1 className="mb-4 text-2xl text-gray-900 dark:text-gray-100">Configurações gerais</h1>
      {abas.length === 0 ? (
        <Aviso tipo="erro">Você não tem permissão para consultar as configurações gerais.</Aviso>
      ) : (
        <Abas abas={abas} abaInicial={params.get('aba') || 'logo'} ariaLabel="Configurações gerais" />
      )}
    </section>
  )
}
