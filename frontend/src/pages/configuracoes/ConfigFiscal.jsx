import { useSearchParams } from 'react-router-dom'
import Abas from '../../components/Abas.jsx'
import Aviso from '../../components/Aviso.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import Certificado from '../fiscal/Certificado.jsx'
import Parametros from '../fiscal/Parametros.jsx'
import ServicosOficiais from '../fiscal/ServicosOficiais.jsx'

/**
 * Configurações fiscais da empresa agrupadas em abas.
 */
export default function ConfigFiscal() {
  const { temPermissao } = useAuth()
  const [params] = useSearchParams()
  const podeConsultar = temPermissao('config.consultar')

  const abas = podeConsultar
    ? [
        { id: 'parametros', rotulo: 'Parâmetros fiscais', conteudo: <Parametros embutido /> },
        { id: 'certificado', rotulo: 'Certificado A1', conteudo: <Certificado embutido /> },
        { id: 'servicos-oficiais', rotulo: 'Serviços oficiais', conteudo: <ServicosOficiais embutido /> },
      ]
    : []

  return (
    <section>
      <h1 className="mb-4 text-2xl text-gray-900 dark:text-gray-100">Configurações fiscais</h1>
      {abas.length === 0 ? (
        <Aviso tipo="erro">Você não tem permissão para consultar as configurações fiscais.</Aviso>
      ) : (
        <Abas abas={abas} abaInicial={params.get('aba') || 'parametros'} ariaLabel="Configurações fiscais" />
      )}
    </section>
  )
}
