import { useEffect } from 'react'
import { useBlocker } from 'react-router-dom'
import { useConfirmacao } from '../contexts/ConfirmacaoContext.jsx'

// Quantos formulários alterados existem agora (a troca de empresa também consulta isto).
let formulariosSujos = 0

export function haFormularioSujo() {
  return formulariosSujos > 0
}

/**
 * Protege um formulário alterado: avisa ao fechar/recarregar a aba e pede confirmação
 * ao navegar para outra tela. Precisa de um roteador de dados (createBrowserRouter).
 */
export function useFormularioSujo(sujo, mensagem = 'Há alterações não salvas. Deseja sair sem salvar?') {
  const confirmar = useConfirmacao()
  const bloqueio = useBlocker(sujo)

  useEffect(() => {
    if (!sujo) return undefined
    formulariosSujos += 1
    const aoFechar = (evento) => {
      evento.preventDefault()
      evento.returnValue = ''
    }
    window.addEventListener('beforeunload', aoFechar)
    return () => {
      formulariosSujos -= 1
      window.removeEventListener('beforeunload', aoFechar)
    }
  }, [sujo])

  useEffect(() => {
    if (bloqueio.state !== 'blocked') return
    confirmar({
      titulo: 'Sair sem salvar?',
      mensagem,
      variante: 'perigo',
      textoConfirmar: 'Sair sem salvar',
      textoCancelar: 'Continuar editando',
    }).then((sair) => (sair ? bloqueio.proceed() : bloqueio.reset()))
  }, [bloqueio, confirmar, mensagem])
}
