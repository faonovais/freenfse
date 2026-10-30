import { useEffect, useState } from 'react'
import { mensagemErro } from '../utils/erros.js'

/**
 * Carrega uma lista da API. `listar` deve ser uma função estável (módulo) e `filtros`
 * um objeto de estado: a lista é buscada de novo quando qualquer um muda ou quando
 * `recarregar()` é chamado.
 */
export function useLista(listar, filtros) {
  const [estado, setEstado] = useState({ itens: [], carregando: true, erro: '' })
  const [versao, setVersao] = useState(0)

  useEffect(() => {
    let ativo = true
    listar(filtros).then((resposta) => {
      if (!ativo) return
      setEstado(
        resposta.ok
          ? { itens: resposta.dados, carregando: false, erro: '' }
          : { itens: [], carregando: false, erro: mensagemErro(resposta, 'Não foi possível carregar a lista.') },
      )
    })
    return () => {
      ativo = false
    }
  }, [listar, filtros, versao])

  return { ...estado, recarregar: () => setVersao((atual) => atual + 1) }
}
