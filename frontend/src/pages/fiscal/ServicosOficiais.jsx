import Aviso from '../../components/Aviso.jsx'

/**
 * Cadastro e consulta de serviços oficiais (LC 116 + NBS + IBS/CBS) vinculados à empresa.
 */
export default function ServicosOficiais({ embutido = false }) {
  const Titulo = embutido ? 'h2' : 'h1'
  return (
    <section>
      <Titulo
        className={embutido ? 'text-lg text-gray-900 dark:text-gray-100' : 'text-2xl text-gray-900 dark:text-gray-100'}
      >
        Serviços oficiais
      </Titulo>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Combinações oficiais de tributação nacional (LC 116), NBS e classificação IBS/CBS disponíveis para o cadastro
        de serviços da empresa.
      </p>
      <Aviso className="mt-4">O cadastro de serviços oficiais com NBS será carregado aqui.</Aviso>
    </section>
  )
}
