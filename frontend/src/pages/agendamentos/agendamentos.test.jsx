import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { limparEmpresaAtiva } from '../../api/empresaAtiva.js'
import { EMPRESA_A, respostaEu } from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'
import { ATRASO_DA_PREVIA } from './AgendamentoForm.jsx'
import { INTERVALO_DO_LOTE } from './Rascunhos.jsx'
import { dataPorExtenso, resumoDaRegra, resumoDoFim } from './regra.js'
import { formatarData } from '../../utils/formatar.js'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  vi.useRealTimers()
})

const EMISSOR = {
  ...EMPRESA_A,
  perfil: 'emissor',
  permissoes: ['nfse.consultar', 'nfse.emitir', 'agendamento.consultar', 'agendamento.editar', 'cadastro.consultar'],
}
const SO_CONSULTA = { ...EMPRESA_A, perfil: 'consulta', permissoes: ['nfse.consultar', 'agendamento.consultar'] }
const SEM_NADA = { ...EMPRESA_A, perfil: 'consulta', permissoes: ['cadastro.consultar'] }

const B = '/api/agendamentos'
const OPCOES = {
  frequencias: [
    { valor: 'unica', rotulo: 'Uma única vez' },
    { valor: 'diaria', rotulo: 'Diária' },
    { valor: 'semanal', rotulo: 'Semanal' },
    { valor: 'mensal', rotulo: 'Mensal' },
    { valor: 'anual', rotulo: 'Anual' },
  ],
  competencias: [],
  variaveis_do_texto: { competencia: 'Competência (MM/AAAA)', mes: 'Mês', ano: 'Ano' },
  modelos: [{ id: 1, nome: 'Mensalidade' }],
  responsaveis: [{ id: 7, email: 'ana@example.com', nome: 'Ana' }],
  tolerancia_horas: 12,
}
const MODELO = {
  id: 1, nome: 'Mensalidade', ativo: true, tomador: 4, tomador_nome: 'TOMADOR FICTICIO LTDA', servico: 3,
  servico_nome: 'Consultoria', valores: { servico: '1500.00' }, informacoes_complementares: 'Referente a {competencia}.',
  percentual_total_tributos_simples: null, competencia_padrao: 'mes_da_execucao',
  email_envio_automatico: null, email_avisar_cancelamento: null, email_anexar_pdf: null, email_anexar_xml: null,
  email_assunto_modelo: '', email_corpo_modelo: '', email_copias_fixas: null, agendamentos_em_uso: 2, problemas: {},
  atualizado_em: '2026-11-01T12:00:00Z',
} // prettier-ignore
const AGENDAMENTO = {
  id: 5, nome: 'Cobrança mensal', modelo: 1, modelo_nome: 'Mensalidade', responsavel: 7, responsavel_email: 'ana@example.com',
  frequencia: 'mensal', frequencia_rotulo: 'Mensal', intervalo: 1, dias_semana: [], dia_do_mes: 5, mes: null, hora: '08:00',
  data_inicio: '2026-11-01', data_fim: null, max_execucoes: null, situacao: 'ativo', situacao_rotulo: 'Ativo',
  motivo_situacao: '', execucoes_realizadas: 2, proxima_execucao: '2026-12-05T11:00:00Z', proximas: [],
} // prettier-ignore
const PREVIA = {
  datas: [
    { instante: '2026-12-05T11:00:00Z', data: '2026-12-05', hora: '08:00', dia_da_semana: 5 },
    { instante: '2027-01-05T11:00:00Z', data: '2027-01-05', hora: '08:00', dia_da_semana: 1 },
  ],
  termina: false,
}
const PESSOAS = [{ id: 4, nome: 'TOMADOR FICTICIO LTDA', documento_formatado: '11.222.333/0001-81' }]
const SERVICOS = [
  { id: 3, nome: 'Consultoria', codigo_tributacao_nacional: '170101', vigencia_inicio: '2026-01-01', vigencia_fim: null },
]

const abrir = (rota, extras = {}, empresa = EMISSOR) =>
  montarApp({
    rota,
    rotasApi: rotasAutenticado({
      eu: respostaEu({ empresas: [empresa] }),
      extras: {
        [`GET ${B}/opcoes/`]: { status: 200, dados: OPCOES },
        'GET /api/cadastros/pessoas/': { status: 200, dados: PESSOAS },
        'GET /api/cadastros/servicos/': { status: 200, dados: SERVICOS },
        ...extras,
      },
    }),
  })

const corpoDe = (chamadas, metodo, caminho) => chamadas.find((c) => c.metodo === metodo && c.caminho === caminho)?.corpo

// ---------------------------------------------------------------------------------------------
// regra.js
// ---------------------------------------------------------------------------------------------

