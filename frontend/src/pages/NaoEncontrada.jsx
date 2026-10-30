import { Link } from 'react-router-dom'

export default function NaoEncontrada() {
  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Página não encontrada</h1>
      <p className="mt-2 text-sm">
        O endereço não existe. <Link className="text-accent underline" to="/">Voltar ao início</Link>.
      </p>
    </section>
  )
}
