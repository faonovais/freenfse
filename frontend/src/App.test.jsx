import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { http } from './api/http.js'
import { limparEmpresaAtiva, obterEmpresaAtiva } from './api/empresaAtiva.js'
import { EMPRESA_A, EMPRESA_B, IDENTIDADE_PADRAO, respostaEu } from './testes/apiFalsa.js'
import { BASE, montarApp, rotasAnonimo, rotasAutenticado } from './testes/montarApp.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  window.localStorage.clear()
  document.documentElement.classList.remove('dark')
})

const trocarEmpresaPara = async (nome) => {
  fireEvent.click(screen.getByRole('combobox', { name: 'Empresa ativa' }))
  fireEvent.mouseDown(await screen.findByRole('option', { name: new RegExp(nome) }))
}

describe('acesso à aplicação', () => {
  it('quem não está logado é levado ao login', async () => {
    const { roteador } = montarApp({ rota: '/admin/empresas', rotasApi: rotasAnonimo() })

    expect(await screen.findByRole('heading', { name: 'freenfse' })).toBeInTheDocument()
    expect(screen.getByLabelText('E-mail')).toBeInTheDocument()
    expect(roteador.state.location.pathname).toBe('/login')
  })

  it('quem precisa configurar o 2FA é levado à tela de configuração', async () => {
    const eu = respostaEu({ mfa: { ativo: false, obrigatorio: true } })
    const { roteador } = montarApp({ rotasApi: rotasAutenticado({ eu }) })

    expect(await screen.findByRole('heading', { name: 'Verificação em duas etapas' })).toBeInTheDocument()
    expect(roteador.state.location.pathname).toBe('/seguranca/2fa')
    expect(screen.getByText(/exige a verificação em duas etapas/)).toBeInTheDocument()
  })

  it('usuário comum não vê a administração nem entra nela', async () => {
    montarApp({ rota: '/admin/empresas', rotasApi: rotasAutenticado() })

    expect(await screen.findByRole('heading', { name: 'Acesso negado' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Empresas' })).not.toBeInTheDocument()
  })

  it('o Master vê a administração no menu', async () => {
    montarApp({ rotasApi: rotasAutenticado({ eu: respostaEu({ master: true }) }) })

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    for (const nome of ['Empresas', 'Usuários', 'Vínculos']) {
      expect(within(menu).getByRole('link', { name: nome })).toBeInTheDocument()
    }
  })

  it('rota desconhecida mostra a página não encontrada dentro do layout', async () => {
    montarApp({ rota: '/nao-existe', rotasApi: rotasAutenticado() })

    expect(await screen.findByRole('heading', { name: 'Página não encontrada' })).toBeInTheDocument()
  })

  it('sair volta ao login e esquece a empresa ativa', async () => {
    const { chamadas } = montarApp({
      rotasApi: rotasAutenticado({ extras: { [`DELETE ${BASE}/auth/session`]: { status: 401, dados: {} } } }),
    })
    await screen.findByLabelText('Empresa em operação')
    expect(obterEmpresaAtiva()).toBe(EMPRESA_A.id)

    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))

    expect(await screen.findByLabelText('E-mail')).toBeInTheDocument()
    expect(obterEmpresaAtiva()).toBeNull()
    expect(chamadas.some((chamada) => chamada.metodo === 'DELETE')).toBe(true)
  })
})

describe('layout e empresa ativa por aba', () => {
  it('mostra sempre o nome e o CNPJ da empresa em operação', async () => {
    montarApp({ rotasApi: rotasAutenticado() })

    const operacao = await screen.findByLabelText('Empresa em operação')
    expect(operacao).toHaveTextContent('Empresa Alfa Ltda')
    expect(operacao).toHaveTextContent('11.222.333/0001-81')
  })

  it('a empresa escolhida vai no cabeçalho X-Empresa das chamadas seguintes', async () => {
    const { chamadas } = montarApp({ rotasApi: rotasAutenticado() })
    await screen.findByLabelText('Empresa em operação')
    expect((await http('/api/algo/')).status).toBe(404)
    expect(chamadas.at(-1).cabecalhos['X-Empresa']).toBe('1')

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(screen.getByLabelText('Empresa em operação')).toHaveTextContent('Empresa Beta S.A.'))
    expect(screen.getByLabelText('Empresa em operação')).toHaveTextContent('11.444.777/0001-61')
    await http('/api/algo/')
    expect(chamadas.at(-1).cabecalhos['X-Empresa']).toBe('2')
  })

  it('guarda a empresa só na aba (sessionStorage), nunca no localStorage', async () => {
    montarApp({ rotasApi: rotasAutenticado() })
    await screen.findByLabelText('Empresa em operação')

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(window.sessionStorage.getItem('freenfse-empresa-ativa')).toBe('2'))
    expect(JSON.stringify({ ...window.localStorage })).not.toMatch(/empresa/i)
  })

  it('retoma a empresa desta aba depois de recarregar a página', async () => {
    window.sessionStorage.setItem('freenfse-empresa-ativa', '2')

    montarApp({ rotasApi: rotasAutenticado() })

    expect(await screen.findByLabelText('Empresa em operação')).toHaveTextContent('Empresa Beta S.A.')
  })

  it('descarta a empresa guardada se o usuário não tem mais acesso a ela', async () => {
    window.sessionStorage.setItem('freenfse-empresa-ativa', '99')

    montarApp({ rotasApi: rotasAutenticado() })

    expect(await screen.findByLabelText('Empresa em operação')).toHaveTextContent('Empresa Alfa Ltda')
    expect(obterEmpresaAtiva()).toBe(1)
  })

  it('mostra o perfil e as permissões da empresa ativa e atualiza ao trocar', async () => {
    montarApp({ rotasApi: rotasAutenticado() })
    const permissoes = await screen.findByRole('list', { name: 'Permissões' })
    expect(within(permissoes).getByText('nfse.emitir')).toBeInTheDocument()

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(screen.queryByText('nfse.emitir')).not.toBeInTheDocument())
    expect(screen.getByText('nfse.consultar')).toBeInTheDocument()
  })

  it('exibe o emblema de produção restrita conforme o ambiente da empresa ativa', async () => {
    const identidade = (chamada) => ({
      status: 200,
      dados: {
        ...IDENTIDADE_PADRAO.dados,
        ambiente: chamada.cabecalhos['X-Empresa'] === '1' ? 'producao_restrita' : 'producao',
      },
    })
    montarApp({ rotasApi: rotasAutenticado({ extras: { 'GET /api/fiscal/identidade/': identidade } }) })

    expect(await screen.findByText('Produção restrita')).toBeInTheDocument()

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(screen.queryByText('Produção restrita')).not.toBeInTheDocument())
  })

  it('mostra o logo da empresa ativa, buscado com o X-Empresa, e some ao trocar para uma sem logo', async () => {
    const identidade = (chamada) => ({
      status: 200,
      dados: {
        ...IDENTIDADE_PADRAO.dados,
        logo: chamada.cabecalhos['X-Empresa'] === '1' ? { claro: 'abc123' } : {},
      },
    })
    const { chamadas } = montarApp({
      rotasApi: rotasAutenticado({
        extras: {
          'GET /api/fiscal/identidade/': identidade,
          'GET /api/fiscal/logo/claro/': { status: 200, blob: new Blob(['x'], { type: 'image/png' }) },
        },
      }),
    })

    const imagem = await screen.findByRole('img', { name: 'Logo de Empresa Alfa Ltda' })
    expect(imagem).toHaveAttribute('src', 'blob:logo-falso')
    const download = chamadas.find((chamada) => chamada.caminho === '/api/fiscal/logo/claro/')
    expect(download.cabecalhos['X-Empresa']).toBe('1')

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(screen.queryByRole('img', { name: /Logo de/ })).not.toBeInTheDocument())
  })

  it('no tema escuro busca o logo escuro', async () => {
    window.localStorage.setItem('freenfse-tema', 'escuro')
    const { chamadas } = montarApp({
      rotasApi: rotasAutenticado({
        extras: {
          'GET /api/fiscal/identidade/': {
            status: 200,
            dados: { ...IDENTIDADE_PADRAO.dados, logo: { claro: 'a', escuro: 'b' } },
          },
          'GET /api/fiscal/logo/escuro/': { status: 200, blob: new Blob(['x']) },
        },
      }),
    })

    await screen.findByRole('img', { name: /Logo de/ })

    expect(chamadas.some((chamada) => chamada.caminho === '/api/fiscal/logo/escuro/')).toBe(true)
    expect(chamadas.some((chamada) => chamada.caminho === '/api/fiscal/logo/claro/')).toBe(false)
  })

  it('avisa quando o certificado está para vencer, com link para quem pode ver a configuração', async () => {
    const empresaComConfig = { ...EMPRESA_A, permissoes: [...EMPRESA_A.permissoes, 'config.consultar'] }
    montarApp({
      rotasApi: rotasAutenticado({
        eu: respostaEu({ empresas: [empresaComConfig] }),
        extras: {
          'GET /api/fiscal/identidade/': {
            status: 200,
            dados: {
              ...IDENTIDADE_PADRAO.dados,
              certificado: { existe: true, vencido: false, dias_para_vencer: 12, faixa_alerta: 15 },
            },
          },
        },
      }),
    })

    expect(await screen.findByText(/vence em 12 dia\(s\)/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver certificado' })).toHaveAttribute('href', '/fiscal/certificado')
  })

  it('certificado vencido aparece como erro', async () => {
    montarApp({
      rotasApi: rotasAutenticado({
        extras: {
          'GET /api/fiscal/identidade/': {
            status: 200,
            dados: {
              ...IDENTIDADE_PADRAO.dados,
              certificado: { existe: true, vencido: true, dias_para_vencer: -3, faixa_alerta: 0 },
            },
          },
        },
      }),
    })

    expect(await screen.findByRole('alert')).toHaveTextContent(/venceu/)
  })

  it('o menu mostra Cadastros e Configuração fiscal conforme as permissões da empresa ativa', async () => {
    const admin = {
      ...EMPRESA_A,
      permissoes: ['cadastro.consultar', 'cadastro.editar', 'config.consultar', 'config.editar'],
    }
    const consulta = { ...EMPRESA_B, permissoes: ['nfse.consultar'] }
    montarApp({ rotasApi: rotasAutenticado({ eu: respostaEu({ empresas: [admin, consulta] }) }) })
    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    for (const nome of ['Pessoas', 'Serviços', 'Parâmetros fiscais', 'Certificado A1', 'Logo da empresa']) {
      expect(within(menu).getByRole('link', { name: nome })).toBeInTheDocument()
    }

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(within(menu).queryByRole('link', { name: 'Pessoas' })).not.toBeInTheDocument())
    expect(within(menu).queryByRole('link', { name: 'Certificado A1' })).not.toBeInTheDocument()
  })

  it('quem não tem empresa vê o aviso e nenhum cabeçalho X-Empresa é enviado', async () => {
    const { chamadas } = montarApp({ rotasApi: rotasAutenticado({ eu: respostaEu({ empresas: [] }) }) })

    expect(await screen.findByText(/não tem acesso a nenhuma empresa/)).toBeInTheDocument()
    expect(screen.getByText('Nenhuma empresa liberada')).toBeInTheDocument()
    expect(chamadas.every((chamada) => !('X-Empresa' in chamada.cabecalhos))).toBe(true)
  })

  it('mostra as versões da interface e da API no rodapé', async () => {
    montarApp({ rotasApi: rotasAutenticado() })

    expect(await screen.findByText('API: v9.9.9')).toBeInTheDocument()
    expect(screen.getByText(`Interface: v${__VERSAO_APP__}`)).toBeInTheDocument()
  })

  it('avisa quando a API está indisponível', async () => {
    montarApp({ rotasApi: rotasAutenticado({ extras: { 'GET /api/versao/': { status: 503, dados: null } } }) })

    expect(await screen.findByText('API indisponível')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Consultar novamente' })).toBeInTheDocument()
  })

  it('o seletor de tema alterna a classe dark', async () => {
    montarApp({ rotasApi: rotasAutenticado() })
    await screen.findByLabelText('Empresa em operação')

    fireEvent.click(screen.getByRole('button', { name: 'Tema escuro' }))

    expect(document.documentElement).toHaveClass('dark')
    expect(window.localStorage.getItem('freenfse-tema')).toBe('escuro')
  })
})
