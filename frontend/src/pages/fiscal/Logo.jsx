import { useState } from 'react'
import { logo as api } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useLogoUrl } from '../../hooks/useLogoUrl.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'

const TEMAS = [
  { tema: 'claro', titulo: 'Logo para o tema claro', fundo: 'bg-white', dica: 'Aparece sobre fundo claro.' },
  {
    tema: 'escuro',
    titulo: 'Logo para o tema escuro (opcional)',
    fundo: 'bg-gray-900',
    dica: 'Sem este, o logo do tema claro é usado também no escuro.',
  },
]

function PainelDoLogo({ tema, titulo, fundo, dica, versao, podeEditar, aoAlterar }) {
  const confirmar = useConfirmacao()
  const url = useLogoUrl(tema, versao)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [reinicio, setReinicio] = useState(0)
  const [enviando, setEnviando] = useState(false)

  async function enviar(evento) {
    const arquivo = evento.target.files[0]
    if (!arquivo) return
    setErro('')
    setAviso('')
    setEnviando(true)
    const resposta = await api.enviar(tema, arquivo)
    setEnviando(false)
    setReinicio((atual) => atual + 1)
    if (!resposta.ok) {
      setErro(errosPorCampo(resposta).arquivo || mensagemErro(resposta, 'Não foi possível enviar o logo.'))
      return
    }
    if (resposta.dados.removidos?.length > 0) {
      setAviso(
        'Por segurança, removemos do arquivo SVG: ' +
          `${resposta.dados.removidos.join(', ')}. Confira se o logo continua como esperado.`,
      )
    }
    aoAlterar()
  }

  async function remover() {
    const seguir = await confirmar({
      titulo: 'Remover este logo?',
      mensagem: 'O logo deixa de aparecer no cabeçalho para todos os usuários da empresa.',
      variante: 'perigo',
      textoConfirmar: 'Remover logo',
    })
    if (!seguir) return
    const resposta = await api.remover(tema)
    if (!resposta.ok) {
      setErro(mensagemErro(resposta))
      return
    }
    setAviso('')
    aoAlterar()
  }

  return (
    <section
      aria-label={titulo}
      className="space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
    >
      <h2 className="text-lg text-gray-900 dark:text-gray-100">{titulo}</h2>
      <p className="text-xs text-gray-600 dark:text-gray-400">{dica}</p>
      <div className={`flex h-24 items-center justify-center rounded border border-gray-200 dark:border-gray-800 ${fundo}`}>
        {url ? (
          <img src={url} alt={`Prévia do ${titulo.toLowerCase()}`} className="max-h-20 max-w-full object-contain" />
        ) : (
          <span className="text-xs text-gray-600">Sem logo</span>
        )}
      </div>
      {podeEditar && (
        <div className="text-sm">
          <label htmlFor={`logo-${tema}`}>Escolher arquivo (PNG ou SVG)</label>
          <input
            key={reinicio}
            id={`logo-${tema}`}
            type="file"
            accept=".png,.svg,image/png,image/svg+xml"
            disabled={enviando}
            className="campo mt-1"
            onChange={enviar}
          />
        </div>
      )}
      <Aviso tipo="erro">{erro}</Aviso>
      <Aviso tipo="atencao">{aviso}</Aviso>
      {podeEditar && versao && (
        <button type="button" className="botao-leve" onClick={remover}>
          Remover logo
        </button>
      )}
    </section>
  )
}

export default function Logo() {
  const { temPermissao, identidade, recarregarIdentidade } = useAuth()
  const podeEditar = temPermissao('config.editar')
  const logos = identidade?.logo ?? {}

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">
        Logo da empresa{' '}
        <BotaoAjuda rotulo="logo da empresa">
          O logo aparece no cabeçalho para todos os usuários da empresa. Aceita PNG (até 512 KB e 2000×2000 pixels) ou
          SVG (até 200 KB). Em SVG, scripts e links externos são removidos automaticamente.
        </BotaoAjuda>
      </h1>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {TEMAS.map((item) => (
          <PainelDoLogo
            key={item.tema}
            {...item}
            versao={logos[item.tema]}
            podeEditar={podeEditar}
            aoAlterar={recarregarIdentidade}
          />
        ))}
      </div>
      {!podeEditar && <Aviso className="mt-4">Você pode ver o logo, mas não alterá-lo.</Aviso>}
    </section>
  )
}
