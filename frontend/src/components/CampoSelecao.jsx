import { useId } from 'react'

/** Lista de opções com rótulo e mensagem de erro ligada ao campo. `opcoes`: [{ valor, rotulo }]. */
export default function CampoSelecao({ rotulo, opcoes, erro, dica, vazio, ...propriedades }) {
  const id = useId()
  const idMensagem = `${id}-mensagem`
  return (
    <div className="text-sm">
      <label htmlFor={id}>{rotulo}</label>
      <select
        id={id}
        className="campo mt-1"
        aria-invalid={erro ? 'true' : undefined}
        aria-describedby={erro || dica ? idMensagem : undefined}
        {...propriedades}
      >
        {vazio !== undefined && <option value="">{vazio}</option>}
        {opcoes.map((opcao) => (
          <option key={opcao.valor} value={opcao.valor}>
            {opcao.rotulo}
          </option>
        ))}
      </select>
      {(erro || dica) && (
        <p id={idMensagem} className={`mt-1 text-xs ${erro ? 'text-estado-erro' : 'text-gray-600 dark:text-gray-400'}`}>
          {erro || dica}
        </p>
      )}
    </div>
  )
}
