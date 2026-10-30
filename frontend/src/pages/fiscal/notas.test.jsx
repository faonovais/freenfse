import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { limparEmpresaAtiva } from '../../api/empresaAtiva.js'
import { EMPRESA_A, IDENTIDADE_PADRAO, respostaEu } from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'
import { INTERVALO_DE_ACOMPANHAMENTO } from './DetalheNota.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  vi.useRealTimers()
})

const EMISSORA = {
  ...EMPRESA_A,
  perfil: 'emissor',
  permissoes: ['nfse.consultar', 'nfse.emitir', 'nfse.cancelar', 'nfse.substituir', 'cadastro.consultar'],
}
const SO_CONSULTA = { ...EMPRESA_A, perfil: 'consulta', permissoes: ['nfse.consultar'] }

const NOTAS = '/api/fiscal/notas/'
const PRONTA = {
  status: 200,
  dados: {
    pronta: true,
    bloqueios: [],
    ambiente: 'producao_restrita',
    leiaute: 'nt009_v101',
    leiaute_descricao: 'NT 009 v1.01',
  },
}
const BLOQUEADA = {
  status: 200,
  dados: {
    ...PRONTA.dados,
    pronta: false,
    bloqueios: [
      { codigo: 'sem_certificado', mensagem: 'Falta o certificado digital A1 da empresa.', tela: '/fiscal/certificado' },
      { codigo: 'convenio_nao_verificado', mensagem: 'Verifique o convênio do município.', tela: '/fiscal/parametros' },
    ],
  },
}
const AUTORIZADA = {
  id: 9, situacao: 'autorizada', situacao_rotulo: 'Autorizada', numero_nfse: '15', numero_dps: 3, serie: 900,
  competencia: '2026-10-01', tomador_nome: 'TOMADOR FICTICIO LTDA', tomador_documento: '11222333000281',
  valor_servico: '1500.00', emitida_em: '2026-11-02T15:00:00Z', criado_em: '2026-11-02T14:00:00Z',
  ambiente: 'producao_restrita', mensagem: '', substitui: null, chave: '2'.repeat(50), id_dps: 'DPS...',
  leiaute: 'nt009_v101', leiaute_descricao: 'NT 009 v1.01', tomador: { nome: 'TOMADOR FICTICIO LTDA', documento: '11222333000281' },
  servico: { nome: 'Consultoria', codigo_tributacao_nacional: '170101', descricao: 'Consultoria.' },
  valores: { servico: '1500.00' }, complementos: {}, erros: [], substituta: null, substitui_numero: '', tomador_id: 4, servico_id: 3,
  totais: { valor_servico: '1500.00', base_calculo: '1500.00', aliquota_iss: '2.00', valor_iss: '30.00', total_retencoes: '0.00', valor_liquido: '1500.00' },
  eventos: [], historico: [{ de: 'rascunho', para: 'enviando', motivo: 'Emissão solicitada', momento: '2026-11-02T14:00:00Z' }, { de: 'enviando', para: 'autorizada', motivo: 'Autorizada pela Sefin', momento: '2026-11-02T15:00:00Z' }],
  acoes: { editar: false, emitir: false, consultar: true, conferir: false, cancelar: true, substituir: true, baixar_xml: true, danfse: true },
}  // fmt: skip
const detalhe = (extra) => ({ status: 200, dados: { ...AUTORIZADA, ...extra } })

const abrir = (rota, extras = {}, empresa = EMISSORA) =>
  montarApp({
    rota,
    rotasApi: rotasAutenticado({
      eu: respostaEu({ empresas: [empresa] }),
      extras: { [`GET ${NOTAS}prontidao/`]: PRONTA, ...extras },
    }),
  })

