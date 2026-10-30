import { Link } from 'react-router-dom'
import PainelColapsavel from '../components/PainelColapsavel.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function Inicio() {
  const { usuario, empresaAtiva } = useAuth()

  if (!empresaAtiva) {
    return (
      <section>
        <h1 className="text-2xl text-gray-900 dark:text-gray-100">Início</h1>
        <p role="status" className="mt-4 text-sm">
          Você ainda não tem acesso a nenhuma empresa.{' '}
          {usuario.is_master ? (
            <>
              Cadastre uma em <Link className="text-accent underline" to="/admin/empresas">Empresas</Link>.
            </>
          ) : (
            'Peça ao administrador do sistema para liberar o seu acesso.'
          )}
        </p>
      </section>
    )
  }

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Início</h1>
      <p className="mt-2 text-sm">
        Você está operando <strong>{empresaAtiva.razao_social}</strong> ({empresaAtiva.cnpj_formatado}) com o perfil{' '}
        <strong>{empresaAtiva.perfil}</strong>.
      </p>
      <div className="mt-6">
        <PainelColapsavel titulo="Suas permissões nesta empresa">
          <ul aria-label="Permissões" className="grid gap-1 text-sm sm:grid-cols-2">
            {empresaAtiva.permissoes.map((permissao) => (
              <li key={permissao}>
                <code>{permissao}</code>
              </li>
            ))}
          </ul>
        </PainelColapsavel>
      </div>
    </section>
  )
}
