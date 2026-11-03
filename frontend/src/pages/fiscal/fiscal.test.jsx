import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { limparEmpresaAtiva } from '../../api/empresaAtiva.js'
import {
  EMPRESA_ADMIN,
  EMPRESA_SO_CONSULTA,
  IDENTIDADE_PADRAO,
  respostaEu,
} from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
})

const PARAMETROS = '/api/fiscal/parametros/'
const VERIFICAR = '/api/fiscal/parametros/verificar-convenio/'
const CERTIFICADO = '/api/fiscal/certificado/'
const OPCOES = {
  regime_tributario: [
    { valor: 'mei', rotulo: 'Microempreendedor individual (MEI)' },
    { valor: 'simples_nacional', rotulo: 'Simples Nacional (ME ou EPP)' },
    { valor: 'lucro_presumido', rotulo: 'Lucro presumido' },
    { valor: 'outro', rotulo: 'Outro (não optante pelo Simples)' },
  ],
  regime_apuracao_simples: [
    { valor: 1, rotulo: 'Tributos federais e municipal pelo Simples' },
    { valor: 2, rotulo: 'Federais pelo Simples e ISSQN fora do Simples' },
  ],
  regime_especial: [
    { valor: 0, rotulo: 'Nenhum' },
    { valor: 5, rotulo: 'Profissional autônomo' },
  ],
  ambiente: [
    { valor: 'producao_restrita', rotulo: 'Produção restrita (testes)' },
    { valor: 'producao', rotulo: 'Produção (notas com valor fiscal)' },
  ],
}
const PARAMS = {
  regime_tributario: 'simples_nacional', regime_apuracao_simples: 1, regime_especial: 0, serie_dps: 1,
  ambiente: 'producao_restrita', codigo_municipio_emissor: '2101400', opcao_simples: 3,
  municipio_emissor: 'Balsas/MA', convenio: null, atualizado_em: '2026-10-30T12:00:00Z', opcoes: OPCOES,
}  // fmt: skip
const CONVENIO = {
  verificado_em: '2026-10-30T15:00:00Z', codigo_municipio: '2101400', ambiente: 'producao_restrita',
  atual: true, aderente: true, aderente_emissor_nacional: true, data_ativacao: '2024-05-02',
  mensagem: 'O município Balsas/MA aderiu à NFS-e Nacional: já é possível emitir por aqui.',
  avisos: [], contribuinte: {},
}  // fmt: skip
const BALSAS = { codigo: '2101400', nome: 'Balsas', uf: 'MA' }

function abrir(rota, extras = {}, empresas = [EMPRESA_ADMIN]) {
  return montarApp({
    rota,
    rotasApi: rotasAutenticado({
      eu: respostaEu({ empresas }),
      extras: {
        [`GET ${PARAMETROS}`]: { status: 200, dados: PARAMS },
        'GET /api/cadastros/municipios/': { status: 200, dados: [BALSAS] },
        ...extras,
      },
    }),
  })
}