describe('Lista de notas', () => {
  const LISTA = {
    status: 200,
    dados: {
      count: 2,
      results: [
        { ...AUTORIZADA },
        { ...AUTORIZADA, id: 10, situacao: 'rejeitada', numero_nfse: '', numero_dps: 4, tomador_nome: 'OUTRO TOMADOR SA' },
      ],
    },
  }

  it('lista as notas com a situação escrita e o ambiente em uso', async () => {
    abrir('/fiscal/notas', { [`GET ${NOTAS}`]: LISTA })

    const tabela = await screen.findByRole('table', { name: 'Notas fiscais' })
    expect(within(tabela).getByRole('link', { name: 'Nº 15' })).toHaveAttribute('href', '/fiscal/notas/9')
    expect(within(tabela).getByRole('link', { name: 'DPS 4' })).toBeInTheDocument()
    expect(within(tabela).getByText('Autorizada')).toBeInTheDocument()
    expect(within(tabela).getByText('Rejeitada')).toBeInTheDocument()
    expect(within(tabela).getAllByText(/R\$\s1\.500,00/)).toHaveLength(2)
    expect(await screen.findByText(/Produção restrita \(testes, sem valor fiscal\)/)).toBeInTheDocument()
  })

  it('aplica os filtros de período, situação, tomador e número na API', async () => {
    const { chamadas } = abrir('/fiscal/notas', { [`GET ${NOTAS}`]: LISTA })
    await screen.findByRole('table', { name: 'Notas fiscais' })

    fireEvent.change(screen.getByLabelText('Competência de'), { target: { value: '2026-10-01' } })
    fireEvent.change(screen.getByLabelText('Competência até'), { target: { value: '2026-10-31' } })
    fireEvent.change(screen.getByLabelText('Situação'), { target: { value: 'autorizada' } })
    fireEvent.change(screen.getByLabelText('Tomador (nome ou CNPJ/CPF)'), { target: { value: 'FICTICIO' } })
    fireEvent.change(screen.getByLabelText('Número da nota'), { target: { value: '15' } })
    fireEvent.click(screen.getByRole('button', { name: 'Filtrar' }))

    await waitFor(() => {
      const ultima = chamadas.filter((c) => c.caminho === NOTAS).at(-1).url
      expect(ultima).toContain('periodo_inicio=2026-10-01')
      expect(ultima).toContain('periodo_fim=2026-10-31')
      expect(ultima).toContain('situacao=autorizada')
      expect(ultima).toContain('tomador=FICTICIO')
      expect(ultima).toContain('numero=15')
    })
  })

  it('mostra cada pendência com o caminho para resolver e não deixa criar nota', async () => {
    abrir('/fiscal/notas', { [`GET ${NOTAS}`]: LISTA, [`GET ${NOTAS}prontidao/`]: BLOQUEADA })

    const secao = await screen.findByRole('region', { name: 'Pendências para emitir' })
    expect(within(secao).getByText(/Falta o certificado digital A1/)).toBeInTheDocument()
    expect(within(secao).getAllByRole('link', { name: 'Resolver' })[0]).toHaveAttribute('href', '/fiscal/certificado')
    expect(within(secao).getAllByRole('link', { name: 'Resolver' })[1]).toHaveAttribute('href', '/fiscal/parametros')
    expect(screen.getByRole('button', { name: 'Nova nota' })).toBeDisabled()
  })

  it('quem só consulta não vê o botão de nova nota', async () => {
    abrir('/fiscal/notas', { [`GET ${NOTAS}`]: LISTA }, SO_CONSULTA)

    await screen.findByRole('table', { name: 'Notas fiscais' })
    expect(screen.queryByRole('button', { name: 'Nova nota' })).not.toBeInTheDocument()
  })

  it('o emblema de produção restrita continua visível no topo', async () => {
    montarApp({
      rota: '/fiscal/notas',
      rotasApi: rotasAutenticado({
        eu: respostaEu({ empresas: [EMISSORA] }),
        extras: {
          [`GET ${NOTAS}prontidao/`]: PRONTA,
          [`GET ${NOTAS}`]: LISTA,
          'GET /api/fiscal/identidade/': { status: 200, dados: { ...IDENTIDADE_PADRAO.dados, ambiente: 'producao_restrita' } },
        },
      }),
    })

    expect((await screen.findAllByText('Produção restrita')).length).toBeGreaterThan(0)
  })

  it('avisa quando nenhum filtro encontra nota', async () => {
    abrir('/fiscal/notas', { [`GET ${NOTAS}`]: { status: 200, dados: { count: 0, results: [] } } })

    expect(await screen.findByText('Nenhuma nota encontrada com estes filtros.')).toBeInTheDocument()
  })
})

