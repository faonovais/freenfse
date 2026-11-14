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

  it('exibe o link "Emissão" apontando para /fiscal/notas no menu de notas fiscais', async () => {
    montarApp({ rotasApi: rotasAutenticado() })

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    expect(within(menu).getByRole('link', { name: 'Emissão' })).toHaveAttribute('href', '/fiscal/notas')
    expect(within(menu).queryByRole('link', { name: 'NFS-e emitidas' })).not.toBeInTheDocument()
  })

  it('posiciona o menu Administração logo após o menu Cadastros', async () => {
    const empresaCompleta = {
      ...EMPRESA_A,
      permissoes: ['nfse.consultar', 'cadastro.consultar', 'config.consultar'],
    }
    montarApp({ rotasApi: rotasAutenticado({ eu: respostaEu({ master: true, empresas: [empresaCompleta] }) }) })

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    const grupos = Array.from(menu.querySelectorAll('.titulo-grupo-menu')).map((item) => item.textContent)
    expect(grupos).toEqual([
      'Notas fiscais',
      'Agendamentos',
      'Cadastros',
      'Administração',
      'Configurações',
      'Conta',
    ])

    const links = Array.from(menu.querySelectorAll('a')).map((item) => item.textContent)
    expect(links.indexOf('Empresas')).toBe(links.indexOf('Serviços') + 1)
    expect(links.indexOf('Geral')).toBe(links.indexOf('Vínculos') + 1)
    expect(links.indexOf('Fiscal')).toBe(links.indexOf('Geral') + 1)
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

  it('mantém título, logo e seletor alinhados na mesma linha sem quebrar a linha interna', async () => {
    const empresaNomeLongo = {
      ...EMPRESA_A,
      razao_social: 'Empresa Alfa com Razão Social Muito Longa Para Caber Sem Truncar Ltda',
    }
    montarApp({
      rotasApi: rotasAutenticado({
        eu: respostaEu({ empresas: [empresaNomeLongo, EMPRESA_B] }),
        extras: {
          'GET /api/fiscal/identidade/': {
            status: 200,
            dados: { ...IDENTIDADE_PADRAO.dados, logo: { claro: 'abc123' } },
          },
          'GET /api/fiscal/logo/claro/': { status: 200, blob: new Blob(['x'], { type: 'image/png' }) },
        },
      }),
    })

    const imagem = await screen.findByRole('img', { name: `Logo de ${empresaNomeLongo.razao_social}` })
    const cabecalho = imagem.closest('header')
    const linhaExterna = cabecalho.firstElementChild
    const areaEmpresa = screen.getByLabelText('Empresa em operação')
    const seletor = screen.getByRole('combobox', { name: 'Empresa ativa' })

    expect(linhaExterna).toHaveClass('md:flex-nowrap')
    expect(imagem).toHaveClass('shrink-0')
    expect(areaEmpresa.parentElement).not.toHaveClass('flex-wrap')
    expect(areaEmpresa).toHaveClass('min-w-0', 'truncate')
    expect(seletor).toHaveClass('overflow-hidden')
    expect(seletor.firstElementChild).toHaveClass('min-w-0', 'flex-1', 'truncate')
  })

  it('mostra Nome para exibição como rótulo principal e razão social com CNPJ como detalhe no seletor', async () => {
    const comApelido = { ...EMPRESA_A, nome_exibicao: 'Grupo Alfa' }
    const semApelido = { ...EMPRESA_B, nome_exibicao: '' }
    montarApp({
      rotasApi: rotasAutenticado({
        eu: respostaEu({ master: true, empresas: [comApelido, semApelido] }),
      }),
    })

    const seletor = await screen.findByRole('combobox', { name: 'Empresa ativa' })
    expect(seletor).toHaveTextContent('Grupo Alfa')
    expect(seletor).not.toHaveTextContent('Empresa Alfa Ltda')

    fireEvent.click(seletor)
    const opcoes = await screen.findAllByRole('option')
    expect(opcoes[0]).toHaveTextContent('Grupo Alfa')
    expect(opcoes[0]).toHaveTextContent('Empresa Alfa Ltda · 11.222.333/0001-81')
    expect(opcoes[1]).toHaveTextContent('Empresa Beta S.A.')
    expect(opcoes[1]).toHaveTextContent('11.444.777/0001-61')

    const detalhe = within(opcoes[0]).getByText('Empresa Alfa Ltda · 11.222.333/0001-81')
    expect(detalhe).toHaveClass('text-xs', 'text-gray-600')
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

  it('o menu mostra Cadastros e Configurações conforme as permissões da empresa ativa', async () => {
    const admin = {
      ...EMPRESA_A,
      permissoes: ['cadastro.consultar', 'cadastro.editar', 'config.consultar', 'config.editar'],
    }
    const consulta = { ...EMPRESA_B, permissoes: ['nfse.consultar'] }
    montarApp({ rotasApi: rotasAutenticado({ eu: respostaEu({ empresas: [admin, consulta] }) }) })
    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    for (const nome of ['Pessoas', 'Serviços', 'Geral', 'Fiscal']) {
      expect(within(menu).getByRole('link', { name: nome })).toBeInTheDocument()
    }

    await trocarEmpresaPara('Empresa Beta')

    await waitFor(() => expect(within(menu).queryByRole('link', { name: 'Pessoas' })).not.toBeInTheDocument())
    expect(within(menu).queryByRole('link', { name: 'Geral' })).not.toBeInTheDocument()
    expect(within(menu).queryByRole('link', { name: 'Fiscal' })).not.toBeInTheDocument()
  })

  it('Configurações gerais agrupa Logo, E-mail e Google Drive em abas', async () => {
    const admin = {
      ...EMPRESA_A,
      permissoes: ['config.consultar', 'config.editar'],
    }
    montarApp({
      rota: '/configuracoes/geral',
      rotasApi: rotasAutenticado({
        eu: respostaEu({ empresas: [admin] }),
        extras: {
          'GET /api/documentos/config/email/': {
            status: 200,
            dados: {
              provedor: 'smtp',
              remetente_email: 'notas@alfa.test',
              remetente_nome: 'Alfa',
              smtp_host: 'smtp.alfa.test',
              smtp_porta: 587,
              smtp_seguranca: 'starttls',
              smtp_usuario: 'notas@alfa.test',
              credenciais_configuradas: {},
              copias_fixas: [],
              emails_alerta: [],
              variaveis: {},
              opcoes: {
                provedores: [{ valor: 'smtp', rotulo: 'SMTP próprio' }],
                seguranca: [{ valor: 'starttls', rotulo: 'STARTTLS' }],
              },
            },
          },
          'GET /api/documentos/config/drive/': {
            status: 200,
            dados: {
              ativo: false,
              pasta_raiz_id: '',
              modelo_subpastas: '{ano}/{mes}',
              modelo_arquivo: '{chave}',
              enviar_automaticamente: false,
              variaveis: {},
            },
          },
        },
      }),
    })

    expect(await screen.findByRole('heading', { name: 'Configurações gerais' })).toBeInTheDocument()
    const abaLogo = screen.getByRole('tab', { name: 'Logo da empresa' })
    const abaEmail = screen.getByRole('tab', { name: 'E-mail da empresa' })
    const abaDrive = screen.getByRole('tab', { name: 'Google Drive' })
    expect(abaLogo).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: /Logo da empresa/ })).toBeInTheDocument()

    fireEvent.click(abaEmail)
    expect(abaEmail).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByLabelText('E-mail do remetente')).toHaveValue('notas@alfa.test')

    fireEvent.click(abaDrive)
    expect(abaDrive).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('heading', { name: 'Google Drive da empresa' })).toBeInTheDocument()
  })

  it('Configurações fiscais agrupa Parâmetros fiscais, Certificado A1 e Serviços oficiais em abas acessíveis', async () => {
    const admin = {
      ...EMPRESA_A,
      permissoes: ['config.consultar', 'config.editar'],
    }
    montarApp({
      rota: '/configuracoes/fiscal',
      rotasApi: rotasAutenticado({
        eu: respostaEu({ empresas: [admin] }),
        extras: {
          'GET /api/fiscal/parametros/': {
            status: 200,
            dados: {
              regime_tributario: 'simples_nacional',
              regime_apuracao_simples: 1,
              regime_especial: 0,
              serie_dps: 1,
              ambiente: 'producao_restrita',
              codigo_municipio_emissor: '2101400',
              ibs_cbs_indicador_destinatario: 0,
              municipio_emissor: 'Balsas/MA',
              convenio: null,
              opcoes: {
                regime_tributario: [{ valor: 'simples_nacional', rotulo: 'Simples Nacional' }],
                regime_apuracao_simples: [{ valor: 1, rotulo: 'Simples' }],
                regime_especial: [{ valor: 0, rotulo: 'Nenhum' }],
                ambiente: [{ valor: 'producao_restrita', rotulo: 'Produção restrita' }],
              },
            },
          },
          'GET /api/cadastros/municipios/': { status: 200, dados: [] },
          'GET /api/fiscal/certificado/': { status: 200, dados: { existe: false } },
        },
      }),
    })

    expect(await screen.findByRole('heading', { name: 'Configurações fiscais' })).toBeInTheDocument()
    const abaParametros = screen.getByRole('tab', { name: 'Parâmetros fiscais' })
    const abaCertificado = screen.getByRole('tab', { name: 'Certificado A1' })
    const abaServicos = screen.getByRole('tab', { name: 'Serviços oficiais' })
    expect(abaParametros).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByLabelText('Série da DPS')).toHaveValue(1)

    fireEvent.click(abaCertificado)
    expect(abaCertificado).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText(/ainda não tem certificado digital/i)).toBeInTheDocument()

    fireEvent.keyDown(abaCertificado, { key: 'ArrowRight' })
    expect(abaServicos).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('heading', { name: 'Serviços oficiais' })).toBeInTheDocument()
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
