import { useEffect, useState } from 'react'
import { municipios } from '../api/cadastros.js'

/**
 * "Nome/UF" do município a partir do código IBGE (o servidor só guarda o código). Enquanto busca, ou se a
 * busca falhar, mostra "IBGE 0000000": a tela nunca fica sem dizer de qual município se trata.
 */
export default function NomeDoMunicipio({ codigo }) {
  const [achado, setAchado] = useState(null)

  useEffect(() => {
    if (!codigo) return undefined
    let ativo = true
    municipios.obterPorCodigo(codigo).then((resposta) => {
      if (ativo && resposta.ok && resposta.dados.length > 0) setAchado(resposta.dados[0])
    })
    return () => {
      ativo = false
    }
  }, [codigo])

  if (!codigo) return null
  return <>{achado?.codigo === codigo ? `${achado.nome}/${achado.uf}` : `IBGE ${codigo}`}</>
}