describe('Emissão guiada', () => {
  const PESSOAS = {
    status: 200,
    dados: { count: 1, results: [{ id: 4, nome: 'TOMADOR FICTICIO LTDA', documento_formatado: '11.222.333/0002-81' }] },
  }
  const SERVICOS = {
    status: 200,
    dados: [{ id: 3, nome: 'Consultoria', codigo_tributacao_nacional: '170101', aliquota_iss: '2.00', iss_retido: false, cst_ibs_cbs: '' }],
  }
  const PREVIA = {
    status: 200,
    dados: {
      tomador: { nome: 'TOMADOR FICTICIO LTDA', documento: '11222333000281' },
      servico: { nome: 'Consultoria', codigo_tributacao_nacional: '170101', descricao: 'Consultoria em gestão agrícola.' },
      competencia: '2026-10-01',
      totais: { valor_servico: '1500.00', desconto_incondicionado: '0.00', deducao: '0.00', base_calculo: '1500.00', aliquota_iss: '2.00', valor_iss: '30.00', iss_retido: false, retencao_irrf: '0.00', retencao_csll: '0.00', retencao_inss: '0.00', total_retencoes: '0.00', valor_liquido: '1500.00' },
      avisos: ['A competência é de outro mês. Confira se é isso mesmo.'],
      bloqueios: [],
    },
  }  // fmt: skip
  const rotas = (extras = {}) => ({
    'GET /api/cadastros/pessoas/': PESSOAS,
    'GET /api/cadastros/servicos/': SERVICOS,
    ...extras,
  })
  const preencher = async () => {
    fireEvent.click(await screen.findByRole('combobox', { name: 'Tomador' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /TOMADOR FICTICIO LTDA/ }))
    fireEvent.click(await screen.findByRole('combobox', { name: 'Serviço' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Consultoria/ }))
    fireEvent.change(screen.getByLabelText('Valor do serviço (R$)'), { target: { value: '1500.00' } })
  }

  it('mostra o ambiente em que a nota será emitida', async () => {
    abrir('/fiscal/notas/nova', rotas())

    expect(await screen.findByText(/Produção restrita \(testes, sem valor fiscal\)/)).toBeInTheDocument()
  })

  it('só oferece serviços vigentes na competência escolhida', async () => {
    const { chamadas } = abrir('/fiscal/notas/nova', rotas())
    await screen.findByRole('combobox', { name: 'Serviço' })

    fireEvent.change(screen.getByLabelText('Competência'), { target: { value: '2026-03-01' } })

    await waitFor(() => {
      const urls = chamadas.filter((c) => c.caminho === '/api/cadastros/servicos/').map((c) => c.url)
      expect(urls.at(-1)).toContain('vigente_em=2026-03-01')
    })
  })

  it('confere a nota antes de enviar, com o cálculo e os avisos', async () => {
    const { chamadas } = abrir('/fiscal/notas/nova', rotas({ [`POST ${NOTAS}previa/`]: PREVIA }))
    await preencher()

    fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

    const conferencia = await screen.findByRole('region', { name: 'Conferência da nota' })
    expect(within(conferencia).getByText(/ISS \(2.00%\)/)).toBeInTheDocument()
    expect(within(conferencia).getByText('Valor líquido a receber')).toBeInTheDocument()
    expect(within(conferencia).getByText('NT 009 v1.01')).toBeInTheDocument()
    expect(screen.getByText('A competência é de outro mês. Confira se é isso mesmo.')).toBeInTheDocument()
    const corpo = chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo
    expect(corpo).toMatchObject({ tomador: 4, servico: 3, valores: { servico: '1500.00', desconto_incondicionado: null } })
    expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho === NOTAS)).toBe(false) // a prévia não grava
  })

  it('emite depois de confirmar: grava o rascunho, pede o envio e abre a nota', async () => {
    const { chamadas } = abrir(
      '/fiscal/notas/nova',
      rotas({
        [`POST ${NOTAS}previa/`]: PREVIA,
        [`POST ${NOTAS}`]: { status: 201, dados: { ...AUTORIZADA, id: 9, situacao: 'rascunho' } },
        [`POST ${NOTAS}9/emitir/`]: { status: 202, dados: { ...AUTORIZADA, situacao: 'enviando' } },
        [`GET ${NOTAS}9/`]: detalhe({ situacao: 'enviando', numero_nfse: '', acoes: { ...AUTORIZADA.acoes, cancelar: false, substituir: false } }),
      }),
    )
    await preencher()
    fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Emitir nota' }))

    const modal = await screen.findByRole('dialog')
    expect(within(modal).getByText('Enviar a nota de teste?')).toBeInTheDocument()
    fireEvent.click(within(modal).getByRole('button', { name: 'Emitir nota' }))

    expect(await screen.findByText(/Enviando à Sefin… esta tela acompanha/)).toBeInTheDocument()
    const ordem = chamadas.filter((c) => c.metodo === 'POST').map((c) => c.caminho)
    expect(ordem).toEqual([`${NOTAS}previa/`, NOTAS, `${NOTAS}9/emitir/`])
  })

  it('aponta o campo com problema devolvido pela conferência', async () => {
    abrir(
      '/fiscal/notas/nova',
      rotas({ [`POST ${NOTAS}previa/`]: { status: 400, dados: { 'valores.servico': ['O valor do serviço deve ser maior que zero.'] } } }),
    )
    await preencher()

    fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

    expect(await screen.findByText('O valor do serviço deve ser maior que zero.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Conferência da nota' })).not.toBeInTheDocument()
  })

  it('com pendências, conferir é possível mas emitir fica bloqueado', async () => {
    abrir('/fiscal/notas/nova', rotas({ [`GET ${NOTAS}prontidao/`]: BLOQUEADA, [`POST ${NOTAS}previa/`]: PREVIA }))
    await preencher()

    fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

    expect(await screen.findByRole('button', { name: 'Emitir nota' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Salvar rascunho' })).toBeEnabled()
    expect(screen.getByText(/Resolva as pendências acima/)).toBeInTheDocument()
  })

  it('em produção, avisa que a nota terá valor fiscal', async () => {
    const producao = { status: 200, dados: { ...PRONTA.dados, ambiente: 'producao', leiaute: 'nt004_v2', leiaute_descricao: 'NT 004 v2.0' } }
    abrir('/fiscal/notas/nova', rotas({ [`GET ${NOTAS}prontidao/`]: producao, [`POST ${NOTAS}previa/`]: PREVIA }))
    await preencher()
    fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

    fireEvent.click(await screen.findByRole('button', { name: 'Emitir nota' }))

    const modal = await screen.findByRole('dialog')
    expect(within(modal).getByText('Emitir nota com valor fiscal?')).toBeInTheDocument()
  })
})

describe('Detalhe da nota', () => {
  it('mostra a nota autorizada com os dados, o histórico e as ações permitidas', async () => {
    abrir('/fiscal/notas/9', { [`GET ${NOTAS}9/`]: detalhe() })

    expect(await screen.findByRole('heading', { name: 'Nota nº 15' })).toBeInTheDocument()
    expect(screen.getByText(/Leiaute NT 009 v1.01/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelar nota' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Emitir nota substituta a partir desta' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Baixar XML' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Abrir DANFSe (PDF)' })).toBeInTheDocument()
    const historico = screen.getByRole('region', { name: 'Histórico da nota' })
    expect(within(historico).getByText(/Enviando à Sefin → Autorizada/)).toBeInTheDocument()
  })

  it('sem permissão, os botões de cancelar e substituir não aparecem', async () => {
    abrir(
      '/fiscal/notas/9',
      { [`GET ${NOTAS}9/`]: detalhe({ acoes: { ...AUTORIZADA.acoes, cancelar: false, substituir: false } }) },
      SO_CONSULTA,
    )

    await screen.findByRole('heading', { name: 'Nota nº 15' })
    expect(screen.queryByRole('button', { name: 'Cancelar nota' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /substituta/ })).not.toBeInTheDocument()
  })

  it('explica a rejeição em linguagem simples, com o que fazer e o texto original', async () => {
    abrir('/fiscal/notas/9', {
      [`GET ${NOTAS}9/`]: detalhe({
        situacao: 'rejeitada',
        numero_nfse: '',
        mensagem: 'O regime não confere. Corrija o regime.',
        erros: [
          {
            codigo: 'E0160',
            explicacao: 'A situação da empresa no Simples Nacional não confere com a do cadastro nacional.',
            orientacao: 'Corrija o regime tributário em Parâmetros fiscais conforme o cadastro da Receita.',
            descricao_original: 'Situação no Simples diverge do cadastro.',
            complemento: '',
          },
        ],
        acoes: { ...AUTORIZADA.acoes, editar: true, emitir: true, cancelar: false, substituir: false, baixar_xml: false, danfse: false },
      }),
    })

    const erros = await screen.findByRole('list', { name: 'Problemas apontados pela Sefin' })
    expect(within(erros).getByText(/Código E0160:/)).toBeInTheDocument()
    expect(within(erros).getByText(/não confere com a do cadastro nacional/)).toBeInTheDocument()
    expect(within(erros).getByText(/Corrija o regime tributário em Parâmetros fiscais/)).toBeInTheDocument()
    expect(within(erros).getByText('Texto original da Sefin')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Corrigir dados' })).toHaveAttribute('href', '/fiscal/notas/9/editar')
    expect(screen.getByRole('button', { name: 'Enviar de novo' })).toBeInTheDocument()
  })

  it('nota incerta: avisa para não emitir de novo e oferece conferir, sem cancelar', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', {
      [`GET ${NOTAS}9/`]: detalhe({
        situacao: 'incerta',
        numero_nfse: '',
        chave: null,
        mensagem: 'A Sefin não confirmou se recebeu esta nota. Não emita esta nota outra vez por conta própria.',
        acoes: { ...AUTORIZADA.acoes, emitir: true, conferir: true, consultar: false, cancelar: false, substituir: false, baixar_xml: false, danfse: false },
      }),
      [`POST ${NOTAS}9/conferir/`]: detalhe({ situacao: 'autorizada' }),
    })

    expect(await screen.findByText(/Não emita esta nota outra vez por conta própria/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar nota' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Conferir agora na Sefin' }))

    await waitFor(() => expect(chamadas.some((c) => c.caminho === `${NOTAS}9/conferir/`)).toBe(true))
    expect(await screen.findByText('Conferência feita.')).toBeInTheDocument()
  })

  it('tentar de novo uma nota incerta explica que a Sefin é consultada antes', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', {
      [`GET ${NOTAS}9/`]: detalhe({
        situacao: 'incerta',
        acoes: { ...AUTORIZADA.acoes, emitir: true, cancelar: false, substituir: false },
      }),
      [`POST ${NOTAS}9/emitir/`]: { status: 202, dados: { ...AUTORIZADA, situacao: 'enviando' } },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Tentar enviar de novo' }))

    const modal = await screen.findByRole('dialog')
    expect(within(modal).getByText(/o sistema consulta a Sefin: se a nota já existir, ela é apenas recuperada/)).toBeInTheDocument()
    fireEvent.click(within(modal).getByRole('button', { name: 'Enviar' }))
    await waitFor(() => expect(chamadas.some((c) => c.caminho === `${NOTAS}9/emitir/`)).toBe(true))
  })

  it('acompanha a nota enquanto ela está sendo enviada', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let consultas = 0
    abrir('/fiscal/notas/9', {
      [`GET ${NOTAS}9/`]: () => {
        consultas += 1
        return consultas < 3 ? detalhe({ situacao: 'enviando', numero_nfse: '' }) : detalhe()
      },
    })
    expect(await screen.findByText(/Enviando à Sefin… esta tela acompanha/)).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DE_ACOMPANHAMENTO + 100))
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DE_ACOMPANHAMENTO + 100))

    expect(await screen.findByRole('heading', { name: 'Nota nº 15' })).toBeInTheDocument()
    expect(screen.queryByText(/Enviando à Sefin… esta tela acompanha/)).not.toBeInTheDocument()
  })

  it('baixa o XML pela API com a empresa da aba', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', {
      [`GET ${NOTAS}9/`]: detalhe(),
      [`GET ${NOTAS}9/xml/`]: { status: 200, dados: null, blob: new Blob(['<xml/>']) },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Baixar XML' }))

    await waitFor(() => expect(chamadas.some((c) => c.caminho === `${NOTAS}9/xml/`)).toBe(true))
  })

  it('mostra os eventos confirmados pela Sefin', async () => {
    abrir('/fiscal/notas/9', {
      [`GET ${NOTAS}9/`]: detalhe({
        situacao: 'cancelada',
        eventos: [{ tipo_evento: '101101', rotulo: 'Cancelamento', descricao: 'Cancelamento', registrado_em: '2026-11-03T12:00:00Z' }],
        acoes: { ...AUTORIZADA.acoes, cancelar: false, substituir: false },
      }),
    })

    const eventos = await screen.findByRole('region', { name: 'Eventos' })
    expect(within(eventos).getByText(/Cancelamento ·/)).toBeInTheDocument()
    expect(screen.getByText('Cancelada')).toBeInTheDocument()
  })
})

