import { useEffect, useMemo, useState } from 'react'
import { parametros as api } from '../../api/fiscal.js'
import Aviso from '../../components/Aviso.jsx'
import BotaoAjuda from '../../components/BotaoAjuda.jsx'
import CampoSelecao from '../../components/CampoSelecao.jsx'
import Campo from '../../components/Campo.jsx'
import SeletorMunicipio from '../../components/SeletorMunicipio.jsx'
import { useAuth } from '../../contexts/AuthContext.jsx'
import { useConfirmacao } from '../../contexts/ConfirmacaoContext.jsx'
import { useFormularioSujo } from '../../hooks/useFormularioSujo.js'
import { errosPorCampo, mensagemErro } from '../../utils/erros.js'
import { formatarDataHora } from '../../utils/formatar.js'

const TEXTO_DE_PRODUCAO = 'PRODUÇÃO'

function formularioDe(dados) {
  return {
    regime_tributario: dados.regime_tributario,
    regime_apuracao_simples: dados.regime_apuracao_simples == null ? '' : String(dados.regime_apuracao_simples),
    regime_especial: String(dados.regime_especial),
    serie_dps: String(dados.serie_dps),
    ambiente: dados.ambiente,
    codigo_municipio_emissor: dados.codigo_municipio_emissor,
  }
}

const comoTexto = (opcoes) => opcoes.map((o) => ({ valor: String(o.valor), rotulo: o.rotulo }))

function ResultadoDoConvenio({ convenio }) {
  if (!convenio) {
    return <Aviso>O convênio ainda não foi verificado para esta empresa.</Aviso>
  }
  const tipo = convenio.aderente === true ? 'sucesso' : convenio.aderente === false ? 'erro' : 'atencao'
  return (
    <div className="space-y-2">
      <Aviso tipo={tipo}>{convenio.mensagem}</Aviso>
      <p className="text-xs text-gray-600 dark:text-gray-400">Verificado em {formatarDataHora(convenio.verificado_em)}.</p>
      {!convenio.atual && (
        <Aviso tipo="atencao">
          Este resultado é de outro município ou de outro ambiente. Verifique de novo para a configuração atual.
        </Aviso>
      )}
      {convenio.avisos?.map((aviso) => (
        <Aviso key={aviso} tipo="atencao">{aviso}</Aviso>
      ))}
    </div>
  )
}

