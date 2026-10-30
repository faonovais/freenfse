import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { limparEmpresaAtiva, obterEmpresaAtiva } from '../../api/empresaAtiva.js'
import { EMPRESA_A, EMPRESA_B, respostaEu } from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
})

const ADMIN = '/api/admin-global'
const eu = respostaEu({ master: true })

const EMPRESAS_API = [
  { id: 1, razao_social: 'Empresa Alfa Ltda', cnpj: '11222333000181', cnpj_formatado: '11.222.333/0001-81', ativo: true },
  { id: 2, razao_social: 'Empresa Beta S.A.', cnpj: '11444777000161', cnpj_formatado: '11.444.777/0001-61', ativo: false },
]
const USUARIOS_API = [
  { id: 7, email: 'ana@example.com', nome: 'Ana', is_active: true, is_master: true, mfa_ativo: true },
  { id: 8, email: 'beto@example.com', nome: 'Beto', is_active: true, is_master: false, mfa_ativo: false },
]
const PERMISSOES_API = {
  permissoes: [
    { nome: 'nfse.consultar', descricao: 'Consultar NFS-e' },
    { nome: 'nfse.emitir', descricao: 'Emitir NFS-e' },
    { nome: 'nfse.cancelar', descricao: 'Cancelar NFS-e' },
  ],
  perfis: [
    { valor: 'emissor', rotulo: 'Emissor', permissoes: ['nfse.consultar', 'nfse.emitir', 'nfse.cancelar'] },
    { valor: 'consulta', rotulo: 'Consulta', permissoes: ['nfse.consultar'] },
  ],
  perfil_master: 'master',
}
const VINCULO_API = {
  id: 30,
  usuario: 8,
  usuario_email: 'beto@example.com',
  empresa: 1,
  empresa_razao_social: 'Empresa Alfa Ltda',
  empresa_cnpj: '11222333000181',
  perfil: 'emissor',
  permissoes_extras: [],
  permissoes_removidas: ['nfse.cancelar'],
  ativo: true,
}