describe('Cancelamento e substituição', () => {
  const abrirAutorizada = (extras) => abrir('/fiscal/notas/9', { [`GET ${NOTAS}9/`]: detalhe(), ...extras })
  const preencherCancelamento = async (justificativa) => {
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar nota' }))
    const formulario = await screen.findByRole('form', { name: 'Cancelar nota' })
    fireEvent.change(within(formulario).getByLabelText(/Justificativa/), { target: { value: justificativa } })
    fireEvent.submit(formulario)
    const modal = await screen.findByRole('dialog')
    fireEvent.click(within(modal).getByRole('button', { name: 'Cancelar a nota' }))
  }

  it('pede a confirmação e envia o motivo e a justificativa', async () => {
    const { chamadas } = abrirAutorizada({
      [`POST ${NOTAS}9/cancelar/`]: detalhe({ situacao: 'cancelada', acoes: { ...AUTORIZADA.acoes, cancelar: false, substituir: false } }),
    })

    await preencherCancelamento('Nota emitida com o valor errado.')

    await waitFor(() => expect(chamadas.some((c) => c.caminho === `${NOTAS}9/cancelar/`)).toBe(true))
    expect(chamadas.find((c) => c.caminho === `${NOTAS}9/cancelar/`).corpo).toEqual({
      codigo_motivo: 1,
      justificativa: 'Nota emitida com o valor errado.',
    })
    expect(await screen.findByText('Cancelamento confirmado pela Sefin.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar nota' })).not.toBeInTheDocument()
  })

  it('mostra a recusa da Sefin (prazo ou regra do município) com a orientação', async () => {
    abrirAutorizada({
      [`POST ${NOTAS}9/cancelar/`]: {
        status: 422,
        dados: {
          codigo: 'cancelamento_recusado',
          detalhe: 'O prazo ou a regra do município não permite cancelar esta nota diretamente. Peça o cancelamento à prefeitura (análise fiscal).',
          erros: [
            {
              codigo: 'E0824',
              explicacao: 'O prazo ou a regra do município não permite cancelar esta nota diretamente.',
              orientacao: 'Peça o cancelamento à prefeitura (análise fiscal).',
              descricao_original: 'Prazo expirado.',
              complemento: '',
            },
          ],
        },
      },
    })

    await preencherCancelamento('Nota emitida com o valor errado.')

    expect(await screen.findByText(/A Sefin recusou o cancelamento/)).toBeInTheDocument()
    expect(screen.getAllByText(/análise fiscal/).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Nota nº 15' })).toBeInTheDocument()
    expect(screen.getByText('Autorizada')).toBeInTheDocument() // a nota segue autorizada
  })

  it('mostra o erro de justificativa curta junto do campo', async () => {
    abrirAutorizada({
      [`POST ${NOTAS}9/cancelar/`]: {
        status: 400,
        dados: { justificativa: ['Explique o motivo do cancelamento em 15 a 255 caracteres.'] },
      },
    })

    await preencherCancelamento('curta')

    expect(await screen.findByText('Explique o motivo do cancelamento em 15 a 255 caracteres.')).toBeInTheDocument()
  })

  it('cria o rascunho da nota substituta e abre a nova nota', async () => {
    const { chamadas } = abrirAutorizada({
      [`POST ${NOTAS}9/substituir/`]: {
        status: 201,
        dados: { ...AUTORIZADA, id: 12, situacao: 'rascunho', numero_nfse: '', numero_dps: null, substitui: 9 },
      },
      [`GET ${NOTAS}12/`]: detalhe({ id: 12, situacao: 'rascunho', numero_nfse: '', numero_dps: null, substitui: 9, substitui_numero: '15', chave: null }),
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Emitir nota substituta a partir desta' }))
    const formulario = await screen.findByRole('form', { name: 'Emitir nota substituta' })
    fireEvent.change(within(formulario).getByLabelText('Motivo da substituição'), { target: { value: '99' } })
    fireEvent.change(within(formulario).getByLabelText(/Explique o motivo/), { target: { value: 'Valor do serviço corrigido.' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Criar rascunho da nota substituta' }))

    expect(await screen.findByRole('heading', { name: 'Rascunho de nota' })).toBeInTheDocument()
    expect(screen.getByText(/Substitui a nota nº 15/)).toBeInTheDocument()
    expect(chamadas.find((c) => c.caminho === `${NOTAS}9/substituir/`).corpo).toEqual({
      codigo_motivo: '99',
      motivo: 'Valor do serviço corrigido.',
    })
  })
})