export default function Parametros() {
  const confirmar = useConfirmacao()
  const { temPermissao, recarregarIdentidade } = useAuth()
  const podeEditar = temPermissao('config.editar')
  const [dados, setDados] = useState(null)
  const [falhaAoCarregar, setFalhaAoCarregar] = useState('')
  const [f, setF] = useState(null)
  const [erros, setErros] = useState({})
  const [erroGeral, setErroGeral] = useState('')
  const [salvo, setSalvo] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [verificando, setVerificando] = useState(false)
  const [erroConvenio, setErroConvenio] = useState('')

  useEffect(() => {
    let ativo = true
    api.obter().then((resposta) => {
      if (!ativo) return
      if (resposta.ok) {
        setDados(resposta.dados)
        setF(formularioDe(resposta.dados))
      } else {
        setFalhaAoCarregar(mensagemErro(resposta, 'Não foi possível carregar os parâmetros.'))
      }
    })
    return () => {
      ativo = false
    }
  }, [])

  const inicial = useMemo(() => (dados ? formularioDe(dados) : null), [dados])
  useFormularioSujo(Boolean(f && inicial && !salvo && JSON.stringify(f) !== JSON.stringify(inicial)))

  if (falhaAoCarregar) return <Aviso tipo="erro">{falhaAoCarregar}</Aviso>
  if (!dados || !f) return <p role="status" className="text-sm">Carregando…</p>

  const opcoes = dados.opcoes
  const mudar = (campo) => (evento) => setF((atual) => ({ ...atual, [campo]: evento.target.value }))
  const simples = f.regime_tributario === 'simples_nacional'

  async function salvar(evento) {
    evento.preventDefault()
    setErros({})
    setErroGeral('')
    const corpo = {
      regime_tributario: f.regime_tributario,
      regime_apuracao_simples: simples && f.regime_apuracao_simples !== '' ? Number(f.regime_apuracao_simples) : null,
      regime_especial: Number(f.regime_especial),
      serie_dps: Number(f.serie_dps),
      ambiente: f.ambiente,
      codigo_municipio_emissor: f.codigo_municipio_emissor,
    }
    if (f.ambiente === 'producao' && dados.ambiente !== 'producao') {
      const confirmado = await confirmar({
        titulo: 'Trocar para o ambiente de produção?',
        mensagem:
          'A partir de agora as notas emitidas têm valor fiscal de verdade. Use este ambiente só depois de testar ' +
          'tudo em produção restrita.',
        variante: 'perigo',
        textoConfirmar: 'Trocar para produção',
        textoDigitado: TEXTO_DE_PRODUCAO,
      })
      if (!confirmado) return
      corpo.confirmar_producao = true
    }
    setSalvando(true)
    const resposta = await api.alterar(corpo)
    setSalvando(false)
    if (!resposta.ok) {
      setErros(errosPorCampo(resposta))
      setErroGeral(mensagemErro(resposta))
      return
    }
    setSalvo(true)
    setDados(resposta.dados)
    setF(formularioDe(resposta.dados))
    setSalvo(false)
    recarregarIdentidade()
  }

  async function verificarConvenio() {
    setErroConvenio('')
    setVerificando(true)
    const resposta = await api.verificarConvenio()
    setVerificando(false)
    if (resposta.ok) setDados(resposta.dados)
    else setErroConvenio(mensagemErro(resposta, 'Não foi possível verificar o convênio.'))
  }

  const alterado = JSON.stringify(f) !== JSON.stringify(inicial)

  return (
    <section>
      <h1 className="text-2xl text-gray-900 dark:text-gray-100">Parâmetros fiscais</h1>
      <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Como esta empresa emite NFS-e. Confira com a contabilidade antes de alterar.
      </p>

      <form
        onSubmit={salvar}
        aria-label="Parâmetros fiscais"
        className="mt-4 space-y-4 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <fieldset disabled={!podeEditar} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <CampoSelecao
              rotulo="Regime tributário"
              opcoes={comoTexto(opcoes.regime_tributario)}
              value={f.regime_tributario}
              onChange={mudar('regime_tributario')}
              erro={erros.regime_tributario}
              dica="Define a opção pelo Simples Nacional informada na nota."
            />
            {simples && (
              <CampoSelecao
                rotulo="Regime de apuração do Simples"
                vazio="Escolha"
                opcoes={comoTexto(opcoes.regime_apuracao_simples)}
                value={f.regime_apuracao_simples}
                onChange={mudar('regime_apuracao_simples')}
                erro={erros.regime_apuracao_simples}
                dica="Como os tributos do Simples são apurados. Obrigatório para ME/EPP."
              />
            )}
            <CampoSelecao
              rotulo="Regime especial de tributação"
              opcoes={comoTexto(opcoes.regime_especial)}
              value={f.regime_especial}
              onChange={mudar('regime_especial')}
              erro={erros.regime_especial}
            />
            <Campo
              rotulo="Série da DPS"
              type="number"
              min={1}
              max={99999}
              value={f.serie_dps}
              onChange={mudar('serie_dps')}
              erro={erros.serie_dps}
              dica="De 1 a 99999. Não troque depois de emitir: a numeração é por série."
            />
          </div>
          <div className="max-w-md">
            <SeletorMunicipio
              rotulo="Município emissor"
              valor={f.codigo_municipio_emissor}
              aoMudar={(codigo) => setF((atual) => ({ ...atual, codigo_municipio_emissor: codigo }))}
              erro={erros.codigo_municipio_emissor}
              dica="Onde a empresa está estabelecida e emite as notas."
            />
          </div>

          <div className="max-w-md">
            <CampoSelecao
              rotulo="Ambiente de emissão"
              opcoes={comoTexto(opcoes.ambiente)}
              value={f.ambiente}
              onChange={mudar('ambiente')}
              erro={erros.ambiente}
            />
            <p className="mt-1 text-xs">
              <BotaoAjuda rotulo="ambiente de emissão">
                Produção restrita é o ambiente de testes da Receita: as notas não têm valor fiscal. Produção emite notas
                de verdade.
              </BotaoAjuda>{' '}
              {f.ambiente === 'producao_restrita'
                ? 'Notas de teste, sem valor fiscal.'
                : 'Atenção: as notas têm valor fiscal.'}
            </p>
          </div>
        </fieldset>

        <Aviso tipo="erro">{erroGeral && Object.keys(erros).length === 0 ? erroGeral : ''}</Aviso>
        {podeEditar ? (
          <button type="submit" className="botao" disabled={salvando || !alterado}>
            Salvar parâmetros
          </button>
        ) : (
          <Aviso>Você pode consultar os parâmetros, mas não alterá-los.</Aviso>
        )}
      </form>

      <section
        aria-label="Convênio do município"
        className="mt-6 space-y-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900"
      >
        <h2 className="text-lg text-gray-900 dark:text-gray-100">
          Convênio do município{' '}
          <BotaoAjuda rotulo="convênio do município">
            Para emitir pelo ambiente nacional, o município precisa ter aderido à NFS-e Nacional. A verificação consulta
            a Receita usando o certificado da empresa.
          </BotaoAjuda>
        </h2>
        <ResultadoDoConvenio convenio={dados.convenio} />
        <Aviso tipo="erro">{erroConvenio}</Aviso>
        {podeEditar && (
          <button type="button" className="botao-leve" disabled={verificando} onClick={verificarConvenio}>
            {verificando ? 'Verificando…' : 'Verificar convênio do município'}
          </button>
        )}
        {alterado && podeEditar && (
          <p className="text-xs text-gray-600 dark:text-gray-400">
            Salve os parâmetros antes de verificar: a consulta usa o município e o ambiente gravados.
          </p>
        )}
      </section>
    </section>
  )
}
