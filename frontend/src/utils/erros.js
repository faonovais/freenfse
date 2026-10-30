// Mensagens de erro em linguagem simples, a partir da resposta de `http()`.

const POR_CODIGO = {
  nao_autenticado: 'Sua sessão terminou. Entre novamente para continuar.',
  sem_acesso_a_empresa: 'Você não tem acesso a esta empresa.',
  empresa_nao_informada: 'Escolha uma empresa para continuar.',
  empresa_invalida: 'A empresa escolhida não é válida.',
  '2fa_obrigatorio': 'Configure a verificação em duas etapas para continuar.',
  email_password_mismatch: 'E-mail ou senha incorretos.',
  too_many_login_attempts:
    'Muitas tentativas de login sem sucesso. Aguarde alguns minutos e tente novamente.',
  incorrect_code: 'Código incorreto. Confira o aplicativo e tente de novo.',
  invalid: 'Valor inválido.',
  required: 'Campo obrigatório.',
}

// Motivos devolvidos pela tela de login quando o login social é recusado (?erro=...).
export const ERROS_SOCIAIS = {
  nao_cadastrado:
    'Este e-mail não está cadastrado. Peça ao administrador do sistema para criar o seu acesso.',
  dominio_nao_permitido: 'O domínio deste e-mail não é permitido neste sistema.',
  email_nao_verificado: 'O provedor não confirmou o seu e-mail. Use outra forma de entrar.',
  usuario_inativo: 'Seu acesso está desativado. Fale com o administrador do sistema.',
  social: 'Não foi possível entrar com o provedor escolhido. Tente novamente.',
}

const POR_STATUS = {
  0: 'Sem conexão com o servidor. Verifique a internet e tente novamente.',
  401: 'Sua sessão terminou. Entre novamente para continuar.',
  403: 'Você não tem permissão para fazer isto.',
  404: 'Não encontrado.',
  429: 'Muitas tentativas. Aguarde um pouco e tente novamente.',
}

function textos(valor) {
  if (valor == null) return []
  if (typeof valor === 'string') return [valor]
  if (Array.isArray(valor)) return valor.flatMap(textos)
  if (typeof valor === 'object') return Object.values(valor).flatMap(textos)
  return [String(valor)]
}

export function mensagemErro(resposta, padrao = 'Não foi possível concluir a operação.') {
  const { status, dados } = resposta
  if (dados && typeof dados === 'object') {
    // allauth: { errors: [{ message, code, param }] }
    if (Array.isArray(dados.errors) && dados.errors.length > 0) {
      return dados.errors.map((erro) => POR_CODIGO[erro.code] ?? erro.message ?? padrao).join(' ')
    }
    // middleware de empresa / 2FA: { codigo, detalhe }
    if (dados.codigo) return POR_CODIGO[dados.codigo] ?? dados.detalhe ?? padrao
    // DRF: { detail } ou { campo: [mensagens] }
    if (dados.detail) return String(dados.detail)
    const lista = textos(dados)
    if (lista.length > 0 && status >= 400 && status < 500) return lista.join(' ')
  }
  if (status >= 500) return 'Erro no servidor. Tente novamente em instantes.'
  return POR_STATUS[status] ?? padrao
}

// Erros de validação do DRF por campo: { campo: 'mensagem' } (para exibir ao lado do campo).
export function errosPorCampo(resposta) {
  const { dados } = resposta
  if (!dados || typeof dados !== 'object' || Array.isArray(dados) || dados.errors) return {}
  return Object.fromEntries(
    Object.entries(dados)
      .filter(([campo]) => campo !== 'detail' && campo !== 'codigo')
      .map(([campo, valor]) => [campo, textos(valor).join(' ')]),
  )
}