describe('Textos da regra', () => {
  it('resume cada frequência em linguagem simples', () => {
    expect(resumoDaRegra({ frequencia: 'unica', hora: '08:00' })).toBe('Uma única vez, às 08:00')
    expect(resumoDaRegra({ frequencia: 'diaria', hora: '08:00', intervalo: 1 })).toBe('Todo dia às 08:00')
    expect(resumoDaRegra({ frequencia: 'diaria', hora: '08:00', intervalo: 3 })).toBe('A cada 3 dias às 08:00')
    expect(resumoDaRegra({ frequencia: 'semanal', hora: '09:30', intervalo: 2, dias_semana: [0, 3] })).toBe(
      'A cada 2 semanas (seg, qui) às 09:30',
    )
    expect(resumoDaRegra({ frequencia: 'mensal', hora: '08:00', intervalo: 1, dia_do_mes: 31 })).toBe('Todo mês, dia 31, às 08:00')
    expect(resumoDaRegra({ frequencia: 'mensal', hora: '08:00', intervalo: 3, dia_do_mes: 10 })).toBe('A cada 3 meses, dia 10, às 08:00')
    expect(resumoDaRegra({ frequencia: 'anual', hora: '08:00', intervalo: 1, dia_do_mes: 29, mes: 2 })).toBe(
      'Todo ano, 29 de fevereiro, às 08:00',
    )
  })

  it('resume o fim da série', () => {
    expect(resumoDoFim({ frequencia: 'mensal', data_fim: '2026-12-31' }, formatarData)).toBe('Até 31/12/2026')
    expect(resumoDoFim({ frequencia: 'mensal', max_execucoes: 12, execucoes_realizadas: 3 }, formatarData)).toBe(
      'Termina após 12 execuções (3 feitas)',
    )
    expect(resumoDoFim({ frequencia: 'mensal' }, formatarData)).toBe('Sem data de fim')
    expect(resumoDoFim({ frequencia: 'unica' }, formatarData)).toBe('')
  })

  it('escreve a data com o dia da semana de Brasília', () => {
    expect(dataPorExtenso({ data: '2026-11-05', hora: '08:00' }, formatarData)).toBe('qui, 05/11/2026 às 08:00')
    expect(dataPorExtenso({ data: '2026-12-27', hora: '23:30' }, formatarData)).toBe('dom, 27/12/2026 às 23:30')
  })
})

// ---------------------------------------------------------------------------------------------
// Modelos
// ---------------------------------------------------------------------------------------------

describe('Modelos de NFS-e', () => {
  it('lista os modelos com o aviso do que impede de gerar rascunho hoje', async () => {
    abrir('/agendamentos/modelos', {
      [`GET ${B}/modelos/`]: {
        status: 200,
        dados: [MODELO, { ...MODELO, id: 2, nome: 'Antigo', ativo: false, problemas: { servico: 'O serviço não tem versão vigente em 11/2026.' } }],
      },
    })

    const lista = await screen.findByRole('list', { name: 'Modelos' })
    const [primeiro, segundo] = within(lista).getAllByRole('listitem')
    expect(within(primeiro).getByText('Mensalidade')).toBeInTheDocument()
    expect(within(primeiro).getByText('2 agendamento(s) usando')).toBeInTheDocument()
    expect(within(primeiro).getByText(/TOMADOR FICTICIO LTDA · Consultoria · R\$\s*1\.500,00/)).toBeInTheDocument()
    expect(within(segundo).getByText('Inativo')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Novo modelo' })).toBeInTheDocument()
  })

  it('mostra o problema do modelo ativo que não geraria rascunho', async () => {
    abrir('/agendamentos/modelos', {
      [`GET ${B}/modelos/`]: {
        status: 200,
        dados: [{ ...MODELO, problemas: { servico: 'O serviço “Consultoria” não tem versão vigente em 11/2026.' } }],
      },
    })

    expect(await screen.findByText(/não conseguiria gerar um rascunho hoje: O serviço “Consultoria” não tem versão vigente/)).toBeInTheDocument()
  })

  it('quem só consulta vê os modelos, mas não cria nem gera rascunho', async () => {
    abrir('/agendamentos/modelos', { [`GET ${B}/modelos/`]: { status: 200, dados: [MODELO] } }, SO_CONSULTA)

    expect(await screen.findByText('Mensalidade')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Novo modelo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Gerar rascunho agora' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver' })).toBeInTheDocument()
  })

  it('gera um rascunho agora, depois de confirmar, e leva à lista de rascunhos', async () => {
    const { chamadas } = abrir('/agendamentos/modelos', {
      [`GET ${B}/modelos/`]: { status: 200, dados: [MODELO] },
      [`POST ${B}/modelos/1/gerar-rascunho/`]: { status: 201, dados: { id: 40 } },
      [`GET ${B}/rascunhos/`]: { status: 200, dados: { total: 0, itens: [] } },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Gerar rascunho agora' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/Nada é enviado à Sefin/)).toBeInTheDocument()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Gerar rascunho' }))

    expect(await screen.findByRole('heading', { name: 'Rascunhos de NFS-e' })).toBeInTheDocument()
    expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho === `${B}/modelos/1/gerar-rascunho/`)).toBe(true)
  })

  it('mostra por que o modelo não gerou o rascunho', async () => {
    abrir('/agendamentos/modelos', {
      [`GET ${B}/modelos/`]: { status: 200, dados: [MODELO] },
      [`POST ${B}/modelos/1/gerar-rascunho/`]: {
        status: 400,
        dados: { codigo: 'modelo_invalido', detalhe: 'x', erros: { servico: 'O serviço não tem versão vigente em 11/2026.' } },
      },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Gerar rascunho agora' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Gerar rascunho' }))

    expect(await screen.findByText('O serviço não tem versão vigente em 11/2026.')).toBeInTheDocument()
  })
})

