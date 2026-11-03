import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { limparEmpresaAtiva } from '../../api/empresaAtiva.js'
import { EMPRESA_A, respostaEu } from '../../testes/apiFalsa.js'
import { montarApp, rotasAutenticado } from '../../testes/montarApp.jsx'
import { INTERVALO_DAS_EXPORTACOES } from './Exportacoes.jsx'
import { INTERVALO_DOS_ENVIOS } from './EnviosDaNota.jsx'

afterEach(() => {
  cleanup()
  limparEmpresaAtiva()
  vi.useRealTimers()
})

const ADMIN = {
  ...EMPRESA_A,
  perfil: 'administrador',
  permissoes: [
    'nfse.consultar', 'config.consultar', 'config.editar', 'documentos.consultar', 'documentos.exportar',
    'documentos.enviar',
  ], // prettier-ignore
}
const SO_CONSULTA = {
  ...EMPRESA_A,
  perfil: 'consulta',
  permissoes: ['nfse.consultar', 'config.consultar', 'documentos.consultar'],
}
const SEM_DOCUMENTOS = { ...EMPRESA_A, perfil: 'consulta', permissoes: ['nfse.consultar'] }

const CONFIG_EMAIL = '/api/documentos/config/email/'
const TESTE_EMAIL = '/api/documentos/config/email/teste/'
const CONFIG_DRIVE = '/api/documentos/config/drive/'
const PREVIA_DRIVE = '/api/documentos/config/drive/previa/'
const EXPORTACOES = '/api/documentos/exportacoes/'
const NOTAS = '/api/fiscal/notas/'

const abrir = (rota, extras = {}, empresa = ADMIN) =>
  montarApp({ rota, rotasApi: rotasAutenticado({ eu: respostaEu({ empresas: [empresa] }), extras }) })

const corpoSalvo = (chamadas, caminho) => chamadas.find((c) => c.metodo === 'PUT' && c.caminho === caminho)?.corpo

// ---------------------------------------------------------------------------------------------
// E-mail
// ---------------------------------------------------------------------------------------------

const EMAIL = {
  provedor: 'smtp',
  remetente_email: 'notas@empresa.test',
  remetente_nome: 'Empresa Alfa',
  smtp_host: 'smtp.empresa.test',
  smtp_porta: 587,
  smtp_seguranca: 'starttls',
  smtp_usuario: 'notas@empresa.test',
  graph_tenant_id: '',
  graph_client_id: '',
  credenciais_configuradas: { smtp_senha: true, graph_client_secret: false, gmail_conta_servico: false },
  envio_automatico: false,
  avisar_cancelamento: true,
  anexar_pdf: true,
  anexar_xml: true,
  copias_fixas: ['financeiro@empresa.test'],
  emails_alerta: [],
  assunto_modelo: 'NFS-e nº {numero_nfse}',
  corpo_modelo: 'Olá, {nome_tomador}.',
  variaveis: { numero_nfse: 'Número da NFS-e', nome_tomador: 'Nome do tomador', valor: 'Valor do serviço' },
  opcoes: {
    provedores: [
      { valor: 'nenhum', rotulo: 'Nenhum (e-mail desligado)' },
      { valor: 'smtp', rotulo: 'SMTP' },
      { valor: 'gmail', rotulo: 'Gmail (API, conta de serviço)' },
      { valor: 'graph', rotulo: 'Microsoft 365 (Graph, aplicativo)' },
    ],
    seguranca: [
      { valor: 'starttls', rotulo: 'STARTTLS (porta 587)' },
      { valor: 'ssl', rotulo: 'SSL/TLS direto (porta 465)' },
      { valor: 'nenhuma', rotulo: 'Sem criptografia (não recomendado)' },
    ],
  },
}
const rotaEmail = (extra = {}) => ({ [`GET ${CONFIG_EMAIL}`]: { status: 200, dados: { ...EMAIL, ...extra } } })

