import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { limparEmpresaAtiva } from '../../api/empresaAtiva.js'
import { EMPRESA_ADMIN, EMPRESA_SO_CONSULTA, respostaEu } from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
})

const PESSOAS = '/api/cadastros/pessoas/'
const PERFIS = [
  { id: 1, codigo: 'cliente', nome: 'Cliente', sistema: true, ativo: true },
  { id: 2, codigo: 'fornecedor', nome: 'Fornecedor', sistema: true, ativo: true },
]
const MARIA = {
  id: 10, tipo: 'pf', documento: '52998224725', documento_formatado: '529.982.247-25', nif: '',
  motivo_sem_nif: null, nome: 'Maria da Silva', inscricao_municipal: '', telefone: '', emails_envio: [],
  logradouro: 'Rua A', numero: '1', complemento: '', bairro: 'Centro', codigo_municipio: '2101400',
  municipio_nome: 'Balsas/MA', cep: '65800000', pais: '', codigo_postal: '', cidade: '', estado: '',
  perfis: ['cliente'], ativo: true,
}  // fmt: skip
const BALSAS = { codigo: '2101400', nome: 'Balsas', uf: 'MA' }

function rotas(extras = {}, empresas = [EMPRESA_ADMIN, EMPRESA_SO_CONSULTA]) {
  return rotasAutenticado({
    eu: respostaEu({ empresas }),
    extras: {
      [`GET ${PESSOAS}`]: { status: 200, dados: { count: 1, results: [MARIA] } },
      'GET /api/cadastros/perfis/': { status: 200, dados: PERFIS },
      'GET /api/cadastros/municipios/': (chamada) => ({
        status: 200,
        dados: chamada.url.includes('codigo=2101400') || chamada.url.includes('busca=bal') ? [BALSAS] : [],
      }),
      ...extras,
    },
  })
}

const abrir = (extras, empresas) => montarApp({ rota: '/cadastros/pessoas', rotasApi: rotas(extras, empresas) })
const digitar = (rotulo, valor) => fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } })

describe('Pessoas: lista', () => {
  it('lista as pessoas com documento formatado, município e perfis', async () => {
    abrir()

    const tabela = await screen.findByRole('table', { name: 'Pessoas cadastradas' })
    expect(await within(tabela).findByText('Maria da Silva')).toBeInTheDocument()
    expect(within(tabela).getByText('529.982.247-25')).toBeInTheDocument()
    expect(within(tabela).getByText('Balsas/MA')).toBeInTheDocument()
    expect(within(tabela).getByText('cliente')).toBeInTheDocument()
  })

  it('o filtro envia a busca à API e volta para a primeira página', async () => {
    const { chamadas } = abrir()
    await screen.findByText('Maria da Silva')

    digitar('Buscar por nome ou documento', 'maria')
    fireEvent.click(screen.getByRole('button', { name: 'Filtrar' }))

    await waitFor(() =>
      expect(chamadas.some((c) => c.caminho === PESSOAS && c.url.includes('busca=maria'))).toBe(true),
    )
  })

  it('pagina quando há mais de 25 pessoas', async () => {
    const { chamadas } = abrir({ [`GET ${PESSOAS}`]: { status: 200, dados: { count: 60, results: [MARIA] } } })
    expect(await screen.findByText('Página 1 de 3')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Próxima' }))

    await waitFor(() => expect(chamadas.some((c) => c.url.includes('page=2'))).toBe(true))
    expect(await screen.findByText('Página 2 de 3')).toBeInTheDocument()
  })

  it('quem só consulta não vê os botões de cadastrar, editar nem copiar', async () => {
    abrir({}, [EMPRESA_SO_CONSULTA])
    await screen.findByText('Maria da Silva')

    expect(screen.queryByRole('button', { name: 'Nova pessoa' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Copiar de outra empresa/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar Maria/ })).not.toBeInTheDocument()
  })

  it('desativar pede confirmação e envia ativo=false', async () => {
    const { chamadas } = abrir({ [`PATCH ${PESSOAS}10/`]: { status: 200, dados: { ...MARIA, ativo: false } } })

    fireEvent.click(await screen.findByRole('button', { name: 'Desativar Maria da Silva' }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Desativar pessoa?' })).getByRole('button', { name: 'Desativar' }))

    await waitFor(() => expect(chamadas.find((c) => c.metodo === 'PATCH')?.corpo).toEqual({ ativo: false }))
  })
})

describe('Pessoas: cadastro', () => {
  async function abrirFormulario() {
    const montado = abrir({ [`POST ${PESSOAS}`]: { status: 201, dados: MARIA } })
    fireEvent.click(await screen.findByRole('button', { name: 'Nova pessoa' }))
    return { ...montado, formulario: screen.getByRole('form', { name: 'Nova pessoa' }) }
  }

  it('cadastra pessoa física escolhendo o município pelo nome (sem digitar o código IBGE)', async () => {
    const { chamadas } = await abrirFormulario()

    digitar('Nome ou razão social', ' Maria da Silva ')
    digitar('CPF', '529.982.247-25')
    digitar('Logradouro', 'Rua A')
    digitar('Número', '1')
    digitar('Bairro', 'Centro')
    digitar('CEP', '65800-000')
    digitar('E-mails para envio da nota', 'fiscal@exemplo.test; outro@exemplo.test')
    fireEvent.change(screen.getByRole('combobox', { name: 'Município' }), { target: { value: 'bal' } })
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Balsas\/MA/ }))
    expect(await screen.findByText(/IBGE 2101400/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST')).toBe(true))
    const corpo = chamadas.find((c) => c.metodo === 'POST').corpo
    expect(corpo).toMatchObject({
      tipo: 'pf',
      documento: '529.982.247-25',
      nome: 'Maria da Silva',
      codigo_municipio: '2101400',
      cep: '65800-000',
      emails_envio: ['fiscal@exemplo.test', 'outro@exemplo.test'],
      nif: '',
      motivo_sem_nif: null,
      pais: '',
    })
  })

  it('mostra o erro da API junto do campo e mantém o formulário aberto', async () => {
    montarApp({
      rota: '/cadastros/pessoas',
      rotasApi: rotas({ [`POST ${PESSOAS}`]: { status: 400, dados: { documento: ['CPF inválido. Confira os 11 dígitos.'], codigo_municipio: ['Informe o município do endereço (código IBGE): ele é obrigatório na DPS.'] } } }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Nova pessoa' }))
    digitar('Nome ou razão social', 'Fulano')
    digitar('CPF', '123')

    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar' }))

    expect(await screen.findByText('CPF inválido. Confira os 11 dígitos.')).toBeInTheDocument()
    expect(screen.getByLabelText('CPF')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText(/obrigatório na DPS/)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Nova pessoa' })).toBeInTheDocument()
  })

  it('o rótulo do documento acompanha o tipo e pessoa jurídica pede CNPJ', async () => {
    await abrirFormulario()

    fireEvent.change(screen.getByLabelText('Tipo de pessoa'), { target: { value: 'pj' } })

    expect(screen.getByLabelText('CNPJ')).toBeInTheDocument()
    expect(screen.queryByLabelText('CPF')).not.toBeInTheDocument()
  })

  it('estrangeiro usa NIF, não pede CPF/CNPJ e não manda documento nem município', async () => {
    const { chamadas } = await abrirFormulario()

    fireEvent.change(screen.getByLabelText('Tipo de pessoa'), { target: { value: 'estrangeiro' } })
    digitar('Nome ou razão social', 'John Test')
    digitar('NIF', 'AB1234567')
    fireEvent.change(screen.getByLabelText('Onde fica o endereço'), { target: { value: 'nenhum' } })
    expect(screen.queryByLabelText('CPF')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('CEP')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST')).toBe(true))
    expect(chamadas.find((c) => c.metodo === 'POST').corpo).toMatchObject({
      tipo: 'estrangeiro', documento: '', nif: 'AB1234567', motivo_sem_nif: null, codigo_municipio: '', cep: '',
    })  // fmt: skip
  })

  it('escolher o motivo sem NIF desabilita o NIF e envia o motivo como número', async () => {
    const { chamadas } = await abrirFormulario()
    fireEvent.change(screen.getByLabelText('Tipo de pessoa'), { target: { value: 'estrangeiro' } })
    digitar('Nome ou razão social', 'John Test')
    fireEvent.change(screen.getByLabelText('Onde fica o endereço'), { target: { value: 'nenhum' } })

    fireEvent.change(screen.getByLabelText('Ou o motivo de não informar o NIF'), { target: { value: '1' } })

    expect(screen.getByLabelText('NIF')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar' }))
    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST')).toBe(true))
    expect(chamadas.find((c) => c.metodo === 'POST').corpo).toMatchObject({ motivo_sem_nif: 1, nif: '' })
  })

  it('estrangeiro com endereço no exterior mostra os campos do exterior', async () => {
    await abrirFormulario()
    fireEvent.change(screen.getByLabelText('Tipo de pessoa'), { target: { value: 'estrangeiro' } })

    fireEvent.change(screen.getByLabelText('Onde fica o endereço'), { target: { value: 'exterior' } })

    expect(screen.getByLabelText('País (código de 2 letras)')).toBeInTheDocument()
    expect(screen.getByLabelText('Código postal')).toBeInTheDocument()
    expect(screen.queryByLabelText('CEP')).not.toBeInTheDocument()
  })

  it('editar abre o formulário preenchido com o município pelo nome', async () => {
    abrir()

    fireEvent.click(await screen.findByRole('button', { name: 'Editar Maria da Silva' }))

    const formulario = screen.getByRole('form', { name: 'Editar pessoa' })
    expect(within(formulario).getByLabelText('Nome ou razão social')).toHaveValue('Maria da Silva')
    expect(within(formulario).getByLabelText('CPF')).toHaveValue('529.982.247-25')
    expect(await within(formulario).findByText(/Balsas\/MA/)).toBeInTheDocument()
  })
})

describe('Pessoas: copiar de outra empresa', () => {
  const ORIGEM = [
    { id: 7, tipo: 'pf', documento: '11144477735', nome: 'Ana da Origem' },
    { id: 8, tipo: 'pj', documento: '11444777000161', nome: 'Comercial da Origem' },
  ]

  async function abrirCopia(extras = {}) {
    const montado = abrir({
      'GET /api/cadastros/copia/pessoas/': { status: 200, dados: ORIGEM },
      ...extras,
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Copiar de outra empresa' }))
    fireEvent.click(screen.getByRole('combobox', { name: 'Empresa de origem' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Empresa Beta/ }))
    return montado
  }

  it('só oferece como origem as outras empresas em que o usuário pode consultar cadastros', async () => {
    const semPermissao = { ...EMPRESA_SO_CONSULTA, id: 3, razao_social: 'Gama Sem Acesso', permissoes: ['nfse.consultar'] }
    abrir({}, [EMPRESA_ADMIN, EMPRESA_SO_CONSULTA, semPermissao])
    fireEvent.click(await screen.findByRole('button', { name: 'Copiar de outra empresa' }))

    fireEvent.click(screen.getByRole('combobox', { name: 'Empresa de origem' }))

    expect(await screen.findByRole('option', { name: /Empresa Beta/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Gama Sem Acesso/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Empresa Alfa/ })).not.toBeInTheDocument() // a ativa
  })

  it('copia as pessoas marcadas depois de confirmar e mostra o resultado', async () => {
    const { chamadas } = await abrirCopia({
      'POST /api/cadastros/copia/pessoas/': {
        status: 201,
        dados: { copiadas: 1, ignoradas: [{ id: 8, nome: 'Comercial da Origem', motivo: 'Já existe uma pessoa com este documento na empresa de destino.' }] },
      },
    })
    const lista = await screen.findByRole('list', { name: 'Pessoas da empresa de origem' })
    fireEvent.click(within(lista).getByRole('checkbox', { name: /Ana da Origem/ }))
    fireEvent.click(within(lista).getByRole('checkbox', { name: /Comercial da Origem/ }))

    fireEvent.click(screen.getByRole('button', { name: 'Copiar selecionadas' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Copiar cadastros?' })
    expect(dialogo).toHaveTextContent(/2 pessoa\(s\) de "Empresa Beta S\.A\."/)
    expect(dialogo).toHaveTextContent(/alterar uma não muda a outra/)
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Copiar' }))

    expect(await screen.findByText(/pessoa\(s\) copiada\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/Já existe uma pessoa com este documento/)).toBeInTheDocument()
    expect(chamadas.find((c) => c.metodo === 'POST').corpo).toEqual({ empresa_origem: 2, ids: [7, 8] })
  })

  it('selecionar todas marca todas as pessoas', async () => {
    await abrirCopia()
    await screen.findByRole('list', { name: 'Pessoas da empresa de origem' })

    fireEvent.click(screen.getByRole('checkbox', { name: /Selecionar todas \(2\)/ }))

    expect(screen.getByRole('button', { name: 'Copiar selecionadas' })).toBeEnabled()
    for (const caixa of within(screen.getByRole('list', { name: 'Pessoas da empresa de origem' })).getAllByRole('checkbox')) {
      expect(caixa).toBeChecked()
    }
  })

  it('cancelar a confirmação não copia nada', async () => {
    const { chamadas } = await abrirCopia()
    const lista = await screen.findByRole('list', { name: 'Pessoas da empresa de origem' })
    fireEvent.click(within(lista).getByRole('checkbox', { name: /Ana da Origem/ }))

    fireEvent.click(screen.getByRole('button', { name: 'Copiar selecionadas' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancelar' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(chamadas.some((c) => c.metodo === 'POST')).toBe(false)
  })

  it('sem acesso à origem mostra a mensagem e não lista pessoas', async () => {
    await abrirCopia({
      'GET /api/cadastros/copia/pessoas/': { status: 403, dados: { codigo: 'sem_acesso_a_empresa', detalhe: 'x' } },
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('Você não tem acesso a esta empresa.')
    expect(screen.queryByRole('list', { name: 'Pessoas da empresa de origem' })).not.toBeInTheDocument()
  })

  it('avisa quando a origem não tem pessoas ativas', async () => {
    await abrirCopia({ 'GET /api/cadastros/copia/pessoas/': { status: 200, dados: [] } })

    expect(await screen.findByText(/não tem pessoas ativas para copiar/)).toBeInTheDocument()
  })
})