describe('Formulário do modelo', () => {
  const escolher = async (rotulo, nome) => {
    fireEvent.click(await screen.findByRole('combobox', { name: rotulo }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: new RegExp(nome) }))
  }

  it('cria um modelo com tomador, serviço, valor e texto', async () => {
    const { chamadas } = abrir('/agendamentos/modelos/novo', {
      [`POST ${B}/modelos/`]: { status: 201, dados: MODELO },
      [`GET ${B}/modelos/`]: { status: 200, dados: [MODELO] },
    })

    fireEvent.change(await screen.findByLabelText('Nome do modelo'), { target: { value: 'Mensalidade' } })
    await escolher('Tomador', 'TOMADOR FICTICIO')
    await escolher('Serviço', 'Consultoria')
    fireEvent.change(screen.getByLabelText('Valor do serviço (R$)'), { target: { value: '1500.00' } })
    fireEvent.change(screen.getByLabelText('Informações complementares na nota'), { target: { value: 'Mês {competencia}' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar modelo' }))

    expect(await screen.findByRole('heading', { name: 'Modelos de NFS-e' })).toBeInTheDocument()
    const corpo = corpoDe(chamadas, 'POST', `${B}/modelos/`)
    expect(corpo).toMatchObject({
      nome: 'Mensalidade', ativo: true, tomador: 4, servico: 3, competencia_padrao: 'mes_da_execucao',
      informacoes_complementares: 'Mês {competencia}',
      valores: { servico: '1500.00', desconto_incondicionado: null, deducao_percentual: null },
      email_envio_automatico: null, email_anexar_pdf: null, email_copias_fixas: null,
    }) // prettier-ignore
  })

  it('só envia o que o modelo muda no e-mail: o resto é herdado da empresa', async () => {
    const { chamadas } = abrir('/agendamentos/modelos/1', {
      [`GET ${B}/modelos/1/`]: { status: 200, dados: MODELO },
      [`PATCH ${B}/modelos/1/`]: { status: 200, dados: MODELO },
      [`GET ${B}/modelos/`]: { status: 200, dados: [] },
    })
    await screen.findByLabelText('Nome do modelo')

    fireEvent.change(screen.getByLabelText('Anexar o PDF'), { target: { value: 'nao' } })
    fireEvent.change(screen.getByLabelText('Enviar automaticamente ao autorizar'), { target: { value: 'sim' } })
    fireEvent.click(screen.getByLabelText('Usar cópias fixas próprias'))
    fireEvent.change(screen.getByLabelText('Cópias fixas deste modelo'), { target: { value: 'a@x.test, b@y.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar modelo' }))

    await waitFor(() => expect(corpoDe(chamadas, 'PATCH', `${B}/modelos/1/`)).toBeDefined())
    expect(corpoDe(chamadas, 'PATCH', `${B}/modelos/1/`)).toMatchObject({
      email_anexar_pdf: false, email_anexar_xml: null, email_envio_automatico: true,
      email_avisar_cancelamento: null, email_copias_fixas: ['a@x.test', 'b@y.test'],
    }) // prettier-ignore
  })

  it('mostra os erros da API ao lado dos campos', async () => {
    abrir('/agendamentos/modelos/novo', {
      [`POST ${B}/modelos/`]: {
        status: 400,
        dados: {
          nome: 'Já existe um modelo com este nome.',
          'valores.servico': 'Informe o valor do serviço.',
          informacoes_complementares: 'A variável {xpto} não existe.',
        },
      },
    })

    fireEvent.change(await screen.findByLabelText('Nome do modelo'), { target: { value: 'Mensalidade' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar modelo' }))

    expect(await screen.findByText('Já existe um modelo com este nome.')).toBeInTheDocument()
    expect(screen.getByText('Informe o valor do serviço.')).toBeInTheDocument()
    expect(screen.getByText('A variável {xpto} não existe.')).toBeInTheDocument()
  })

  it('confere como o rascunho ficaria hoje (só com o modelo salvo)', async () => {
    abrir('/agendamentos/modelos/1', {
      [`GET ${B}/modelos/1/`]: { status: 200, dados: MODELO },
      [`POST ${B}/modelos/1/previa/`]: {
        status: 200,
        dados: {
          ok: true, competencia: '2026-11-01', tomador: 'TOMADOR FICTICIO LTDA',
          totais: { valor_servico: '1500.00', valor_iss: '30.00', valor_liquido: '1470.00' },
          avisos: [], informacoes_complementares: 'Referente a 11/2026.',
        },
      },
    }) // prettier-ignore
    fireEvent.change(await screen.findByLabelText('Nome do modelo'), { target: { value: 'Mensalidade 2' } })
    expect(screen.getByRole('button', { name: 'Conferir como ficaria hoje' })).toBeDisabled()
    expect(screen.getByText(/Salve o modelo antes de conferir/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nome do modelo'), { target: { value: 'Mensalidade' } })

    fireEvent.click(screen.getByRole('button', { name: 'Conferir como ficaria hoje' }))

    const previa = await screen.findByRole('region', { name: 'Como ficaria o rascunho' })
    expect(within(previa).getByText('01/11/2026')).toBeInTheDocument()
    expect(within(previa).getByText(/Referente a 11\/2026\./)).toBeInTheDocument()
  })

  it('mostra o motivo quando o modelo não geraria rascunho', async () => {
    abrir('/agendamentos/modelos/1', {
      [`GET ${B}/modelos/1/`]: { status: 200, dados: MODELO },
      [`POST ${B}/modelos/1/previa/`]: { status: 200, dados: { ok: false, erros: { servico: 'Sem versão vigente.' } } },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Conferir como ficaria hoje' }))

    expect(await screen.findByText(/falharia: Sem versão vigente\./)).toBeInTheDocument()
  })

  it('insere a variável escolhida no texto da nota', async () => {
    abrir('/agendamentos/modelos/novo')
    const texto = await screen.findByLabelText('Informações complementares na nota')

    fireEvent.click(await screen.findByRole('button', { name: '{ano}' }))

    expect(texto.value).toContain('{ano}')
  })

  it('quem só consulta vê o modelo bloqueado', async () => {
    abrir('/agendamentos/modelos/1', { [`GET ${B}/modelos/1/`]: { status: 200, dados: MODELO } }, SO_CONSULTA)

    expect(await screen.findByLabelText('Nome do modelo')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Salvar modelo' })).not.toBeInTheDocument()
    expect(screen.getByText('Você pode consultar o modelo, mas não alterá-lo.')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Agendamentos
// ---------------------------------------------------------------------------------------------

describe('Lista de agendamentos', () => {
  const LISTA = [
    { ...AGENDAMENTO, proximas: PREVIA.datas },
    {
      ...AGENDAMENTO, id: 6, nome: 'Anuidade', situacao: 'suspenso', situacao_rotulo: 'Suspenso', proxima_execucao: null,
      motivo_situacao: 'O responsável (ana@example.com) não tem mais vínculo ativo com a empresa.',
    },
  ] // prettier-ignore

  it('resume a regra, a próxima execução e destaca os suspensos com o motivo', async () => {
    abrir('/agendamentos', { [`GET ${B}/agendamentos/`]: { status: 200, dados: LISTA } })

    const lista = await screen.findByRole('list', { name: 'Agendamentos' })
    const [ativo, suspenso] = within(lista).getAllByRole('listitem')
    expect(within(ativo).getByText(/Todo mês, dia 5, às 08:00/)).toBeInTheDocument()
    expect(within(ativo).getByText(/Responsável: ana@example.com/)).toBeInTheDocument()
    expect(within(suspenso).getByText(/não tem mais vínculo ativo/)).toBeInTheDocument()
    expect(within(suspenso).getByText('Próxima execução: —', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('1 agendamento(s) suspenso(s): não estão gerando rascunhos.')).toBeInTheDocument()
  })

  it('suspende depois de explicar a regra de reativação', async () => {
    const { chamadas } = abrir('/agendamentos', {
      [`GET ${B}/agendamentos/`]: { status: 200, dados: LISTA },
      [`POST ${B}/agendamentos/5/suspender/`]: { status: 200, dados: LISTA[0] },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Suspender' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText(/não são geradas depois/)).toBeInTheDocument()
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Suspender' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho === `${B}/agendamentos/5/suspender/`)).toBe(true))
  })

  it('reativa e mostra o erro quando o responsável não pode mais', async () => {
    abrir('/agendamentos', {
      [`GET ${B}/agendamentos/`]: { status: 200, dados: LISTA },
      [`POST ${B}/agendamentos/6/reativar/`]: {
        status: 400,
        dados: { responsavel: 'O responsável (ana@example.com) não tem mais vínculo ativo com a empresa. Escolha outro responsável.' },
      },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Reativar' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Reativar' }))

    expect(await screen.findByText(/Escolha outro responsável\./)).toBeInTheDocument()
  })

  it('quem só consulta não suspende nem reativa nem cria', async () => {
    abrir('/agendamentos', { [`GET ${B}/agendamentos/`]: { status: 200, dados: LISTA } }, SO_CONSULTA)

    await screen.findByRole('list', { name: 'Agendamentos' })
    expect(screen.queryByRole('button', { name: 'Suspender' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reativar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Novo agendamento' })).not.toBeInTheDocument()
  })
})

describe('Formulário do agendamento', () => {
  const rotasDoForm = (extras = {}) => ({
    [`POST ${B}/agendamentos/previa-datas/`]: { status: 200, dados: PREVIA },
    [`GET ${B}/agendamentos/`]: { status: 200, dados: [] },
    ...extras,
  })

  it('mostra as próximas datas e refaz ao mudar a regra, enviando só os campos da frequência', async () => {
    const { chamadas } = abrir('/agendamentos/novo', rotasDoForm())

    const previa = await screen.findByRole('region', { name: 'Próximas datas' })
    expect(within(previa).getAllByRole('listitem')).toHaveLength(2)
    expect(within(previa).getByText('sáb, 05/12/2026 às 08:00')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Repete'), { target: { value: 'semanal' } })
    fireEvent.click(screen.getByLabelText('seg'))
    fireEvent.click(screen.getByLabelText('qui'))

    await waitFor(() => {
      const ultima = chamadas.filter((c) => c.caminho === `${B}/agendamentos/previa-datas/`).at(-1).corpo
      expect(ultima).toMatchObject({ frequencia: 'semanal', dias_semana: [0, 3], intervalo: 1, quantidade: 6 })
      expect(ultima).not.toHaveProperty('dia_do_mes')
      expect(ultima).not.toHaveProperty('mes')
    }, { timeout: 3000 }) // prettier-ignore
    expect(ATRASO_DA_PREVIA).toBeLessThan(1000)
  })

  it('a regra inválida aparece na prévia, em linguagem simples', async () => {
    abrir(
      '/agendamentos/novo',
      rotasDoForm({
        [`POST ${B}/agendamentos/previa-datas/`]: { status: 400, dados: { dias_semana: 'Escolha pelo menos um dia da semana.' } },
      }),
    )

    expect(await screen.findByText('Escolha pelo menos um dia da semana.')).toBeInTheDocument()
  })

  it('cria um agendamento mensal e volta à lista', async () => {
    const { chamadas } = abrir('/agendamentos/novo', rotasDoForm({ [`POST ${B}/agendamentos/`]: { status: 201, dados: AGENDAMENTO } }))

    fireEvent.change(await screen.findByLabelText('Nome do agendamento'), { target: { value: 'Cobrança mensal' } })
    fireEvent.change(screen.getByLabelText('Modelo de NFS-e'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: '7' } })
    fireEvent.change(screen.getByLabelText('Dia do mês'), { target: { value: '31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar agendamento' }))

    expect(await screen.findByRole('heading', { name: 'Agendamentos' })).toBeInTheDocument()
    const corpo = corpoDe(chamadas, 'POST', `${B}/agendamentos/`)
    expect(corpo).toMatchObject({
      nome: 'Cobrança mensal', modelo: 1, responsavel: 7, frequencia: 'mensal', intervalo: 1, dia_do_mes: 31,
      hora: '08:00', data_fim: null, max_execucoes: null,
    }) // prettier-ignore
    expect(corpo.data_inicio).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(corpo).not.toHaveProperty('dias_semana')
  })

  it('data de fim e número de execuções são excludentes: só o escolhido vai', async () => {
    const { chamadas } = abrir('/agendamentos/novo', rotasDoForm({ [`POST ${B}/agendamentos/`]: { status: 201, dados: AGENDAMENTO } }))
    fireEvent.change(await screen.findByLabelText('Nome do agendamento'), { target: { value: 'Limitado' } })
    fireEvent.change(screen.getByLabelText('Modelo de NFS-e'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Responsável'), { target: { value: '7' } })

    fireEvent.click(screen.getByLabelText('Em uma data'))
    fireEvent.change(screen.getByLabelText('Data de fim (inclusive)'), { target: { value: '2027-12-31' } })
    fireEvent.click(screen.getByLabelText('Após N execuções'))
    expect(screen.queryByLabelText('Data de fim (inclusive)')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Número de execuções'), { target: { value: '12' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar agendamento' }))

    await waitFor(() => expect(corpoDe(chamadas, 'POST', `${B}/agendamentos/`)).toBeDefined())
    expect(corpoDe(chamadas, 'POST', `${B}/agendamentos/`)).toMatchObject({ data_fim: null, max_execucoes: 12 })
  })

  it('mostra os erros do servidor ao lado dos campos', async () => {
    abrir(
      '/agendamentos/novo',
      rotasDoForm({
        [`POST ${B}/agendamentos/`]: {
          status: 400,
          dados: { responsavel: 'O responsável (x@y.test) não tem mais permissão para emitir notas.', nome: 'Já existe um agendamento com este nome.' },
        },
      }),
    )
    fireEvent.change(await screen.findByLabelText('Nome do agendamento'), { target: { value: 'Repetido' } })

    fireEvent.click(screen.getByRole('button', { name: 'Salvar agendamento' }))

    expect(await screen.findByText('Já existe um agendamento com este nome.')).toBeInTheDocument()
    expect(screen.getByText(/não tem mais permissão para emitir notas/)).toBeInTheDocument()
  })

  it('edita um agendamento existente (PATCH) e leva o que já foi executado à prévia', async () => {
    const { chamadas } = abrir(
      '/agendamentos/5',
      rotasDoForm({
        [`GET ${B}/agendamentos/5/`]: { status: 200, dados: AGENDAMENTO },
        [`PATCH ${B}/agendamentos/5/`]: { status: 200, dados: AGENDAMENTO },
      }),
    )

    const campo = await screen.findByLabelText('Dia do mês')
    expect(campo).toHaveValue(5)
    fireEvent.change(campo, { target: { value: '20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar agendamento' }))

    await waitFor(() => expect(corpoDe(chamadas, 'PATCH', `${B}/agendamentos/5/`)).toBeDefined())
    expect(corpoDe(chamadas, 'PATCH', `${B}/agendamentos/5/`)).toMatchObject({ dia_do_mes: 20, modelo: 1, responsavel: 7 })
    const previa = chamadas.filter((c) => c.caminho === `${B}/agendamentos/previa-datas/`)
    expect(previa.every((c) => c.corpo.agendamento === 5)).toBe(true)
  })

  it('anual pede o mês e explica o 29 de fevereiro', async () => {
    abrir('/agendamentos/novo', rotasDoForm())
    await screen.findByRole('option', { name: 'Anual' }) // as opções da API já chegaram

    fireEvent.change(screen.getByLabelText('Repete'), { target: { value: 'anual' } })

    expect(screen.getByLabelText('Mês')).toBeInTheDocument()
    expect(screen.getByText(/29\/02 em ano comum vale 28\/02/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/A cada quantos/)).not.toBeInTheDocument()
  })

  it('quem só consulta vê o agendamento bloqueado', async () => {
    abrir('/agendamentos/5', rotasDoForm({ [`GET ${B}/agendamentos/5/`]: { status: 200, dados: AGENDAMENTO } }), SO_CONSULTA)

    expect(await screen.findByLabelText('Nome do agendamento')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Salvar agendamento' })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Rascunhos
// ---------------------------------------------------------------------------------------------

describe('Rascunhos', () => {
  const ITENS = {
    total: 3,
    itens: [
      { id: 40, tomador_nome: 'TOMADOR UM', valor_servico: '1500.00', competencia: '2026-11-01', criado_em: '2026-11-05T11:00:00Z', criado_por_email: 'ana@example.com', origem: { tipo: 'agendamento', nome: 'Cobrança mensal', agendamento: 5, data_execucao: '2026-11-05' } },
      { id: 41, tomador_nome: 'TOMADOR DOIS', valor_servico: '900.00', competencia: '2026-11-01', criado_em: '2026-11-05T11:00:00Z', criado_por_email: '', origem: { tipo: 'modelo', nome: 'Mensalidade', data_execucao: null } },
      { id: 42, tomador_nome: 'TOMADOR TRÊS', valor_servico: '10.00', competencia: '2026-10-01', criado_em: '2026-11-05T11:00:00Z', criado_por_email: '', origem: { tipo: 'manual', nome: '', data_execucao: null } },
    ],
  } // prettier-ignore

  const aprovarSelecionados = async () => {
    fireEvent.click(await screen.findByLabelText('Selecionar todos'))
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar selecionados (3)' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Aprovar e emitir' }))
  }

  it('lista os rascunhos com a origem de cada um', async () => {
    abrir('/agendamentos/rascunhos', { [`GET ${B}/rascunhos/`]: { status: 200, dados: ITENS } })

    const lista = await screen.findByRole('list', { name: 'Rascunhos' })
    const [agendado, modelo, manual] = within(lista).getAllByRole('listitem')
    expect(within(agendado).getByText(/Agendamento “Cobrança mensal” \(05\/11\/2026\)/)).toBeInTheDocument()
    expect(within(modelo).getByText(/Modelo “Mensalidade”/)).toBeInTheDocument()
    expect(within(manual).getByText(/Criado à mão/)).toBeInTheDocument()
    expect(within(agendado).getByRole('link', { name: 'Editar' })).toHaveAttribute('href', '/fiscal/notas/40/editar')
  })

  it('aprova em lote, mostra o resultado por item e acompanha até a Sefin responder', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let consultas = 0
    const { chamadas } = abrir('/agendamentos/rascunhos', {
      [`GET ${B}/rascunhos/`]: { status: 200, dados: ITENS },
      [`POST ${B}/rascunhos/aprovar/`]: {
        status: 200,
        dados: {
          aceitas: 2, recusadas: 1,
          resultados: [
            { id: 40, ok: true, situacao: 'enviando', mensagem: 'Enviada para emissão.' },
            { id: 41, ok: true, situacao: 'enviando', mensagem: 'Enviada para emissão.' },
            { id: 42, ok: false, codigo: 'empresa_nao_pronta', mensagem: 'Falta o certificado digital A1.' },
          ],
        },
      },
      [`GET ${B}/rascunhos/situacao/`]: () => {
        consultas += 1
        const fim = consultas >= 2
        return {
          status: 200,
          dados: [
            { id: 40, situacao: fim ? 'autorizada' : 'enviando', situacao_rotulo: fim ? 'Autorizada' : 'Enviando à Sefin', numero_nfse: fim ? '15' : '', mensagem: '' },
            { id: 41, situacao: fim ? 'rejeitada' : 'enviando', situacao_rotulo: fim ? 'Rejeitada' : 'Enviando à Sefin', numero_nfse: '', mensagem: 'CNPJ inválido.' },
          ],
        }
      },
    }) // prettier-ignore

    await aprovarSelecionados()

    const resultado = await screen.findByRole('region', { name: 'Resultado da aprovação' })
    expect(within(resultado).getByText(/2 enviado\(s\) para emissão · 1 recusado\(s\)/)).toBeInTheDocument()
    expect(within(resultado).getByText('Falta o certificado digital A1.')).toBeInTheDocument()
    expect(corpoDe(chamadas, 'POST', `${B}/rascunhos/aprovar/`)).toEqual({ ids: [40, 41, 42] })
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DO_LOTE + 100))
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DO_LOTE + 100))
    expect(await within(resultado).findByText('Autorizada')).toBeInTheDocument()
    expect(within(resultado).getByText('NFS-e nº 15')).toBeInTheDocument()
    expect(within(resultado).getByText('Rejeitada')).toBeInTheDocument()
    expect(within(resultado).getByRole('link', { name: 'Ver nota' })).toHaveAttribute('href', '/fiscal/notas/41')
  })

  it('aprova um único rascunho pelo botão da linha', async () => {
    const { chamadas } = abrir('/agendamentos/rascunhos', {
      [`GET ${B}/rascunhos/`]: { status: 200, dados: ITENS },
      [`POST ${B}/rascunhos/aprovar/`]: { status: 200, dados: { aceitas: 1, recusadas: 0, resultados: [{ id: 41, ok: true, situacao: 'enviando', mensagem: 'x' }] } },
      [`GET ${B}/rascunhos/situacao/`]: { status: 200, dados: [] },
    })

    const linha = (await screen.findAllByRole('listitem'))[1]
    fireEvent.click(within(linha).getByRole('button', { name: 'Aprovar' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Aprovar este rascunho?' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Aprovar e emitir' }))

    await waitFor(() => expect(corpoDe(chamadas, 'POST', `${B}/rascunhos/aprovar/`)).toEqual({ ids: [41] }))
  })

  it('não aprova sem a confirmação', async () => {
    const { chamadas } = abrir('/agendamentos/rascunhos', { [`GET ${B}/rascunhos/`]: { status: 200, dados: ITENS } })

    fireEvent.click(await screen.findByLabelText('Selecionar todos'))
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar selecionados (3)' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Voltar' }))

    expect(chamadas.some((c) => c.caminho === `${B}/rascunhos/aprovar/`)).toBe(false)
  })

  it('o botão de aprovar só vale com rascunho selecionado', async () => {
    abrir('/agendamentos/rascunhos', { [`GET ${B}/rascunhos/`]: { status: 200, dados: ITENS } })

    expect(await screen.findByRole('button', { name: 'Aprovar selecionados (0)' })).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Selecionar rascunho 41'))
    expect(screen.getByRole('button', { name: 'Aprovar selecionados (1)' })).toBeEnabled()
  })

  it('descarta com motivo: o servidor exige o motivo e depois a lista é atualizada', async () => {
    let descartado = false
    const { chamadas } = abrir('/agendamentos/rascunhos', {
      [`GET ${B}/rascunhos/`]: () => ({
        status: 200,
        dados: descartado ? { total: 2, itens: ITENS.itens.slice(1) } : ITENS,
      }),
      [`POST ${B}/rascunhos/40/descartar/`]: (chamada) => {
        if (!chamada.corpo.motivo.trim()) return { status: 400, dados: { motivo: 'Explique por que o rascunho será descartado.' } }
        descartado = true
        return { status: 200, dados: { id: 40, situacao: 'descartada' } }
      },
    })

    const linha = (await screen.findAllByRole('listitem'))[0]
    fireEvent.click(within(linha).getByRole('button', { name: 'Descartar' }))
    const formulario = await screen.findByRole('form', { name: 'Descartar rascunho' })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Descartar rascunho' }))
    expect(await within(formulario).findByText('Explique por que o rascunho será descartado.')).toBeInTheDocument()
    fireEvent.change(within(formulario).getByLabelText('Por que este rascunho será descartado?'), { target: { value: 'Contrato encerrado' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Descartar rascunho' }))

    await waitFor(() => expect(screen.queryByText('TOMADOR UM')).not.toBeInTheDocument())
    expect(chamadas.filter((c) => c.caminho === `${B}/rascunhos/40/descartar/`).at(-1).corpo).toEqual({ motivo: 'Contrato encerrado' })
  })

  it('sem nfse.emitir, vê os rascunhos mas não aprova, edita nem descarta', async () => {
    abrir('/agendamentos/rascunhos', { [`GET ${B}/rascunhos/`]: { status: 200, dados: ITENS } }, SO_CONSULTA)

    await screen.findByRole('list', { name: 'Rascunhos' })
    expect(screen.queryByLabelText('Selecionar todos')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aprovar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Descartar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Editar' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Abrir' })).toHaveLength(3)
  })

  it('avisa quando não há rascunho esperando', async () => {
    abrir('/agendamentos/rascunhos', { [`GET ${B}/rascunhos/`]: { status: 200, dados: { total: 0, itens: [] } } })

    expect(await screen.findByText('Nenhum rascunho esperando decisão.')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Histórico e menu
// ---------------------------------------------------------------------------------------------

describe('Histórico de execuções', () => {
  const EXECUCOES = [
    { id: 1, agendamento: 5, agendamento_nome: 'Cobrança mensal', data_execucao: '2026-11-05', situacao: 'gerada', situacao_rotulo: 'Rascunho gerado', erro: '', nfse: 40, nfse_situacao: 'rascunho', concluido_em: '2026-11-05T11:01:00Z' },
    { id: 2, agendamento: 5, agendamento_nome: 'Cobrança mensal', data_execucao: '2026-10-05', situacao: 'falhou', situacao_rotulo: 'Falhou', erro: 'O serviço “Consultoria” não tem versão vigente em 10/2026.', nfse: null, nfse_situacao: null, concluido_em: '2026-10-05T11:01:00Z' },
  ] // prettier-ignore

  it('mostra o que o dispatcher fez em cada data, com o motivo das falhas', async () => {
    abrir('/agendamentos/historico', {
      [`GET ${B}/execucoes/`]: { status: 200, dados: EXECUCOES },
      [`GET ${B}/agendamentos/`]: { status: 200, dados: [AGENDAMENTO] },
    })

    const lista = await screen.findByRole('list', { name: 'Execuções' })
    const [gerada, falha] = within(lista).getAllByRole('listitem')
    expect(within(gerada).getByText('Rascunho gerado')).toBeInTheDocument()
    expect(within(gerada).getByRole('link', { name: 'Abrir o rascunho' })).toHaveAttribute('href', '/fiscal/notas/40')
    expect(within(falha).getByText('Falhou')).toBeInTheDocument()
    expect(within(falha).getByText(/não tem versão vigente em 10\/2026/)).toBeInTheDocument()
  })

  it('filtra por agendamento e por situação (e refaz a consulta)', async () => {
    const { chamadas } = abrir('/agendamentos/historico?agendamento=5', {
      [`GET ${B}/execucoes/`]: { status: 200, dados: EXECUCOES },
      [`GET ${B}/agendamentos/`]: { status: 200, dados: [AGENDAMENTO] },
    })
    await screen.findByRole('list', { name: 'Execuções' })
    expect(chamadas.find((c) => c.caminho === `${B}/execucoes/`).url).toContain('agendamento=5')

    fireEvent.change(screen.getByLabelText('Situação'), { target: { value: 'falhou' } })

    await waitFor(() => expect(chamadas.some((c) => c.url.includes('situacao=falhou'))).toBe(true))
  })
})

describe('Menu de agendamentos', () => {
  const extras = { [`GET ${B}/rascunhos/`]: { status: 200, dados: { total: 0, itens: [] } } }

  it('mostra todas as entradas a quem tem as permissões', async () => {
    abrir('/', extras)

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    expect(within(menu).getByRole('link', { name: 'Rascunhos' })).toHaveAttribute('href', '/agendamentos/rascunhos')
    expect(within(menu).getByRole('link', { name: 'Agendamentos' })).toHaveAttribute('href', '/agendamentos')
    expect(within(menu).getByRole('link', { name: 'Modelos de NFS-e' })).toHaveAttribute('href', '/agendamentos/modelos')
    expect(within(menu).getByRole('link', { name: 'Histórico de execuções' })).toHaveAttribute('href', '/agendamentos/historico')
  })

  it('não mostra nada a quem não tem permissão', async () => {
    abrir('/', extras, SEM_NADA)

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    expect(within(menu).queryByRole('link', { name: 'Rascunhos' })).not.toBeInTheDocument()
    expect(within(menu).queryByRole('link', { name: 'Modelos de NFS-e' })).not.toBeInTheDocument()
  })
})