describe('Configuração de e-mail', () => {
  it('mostra a configuração sem credencial e avisa que a senha já está guardada', async () => {
    abrir('/documentos/email', rotaEmail())

    expect(await screen.findByLabelText('Provedor de e-mail')).toHaveValue('smtp')
    expect(screen.getByLabelText('Servidor SMTP')).toHaveValue('smtp.empresa.test')
    const senha = screen.getByLabelText('Senha do SMTP')
    expect(senha).toHaveValue('')
    expect(senha).toHaveAttribute('placeholder', expect.stringContaining('Configurada'))
    expect(screen.getByLabelText('Cópias fixas')).toHaveValue('financeiro@empresa.test')
  })

  it('salvar sem digitar a senha não envia a credencial; digitar envia e limpa o campo', async () => {
    const { chamadas } = abrir('/documentos/email', {
      ...rotaEmail(),
      [`PUT ${CONFIG_EMAIL}`]: (c) => ({ status: 200, dados: { ...EMAIL, ...c.corpo, copias_fixas: c.corpo.copias_fixas } }),
    })
    fireEvent.change(await screen.findByLabelText('Nome do remetente'), { target: { value: 'Alfa Serviços' } })

    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))
    await waitFor(() => expect(corpoSalvo(chamadas, CONFIG_EMAIL)).toBeDefined())
    expect(corpoSalvo(chamadas, CONFIG_EMAIL)).not.toHaveProperty('smtp_senha')
    expect(corpoSalvo(chamadas, CONFIG_EMAIL).copias_fixas).toEqual(['financeiro@empresa.test'])

    fireEvent.change(screen.getByLabelText('Senha do SMTP'), { target: { value: 'nova-senha' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))
    await waitFor(() => expect(chamadas.filter((c) => c.metodo === 'PUT')).toHaveLength(2))
    expect(chamadas.filter((c) => c.metodo === 'PUT')[1].corpo.smtp_senha).toBe('nova-senha')
    await waitFor(() => expect(screen.getByLabelText('Senha do SMTP')).toHaveValue(''))
  })

  it('mostra os erros da API ao lado dos campos (variável desconhecida, e-mail inválido)', async () => {
    abrir('/documentos/email', {
      ...rotaEmail(),
      [`PUT ${CONFIG_EMAIL}`]: {
        status: 400,
        dados: { assunto_modelo: 'Variável desconhecida: {xpto}.', copias_fixas: 'E-mail inválido: a@' },
      },
    })
    fireEvent.change(await screen.findByLabelText('Assunto da mensagem'), { target: { value: '{xpto}' } })

    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))

    expect(await screen.findByText('Variável desconhecida: {xpto}.')).toBeInTheDocument()
    expect(screen.getByText('E-mail inválido: a@')).toBeInTheDocument()
  })

  it('troca de provedor mostra só os campos daquele provedor', async () => {
    abrir('/documentos/email', rotaEmail())
    const provedor = await screen.findByLabelText('Provedor de e-mail')

    fireEvent.change(provedor, { target: { value: 'graph' } })
    expect(screen.getByLabelText('ID do tenant (diretório)')).toBeInTheDocument()
    expect(screen.getByLabelText('Segredo do aplicativo')).toBeInTheDocument()
    expect(screen.queryByLabelText('Servidor SMTP')).not.toBeInTheDocument()

    fireEvent.change(provedor, { target: { value: 'gmail' } })
    expect(screen.getByLabelText(/Chave JSON da conta de serviço do Google/)).toBeInTheDocument()

    fireEvent.change(provedor, { target: { value: 'nenhum' } })
    expect(screen.queryByLabelText('E-mail do remetente')).not.toBeInTheDocument()
  })

  it('a chave do Gmail é lida do arquivo e enviada uma vez, sem aparecer na tela', async () => {
    const { chamadas } = abrir('/documentos/email', {
      ...rotaEmail({ provedor: 'gmail' }),
      [`PUT ${CONFIG_EMAIL}`]: { status: 200, dados: { ...EMAIL, provedor: 'gmail', credenciais_configuradas: { ...EMAIL.credenciais_configuradas, gmail_conta_servico: true } } },
    })
    const chave = '{"type":"service_account","client_email":"x@y.test"}'
    const campo = await screen.findByLabelText(/Chave JSON da conta de serviço do Google/)

    fireEvent.change(campo, { target: { files: [new File([chave], 'chave.json', { type: 'application/json' })] } })

    expect(await screen.findByText(/Arquivo carregado: chave\.json/)).toBeInTheDocument()
    expect(screen.queryByText(/service_account/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))
    await waitFor(() => expect(corpoSalvo(chamadas, CONFIG_EMAIL)).toBeDefined())
    expect(corpoSalvo(chamadas, CONFIG_EMAIL).gmail_conta_servico).toBe(chave)
    expect(await screen.findByText(/Já há uma chave guardada \(cifrada\)/)).toBeInTheDocument()
  })

  it('remove a credencial guardada só depois de confirmar (envia null)', async () => {
    const { chamadas } = abrir('/documentos/email', {
      ...rotaEmail(),
      [`PUT ${CONFIG_EMAIL}`]: { status: 200, dados: { ...EMAIL, credenciais_configuradas: { ...EMAIL.credenciais_configuradas, smtp_senha: false } } },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Remover a senha do SMTP' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Remover credencial' }))

    await waitFor(() => expect(corpoSalvo(chamadas, CONFIG_EMAIL)).toEqual({ provedor: 'smtp', smtp_senha: null }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Remover a senha do SMTP' })).not.toBeInTheDocument())
  })

  it('inclui a variável escolhida no texto da mensagem', async () => {
    abrir('/documentos/email', rotaEmail())
    const texto = await screen.findByLabelText('Texto da mensagem')

    fireEvent.click(screen.getByRole('button', { name: '{valor}' }))

    expect(texto.value).toContain('{valor}')
  })

  it('envia o e-mail de teste e mostra o resultado em linguagem simples', async () => {
    const { chamadas } = abrir('/documentos/email', {
      ...rotaEmail(),
      [`POST ${TESTE_EMAIL}`]: { status: 200, dados: { situacao: 'enviado', destinatarios: ['eu@empresa.test'], erro: '' } },
    })

    fireEvent.change(await screen.findByLabelText('Enviar o teste para'), { target: { value: 'eu@empresa.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar e-mail de teste' }))

    expect(await screen.findByText('E-mail de teste enviado para eu@empresa.test.')).toBeInTheDocument()
    expect(chamadas.find((c) => c.caminho === TESTE_EMAIL).corpo).toEqual({ destino: 'eu@empresa.test' })
  })

  it('mostra a falha do teste sem esconder o motivo', async () => {
    abrir('/documentos/email', {
      ...rotaEmail(),
      [`POST ${TESTE_EMAIL}`]: {
        status: 200,
        dados: { situacao: 'falhou', destinatarios: ['eu@empresa.test'], erro: 'O servidor recusou o usuário ou a senha.' },
      },
    })

    fireEvent.change(await screen.findByLabelText('Enviar o teste para'), { target: { value: 'eu@empresa.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar e-mail de teste' }))

    expect(await screen.findByText(/O teste falhou: O servidor recusou o usuário ou a senha\./)).toBeInTheDocument()
  })

  it('o teste fica desligado quando não há provedor', async () => {
    abrir('/documentos/email', rotaEmail({ provedor: 'nenhum' }))

    expect(await screen.findByText('Escolha e salve um provedor de e-mail para poder testar.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar e-mail de teste' })).toBeDisabled()
  })

  it('quem só consulta vê a configuração desabilitada, sem salvar nem testar', async () => {
    abrir('/documentos/email', rotaEmail(), SO_CONSULTA)

    expect(await screen.findByLabelText('Provedor de e-mail')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Salvar configuração' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar e-mail de teste' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Remover/ })).not.toBeInTheDocument()
    expect(screen.getByText('Você pode consultar a configuração de e-mail, mas não alterá-la.')).toBeInTheDocument()
  })

  it('mostra o erro de carga quando a API recusa', async () => {
    abrir('/documentos/email', { [`GET ${CONFIG_EMAIL}`]: { status: 403, dados: { detail: 'Sem permissão.' } } })

    expect(await screen.findByText('Sem permissão.')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Google Drive
// ---------------------------------------------------------------------------------------------

const DRIVE = {
  ativo: true,
  conta_servico_configurada: true,
  conta_servico_email: 'drive@projeto.iam.test',
  pasta_raiz_id: 'RAIZ123',
  pasta_raiz_nome: 'Notas fiscais',
  modelo_subpastas: '{ano}/{mes}',
  modelo_arquivo: 'NFSe_{numero_nfse}_{cnpj_emitente}',
  enviar_automaticamente: true,
  validado_em: '2026-10-30T12:00:00Z',
  variaveis: {
    ano: 'Ano da data de emissão (2026)',
    mes: 'Mês da data de emissão (01 a 12)',
    numero_nfse: 'Número da NFS-e, sem zeros à esquerda',
    cnpj_emitente: 'CNPJ (ou CPF) do prestador, só dígitos',
    chave: 'Chave de acesso (50 dígitos): garante nome único',
  },
}
const rotaDrive = (extra = {}) => ({ [`GET ${CONFIG_DRIVE}`]: { status: 200, dados: { ...DRIVE, ...extra } } })

describe('Configuração do Google Drive', () => {
  it('mostra a pasta confirmada e a conta de serviço, sem a chave', async () => {
    abrir('/documentos/drive', rotaDrive())

    expect(await screen.findByLabelText('ID da pasta raiz no Drive')).toHaveValue('RAIZ123')
    expect(screen.getByText('Notas fiscais', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('drive@projeto.iam.test')).toBeInTheDocument()
    expect(screen.getByLabelText('Modelo das subpastas')).toHaveValue('{ano}/{mes}')
    expect(screen.queryByText(/private_key/)).not.toBeInTheDocument()
  })

  it('a prévia mostra o caminho de uma nota real', async () => {
    const { chamadas } = abrir('/documentos/drive', {
      ...rotaDrive(),
      [`POST ${PREVIA_DRIVE}`]: {
        status: 200,
        dados: {
          previa: {
            pasta: '2026/10',
            arquivos: ['2026/10/NFSe_15_11222333000181.xml', '2026/10/NFSe_15_11222333000181.pdf'],
            evento: '2026/10/NFSe_15_11222333000181_cancelamento.xml',
          },
          nota: 9,
          numero_nfse: '15',
        },
      },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Ver exemplo com uma nota real' }))

    const exemplo = await screen.findByLabelText('Como a nota ficaria no Drive')
    expect(within(exemplo).getByText('2026/10/NFSe_15_11222333000181.pdf')).toBeInTheDocument()
    expect(within(exemplo).getByText(/nota nº 15/)).toBeInTheDocument()
    expect(chamadas.find((c) => c.caminho === PREVIA_DRIVE).corpo).toEqual({
      modelo_subpastas: '{ano}/{mes}',
      modelo_arquivo: 'NFSe_{numero_nfse}_{cnpj_emitente}',
    })
  })

  it('a prévia lista todos os erros dos modelos de uma vez', async () => {
    abrir('/documentos/drive', {
      ...rotaDrive(),
      [`POST ${PREVIA_DRIVE}`]: {
        status: 400,
        dados: {
          modelo_subpastas: ['Variável desconhecida: {xpto}.', 'Chave sem fechar em “{ano”.'],
          modelo_arquivo: ['O nome do arquivo não pode ter “/” nem “\\”.'],
        },
      },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Ver exemplo com uma nota real' }))

    const lista = await screen.findByRole('list', { name: 'Problemas nos modelos' })
    expect(within(lista).getAllByRole('listitem')).toHaveLength(3)
    expect(within(lista).getByText('Variável desconhecida: {xpto}.')).toBeInTheDocument()
  })

  it('a prévia avisa quando ainda não há nota para servir de exemplo', async () => {
    abrir('/documentos/drive', {
      ...rotaDrive(),
      [`POST ${PREVIA_DRIVE}`]: { status: 200, dados: { previa: null, detalhe: 'Ainda não há nota emitida para servir de exemplo.' } },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Ver exemplo com uma nota real' }))

    expect(await screen.findByText('Ainda não há nota emitida para servir de exemplo.')).toBeInTheDocument()
  })

  it('a variável escolhida entra no último campo usado', async () => {
    abrir('/documentos/drive', rotaDrive())
    const arquivo = await screen.findByLabelText('Modelo do nome do arquivo')

    fireEvent.focus(arquivo)
    fireEvent.click(screen.getByRole('button', { name: '{chave}' }))

    expect(arquivo).toHaveValue('NFSe_{numero_nfse}_{cnpj_emitente}{chave}')
    expect(screen.getByLabelText('Modelo das subpastas')).toHaveValue('{ano}/{mes}')
  })

  it('salva sem a chave quando nenhum arquivo foi escolhido', async () => {
    const { chamadas } = abrir('/documentos/drive', {
      ...rotaDrive(),
      [`PUT ${CONFIG_DRIVE}`]: (c) => ({ status: 200, dados: { ...DRIVE, ...c.corpo } }),
    })
    fireEvent.change(await screen.findByLabelText('Modelo das subpastas'), { target: { value: '{ano}' } })

    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))

    await waitFor(() => expect(corpoSalvo(chamadas, CONFIG_DRIVE)).toBeDefined())
    expect(corpoSalvo(chamadas, CONFIG_DRIVE)).not.toHaveProperty('conta_servico')
    expect(corpoSalvo(chamadas, CONFIG_DRIVE).modelo_subpastas).toBe('{ano}')
  })

  it('envia a chave escolhida uma vez e esquece o conteúdo', async () => {
    const { chamadas } = abrir('/documentos/drive', {
      ...rotaDrive({ conta_servico_configurada: false, conta_servico_email: '' }),
      [`PUT ${CONFIG_DRIVE}`]: { status: 200, dados: DRIVE },
    })
    const chave = '{"type":"service_account","client_email":"drive@projeto.iam.test"}'

    fireEvent.change(await screen.findByLabelText(/Chave JSON da conta de serviço do Google/), {
      target: { files: [new File([chave], 'drive.json', { type: 'application/json' })] },
    })
    expect(await screen.findByText(/Arquivo carregado: drive\.json/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))

    await waitFor(() => expect(corpoSalvo(chamadas, CONFIG_DRIVE)?.conta_servico).toBe(chave))
    await waitFor(() => expect(screen.queryByText(/Arquivo carregado/)).not.toBeInTheDocument())
  })

  it('mostra juntos os erros de validação ao salvar (pasta sem acesso, unicidade)', async () => {
    abrir('/documentos/drive', {
      ...rotaDrive(),
      [`PUT ${CONFIG_DRIVE}`]: {
        status: 400,
        dados: {
          pasta_raiz_id: ['A conta de serviço não tem permissão de escrita nesta pasta.'],
          unicidade: ['O caminho completo precisa identificar uma única nota: use {chave}.'],
        },
      },
    })
    fireEvent.change(await screen.findByLabelText('Modelo do nome do arquivo'), { target: { value: 'nota' } })

    fireEvent.click(screen.getByRole('button', { name: 'Salvar configuração' }))

    expect(await screen.findByText('A conta de serviço não tem permissão de escrita nesta pasta.')).toBeInTheDocument()
    expect(screen.getByText('O caminho completo precisa identificar uma única nota: use {chave}.')).toBeInTheDocument()
  })

  it('reenvia um período ao Drive e informa quantas notas entraram na fila', async () => {
    const { chamadas } = abrir('/documentos/drive', {
      ...rotaDrive(),
      'POST /api/documentos/drive/reenviar-periodo/': { status: 202, dados: { enfileiradas: 12 } },
    })

    const formulario = await screen.findByRole('form', { name: 'Reenviar um período ao Drive' })
    fireEvent.change(within(formulario).getByLabelText('De'), { target: { value: '2026-10-01' } })
    fireEvent.change(within(formulario).getByLabelText('Até'), { target: { value: '2026-10-31' } })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Reenviar notas do período' }))

    expect(await screen.findByText(/12 nota\(s\) na fila para o Drive/)).toBeInTheDocument()
    expect(chamadas.find((c) => c.caminho === '/api/documentos/drive/reenviar-periodo/').corpo).toEqual({
      periodo_inicio: '2026-10-01',
      periodo_fim: '2026-10-31',
    })
  })

  it('quem só consulta não vê o salvar nem o reenvio do período', async () => {
    abrir('/documentos/drive', rotaDrive(), SO_CONSULTA)

    expect(await screen.findByLabelText('ID da pasta raiz no Drive')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Salvar configuração' })).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Reenviar um período ao Drive' })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Envios da nota
// ---------------------------------------------------------------------------------------------

const NOTA = {
  id: 9, situacao: 'autorizada', numero_nfse: '15', numero_dps: 3, serie: 900, competencia: '2026-10-01',
  emitida_em: '2026-11-02T15:00:00Z', ambiente: 'producao_restrita', mensagem: '', substitui: null,
  chave: '2'.repeat(50), leiaute_descricao: 'NT 009 v1.01', erros: [], substituta: null, substitui_numero: '',
  tomador: { nome: 'TOMADOR FICTICIO LTDA', documento: '11222333000281' },
  servico: { nome: 'Consultoria', codigo_tributacao_nacional: '170101' },
  totais: { valor_servico: '1500.00', base_calculo: '1500.00', aliquota_iss: '2.00', valor_iss: '30.00', total_retencoes: '0.00', valor_liquido: '1500.00' },
  eventos: [], historico: [],
  acoes: { editar: false, emitir: false, consultar: true, conferir: false, cancelar: false, substituir: false, baixar_xml: true, danfse: true },
} // prettier-ignore
const ENVIOS = '/api/documentos/notas/9/envios/'
const ENVIOS_DA_NOTA = {
  emails: [
    {
      id: 5, tipo: 'autorizacao', tipo_rotulo: 'Ao autorizar', situacao: 'falhou', situacao_rotulo: 'Falhou',
      destinatarios: ['cli@tomador.test'], copias: ['financeiro@empresa.test'], assunto: 'NFS-e nº 15',
      anexos: ['nfse-15.xml', 'danfse-15.pdf'], tentativas: 5, proxima_tentativa: null,
      erro: 'O servidor de e-mail recusou a mensagem. Confira a senha em Configuração › E-mail.',
      enviado_em: null, criado_em: '2026-11-02T15:01:00Z', criado_por_email: '',
    },
    {
      id: 4, tipo: 'manual', tipo_rotulo: 'Envio manual', situacao: 'enviado', situacao_rotulo: 'Enviado',
      destinatarios: ['cli@tomador.test'], copias: [], assunto: 'NFS-e nº 15', anexos: ['nfse-15.xml'],
      tentativas: 1, proxima_tentativa: null, erro: '', enviado_em: '2026-11-02T14:00:00Z',
      criado_em: '2026-11-02T13:59:00Z', criado_por_email: 'ana@example.com',
    },
  ],
  drive: [
    {
      id: 1, papel: 'xml', situacao: 'enviado', situacao_rotulo: 'Enviado', caminho: '2026/11/NFSe_15.xml',
      nome: 'NFSe_15.xml', tentativas: 1, proxima_tentativa: null, erro: '', aviso: '', enviado_em: '2026-11-02T15:02:00Z',
    },
    {
      id: 2, papel: 'pdf', situacao: 'enviado', situacao_rotulo: 'Enviado', caminho: '2026/11/NFSe_15 (2).pdf',
      nome: 'NFSe_15 (2).pdf', tentativas: 1, proxima_tentativa: null, erro: '',
      aviso: 'Já existia outro arquivo com este nome na pasta; este foi salvo como “(2)”.',
      enviado_em: '2026-11-02T15:02:00Z',
    },
  ],
  destinatarios_padrao: ['cli@tomador.test'],
  email_configurado: true,
  drive_ativo: true,
} // prettier-ignore
const rotasNota = (envios = ENVIOS_DA_NOTA, nota = NOTA) => ({
  [`GET ${NOTAS}9/`]: { status: 200, dados: nota },
  [`GET ${ENVIOS}`]: { status: 200, dados: envios },
})

describe('Envios da nota', () => {
  it('mostra o histórico de e-mails com o motivo da falha e a situação da cópia ao Drive', async () => {
    abrir('/fiscal/notas/9', rotasNota())

    const secao = await screen.findByRole('region', { name: 'Envios da nota' })
    const emails = within(await within(secao).findByRole('list', { name: 'Histórico de e-mails' })).getAllByRole('listitem')
    expect(emails).toHaveLength(2)
    expect(within(emails[0]).getByText('Falhou')).toBeInTheDocument()
    expect(within(emails[0]).getByText(/Confira a senha em Configuração › E-mail/)).toBeInTheDocument()
    expect(within(emails[0]).getByText(/nfse-15\.xml, danfse-15\.pdf/)).toBeInTheDocument()
    const arquivos = within(secao).getByRole('list', { name: 'Arquivos no Drive' })
    expect(within(arquivos).getByText('2026/11/NFSe_15 (2).pdf')).toBeInTheDocument()
    expect(within(arquivos).getByText(/foi salvo como “\(2\)”/)).toBeInTheDocument()
  })

  it('a seção não existe sem a permissão de consultar documentos (nem chama a API)', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', rotasNota(), SEM_DOCUMENTOS)

    expect(await screen.findByRole('heading', { name: 'Nota nº 15' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Envios da nota' })).not.toBeInTheDocument()
    expect(chamadas.some((c) => c.caminho.startsWith('/api/documentos/'))).toBe(false)
  })

  it('rascunho e nota rejeitada não têm envios', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', rotasNota(ENVIOS_DA_NOTA, { ...NOTA, situacao: 'rejeitada' }))

    expect(await screen.findByRole('heading', { name: 'Nota nº 15' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Envios da nota' })).not.toBeInTheDocument()
    expect(chamadas.some((c) => c.caminho === ENVIOS)).toBe(false)
  })

  it('envia por e-mail aos destinatários padrão e, se informados, aos digitados', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', {
      ...rotasNota(),
      'POST /api/documentos/notas/9/email/': { status: 202, dados: { id: 6, situacao: 'pendente' } },
    })
    const formulario = await screen.findByRole('form', { name: 'Enviar por e-mail' })
    expect(within(formulario).getByText(/Sem preencher, vai para: cli@tomador\.test/)).toBeInTheDocument()

    fireEvent.click(within(formulario).getByRole('button', { name: 'Enviar por e-mail' }))
    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho.endsWith('/9/email/'))).toBe(true))
    expect(chamadas.find((c) => c.caminho.endsWith('/9/email/')).corpo).toEqual({})

    fireEvent.change(within(formulario).getByLabelText('Destinatários (opcional)'), {
      target: { value: 'a@x.test, b@y.test' },
    })
    fireEvent.click(within(formulario).getByRole('button', { name: 'Enviar por e-mail' }))
    await waitFor(() => expect(chamadas.filter((c) => c.caminho.endsWith('/9/email/'))).toHaveLength(2))
    expect(chamadas.filter((c) => c.caminho.endsWith('/9/email/'))[1].corpo).toEqual({ destinatarios: ['a@x.test', 'b@y.test'] })
  })

  it('mostra a recusa do servidor ao enviar (por exemplo, e-mail não configurado)', async () => {
    abrir('/fiscal/notas/9', {
      ...rotasNota(),
      'POST /api/documentos/notas/9/email/': {
        status: 409,
        dados: { codigo: 'email_recusado', detalhe: 'O tomador não tem e-mail cadastrado.' },
      },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Enviar por e-mail' }))

    expect(await screen.findByText('O tomador não tem e-mail cadastrado.')).toBeInTheDocument()
  })

  it('reenvia um e-mail do histórico', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', {
      ...rotasNota(),
      'POST /api/documentos/envios-email/5/reenviar/': { status: 202, dados: { id: 7, situacao: 'pendente' } },
    })
    const historico = await screen.findByRole('list', { name: 'Histórico de e-mails' })

    fireEvent.click(within(within(historico).getAllByRole('listitem')[0]).getByRole('button', { name: 'Reenviar' }))

    expect(await screen.findByText('Reenvio na fila.')).toBeInTheDocument()
    expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho === '/api/documentos/envios-email/5/reenviar/')).toBe(true)
  })

  it('reenvia a nota ao Drive', async () => {
    const { chamadas } = abrir('/fiscal/notas/9', {
      ...rotasNota(),
      'POST /api/documentos/notas/9/drive/reenviar/': { status: 202, dados: { enfileirada: true } },
    })

    fireEvent.click(await screen.findByRole('button', { name: 'Reenviar ao Drive' }))

    expect(await screen.findByText('Cópia ao Drive na fila.')).toBeInTheDocument()
    expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho.endsWith('/9/drive/reenviar/'))).toBe(true)
  })

  it('quem só consulta vê o histórico, mas não os botões de enviar e reenviar', async () => {
    abrir('/fiscal/notas/9', rotasNota(), SO_CONSULTA)

    expect(await screen.findByRole('list', { name: 'Histórico de e-mails' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reenviar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Enviar por e-mail' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reenviar ao Drive' })).not.toBeInTheDocument()
  })

  it('avisa e leva à configuração quando e-mail e Drive não estão ativos', async () => {
    abrir('/fiscal/notas/9', rotasNota({ ...ENVIOS_DA_NOTA, emails: [], drive: [], email_configurado: false, drive_ativo: false }))

    expect(await screen.findByText(/O e-mail da empresa ainda não está configurado/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Configurar e-mail' })).toHaveAttribute('href', '/documentos/email')
    expect(screen.getByRole('link', { name: 'Configurar o Drive' })).toHaveAttribute('href', '/documentos/drive')
    expect(screen.queryByRole('form', { name: 'Enviar por e-mail' })).not.toBeInTheDocument()
  })

  it('acompanha sozinha enquanto há envio na fila', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let consultas = 0
    const fila = { ...ENVIOS_DA_NOTA.emails[1], id: 8, situacao: 'pendente', situacao_rotulo: 'Na fila', tentativas: 0, enviado_em: null }
    abrir('/fiscal/notas/9', {
      ...rotasNota(),
      [`GET ${ENVIOS}`]: () => {
        consultas += 1
        return {
          status: 200,
          dados: { ...ENVIOS_DA_NOTA, emails: consultas < 3 ? [fila] : [{ ...fila, situacao: 'enviado', situacao_rotulo: 'Enviado' }] },
        }
      },
    })
    expect(await screen.findByText('Na fila')).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DOS_ENVIOS + 100))
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DOS_ENVIOS + 100))

    const historico = screen.getByRole('list', { name: 'Histórico de e-mails' })
    expect(await within(historico).findByText('Enviado')).toBeInTheDocument()
    expect(screen.queryByText('Na fila')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Download em lote
// ---------------------------------------------------------------------------------------------

const PEDIDO = {
  id: 3, situacao: 'pronta', situacao_rotulo: 'Pronta para baixar', filtros: { competencia: '2026-10' },
  total: 4, processadas: 4, tamanho_bytes: 2048, nome_download: 'notas-3.zip', erro: '',
  avisos: ['Nota 12: o PDF não pôde ser gerado agora.'], criado_em: '2026-11-02T10:00:00Z',
  concluido_em: '2026-11-02T10:01:00Z', expira_em: '2026-11-03T10:01:00Z',
} // prettier-ignore

describe('Download em lote', () => {
  it('lista os pedidos do usuário com tamanho, validade e avisos', async () => {
    abrir('/documentos/exportacoes', { [`GET ${EXPORTACOES}`]: { status: 200, dados: [PEDIDO] } })

    const lista = await screen.findByRole('list', { name: 'Downloads em lote' })
    expect(within(lista).getByText('Lote nº 3')).toBeInTheDocument()
    expect(within(lista).getByText('Competência 2026-10')).toBeInTheDocument()
    expect(within(lista).getByRole('button', { name: 'Baixar ZIP (2.0 KB)' })).toBeInTheDocument()
    expect(within(lista).getByText('1 aviso(s) sobre notas deste lote')).toBeInTheDocument()
  })

  it('pede o lote com os filtros preenchidos e mostra o pedido na lista', async () => {
    const { chamadas } = abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: { status: 200, dados: [] },
      [`POST ${EXPORTACOES}`]: {
        status: 202,
        dados: { ...PEDIDO, id: 4, situacao: 'pendente', situacao_rotulo: 'Na fila', processadas: 0, filtros: { competencia: '2026-10', tomador: 'ACME' } },
      },
    })
    expect(await screen.findByText('Você ainda não pediu nenhum download em lote.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Competência'), { target: { value: '2026-10' } })
    fireEvent.change(screen.getByLabelText('Tomador'), { target: { value: 'ACME' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gerar arquivo ZIP' }))

    expect(await screen.findByText('Lote nº 4')).toBeInTheDocument()
    expect(chamadas.find((c) => c.metodo === 'POST' && c.caminho === EXPORTACOES).corpo).toEqual({
      competencia: '2026-10',
      tomador: 'ACME',
    })
  })

  it('só envia a situação quando o usuário restringe (todas marcadas = sem filtro)', async () => {
    const { chamadas } = abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: { status: 200, dados: [] },
      [`POST ${EXPORTACOES}`]: { status: 202, dados: { ...PEDIDO, id: 5, situacao: 'pendente', situacao_rotulo: 'Na fila' } },
    })
    await screen.findByText('Você ainda não pediu nenhum download em lote.')

    fireEvent.click(screen.getByRole('checkbox', { name: 'Substituída' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Cancelada' }))
    fireEvent.click(screen.getByRole('button', { name: 'Gerar arquivo ZIP' }))

    await waitFor(() => expect(chamadas.some((c) => c.metodo === 'POST' && c.caminho === EXPORTACOES)).toBe(true))
    expect(chamadas.find((c) => c.metodo === 'POST').corpo).toEqual({ situacao: ['autorizada'] })
  })

  it('mostra a recusa do limite do lote em linguagem simples', async () => {
    abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: { status: 200, dados: [] },
      [`POST ${EXPORTACOES}`]: {
        status: 400,
        dados: { codigo: 'lote_recusado', detalhe: 'Estes filtros reúnem 900 notas e o limite de um lote é 500. Reduza o período.' },
      },
    })
    await screen.findByText('Você ainda não pediu nenhum download em lote.')

    fireEvent.click(screen.getByRole('button', { name: 'Gerar arquivo ZIP' }))

    expect(await screen.findByText(/o limite de um lote é 500/)).toBeInTheDocument()
  })

  it('acompanha o progresso e avisa na tela quando o arquivo fica pronto', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let consultas = 0
    abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: () => {
        consultas += 1
        const pedido =
          consultas === 1
            ? { ...PEDIDO, situacao: 'gerando', situacao_rotulo: 'Gerando', processadas: 1, tamanho_bytes: null }
            : consultas === 2
              ? { ...PEDIDO, situacao: 'gerando', situacao_rotulo: 'Gerando', processadas: 3, tamanho_bytes: null }
              : PEDIDO
        return { status: 200, dados: [pedido] }
      },
    })
    const barra = await screen.findByRole('progressbar', { name: 'Progresso do lote nº 3' })
    expect(barra).toHaveAttribute('value', '1')
    expect(screen.getByText('1 de 4 nota(s) processada(s).')).toBeInTheDocument()

    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DAS_EXPORTACOES + 100))
    expect(await screen.findByText('3 de 4 nota(s) processada(s).')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DAS_EXPORTACOES + 100))

    expect(await screen.findByText('O download em lote nº 3 está pronto para baixar.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Baixar ZIP/ })).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('avisa quando o lote não pôde ser gerado e mostra o motivo', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let consultas = 0
    abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: () => {
        consultas += 1
        return {
          status: 200,
          dados: [
            consultas === 1
              ? { ...PEDIDO, situacao: 'pendente', situacao_rotulo: 'Na fila', processadas: 0 }
              : { ...PEDIDO, situacao: 'falhou', situacao_rotulo: 'Falhou', erro: 'O lote passou do limite de 200 MB.' },
          ],
        }
      },
    })
    await screen.findByRole('progressbar')

    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_DAS_EXPORTACOES + 100))

    expect(await screen.findByText('O download em lote nº 3 não pôde ser gerado.')).toBeInTheDocument()
    expect(screen.getByText('O lote passou do limite de 200 MB.')).toBeInTheDocument()
  })

  it('baixa o ZIP pela API com a empresa da aba', async () => {
    const { chamadas } = abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: { status: 200, dados: [PEDIDO] },
      [`GET ${EXPORTACOES}3/download/`]: { status: 200, dados: null, blob: new Blob(['zip']) },
    })

    fireEvent.click(await screen.findByRole('button', { name: /Baixar ZIP/ }))

    await waitFor(() => expect(chamadas.some((c) => c.caminho === `${EXPORTACOES}3/download/`)).toBe(true))
  })

  it('explica quando o arquivo já expirou', async () => {
    abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: { status: 200, dados: [PEDIDO] },
      [`GET ${EXPORTACOES}3/download/`]: { status: 409, dados: { codigo: 'download_indisponivel' } },
    })

    fireEvent.click(await screen.findByRole('button', { name: /Baixar ZIP/ }))

    expect(await screen.findByText('Este download expirou ou já não está disponível. Peça um novo.')).toBeInTheDocument()
  })

  it('pedido expirado mostra o porquê e não oferece o download', async () => {
    abrir('/documentos/exportacoes', {
      [`GET ${EXPORTACOES}`]: { status: 200, dados: [{ ...PEDIDO, situacao: 'expirada', situacao_rotulo: 'Expirada' }] },
    })

    expect(await screen.findByText(/O arquivo foi apagado depois do prazo de guarda/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Baixar ZIP/ })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------------------------
// Menu
// ---------------------------------------------------------------------------------------------

describe('Menu de documentos', () => {
  const extras = {
    [`GET ${EXPORTACOES}`]: { status: 200, dados: [] },
    [`GET ${CONFIG_EMAIL}`]: { status: 200, dados: EMAIL },
  }

  it('mostra download em lote e as configurações a quem tem as permissões', async () => {
    abrir('/', extras)

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    expect(within(menu).getByRole('link', { name: 'Download em lote' })).toHaveAttribute('href', '/documentos/exportacoes')
    expect(within(menu).getByRole('link', { name: 'E-mail da empresa' })).toHaveAttribute('href', '/documentos/email')
    expect(within(menu).getByRole('link', { name: 'Google Drive' })).toHaveAttribute('href', '/documentos/drive')
  })

  it('não mostra nada de documentos a quem não tem permissão', async () => {
    abrir('/', extras, SEM_DOCUMENTOS)

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    expect(within(menu).queryByRole('link', { name: 'Download em lote' })).not.toBeInTheDocument()
    expect(within(menu).queryByRole('link', { name: 'E-mail da empresa' })).not.toBeInTheDocument()
    expect(within(menu).queryByRole('link', { name: 'Google Drive' })).not.toBeInTheDocument()
  })

  it('quem consulta documentos, mas não exporta, não vê o download em lote', async () => {
    abrir('/', extras, SO_CONSULTA)

    const menu = await screen.findByRole('navigation', { name: 'Menu principal' })
    expect(within(menu).queryByRole('link', { name: 'Download em lote' })).not.toBeInTheDocument()
    expect(within(menu).getByRole('link', { name: 'E-mail da empresa' })).toBeInTheDocument()
  })
})
