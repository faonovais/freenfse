import { useId } from 'react'

/** Campo de formulário com rótulo e mensagem de erro ligada ao campo (acessível). */
export default function Campo({ rotulo, erro, dica, ...propriedades }) {
  const id = useId()
  const idMensagem = `${id}-mensagem`
  return (
    <div className="text-sm">
      <label htmlFor={id}>{rotulo}</label>
      <input
        id={id}
        className="campo mt-1"
        aria-invalid={erro ? 'true' : undefined}
        aria-describedby={erro || dica ? idMensagem : undefined}
        {...propriedades}
      />
      {(erro || dica) && (
        <p id={idMensagem} className={`mt-1 text-xs ${erro ? 'text-estado-erro' : 'text-gray-600 dark:text-gray-400'}`}>
          {erro || dica}
        </p>
      )}
    </div>
  )
}
