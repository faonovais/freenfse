import { useCallback, useEffect, useState } from 'react'
import { buscarVersaoApi } from './api/versao.js'

export default function App() {
  const [versaoApi, setVersaoApi] = useState(null)
  const [indisponivel, setIndisponivel] = useState(false)

  const consultar = useCallback(async () => {
    const resposta = await buscarVersaoApi()
    setIndisponivel(!resposta.ok)
    setVersaoApi(resposta.ok ? resposta.dados.versao : null)
  }, [])

  useEffect(() => {
    // Consulta inicial; o estado só muda depois da resposta (assíncrona).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    consultar()
  }, [consultar])

  return (
    <div className="min-h-screen bg-gray-100 text-gray-800 dark:bg-[#121212] dark:text-gray-300">
      <main className="mx-auto max-w-2xl p-8">
        <h1 className="text-3xl">freenfse</h1>
        <p className="mt-2">Emissão e gestão de NFS-e pelo ambiente nacional.</p>

        <section className="mt-8 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
          <p>Interface: v{__VERSAO_APP__}</p>
          <p role="status">
            {indisponivel && 'API indisponível'}
            {!indisponivel && versaoApi === null && 'Consultando a API…'}
            {!indisponivel && versaoApi !== null && `API: v${versaoApi}`}
          </p>
          <button type="button" className="botao mt-4" onClick={consultar}>
            Consultar novamente
          </button>
        </section>
      </main>
    </div>
  )
}