describe('Parâmetros fiscais', () => {
  const abrirParametros = (extras, empresas) => abrir('/fiscal/parametros', extras, empresas)
  const escolher = (rotulo, valor) => fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } })

  it('mostra os parâmetros da empresa e o aviso de que produção restrita não tem valor fiscal', async () => {
    abrirParametros()

    expect(await screen.findByLabelText('Regime tributário')).toHaveValue('simples_nacional')
    expect(screen.getByLabelText('Série da DPS')).toHaveValue(1)
    expect(screen.getByLabelText('Ambiente de emissão')).toHaveValue('producao_restrita')
    expect(screen.getByText('Notas de teste, sem valor fiscal.')).toBeInTheDocument()
    expect(await screen.findByText(/Balsas\/MA/)).toBeInTheDocument()
  })

  it('o regime de apuração só aparece para quem é ME/EPP no Simples', async () => {
    abrirParametros()
    await screen.findByLabelText('Regime tributário')
    expect(screen.getByLabelText('Regime de apuração do Simples')).toBeInTheDocument()

    escolher('Regime tributário', 'lucro_presumido')

    expect(screen.queryByLabelText('Regime de apuração do Simples')).not.toBeInTheDocument()
  })

  it('salva sem pedir confirmação quando o ambiente não vai para produção', async () => {
    const { chamadas } = abrirParametros({ [`PATCH ${PARAMETROS}`]: { status: 200, dados: { ...PARAMS, serie_dps: 4 } } })
    await screen.findByLabelText('Regime tributário')

    escolher('Série da DPS', '4')
    fireEvent.click(screen.getByRole('button', { name: 'Salvar parâmetros' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'PATCH')).toBe(true))
    const corpo = chamadas.find((c) => c.metodo === 'PATCH').corpo
    expect(corpo).toMatchObject({ serie_dps: 4, ambiente: 'producao_restrita', regime_apuracao_simples: 1 })
    expect(corpo).not.toHaveProperty('confirmar_producao')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('só habilita o salvamento quando algo mudou', async () => {
    abrirParametros()
    await screen.findByLabelText('Regime tributário')

    expect(screen.getByRole('button', { name: 'Salvar parâmetros' })).toBeDisabled()
    escolher('Série da DPS', '2')
    expect(screen.getByRole('button', { name: 'Salvar parâmetros' })).toBeEnabled()
  })

  it('trocar para produção exige confirmação digitando PRODUÇÃO e envia confirmar_producao', async () => {
    const { chamadas } = abrirParametros({
      [`PATCH ${PARAMETROS}`]: { status: 200, dados: { ...PARAMS, ambiente: 'producao' } },
    })
    await screen.findByLabelText('Regime tributário')

    escolher('Ambiente de emissão', 'producao')
    expect(screen.getByText('Atenção: as notas têm valor fiscal.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar parâmetros' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Trocar para o ambiente de produção?' })
    const botao = within(dialogo).getByRole('button', { name: 'Trocar para produção' })
    expect(botao).toBeDisabled()
    fireEvent.change(within(dialogo).getByLabelText(/Digite/), { target: { value: 'produção' } })
    expect(botao).toBeDisabled() // exige exatamente PRODUÇÃO
    fireEvent.change(within(dialogo).getByLabelText(/Digite/), { target: { value: 'PRODUÇÃO' } })
    fireEvent.click(botao)

    await waitFor(() => expect(chamadas.find((c) => c.metodo === 'PATCH')?.corpo).toMatchObject({
      ambiente: 'producao', confirmar_producao: true,
    }))  // fmt: skip
    // O selo de ambiente do cabeçalho é recarregado.
    await waitFor(() =>
      expect(chamadas.filter((c) => c.caminho === '/api/fiscal/identidade/').length).toBeGreaterThan(1),
    )
  })

  it('cancelar a confirmação de produção não altera nada', async () => {
    const { chamadas } = abrirParametros()
    await screen.findByLabelText('Regime tributário')
    escolher('Ambiente de emissão', 'producao')

    fireEvent.click(screen.getByRole('button', { name: 'Salvar parâmetros' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(chamadas.some((c) => c.metodo === 'PATCH')).toBe(false)
  })

  it('mostra o erro de validação do servidor junto do campo', async () => {
    abrirParametros({
      [`PATCH ${PARAMETROS}`]: {
        status: 400,
        dados: { regime_apuracao_simples: ['ME/EPP optante pelo Simples precisa informar como os tributos são apurados.'] },
      },
    })
    await screen.findByLabelText('Regime tributário')
    escolher('Série da DPS', '9')

    fireEvent.click(screen.getByRole('button', { name: 'Salvar parâmetros' }))

    expect(await screen.findByText(/precisa informar como os tributos são apurados/)).toBeInTheDocument()
  })

  it('quem só consulta vê os campos bloqueados, sem salvar nem verificar', async () => {
    abrirParametros({}, [EMPRESA_SO_CONSULTA])

    expect(await screen.findByLabelText('Série da DPS')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Salvar parâmetros' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Verificar convênio do município' })).not.toBeInTheDocument()
    expect(screen.getByText(/pode consultar os parâmetros, mas não alterá-los/)).toBeInTheDocument()
  })

  it('os campos fiscais têm ajuda em linguagem simples', async () => {
    abrirParametros()
    await screen.findByLabelText('Regime tributário')

    fireEvent.click(screen.getByRole('button', { name: 'Ajuda: ambiente de emissão' }))

    expect(screen.getByRole('note')).toHaveTextContent(/ambiente de testes da Receita/)
  })

  describe('convênio do município', () => {
    it('avisa que ainda não foi verificado', async () => {
      abrirParametros()

      expect(await screen.findByText(/ainda não foi verificado/)).toBeInTheDocument()
    })

    it('verifica, mostra o resultado em linguagem simples e a data', async () => {
      abrirParametros({ [`POST ${VERIFICAR}`]: { status: 200, dados: { ...PARAMS, convenio: CONVENIO } } })
      fireEvent.click(await screen.findByRole('button', { name: 'Verificar convênio do município' }))

      expect(await screen.findByText(/aderiu à NFS-e Nacional/)).toBeInTheDocument()
      expect(screen.getByText(/Verificado em 30\/10\/2026/)).toBeInTheDocument()
    })

    it('município sem convênio aparece como erro', async () => {
      const semConvenio = { ...CONVENIO, aderente: false, mensagem: 'O município Balsas/MA NÃO tem convênio com a NFS-e Nacional neste ambiente. As notas seriam rejeitadas (E0037).' }
      abrirParametros({ [`GET ${PARAMETROS}`]: { status: 200, dados: { ...PARAMS, convenio: semConvenio } } })

      expect(await screen.findByRole('alert')).toHaveTextContent(/NÃO tem convênio/)
    })

    it('falha de rede mostra a mensagem clara e mantém o último resultado', async () => {
      abrirParametros({
        [`GET ${PARAMETROS}`]: { status: 200, dados: { ...PARAMS, convenio: CONVENIO } },
        [`POST ${VERIFICAR}`]: {
          status: 502,
          dados: { codigo: 'convenio_indisponivel', detalhe: 'Não foi possível falar com o ambiente nacional da NFS-e agora (sem internet ou serviço fora do ar). Tente novamente em alguns minutos.' },
        },
      })
      fireEvent.click(await screen.findByRole('button', { name: 'Verificar convênio do município' }))

      expect(await screen.findByRole('alert')).toHaveTextContent(/sem internet ou serviço fora do ar/)
      expect(screen.getByText(/aderiu à NFS-e Nacional/)).toBeInTheDocument()
    })

    it('falta de certificado é explicada ao usuário', async () => {
      abrirParametros({
        [`POST ${VERIFICAR}`]: {
          status: 400,
          dados: { codigo: 'convenio_nao_verificado', detalhe: 'Envie o certificado A1 da empresa antes de verificar o convênio.' },
        },
      })
      fireEvent.click(await screen.findByRole('button', { name: 'Verificar convênio do município' }))

      expect(await screen.findByRole('alert')).toHaveTextContent(/Envie o certificado A1/)
    })

    it('resultado de outro município ou ambiente vem com aviso para verificar de novo', async () => {
      abrirParametros({
        [`GET ${PARAMETROS}`]: { status: 200, dados: { ...PARAMS, convenio: { ...CONVENIO, atual: false } } },
      })

      expect(await screen.findByText(/outro município ou de outro ambiente/)).toBeInTheDocument()
    })

    it('com alterações não salvas orienta salvar antes de verificar', async () => {
      abrirParametros()
      await screen.findByLabelText('Regime tributário')

      escolher('Série da DPS', '3')

      expect(screen.getByText(/Salve os parâmetros antes de verificar/)).toBeInTheDocument()
    })
  })
})

describe('Certificado A1', () => {
  const EXISTENTE = {
    existe: true, titular: 'O=ICP-Brasil (teste),CN=EMPRESA TESTE:11222333000181', cnpj_titular: '11222333000181',
    cnpj_formatado: '11.222.333/0001-81', valido_de: '2026-01-01T00:00:00-03:00', valido_ate: '2027-01-01T00:00:00-03:00',
    dias_para_vencer: 200, vencido: false, faixa_alerta: null, impressao_digital: 'a'.repeat(64),
    mesma_raiz_autorizada: false, enviado_por: 'ana@example.com', enviado_em: '2026-10-30T12:00:00Z',
  }  // fmt: skip
  const abrirCertificado = (extras, empresas) => abrir('/fiscal/certificado', extras, empresas)
  const arquivo = () => new File(['conteudo-ficticio'], 'certificado.pfx', { type: 'application/x-pkcs12' })

  function preencher({ senha = 'senha-de-teste-123', mesmaRaiz = false } = {}) {
    fireEvent.change(screen.getByLabelText(/Arquivo do certificado/), { target: { files: [arquivo()] } })
    fireEvent.change(screen.getByLabelText('Senha do certificado'), { target: { value: senha } })
    if (mesmaRaiz) fireEvent.click(screen.getByRole('checkbox', { name: /mesma raiz de CNPJ/ }))
  }

  it('sem certificado, avisa e oferece o envio', async () => {
    abrirCertificado({ [`GET ${CERTIFICADO}`]: { status: 200, dados: { existe: false } } })

    expect(await screen.findByText(/ainda não tem certificado digital cadastrado/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Enviar certificado' })).toBeInTheDocument()
    expect(screen.getByLabelText('Senha do certificado')).toHaveAttribute('type', 'password')
  })

  it('mostra titular, CNPJ e validade, nunca o arquivo nem a senha', async () => {
    abrirCertificado({ [`GET ${CERTIFICADO}`]: { status: 200, dados: EXISTENTE } })

    expect(await screen.findByText('CNPJ do titular')).toBeInTheDocument()
    expect(screen.getByText('11.222.333/0001-81', { selector: 'dd' })).toBeInTheDocument()
    expect(screen.getByText(/Válido até 01\/01\/2027 \(200 dia\(s\)\)/)).toBeInTheDocument()
    expect(screen.getByText(/EMPRESA TESTE/)).toBeInTheDocument()
    expect(screen.getByText('ana@example.com')).toBeInTheDocument()
  })

  it.each([
    [{ vencido: true, dias_para_vencer: -2, faixa_alerta: 0 }, /Venceu em/],
    [{ dias_para_vencer: 10, faixa_alerta: 15 }, /Válido até .* \(10 dia\(s\)\)/],
  ])('situação de vencimento %j', async (ajuste, texto) => {
    abrirCertificado({ [`GET ${CERTIFICADO}`]: { status: 200, dados: { ...EXISTENTE, ...ajuste } } })

    expect(await screen.findByText(texto)).toBeInTheDocument()
  })

  it('envia o arquivo, a senha e a opção de mesma raiz como multipart', async () => {
    let enviado = false
    const { chamadas } = abrirCertificado({
      [`GET ${CERTIFICADO}`]: () => ({ status: 200, dados: enviado ? EXISTENTE : { existe: false } }),
      [`POST ${CERTIFICADO}`]: () => {
        enviado = true
        return { status: 201, dados: EXISTENTE }
      },
    })
    await screen.findByRole('form', { name: 'Enviar certificado' })

    preencher({ mesmaRaiz: true })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar certificado' }))

    expect(await screen.findByText('CNPJ do titular')).toBeInTheDocument()
    const corpo = chamadas.find((c) => c.metodo === 'POST').corpo
    expect(corpo.arquivo).toBeInstanceOf(File)
    expect(corpo.arquivo.name).toBe('certificado.pfx')
    expect(corpo.senha).toBe('senha-de-teste-123')
    expect(corpo.mesma_raiz).toBe('true')
  })

  it('a senha é apagada da tela depois do envio, mesmo quando o servidor recusa', async () => {
    abrirCertificado({
      [`GET ${CERTIFICADO}`]: { status: 200, dados: { existe: false } },
      [`POST ${CERTIFICADO}`]: {
        status: 400,
        dados: { codigo: 'certificado_recusado', detalhe: 'Não foi possível abrir o certificado. Confira se a senha está correta.' },
      },
    })
    await screen.findByRole('form', { name: 'Enviar certificado' })

    preencher({ senha: 'senha-errada-999' })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar certificado' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Confira se a senha está correta.')
    expect(screen.getByLabelText('Senha do certificado')).toHaveValue('')
    expect(document.body.textContent).not.toContain('senha-errada-999')
  })

  it('remover pede confirmação e apaga', async () => {
    const { chamadas } = abrirCertificado({
      [`GET ${CERTIFICADO}`]: { status: 200, dados: EXISTENTE },
      [`DELETE ${CERTIFICADO}`]: { status: 204, dados: null },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Remover certificado' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Remover o certificado digital?' })).getByRole('button', { name: 'Remover certificado' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'DELETE')).toBe(true))
  })

  it('quem só consulta vê o certificado mas não envia nem remove', async () => {
    abrirCertificado({ [`GET ${CERTIFICADO}`]: { status: 200, dados: EXISTENTE } }, [EMPRESA_SO_CONSULTA])

    expect(await screen.findByText('CNPJ do titular')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Enviar certificado' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remover certificado' })).not.toBeInTheDocument()
  })

  it('o envio exige o arquivo escolhido', async () => {
    abrirCertificado({ [`GET ${CERTIFICADO}`]: { status: 200, dados: { existe: false } } })
    await screen.findByRole('form', { name: 'Enviar certificado' })

    expect(screen.getByRole('button', { name: 'Enviar certificado' })).toBeDisabled()
  })
})

