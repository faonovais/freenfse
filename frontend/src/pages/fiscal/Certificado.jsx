import { useEffect, useState } from 'react'
import { certificado as api } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import Campo from '../../components/Campo.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { mensagemErro } from '../../utils/erros.js'
import { formatarData } from '../../utils/formatar.js'

function Situacao({ certificado }) {
  if (!certificado.existe) return <Aviso>A empresa ainda não tem certificado digital cadastrado.</Aviso>
  const prazo = certificado.vencido
    ? `Venceu em ${formatarData(certificado.valido_ate)}.`
    : `Válido até ${formatarData(certificado.valido_ate)} (${certificado.dias_para_vencer} dia(s)).`
  const tipo = certificado.vencido ? 'erro' : certificado.faixa_alerta != null ? 'atencao' : 'sucesso'
  return (
    <div className="space-y-2">
      <Aviso tipo={tipo}>{prazo}</Aviso>
      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-gray-600 dark:text-gray-400">Titular</dt>
        <dd className="break-all">{certificado.titular}</dd>
        <dt className="text-gray-600 dark:text-gray-400">CNPJ do titular</dt>
        <dd>{certificado.cnpj_formatado}</dd>
        <dt className="text-gray-600 dark:text-gray-400">Início da validade</dt>
        <dd>{formatarData(certificado.valido_de)}</dd>
        <dt className="text-gray-600 dark:text-gray-400">Enviado por</dt>
        <dd>{certificado.enviado_por || '—'}</dd>
        {certificado.mesma_raiz_autorizada && (
          <>
            <dt className="text-gray-600 dark:text-gray-400">Observação</dt>
            <dd>Certificado de outro estabelecimento da mesma empresa (mesma raiz de CNPJ).</dd>
          </>
        )}
      </dl>
    </div>
  )
}

export default function Certificado() {
  const confirmar = useConfirmacao()
  const { temPermissao, recarregarIdentidade } = useAuth()
  const podeEditar = temPermissao('config.editar')
  const [certificado, setCertificado] = useState(null)
  const [falha, setFalha] = useState('')
  const [arquivo, setArquivo] = useState(null)
  const [senha, setSenha] = useState('')
  const [mesmaRaiz, setMesmaRaiz] = useState(false)
  const [reinicio, setReinicio] = useState(0) // troca a chave do campo de arquivo para limpá-lo
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [versao, setVersao] = useState(0)

  useEffect(() => {
    let ativo = true
    api.obter().then((resposta) => {
      if (!ativo) return
      if (resposta.ok) setCertificado(resposta.dados)
      else setFalha(mensagemErro(resposta, 'Não foi possível carregar o certificado.'))
    })
    return () => {
      ativo = false
    }
  }, [versao])

  async function enviar(evento) {
    evento.preventDefault()
    setErro('')
    const senhaDigitada = senha
    setSenha('') // a senha não fica na tela nem no estado depois do envio, dê certo ou não
    setEnviando(true)
    const resposta = await api.enviar({ arquivo, senha: senhaDigitada, mesmaRaiz })
    setEnviando(false)
    if (!resposta.ok) {
      setErro(mensagemErro(resposta, 'Não foi possível enviar o certificado.'))
      return
    }
    setArquivo(null)
    setMesmaRaiz(false)
    setReinicio((atual) => atual + 1)
    setVersao((atual) => atual + 1)
    recarregarIdentidade()
  }

  async function remover() {
    const seguir = await confirmar({
      titulo: 'Remover o certificado digital?',
      mensagem: 'A empresa não conseguirá emitir notas até enviar outro certificado.',
      variante: 'perigo',
      textoConfirmar: 'Remover certificado',
    })
    if (!seguir) return
    const resposta = await api.remover()
    if (!resposta.ok) {
      setErro(mensagemErro(resposta))
      return
    }
    setVersao((atual) => atual + 1)
    recarregarIdentidade()
  }

  if (falha) return <Aviso tipo="erro">{falha}</Aviso>
  if (!certificado) return <p role="status" className="text-sm">Carregando…</p>

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Certificado A1</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        O certificado digital identifica a empresa perante a Receita. Ele fica guardado cifrado, e o arquivo e a senha
        nunca são mostrados de volta.
      </p>

      <div className="mt-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <Situacao certificado={certificado} />
        {podeEditar && certificado.existe && (
          <button type="button" className="botao-leve mt-4" onClick={remover}>
            Remover certificado
          </button>
        )}
      </div>

      {podeEditar ? (
        <form
          onSubmit={enviar}
          aria-label="Enviar certificado"
          className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
        >
          <h2 className="text-lg text-gray-900 dark:text-gray-100">
            {certificado.existe ? 'Trocar o certificado' : 'Enviar o certificado'}
          </h2>
          <div className="text-sm">
            <label htmlFor="certificado-arquivo">Arquivo do certificado (.pfx ou .p12)</label>
            <input
              key={reinicio}
              id="certificado-arquivo"
              type="file"
              accept=".pfx,.p12,application/x-pkcs12"
              className="campo mt-1"
              onChange={(evento) => setArquivo(evento.target.files[0] ?? null)}
            />
          </div>
          <Campo
            rotulo="Senha do certificado"
            type="password"
            autoComplete="off"
            required
            value={senha}
            onChange={(evento) => setSenha(evento.target.value)}
          />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={mesmaRaiz} onChange={(e) => setMesmaRaiz(e.target.checked)} />
            <span>
              O certificado é da matriz ou de outra filial (mesma raiz de CNPJ){' '}
              <BotaoAjuda rotulo="mesma raiz de CNPJ">
                Os 8 primeiros caracteres do CNPJ identificam a empresa; o restante, o estabelecimento. Marque só se o
                certificado for de outro estabelecimento da mesma empresa.
              </BotaoAjuda>
            </span>
          </label>
          <Aviso tipo="erro">{erro}</Aviso>
          <button type="submit" className="botao" disabled={enviando || !arquivo}>
            {enviando ? 'Enviando…' : 'Enviar certificado'}
          </button>
        </form>
      ) : (
        <Aviso className="mt-4">Você pode consultar o certificado, mas não enviá-lo nem removê-lo.</Aviso>
      )}
    </section>
  )
}