describe('administração de empresas', () => {
  it('lista as empresas com a situação de cada uma', async () => {
    montarApp({
      rota: '/admin/empresas',
      rotasApi: rotasAutenticado({ eu, extras: { [`GET ${ADMIN}/empresas/`]: { status: 200, dados: EMPRESAS_API } } }),
    })

    const tabela = await screen.findByRole('table', { name: 'Empresas cadastradas' })
    expect(await within(tabela).findByText('11.222.333/0001-81')).toBeInTheDocument()
    expect(within(tabela).getByText('Ativa')).toBeInTheDocument()
    expect(within(tabela).getByText('Inativa')).toBeInTheDocument()
  })

  it('mostra o erro de validação do CNPJ junto do campo e não fecha o formulário', async () => {
    montarApp({
      rota: '/admin/empresas',
      rotasApi: rotasAutenticado({
        eu,
        extras: {
          [`GET ${ADMIN}/empresas/`]: { status: 200, dados: [] },
          [`POST ${ADMIN}/empresas/`]: { status: 400, dados: { cnpj: ['CNPJ inválido.'] } },
        },
      }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Nova empresa' }))
    const formulario = screen.getByRole('form', { name: 'Nova empresa' })

    fireEvent.change(within(formulario).getByLabelText('Razão social'), { target: { value: 'Gama ME' } })
    fireEvent.change(within(formulario).getByLabelText('CNPJ'), { target: { value: '11.111.111/0001-11' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Criar empresa' }))

    expect(await within(formulario).findByText('CNPJ inválido.')).toBeInTheDocument()
    expect(within(formulario).getByLabelText('CNPJ')).toHaveAttribute('aria-invalid', 'true')
  })

  it('cria a empresa, fecha o formulário e recarrega a lista', async () => {
    let criada = false
    const { chamadas } = montarApp({
      rota: '/admin/empresas',
      rotasApi: rotasAutenticado({
        eu,
        extras: {
          [`GET ${ADMIN}/empresas/`]: () => ({ status: 200, dados: criada ? EMPRESAS_API : [] }),
          [`POST ${ADMIN}/empresas/`]: () => {
            criada = true
            return { status: 201, dados: EMPRESAS_API[0] }
          },
        },
      }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Nova empresa' }))
    const formulario = screen.getByRole('form', { name: 'Nova empresa' })

    fireEvent.change(within(formulario).getByLabelText('Razão social'), { target: { value: ' Empresa Alfa Ltda ' } })
    fireEvent.change(within(formulario).getByLabelText('CNPJ'), { target: { value: '11.222.333/0001-81' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Criar empresa' }))

    const tabela = await screen.findByRole('table', { name: 'Empresas cadastradas' })
    await waitFor(() => expect(tabela).toHaveTextContent('Empresa Alfa Ltda'))
    await waitFor(() => expect(screen.queryByRole('form', { name: 'Nova empresa' })).not.toBeInTheDocument())
    const envio = chamadas.find((chamada) => chamada.metodo === 'POST')
    expect(envio.corpo).toEqual({ razao_social: 'Empresa Alfa Ltda', cnpj: '11.222.333/0001-81' })
    expect(envio.cabecalhos).not.toHaveProperty('X-Empresa') // administração é global
  })

  it('na edição o CNPJ fica bloqueado e só a razão social é enviada', async () => {
    const { chamadas } = montarApp({
      rota: '/admin/empresas',
      rotasApi: rotasAutenticado({
        eu,
        extras: {
          [`GET ${ADMIN}/empresas/`]: { status: 200, dados: EMPRESAS_API },
          [`PATCH ${ADMIN}/empresas/1/`]: { status: 200, dados: EMPRESAS_API[0] },
        },
      }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Editar Empresa Alfa Ltda' }))
    const formulario = screen.getByRole('form', { name: 'Editar empresa' })
    expect(within(formulario).getByLabelText('CNPJ')).toBeDisabled()

    fireEvent.change(within(formulario).getByLabelText('Razão social'), { target: { value: 'Alfa Agro Ltda' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Salvar' }))

    await waitFor(() => expect(chamadas.some((chamada) => chamada.metodo === 'PATCH')).toBe(true))
    expect(chamadas.find((chamada) => chamada.metodo === 'PATCH').corpo).toEqual({ razao_social: 'Alfa Agro Ltda' })
  })

  it('desativar pede confirmação; cancelar não altera nada', async () => {
    const { chamadas } = montarApp({
      rota: '/admin/empresas',
      rotasApi: rotasAutenticado({
        eu,
        extras: {
          [`GET ${ADMIN}/empresas/`]: { status: 200, dados: EMPRESAS_API },
          [`PATCH ${ADMIN}/empresas/1/`]: { status: 200, dados: EMPRESAS_API[0] },
        },
      }),
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Desativar Empresa Alfa Ltda' }))
    const dialogo = await screen.findByRole('dialog', { name: 'Desativar empresa?' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cancelar' }))
    await waitFor(() => expect(dialogo).not.toBeInTheDocument())
    expect(chamadas.some((chamada) => chamada.metodo === 'PATCH')).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Desativar Empresa Alfa Ltda' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Desativar' }))

    await waitFor(() => expect(chamadas.find((chamada) => chamada.metodo === 'PATCH')?.corpo).toEqual({ ativo: false }))
  })

  it('trocar de empresa com formulário alterado pede confirmação e mantém a empresa se cancelar', async () => {
    montarApp({
      rota: '/admin/empresas',
      rotasApi: rotasAutenticado({
        eu,
        extras: { [`GET ${ADMIN}/empresas/`]: { status: 200, dados: EMPRESAS_API } },
      }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Nova empresa' }))
    fireEvent.change(screen.getByLabelText('Razão social'), { target: { value: 'Rascunho' } })

    fireEvent.click(screen.getByRole('combobox', { name: 'Empresa ativa' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Empresa Beta/ }))
    const dialogo = await screen.findByRole('dialog', { name: 'Trocar de empresa?' })
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Continuar editando' }))

    await waitFor(() => expect(dialogo).not.toBeInTheDocument())
    expect(obterEmpresaAtiva()).toBe(EMPRESA_A.id)
    expect(screen.getByLabelText('Razão social')).toHaveValue('Rascunho')

    fireEvent.click(screen.getByRole('combobox', { name: 'Empresa ativa' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Empresa Beta/ }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Trocar e descartar' }))

    await waitFor(() => expect(obterEmpresaAtiva()).toBe(EMPRESA_B.id))
  })
})

describe('administração de usuários', () => {
  const rotasUsuarios = (extras = {}) =>
    rotasAutenticado({ eu, extras: { [`GET ${ADMIN}/usuarios/`]: { status: 200, dados: USUARIOS_API }, ...extras } })

  it('lista usuários com papel, 2FA e situação', async () => {
    montarApp({ rota: '/admin/usuarios', rotasApi: rotasUsuarios() })

    const tabela = await screen.findByRole('table', { name: 'Usuários cadastrados' })
    expect(await within(tabela).findByText('beto@example.com')).toBeInTheDocument()
    expect(within(tabela).getByText('Não configurado')).toBeInTheDocument()
  })

  it('o Master não consegue desativar o próprio usuário pela tela', async () => {
    montarApp({ rota: '/admin/usuarios', rotasApi: rotasUsuarios() })

    const proprio = await screen.findByRole('button', { name: 'Desativar ana@example.com' })

    expect(proprio).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Desativar beto@example.com' })).toBeEnabled()
  })

  it('cria usuário sem enviar senha quando ela fica em branco', async () => {
    const { chamadas } = montarApp({
      rota: '/admin/usuarios',
      rotasApi: rotasUsuarios({ [`POST ${ADMIN}/usuarios/`]: { status: 201, dados: USUARIOS_API[1] } }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Novo usuário' }))
    const formulario = screen.getByRole('form', { name: 'Novo usuário' })

    fireEvent.change(within(formulario).getByLabelText('E-mail'), { target: { value: ' Carla@Example.com ' } })
    fireEvent.change(within(formulario).getByLabelText('Nome'), { target: { value: 'Carla' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Criar usuário' }))

    await waitFor(() => expect(chamadas.some((chamada) => chamada.metodo === 'POST')).toBe(true))
    expect(chamadas.find((chamada) => chamada.metodo === 'POST').corpo).toEqual({
      email: 'Carla@Example.com',
      nome: 'Carla',
      is_master: false,
    })
  })

  it('mostra o erro de e-mail duplicado junto do campo', async () => {
    montarApp({
      rota: '/admin/usuarios',
      rotasApi: rotasUsuarios({
        [`POST ${ADMIN}/usuarios/`]: { status: 400, dados: { email: ['Já existe um usuário com este e-mail.'] } },
      }),
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Novo usuário' }))
    const formulario = screen.getByRole('form', { name: 'Novo usuário' })

    fireEvent.change(within(formulario).getByLabelText('E-mail'), { target: { value: 'ana@example.com' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Criar usuário' }))

    expect(await within(formulario).findByText('Já existe um usuário com este e-mail.')).toBeInTheDocument()
  })
})

describe('administração de vínculos', () => {
  const rotasVinculos = (extras = {}) =>
    rotasAutenticado({
      eu,
      extras: {
        [`GET ${ADMIN}/vinculos/`]: { status: 200, dados: [VINCULO_API] },
        [`GET ${ADMIN}/usuarios/`]: { status: 200, dados: USUARIOS_API },
        [`GET ${ADMIN}/empresas/`]: { status: 200, dados: EMPRESAS_API },
        [`GET ${ADMIN}/permissoes/`]: { status: 200, dados: PERMISSOES_API },
        ...extras,
      },
    })

  it('lista os vínculos com o perfil de cada um', async () => {
    montarApp({ rota: '/admin/vinculos', rotasApi: rotasVinculos() })

    const tabela = await screen.findByRole('table', { name: 'Vínculos entre usuários e empresas' })
    expect(await within(tabela).findByText('beto@example.com')).toBeInTheDocument()
    expect(within(tabela).getByText('Emissor')).toBeInTheDocument()
  })

  it('filtrar por empresa envia o filtro à API', async () => {
    const { chamadas } = montarApp({ rota: '/admin/vinculos', rotasApi: rotasVinculos() })
    await screen.findByRole('table', { name: 'Vínculos entre usuários e empresas' })

    fireEvent.click(screen.getByRole('combobox', { name: 'Filtrar por empresa' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Empresa Alfa/ }))

    await waitFor(() =>
      expect(chamadas.some((chamada) => chamada.caminho === `${ADMIN}/vinculos/` && chamada.url.includes('empresa=1'))).toBe(true),
    )
  })

  it('concede acesso escolhendo usuário, empresa, perfil e removendo uma permissão do perfil', async () => {
    const { chamadas } = montarApp({
      rota: '/admin/vinculos',
      rotasApi: rotasVinculos({ [`POST ${ADMIN}/vinculos/`]: { status: 201, dados: VINCULO_API } }),
    })
    await screen.findByRole('table', { name: 'Vínculos entre usuários e empresas' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Novo vínculo' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Novo vínculo' }))
    const formulario = screen.getByRole('form', { name: 'Novo vínculo' })

    fireEvent.click(within(formulario).getByRole('combobox', { name: 'Usuário' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /beto@example.com/ }))
    fireEvent.click(within(formulario).getByRole('combobox', { name: 'Empresa' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Empresa Alfa/ }))
    fireEvent.change(within(formulario).getByLabelText('Perfil'), { target: { value: 'emissor' } })
    fireEvent.click(within(formulario).getByRole('combobox', { name: 'Permissões removidas' }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /nfse.cancelar/ })) // retira do perfil
    fireEvent.click(within(formulario).getByRole('button', { name: 'Conceder acesso' }))

    await waitFor(() => expect(chamadas.some((chamada) => chamada.metodo === 'POST')).toBe(true))
    expect(chamadas.find((chamada) => chamada.metodo === 'POST').corpo).toEqual({
      usuario: 8,
      empresa: 1,
      perfil: 'emissor',
      permissoes_extras: [],
      permissoes_removidas: ['nfse.cancelar'],
    })
  })

  it('exige escolher usuário e empresa antes de enviar', async () => {
    const { chamadas } = montarApp({ rota: '/admin/vinculos', rotasApi: rotasVinculos() })
    await screen.findByRole('table', { name: 'Vínculos entre usuários e empresas' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Novo vínculo' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Novo vínculo' }))

    fireEvent.click(screen.getByRole('button', { name: 'Conceder acesso' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Escolha o usuário e a empresa.')
    expect(chamadas.some((chamada) => chamada.metodo === 'POST')).toBe(false)
  })

  it('ao trocar o perfil, descarta ajustes que deixam de fazer sentido', async () => {
    montarApp({ rota: '/admin/vinculos', rotasApi: rotasVinculos() })
    fireEvent.click(await screen.findByRole('button', { name: /Editar vínculo de beto@example.com/ }))
    const formulario = screen.getByRole('form', { name: 'Editar vínculo' })
    expect(within(formulario).getByRole('button', { name: 'Remover nfse.cancelar' })).toBeInTheDocument()

    fireEvent.change(within(formulario).getByLabelText('Perfil'), { target: { value: 'consulta' } })

    // No perfil Consulta, nfse.cancelar nunca vinha do perfil: não há mais o que remover dele.
    expect(within(formulario).queryByRole('button', { name: 'Remover nfse.cancelar' })).not.toBeInTheDocument()
    // E passa a ser oferecida como permissão extra.
    fireEvent.click(within(formulario).getByRole('combobox', { name: 'Permissões extras' }))
    expect(await screen.findByRole('option', { name: /nfse.cancelar/ })).toBeInTheDocument()
  })

  it('oferece como extras só o que o perfil não inclui, e como remoção só o que ele inclui', async () => {
    montarApp({ rota: '/admin/vinculos', rotasApi: rotasVinculos() })
    fireEvent.click(await screen.findByRole('button', { name: /Editar vínculo de beto@example.com/ }))
    const formulario = screen.getByRole('form', { name: 'Editar vínculo' })

    fireEvent.click(within(formulario).getByRole('combobox', { name: 'Permissões removidas' }))

    const lista = await screen.findByRole('listbox', { name: 'Permissões removidas' })
    expect(within(lista).getAllByRole('option')).toHaveLength(3) // emissor tem as três do catálogo de teste
  })

  it('revogar acesso pede confirmação e envia ativo=false', async () => {
    const { chamadas } = montarApp({
      rota: '/admin/vinculos',
      rotasApi: rotasVinculos({ [`PATCH ${ADMIN}/vinculos/30/`]: { status: 200, dados: VINCULO_API } }),
    })

    fireEvent.click(await screen.findByRole('button', { name: /Revogar vínculo de beto@example.com/ }))
    fireEvent.click(within(await screen.findByRole('dialog', { name: 'Revogar acesso?' })).getByRole('button', { name: 'Revogar acesso' }))

    await waitFor(() => expect(chamadas.find((chamada) => chamada.metodo === 'PATCH')?.corpo).toEqual({ ativo: false }))
  })
})
