import { useId, useState } from 'react'

/** Seção que o usuário recolhe/expande. O conteúdo recolhido fica fora da árvore de acessibilidade. */
export default function PainelColapsavel({ titulo, children, abertoInicial = true }) {
  const [aberto, setAberto] = useState(abertoInicial)
  const idConteudo = useId()
  return (
    <section className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      <h2 className="text-lg">
        <button
          type="button"
          aria-expanded={aberto}
          aria-controls={idConteudo}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-gray-900 dark:text-gray-100"
          onClick={() => setAberto((atual) => !atual)}
        >
          {titulo}
          <span aria-hidden="true">{aberto ? '−' : '+'}</span>
        </button>
      </h2>
      <div id={idConteudo} hidden={!aberto} className="px-4 pb-4">
        {children}
      </div>
    </section>
  )
}