describe('Logo da empresa', () => {
  const LOGO = (tema) => `/api/fiscal/logo/${tema}/`
  const abrirLogo = (extras, empresas) => abrir('/fiscal/logo', extras, empresas)
  const png = () => new File(['x'], 'logo.png', { type: 'image/png' })
  const identidadeComLogo = (logo) => ({ status: 200, dados: { ...IDENTIDADE_PADRAO.dados, logo } })

  it('sem logo mostra "Sem logo" nos dois temas', async () => {
    abrirLogo()

    expect(await screen.findAllByText('Sem logo')).toHaveLength(2)
    expect(screen.getByText(/Sem este, o logo do tema claro é usado também no escuro/)).toBeInTheDocument()
  })

  it('mostra a prévia do logo que a empresa já tem', async () => {
    abrirLogo({
      'GET /api/fiscal/identidade/': identidadeComLogo({ claro: 'abc' }),
      [`GET ${LOGO('claro')}`]: { status: 200, blob: new Blob(['x']) },
    })

    expect(await screen.findByRole('img', { name: /Prévia do logo para o tema claro/ })).toHaveAttribute('src', 'blob:logo-falso')
  })

  it('envia o arquivo escolhido e recarrega a identidade da empresa', async () => {
    const { chamadas } = abrirLogo({
      [`PUT ${LOGO('claro')}`]: { status: 201, dados: { tema: 'claro', sha256: 'abc', tipo_conteudo: 'image/png', removidos: [] } },
    })
    const entrada = await screen.findByLabelText('Escolher arquivo (PNG ou SVG)', { selector: '#logo-claro' })

    fireEvent.change(entrada, { target: { files: [png()] } })

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'PUT')).toBe(true))
    const envio = chamadas.find((c) => c.metodo === 'PUT')
    expect(envio.caminho).toBe(LOGO('claro'))
    expect(envio.corpo.arquivo).toBeInstanceOf(File)
    await waitFor(() => expect(chamadas.filter((c) => c.caminho === '/api/fiscal/identidade/').length).toBeGreaterThan(1))
  })

  it('avisa o que foi removido do SVG por segurança', async () => {
    abrirLogo({
      [`PUT ${LOGO('claro')}`]: {
        status: 201,
        dados: { tema: 'claro', sha256: 'abc', tipo_conteudo: 'image/svg+xml', removidos: ['elemento <script>', 'atributo onload'] },
      },
    })
    const entrada = await screen.findByLabelText('Escolher arquivo (PNG ou SVG)', { selector: '#logo-claro' })

    fireEvent.change(entrada, { target: { files: [new File(['<svg/>'], 'logo.svg')] } })

    expect(await screen.findByText(/removemos do arquivo SVG: elemento <script>, atributo onload/)).toBeInTheDocument()
  })

  it('mostra a recusa do servidor com a mensagem do arquivo', async () => {
    abrirLogo({ [`PUT ${LOGO('escuro')}`]: { status: 400, dados: { arquivo: ['O PNG deve ter no máximo 2000×2000 pixels.'] } } })
    const entrada = await screen.findByLabelText('Escolher arquivo (PNG ou SVG)', { selector: '#logo-escuro' })

    fireEvent.change(entrada, { target: { files: [png()] } })

    expect(await screen.findByRole('alert')).toHaveTextContent('O PNG deve ter no máximo 2000×2000 pixels.')
  })

  it('remover pede confirmação', async () => {
    const { chamadas } = abrirLogo({
      'GET /api/fiscal/identidade/': identidadeComLogo({ claro: 'abc' }),
      [`GET ${LOGO('claro')}`]: { status: 200, blob: new Blob(['x']) },
      [`DELETE ${LOGO('claro')}`]: { status: 204, dados: null },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Remover logo' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Remover este logo?' })).getByRole('button', { name: 'Remover logo' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'DELETE')).toBe(true))
  })

  it('quem só consulta vê a prévia mas não altera', async () => {
    abrirLogo({}, [EMPRESA_SO_CONSULTA])

    expect(await screen.findAllByText('Sem logo')).toHaveLength(2)
    expect(screen.queryByLabelText('Escolher arquivo (PNG ou SVG)', { selector: '#logo-claro' })).not.toBeInTheDocument()
    expect(screen.getByText(/pode ver o logo, mas não alterá-lo/)).toBeInTheDocument()
  })
})
