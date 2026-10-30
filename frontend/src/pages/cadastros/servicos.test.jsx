import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { limparEmpresaAtiva } from '../../api/empresaAtiva.js'
import { EMPRESA_ADMIN, EMPRESA_SO_CONSULTA, respostaEu } from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
})

const SERVICOS = '/api/cadastros/servicos/'
const CONSULTORIA = {
  id: 3, nome: 'Consultoria agrícola', descricao: 'Consultoria.', codigo_tributacao_nacional: '170101',
  codigo_tributacao_municipal: '001', nbs: '', cst_ibs_cbs: '', c_class_trib: '', aliquota_iss: '3.00',
  iss_retido: false, retencao_irrf: null, retencao_csll: null, retencao_pis: null, retencao_cofins: null,
  retencao_inss: null, vigencia_inicio: '2026-01-01', vigencia_fim: '2026-06-30', ativo: true,
}  // fmt: skip

const abrir = (extras = {}, empresas = [EMPRESA_ADMIN]) =>
  montarApp({
    rota: '/cadastros/servicos',
    rotasApi: rotasAutenticado({
      eu: respostaEu({ empresas }),
      extras: { [`GET ${SERVICOS}`]: { status: 200, dados: [CONSULTORIA] }, ...extras },
    }),
  })
const digitar = (rotulo, valor) => fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } })

describe('Serviços', () => {
  it('lista os serviços com código, ISS e a vigência em formato brasileiro', async () => {
    abrir()

    const tabela = await screen.findByRole('table', { name: 'Serviços cadastrados' })
    expect(await within(tabela).findByText('Consultoria agrícola')).toBeInTheDocument()
    expect(within(tabela).getByText('170101')).toBeInTheDocument()
    expect(within(tabela).getByText('municipal 001')).toBeInTheDocument()
    expect(within(tabela).getByText('3.00%')).toBeInTheDocument()
    expect(within(tabela).getByText('01/01/2026 a 30/06/2026')).toBeInTheDocument()
  })

  it('cadastra um serviço: números vazios vão como nulos e o fim da vigência vazio como "sem fim"', async () => {
    const { chamadas } = abrir({ [`POST ${SERVICOS}`]: { status: 201, dados: CONSULTORIA } })
    fireEvent.click(await screen.findByRole('button', { name: 'Novo serviço' }))

    digitar('Nome (uso interno)', 'Assessoria')
    digitar('Descrição que sai na nota', 'Assessoria técnica.')
    digitar('Código de tributação nacional', '17.01.01')
    digitar('Alíquota do ISS (%)', '2.5')
    digitar('Início da vigência', '2026-07-01')
    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar serviço' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST')).toBe(true))
    expect(chamadas.find((c) => c.metodo === 'POST').corpo).toMatchObject({
      nome: 'Assessoria',
      codigo_tributacao_nacional: '17.01.01',
      aliquota_iss: '2.5',
      retencao_irrf: null,
      retencao_inss: null,
      vigencia_inicio: '2026-07-01',
      vigencia_fim: null,
      iss_retido: false,
    })
  })

  it('mostra a recusa por sobreposição de vigência junto do campo', async () => {
    abrir({
      [`POST ${SERVICOS}`]: {
        status: 400,
        dados: { vigencia_inicio: ['A vigência se sobrepõe à versão de 01/01/2026 até aberta deste serviço.'] },
      },
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Novo serviço' }))
    digitar('Nome (uso interno)', 'Assessoria')
    digitar('Descrição que sai na nota', 'Assessoria técnica.')
    digitar('Código de tributação nacional', '170101')
    digitar('Início da vigência', '2026-03-01')

    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar serviço' }))

    expect(await screen.findByText(/se sobrepõe à versão de 01\/01\/2026/)).toBeInTheDocument()
    expect(screen.getByLabelText('Início da vigência')).toHaveAttribute('aria-invalid', 'true')
  })

  it('os campos fiscais têm ajuda explicando o que preencher', async () => {
    abrir()
    fireEvent.click(await screen.findByRole('button', { name: 'Novo serviço' }))

    for (const tema of ['classificação do serviço', 'IBS e CBS', 'ISS e retenções', 'vigência']) {
      expect(screen.getByRole('button', { name: `Ajuda: ${tema}` })).toBeInTheDocument()
    }
    fireEvent.click(screen.getByRole('button', { name: 'Ajuda: vigência' }))
    expect(screen.getByRole('note')).toHaveTextContent(/não podem se sobrepor/)
  })

  it('editar abre o formulário com os valores e envia a alteração', async () => {
    const { chamadas } = abrir({ [`PATCH ${SERVICOS}3/`]: { status: 200, dados: CONSULTORIA } })

    fireEvent.click(await screen.findByRole('button', { name: 'Editar Consultoria agrícola de 01/01/2026' }))
    const formulario = screen.getByRole('form', { name: 'Editar serviço' })
    expect(within(formulario).getByLabelText('Nome (uso interno)')).toHaveValue('Consultoria agrícola')
    expect(within(formulario).getByLabelText('Fim da vigência')).toHaveValue('2026-06-30')
    digitar('Fim da vigência', '2026-05-31')
    fireEvent.click(within(formulario).getByRole('button', { name: 'Salvar' }))

    await waitFor(() => expect(chamadas.find((c) => c.metodo === 'PATCH')?.corpo.vigencia_fim).toBe('2026-05-31'))
  })

  it('desativar uma versão pede confirmação', async () => {
    const { chamadas } = abrir({ [`PATCH ${SERVICOS}3/`]: { status: 200, dados: CONSULTORIA } })

    fireEvent.click(await screen.findByRole('button', { name: 'Desativar Consultoria agrícola de 01/01/2026' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Desativar' }))

    await waitFor(() => expect(chamadas.find((c) => c.metodo === 'PATCH')?.corpo).toEqual({ ativo: false }))
  })

  it('consulta a versão vigente numa data', async () => {
    const { chamadas } = abrir({ [`GET ${SERVICOS}vigente/`]: { status: 200, dados: CONSULTORIA } })
    await screen.findByText('Consultoria agrícola')

    digitar('Código nacional', '170101')
    digitar('Data', '2026-03-10')
    fireEvent.click(screen.getByRole('button', { name: 'Consultar' }))

    expect(await screen.findByText(/ISS 3\.00%, vigente de 01\/01\/2026 a 30\/06\/2026/)).toBeInTheDocument()
    const consulta = chamadas.find((c) => c.caminho === `${SERVICOS}vigente/`)
    expect(consulta.url).toContain('codigo_nacional=170101')
    expect(consulta.url).toContain('data=2026-03-10')
  })

  it('sem versão vigente na data mostra a mensagem do servidor', async () => {
    abrir({
      [`GET ${SERVICOS}vigente/`]: { status: 404, dados: { detalhe: 'Nenhuma versão deste serviço vigente em 31/12/2025.' } },
    })
    await screen.findByText('Consultoria agrícola')
    digitar('Código nacional', '170101')

    fireEvent.click(screen.getByRole('button', { name: 'Consultar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Nenhuma versão deste serviço vigente em 31/12/2025.')
  })

  it('quem só consulta não vê os botões de alteração', async () => {
    abrir({}, [EMPRESA_SO_CONSULTA])
    await screen.findByText('Consultoria agrícola')

    expect(screen.queryByRole('button', { name: 'Novo serviço' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
  })
})
