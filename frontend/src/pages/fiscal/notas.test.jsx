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

  it('sugere a competência do mês de Brasília às 23:30 do último dia do mês (issue #24)', async () => {
    // Em UTC já é 01/11; o servidor recusaria a competência de novembro como futura.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-11-01T02:30:00Z'))
    abrir('/fiscal/notas/nova', rotas())

    expect(await screen.findByLabelText('Competência')).toHaveValue('2026-10-01')
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

  describe('IBS/CBS: o serviço decide; nota > modelo > serviço (cIndOp)', () => {
    const COM_CLASSIFICACAO = {
      status: 200,
      dados: [
        {
          ...SERVICOS.dados[0], cst_ibs_cbs: '000', c_class_trib: '000001', nbs: '115021000',
          codigo_indicador_operacao: '100301',
        },
      ],
    } // prettier-ignore
    const PRONTA_COM_PADRAO = { status: 200, dados: { ...PRONTA.dados, ibs_cbs: { indicador_destinatario: 0 } } }
    const previaCom = (ibs, aliquota) => ({
      status: 200,
      dados: {
        ...PREVIA.dados,
        servico: { ...PREVIA.dados.servico, cst_ibs_cbs: '000' },
        ibs_cbs: ibs,
        complementos: { ...(PREVIA.dados.complementos ?? {}), aliquota_issqn: aliquota },
      },
    })
    const ORIGENS_DO_SERVICO = { codigo_indicador_operacao: 'servico', indicador_destinatario: 'empresa' }
    const DO_SERVICO = {
      na_dps: true, motivo: null, codigo_indicador_operacao: '100301', indicador_destinatario: 0,
      origens: ORIGENS_DO_SERVICO, nbs: '115021000', cst: '000', c_class_trib: '000001',
    }  // fmt: skip
    const abrirComServico = (extras = {}, rota = '/fiscal/notas/nova') =>
      abrir(
        rota,
        rotas({
          'GET /api/cadastros/servicos/': COM_CLASSIFICACAO,
          [`GET ${NOTAS}prontidao/`]: PRONTA_COM_PADRAO,
          [`POST ${NOTAS}previa/`]: previaCom(DO_SERVICO),
          ...extras,
        }),
      )
    const conferir = async () => {
      await preencher()
      fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))
      return screen.findByRole('region', { name: 'Conferência da nota' })
    }

    it('sem ajuste, a nota herda: nada é enviado em ibs_cbs e a conferência mostra a origem de cada campo', async () => {
      const { chamadas } = abrirComServico()

      const conferencia = await conferir()

      expect(chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo.ibs_cbs).toBeNull()
      expect(screen.getByText(/Em branco: vale o do serviço \(100301\)/)).toBeInTheDocument()
      const linha = within(conferencia).getByText('IBS/CBS na DPS').closest('div')
      expect(linha).toHaveTextContent('Indicador da operação 100301 (do serviço)')
      expect(linha).toHaveTextContent('destinatário é o próprio tomador (padrão da empresa)')
      expect(linha).toHaveTextContent('NBS 115021000 · CST 000 · cClassTrib 000001')
    })

    it('a conferência mostra o modelo como origem do que o modelo ajustou', async () => {
      const doModelo = { ...DO_SERVICO, codigo_indicador_operacao: '050101', origens: { ...ORIGENS_DO_SERVICO, codigo_indicador_operacao: 'modelo' } }
      abrirComServico({ [`POST ${NOTAS}previa/`]: previaCom(doModelo) })

      const conferencia = await conferir()

      const linha = within(conferencia).getByText('IBS/CBS na DPS').closest('div')
      expect(linha).toHaveTextContent('Indicador da operação 050101 (do modelo)')
    })

    it('não existe mais a opção "não informar nesta nota": a classificação do serviço decide', async () => {
      abrirComServico()
      await preencher()

      expect(screen.queryByLabelText('Não informar o IBS/CBS nesta nota')).not.toBeInTheDocument()
    })

    it('serviço sem indicador da operação: a tela manda completar o cadastro do serviço', async () => {
      abrirComServico({
        'GET /api/cadastros/servicos/': { status: 200, dados: [{ ...COM_CLASSIFICACAO.dados[0], codigo_indicador_operacao: '' }] },
      })
      await preencher()

      expect(await screen.findByText(/O serviço não tem indicador da operação\. Complete o cadastro do serviço/)).toBeInTheDocument()
    })

    it('ajuste pontual: o indicador e o destinatário digitados vão na nota e a origem é a nota', async () => {
      const daNota = { ...DO_SERVICO, codigo_indicador_operacao: '050101', indicador_destinatario: 1, origens: { codigo_indicador_operacao: 'nota', indicador_destinatario: 'nota' } }
      const { chamadas } = abrirComServico({ [`POST ${NOTAS}previa/`]: previaCom(daNota) })
      await preencher()
      fireEvent.change(screen.getByLabelText('Ajustar o indicador da operação (IBS/CBS)'), { target: { value: '050101' } })
      fireEvent.change(screen.getByLabelText('O destinatário é o próprio tomador?'), { target: { value: '1' } })

      fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

      const conferencia = await screen.findByRole('region', { name: 'Conferência da nota' })
      expect(chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo.ibs_cbs).toEqual({
        codigo_indicador_operacao: '050101',
        indicador_destinatario: 1,
      })
      const linha = within(conferencia).getByText('IBS/CBS na DPS').closest('div')
      expect(linha).toHaveTextContent('Indicador da operação 050101 (ajuste desta nota)')
      expect(linha).toHaveTextContent('destinatário é outra pessoa (ajuste desta nota)')
    })

    it('o destinatário em branco herda; escolher "Sim" explicitamente é um ajuste da nota', async () => {
      const { chamadas } = abrirComServico()
      await preencher()
      const select = screen.getByLabelText('O destinatário é o próprio tomador?')
      expect(select).toHaveValue('') // herdar
      expect(within(select).getByRole('option', { name: 'Herdar (da empresa: sim)' })).toBeInTheDocument()

      fireEvent.change(select, { target: { value: '0' } })
      fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))
      await screen.findByRole('region', { name: 'Conferência da nota' })

      expect(chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo.ibs_cbs).toEqual({ indicador_destinatario: 0 })
    })

    describe('destinatário (issue #33): obrigatório quando é outra pessoa', () => {
      const DOIS = {
        'GET /api/cadastros/pessoas/': {
          status: 200,
          dados: {
            count: 2,
            results: [
              { id: 4, nome: 'TOMADOR FICTICIO LTDA', documento_formatado: '11.222.333/0002-81' },
              { id: 5, nome: 'DESTINATARIO FICTICIO LTDA', documento_formatado: '05.423.960/0001-70' },
            ],
          },
        },
      }
      const COM_DESTINATARIO = {
        ...DO_SERVICO,
        indicador_destinatario: 1,
        origens: { codigo_indicador_operacao: 'servico', indicador_destinatario: 'nota' },
      }
      const escolherOutraPessoa = () =>
        fireEvent.change(screen.getByLabelText('O destinatário é o próprio tomador?'), { target: { value: '1' } })

      it('com o destinatário sendo o próprio tomador, a escolha do destinatário não aparece', async () => {
        abrirComServico(DOIS)
        await preencher()

        expect(screen.queryByRole('combobox', { name: 'Destinatário' })).not.toBeInTheDocument()
      })

      it('"Não" mostra o seletor, que é obrigatório, e o envio leva a pessoa escolhida', async () => {
        const previa = previaCom(COM_DESTINATARIO)
        previa.dados.complementos.destinatario = {
          pessoa: 5, origem: 'nota', dados: { nome: 'DESTINATARIO FICTICIO LTDA', documento: '05423960000170' },
        } // prettier-ignore
        const { chamadas } = abrirComServico({ ...DOIS, [`POST ${NOTAS}previa/`]: previa })
        await preencher()
        escolherOutraPessoa()

        fireEvent.click(await screen.findByRole('combobox', { name: 'Destinatário' }))
        fireEvent.mouseDown(await screen.findByRole('option', { name: /DESTINATARIO FICTICIO LTDA/ }))
        fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

        const conferencia = await screen.findByRole('region', { name: 'Conferência da nota' })
        const corpo = chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo
        expect(corpo.destinatario).toBe(5)
        expect(corpo.ibs_cbs).toEqual({ indicador_destinatario: 1 })
        const linha = within(conferencia).getByText('Destinatário').closest('div')
        expect(linha).toHaveTextContent('DESTINATARIO FICTICIO LTDA (05423960000170)')
        expect(linha).toHaveTextContent('escolhido nesta nota')
      })

      it('mostra junto do seletor a regra E0919 quando o destinatário não serve', async () => {
        const mensagem = 'Regra E0919 da Sefin: o destinatário precisa ter CPF ou CNPJ e endereço no Brasil completo.'
        abrirComServico({ ...DOIS, [`POST ${NOTAS}previa/`]: { status: 400, dados: { destinatario: mensagem } } })
        await preencher()
        escolherOutraPessoa()

        fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

        expect(await screen.findByText(mensagem)).toBeInTheDocument()
        expect(screen.queryByRole('region', { name: 'Conferência da nota' })).not.toBeInTheDocument()
      })

      it('voltar para "o próprio tomador" esconde o seletor', async () => {
        abrirComServico(DOIS)
        await preencher()
        escolherOutraPessoa()
        expect(await screen.findByRole('combobox', { name: 'Destinatário' })).toBeInTheDocument()

        fireEvent.change(screen.getByLabelText('O destinatário é o próprio tomador?'), { target: { value: '0' } })

        expect(screen.queryByRole('combobox', { name: 'Destinatário' })).not.toBeInTheDocument()
      })
    })

    describe('endereço do tomador pelo cIndOp (E0239, E0243)', () => {
      it('mostra junto do tomador a regra E0239 devolvida pela conferência', async () => {
        const mensagem = 'Regra E0239 da Sefin: o tomador precisa ter CPF ou CNPJ e endereço no Brasil completo.'
        abrirComServico({ [`POST ${NOTAS}previa/`]: { status: 400, dados: { tomador: mensagem } } })
        await preencher()

        fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

        expect(await screen.findByText(mensagem)).toBeInTheDocument()
        expect(screen.queryByRole('region', { name: 'Conferência da nota' })).not.toBeInTheDocument()
      })

      it('mostra o aviso do indicador 130201 na conferência sem bloquear o envio', async () => {
        const aviso =
          'O texto do Anexo VII indica o endereço do adquirente para este indicador; confira se o tomador tem CPF/CNPJ e endereço nacional, para evitar a rejeição E0239.'
        const previa = previaCom({ ...DO_SERVICO, codigo_indicador_operacao: '130201' })
        previa.dados.avisos = [aviso]
        abrirComServico({ [`POST ${NOTAS}previa/`]: previa })

        await conferir()

        expect(screen.getByText(aviso)).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Emitir nota' })).toBeEnabled()
      })
    })

    it('a conferência diz por que o grupo não vai quando a classificação não tem tributação de IBS/CBS', async () => {
      const semGrupo = {
        na_dps: false, motivo: 'A classificação 410009 não tem tributação de IBS/CBS (ind_gIBSCBS = 0).',
        origens: ORIGENS_DO_SERVICO, nbs: '115021000', cst: '410', c_class_trib: '410009',
      }  // fmt: skip
      abrirComServico({ [`POST ${NOTAS}previa/`]: previaCom(semGrupo) })

      const conferencia = await conferir()

      expect(within(conferencia).getByText(/Não vai na nota\. A classificação 410009 não tem tributação de IBS\/CBS/)).toBeInTheDocument()
    })

    it('mudar o ajuste depois de conferir invalida a conferência', async () => {
      abrirComServico()
      await conferir()

      fireEvent.change(screen.getByLabelText('Ajustar o indicador da operação (IBS/CBS)'), { target: { value: '050101' } })

      expect(screen.queryByRole('region', { name: 'Conferência da nota' })).not.toBeInTheDocument()
    })

    it('serviço sem classificação não mostra a seção de IBS/CBS', async () => {
      abrir('/fiscal/notas/nova', rotas({ [`GET ${NOTAS}prontidao/`]: PRONTA_COM_PADRAO }))
      await preencher()

      expect(screen.queryByLabelText('Ajustar o indicador da operação (IBS/CBS)')).not.toBeInTheDocument()
    })

    it('mostra o erro do indicador junto do campo', async () => {
      abrirComServico({
        [`POST ${NOTAS}previa/`]: { status: 400, dados: { ibs_cbs: 'O código do indicador da operação tem 6 dígitos.' } },
      })
      await preencher()
      fireEvent.change(screen.getByLabelText('Ajustar o indicador da operação (IBS/CBS)'), { target: { value: '12' } })

      fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))

      expect(await screen.findByText('O código do indicador da operação tem 6 dígitos.')).toBeInTheDocument()
    })

    describe('alíquota do ISS na DPS (pAliq, regras E0600 a E0640)', () => {
      const decisao = (extra) => ({
        envia: false, situacao: 'proibida', codigo_regra: 'E0617', explicacao: 'Prestador não optante e município com convênio ativo: a alíquota não pode ser informada.',
        minimo: null, bloqueio: null, municipio_incidencia: '2903201', regra_incidencia: 'EP',
        regra_incidencia_descricao: 'estabelecimento do prestador', convenio_ativo: true, avisos: [], ...extra,
      })  // fmt: skip

      it('mostra se a alíquota vai, a regra aplicada e onde incide o ISSQN', async () => {
        abrirComServico({ [`POST ${NOTAS}previa/`]: previaCom(DO_SERVICO, decisao()) })

        const conferencia = await conferir()

        const linha = within(conferencia).getByText('Alíquota do ISS na DPS').closest('div')
        expect(linha).toHaveTextContent('Não vai na nota (regra E0617)')
        expect(linha).toHaveTextContent('a alíquota não pode ser informada')
        expect(linha).toHaveTextContent('ISSQN devido no estabelecimento do prestador, município IBGE 2903201')
      })

      it('quando a alíquota é obrigatória, diz que vai na nota', async () => {
        const vai = decisao({ envia: true, situacao: 'obrigatoria', codigo_regra: 'E0619', explicacao: 'Convênio não ativo na competência: a alíquota é obrigatória.' })
        abrirComServico({ [`POST ${NOTAS}previa/`]: previaCom(DO_SERVICO, vai) })

        const conferencia = await conferir()

        expect(within(conferencia).getByText('Alíquota do ISS na DPS').closest('div')).toHaveTextContent('Vai na nota (regra E0619)')
      })

      it('bloqueio da regra aparece na conferência com o código e a orientação', async () => {
        const bloqueada = decisao({
          situacao: 'obrigatoria', codigo_regra: 'E0621', minimo: '1.8',
          bloqueio: 'A alíquota do serviço (1.50%) é menor que o mínimo de 1.8% exigido para este caso (regra E0621). Corrija o cadastro do serviço.',
        })
        abrirComServico({ [`POST ${NOTAS}previa/`]: previaCom(DO_SERVICO, bloqueada) })

        const conferencia = await conferir()

        const linha = within(conferencia).getByText('Alíquota do ISS na DPS').closest('div')
        expect(linha).toHaveTextContent('Bloqueia o envio (regra E0621)')
        expect(linha).toHaveTextContent('menor que o mínimo de 1.8%')
      })
    })

    describe('município da prestação (cLocPrestacao)', () => {
      const BALSAS = { codigo: '2101400', nome: 'Balsas', uf: 'MA' }
      const PALMAS = { codigo: '1721000', nome: 'Palmas', uf: 'TO' }
      const PRONTA_COM_EMISSOR = { status: 200, dados: { ...PRONTA.dados, municipio_prestacao_padrao: '2101400' } }
      const municipios = {
        'GET /api/cadastros/municipios/': (chamada) => {
          if (chamada.url.includes('codigo=2101400')) return { status: 200, dados: [BALSAS] }
          if (chamada.url.includes('codigo=1721000') || chamada.url.includes('busca=pal')) return { status: 200, dados: [PALMAS] }
          return { status: 200, dados: [] }
        },
      }
      const abrirComMunicipio = (extras = {}, rota = '/fiscal/notas/nova') =>
        abrirComServico({ [`GET ${NOTAS}prontidao/`]: PRONTA_COM_EMISSOR, ...municipios, ...extras }, rota)
      const corpoDaPrevia = (chamadas) => chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo

      it('em branco, diz que vale o município do emissor e o envia vazio (herda)', async () => {
        const { chamadas } = abrirComMunicipio()

        expect(await screen.findByText(/Em branco, vale o município do emissor/)).toBeInTheDocument()
        expect(await screen.findByText('Balsas/MA')).toBeInTheDocument()
        await conferir()

        expect(corpoDaPrevia(chamadas).codigo_municipio_prestacao).toBe('')
      })

      it('escolhendo outro município, ele vai no corpo e "Voltar ao padrão" o devolve em branco', async () => {
        const { chamadas } = abrirComMunicipio()
        const campo = await screen.findByRole('combobox', { name: 'Município da prestação' })
        fireEvent.change(campo, { target: { value: 'pal' } })
        fireEvent.mouseDown(await screen.findByRole('option', { name: /Palmas\/TO/ }))

        await conferir()
        expect(corpoDaPrevia(chamadas).codigo_municipio_prestacao).toBe('1721000')

        fireEvent.click(screen.getByRole('button', { name: 'Voltar ao padrão' }))
        fireEvent.click(screen.getByRole('button', { name: 'Conferir a nota' }))
        await waitFor(() => expect(chamadas.filter((c) => c.caminho === `${NOTAS}previa/`)).toHaveLength(2))
        expect(chamadas.filter((c) => c.caminho === `${NOTAS}previa/`)[1].corpo.codigo_municipio_prestacao).toBe('')
      })

      it('a conferência mostra o município da prestação e de onde ele veio', async () => {
        const local = { codigo: '1721000', origem: 'nota' }
        const resposta = previaCom(DO_SERVICO)
        resposta.dados.complementos.local_prestacao = local
        abrirComMunicipio({ [`POST ${NOTAS}previa/`]: resposta })

        const conferencia = await conferir()

        const linha = within(conferencia).getByText('Município da prestação').closest('div')
        await waitFor(() => expect(linha).toHaveTextContent('Palmas/TO'))
        expect(linha).toHaveTextContent('informado nesta nota')
      })

      it('no serviço do local da prestação, a regra da alíquota mostra o município e a origem', async () => {
        const lp = {
          envia: true, situacao: 'obrigatoria', codigo_regra: 'E0619', explicacao: 'Convênio não ativo na competência: a alíquota é obrigatória.',
          minimo: null, bloqueio: null, municipio_incidencia: '1721000', regra_incidencia: 'LP',
          regra_incidencia_descricao: 'local da prestação', origem_prestacao: 'modelo', convenio_ativo: false, avisos: [],
        }  // fmt: skip
        abrirComMunicipio({ [`POST ${NOTAS}previa/`]: previaCom(DO_SERVICO, lp) })

        const conferencia = await conferir()

        const linha = within(conferencia).getByText('Alíquota do ISS na DPS').closest('div')
        await waitFor(() => expect(linha).toHaveTextContent('ISSQN devido no local da prestação, município Palmas/TO, do modelo'))
      })

      it('mostra junto do campo o erro de um município que não existe', async () => {
        abrirComMunicipio({
          [`POST ${NOTAS}previa/`]: { status: 400, dados: { codigo_municipio_prestacao: 'Município com o código IBGE 9999999 não encontrado.' } },
        })

        await conferir().catch(() => null)

        expect(await screen.findByText('Município com o código IBGE 9999999 não encontrado.')).toBeInTheDocument()
      })
    })

    describe('ao corrigir um rascunho', () => {
      const rascunho = (complementos) =>
        detalhe({ situacao: 'rascunho', complementos: { informacoes_complementares: '', ...complementos } })
      const abrirRascunho = (complementos, extras = {}) =>
        abrirComServico({ [`GET ${NOTAS}9/`]: rascunho(complementos), ...extras }, '/fiscal/notas/9/editar')

      it('só o que a PRÓPRIA nota ajustou volta preenchido; o que veio do modelo ou do serviço volta em branco', async () => {
        abrirRascunho({
          ibs_cbs: { codigo_indicador_operacao: '050101', indicador_destinatario: 1, origens: { codigo_indicador_operacao: 'modelo', indicador_destinatario: 'modelo' } },
          ibs_cbs_modelo: { codigo_indicador_operacao: '050101', indicador_destinatario: 1 },
          ibs_cbs_nota: null,
        })

        const campo = await screen.findByLabelText('Ajustar o indicador da operação (IBS/CBS)')

        await waitFor(() => expect(screen.getByLabelText('O destinatário é o próprio tomador?')).toHaveValue(''))
        expect(campo).toHaveValue('')
        // As dicas dizem de onde vem o valor herdado: do modelo do rascunho.
        expect(screen.getByText(/Em branco: vale o do modelo \(050101\)/)).toBeInTheDocument()
        expect(screen.getByRole('option', { name: 'Herdar (do modelo: não)' })).toBeInTheDocument()
      })

      it('o ajuste de indicador e de destinatário da nota volta preenchido', async () => {
        abrirRascunho({
          ibs_cbs: { codigo_indicador_operacao: '050102', indicador_destinatario: 0, origens: { codigo_indicador_operacao: 'nota', indicador_destinatario: 'nota' } },
          ibs_cbs_nota: { codigo_indicador_operacao: '050102', indicador_destinatario: 0 },
          ibs_cbs_modelo: null,
        })

        const campo = await screen.findByLabelText('Ajustar o indicador da operação (IBS/CBS)')

        await waitFor(() => expect(campo).toHaveValue('050102'))
        expect(screen.getByLabelText('O destinatário é o próprio tomador?')).toHaveValue('0')
      })

      it('um ajuste antigo com "informar" é ignorado: não há mais o que desmarcar', async () => {
        abrirRascunho({ ibs_cbs: null, ibs_cbs_nota: { informar: false }, ibs_cbs_modelo: null })

        const campo = await screen.findByLabelText('Ajustar o indicador da operação (IBS/CBS)')

        expect(campo).toHaveValue('')
        expect(screen.queryByLabelText('Não informar o IBS/CBS nesta nota')).not.toBeInTheDocument()
      })

      it('o município da prestação da PRÓPRIA nota volta preenchido; o do modelo só aparece como padrão', async () => {
        const municipios = {
          'GET /api/cadastros/municipios/': (chamada) => ({
            status: 200,
            dados: chamada.url.includes('codigo=1721000')
              ? [{ codigo: '1721000', nome: 'Palmas', uf: 'TO' }]
              : [{ codigo: '2101400', nome: 'Balsas', uf: 'MA' }],
          }),
        }
        abrirRascunho(
          { ibs_cbs: null, ibs_cbs_nota: null, ibs_cbs_modelo: null, municipio_prestacao_nota: null, municipio_prestacao_modelo: '2101400' },
          municipios,
        )
        expect(await screen.findByText(/Em branco, vale o do modelo/)).toBeInTheDocument()
        expect(await screen.findByText('Balsas/MA')).toBeInTheDocument()
        cleanup()

        abrirRascunho(
          { ibs_cbs: null, ibs_cbs_nota: null, ibs_cbs_modelo: null, municipio_prestacao_nota: '1721000', municipio_prestacao_modelo: '2101400' },
          municipios,
        )
        expect(await screen.findByText(/Selecionado:/)).toHaveTextContent('Palmas/TO')
      })

      it('a conferência do rascunho informa qual é o rascunho (vale o que o modelo dele definia)', async () => {
        const { chamadas } = abrirRascunho({ ibs_cbs: null, ibs_cbs_nota: null, ibs_cbs_modelo: null })
        await screen.findByLabelText('Ajustar o indicador da operação (IBS/CBS)')

        fireEvent.click(await screen.findByRole('button', { name: 'Conferir a nota' }))
        await screen.findByRole('region', { name: 'Conferência da nota' })

        expect(chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo.rascunho).toBe(9)
      })
    })

    it('nota nova não informa rascunho na conferência', async () => {
      const { chamadas } = abrirComServico()

      await conferir()

      expect(chamadas.find((c) => c.caminho === `${NOTAS}previa/`).corpo.rascunho).toBeNull()
    })
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
