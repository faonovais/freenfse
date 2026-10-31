import { useEffect, useState } from 'react'
import { logo } from '../api/fiscal.js'

/**
 * URL local (blob) do logo da empresa ativa para o tema. O arquivo é buscado com o X-Empresa
 * (um `<img src>` direto não o enviaria). `versao` é o hash do logo: quando muda, busca de novo.
 * Devolve `null` sem logo.
 */
export function useLogoUrl(tema, versao) {
  const [estado, setEstado] = useState({ chave: null, url: null })
  const chave = versao ? `${tema}:${versao}` : null

  useEffect(() => {
    if (!chave) return undefined
    let ativo = true
    let objeto = null
    logo.baixar(tema).then((resposta) => {
      if (!ativo || !resposta.ok) return
      objeto = URL.createObjectURL(resposta.blob)
      setEstado({ chave, url: objeto })
    })
    return () => {
      ativo = false
      if (objeto) URL.revokeObjectURL(objeto)
    }
  }, [chave, tema])

  return estado.chave === chave ? estado.url : null
}
