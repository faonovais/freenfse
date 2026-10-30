# ADR 0002 — Acesso, empresas e segurança (Fase 1)

- **Status:** aceita
- **Data:** 2026-10-30
- **Decisões relacionadas:** D8 (autenticação), D10 (empresa por requisição), D22 (papéis e perfis), D23 (sem autocadastro) em `docs/analise-requisitos.md`; Fase 1 em `docs/plano-implementacao.md`

## Contexto

A Fase 1 entrega login, isolamento entre empresas, permissões e criptografia. Várias escolhas não estavam fechadas no plano; esta ADR registra o que foi decidido, o motivo e o que ficou de fora de propósito.

## Decisões

### 1. Empresa ativa por requisição, nunca por sessão

- A SPA envia `X-Empresa: <id numérico>` em cada chamada; a empresa ativa fica no `sessionStorage` **da aba**. Duas abas na mesma sessão operam empresas diferentes sem interferir.
- `EmpresaPorCabecalhoMiddleware` (último da cadeia) valida o vínculo ativo (ou Master) e só então ativa o schema. Qualquer rota `/api/` fora de `/api/versao/`, `/api/eu/` e `/api/admin-global/` exige empresa: **o padrão é negar**, então uma rota nova de tenant já nasce protegida.
- Respostas: sem cabeçalho → 400 `empresa_nao_informada`; não numérico → 400 `empresa_invalida`; anônimo → 401 `nao_autenticado`; sem vínculo, empresa inexistente ou inativa → **a mesma** 403 `sem_acesso_a_empresa`. Não distinguir os três casos impede que um usuário descubra quais empresas existem. A negação é auditada (`ACESSO_NEGADO`).
- Alternativas descartadas: empresa na sessão (uma aba troca a empresa da outra: risco de emitir no CNPJ errado) e subdomínio por empresa (exige DNS/certificado curinga, inviável em instalações pequenas).

### 2. Usuário global, acesso por vínculo, perfis em código

- `Usuario` fica no schema público e não conhece empresa. O acesso é `VinculoUsuarioEmpresa` (único por par), com perfil e listas de permissões extras e removidas.
- Perfis (Administrador, Emissor, Financeiro, Consulta) e o catálogo de permissões vivem **em código** (`core/permissoes.py`), não no banco. Motivo: permissão nova nasce junto com a operação que protege, é versionada e revisada em PR, e não há como um perfil apontar para uma permissão que o código desconhece. Custo: perfis personalizados por cliente exigem ajustar o vínculo (extras/removidas) em vez de criar um perfil novo. Se a demanda por perfis customizados aparecer, a migração para tabela é localizada em `permissoes_do_perfil`.
- O Master tem todas as permissões em qualquer empresa **ativa**, sem vínculo, e o acesso é marcado como `master` na auditoria.
- `PermissaoPorOperacao` **falha fechado**: operação sem entrada em `permissao_requerida` é negada, inclusive para o Master. Esquecer de declarar a permissão de uma ação nunca a deixa aberta.

### 3. Dados de cadastro

- **CNPJ alfanumérico** (IN RFB 2.229/2024, a partir de 2026) é aceito e validado; o CNPJ é **imutável** depois da criação (o nome do schema deriva dele e há certificado e notas associados).
- **Sem exclusão** de empresas, usuários e vínculos pela API: desativa-se. O histórico fiscal e a auditoria referenciam essas linhas.
- O Master não pode desativar nem rebaixar a si mesmo (evita trancar o sistema).
- A criação do schema da empresa é **síncrona** na requisição (segundos, e é uma operação rara e administrativa). Se passar a ser lenta, mover para task Celery.

### 4. Autenticação

- `django-allauth` headless, cliente `browser` (sessão por cookie + CSRF; a SPA e a API têm a mesma origem). Não há JWT: o cookie `HttpOnly` não é legível por scripts e a revogação é imediata no servidor.
- **Sem autocadastro**, nem social. O adapter de conta fecha o `signup`; o adapter social só **vincula** o login a um usuário já cadastrado e ativo, e só aceita e-mail **verificado** pelo provedor (e domínio permitido, se configurado). A recusa redireciona para `/login?erro=<motivo>` e é auditada.
- Bloqueio: 5 falhas por e-mail em 15 minutos (e 10/min por IP) via `ACCOUNT_RATE_LIMITS` do allauth, com contadores no Redis. Sessão expira por **inatividade** (30 min, renovada a cada requisição).
- **O login social respeita o 2FA** (decisão e prova). O Google confirma a identidade, mas não substitui o segundo fator: o retorno do provedor passa pelas mesmas etapas de login do allauth (`perform_login` → `AuthenticateStage`). Para quem tem TOTP ativo, a sessão continua **anônima**, com a etapa `mfa_authenticate` pendente, até o código (ou um código de recuperação) ser validado em `/_allauth/browser/v1/auth/2fa/authenticate`. Isso vale para o Master e para as duas portas sociais do allauth headless: o retorno OAuth (`/accounts/google/login/callback/`) e o login por token (`/auth/provider/token`). Como o allauth já desafia, **não foi escrito desafio próprio nem recusa ao login social**; em vez disso, `core/tests/test_login_social_2fa.py` percorre o fluxo real (rotas, sessão e etapas) com o Google simulado e prova: sem código, `meta.is_authenticated` é falso, `/api/eu/` responde 403 e nenhum `LOGIN` é auditado; código errado não abre a sessão; código certo abre e audita; o controle sem TOTP entra direto; o Master sem TOTP entra, mas só alcança a tela de configuração (`2fa_obrigatorio`). Remover o desafio (mutação em `AuthenticateStage._should_handle`) reprova 8 dos 13 testes. Um teste também garante que "confiar neste navegador" (`MFA_TRUST_ENABLED`) segue desligado, pois ele dispensaria o código no login social. A SPA lê o estado pendente da sessão (`flows[].is_pending`) e abre a tela de login já no passo do código. Dependência: o comportamento é do allauth; os testes são a trava contra uma atualização que o altere.
- 2FA TOTP + códigos de recuperação. **Obrigatório para o Master por padrão** (`AUTH_EXIGIR_2FA_MASTER`) e opcionalmente para todos (`AUTH_EXIGIR_2FA_TODOS`). `Exigir2FAMiddleware` bloqueia a API com 403 `2fa_obrigatorio` enquanto o 2FA não é configurado, liberando só as rotas necessárias para configurá-lo.
- Microsoft e OpenID Connect ficam instalados e **desligados**: só entram na configuração quando as variáveis do `.env` os habilitam.
- O IP do cliente vem de um cabeçalho confiável **apenas** quando `IP_CABECALHO_CONFIAVEL` está definido (o Compose usa `X-Real-IP`, escrito pelo Nginx). Com o cabeçalho configurado e ausente, o login é recusado (falha fechada): isso impede burlar o limite por IP omitindo o cabeçalho.

### 5. Criptografia

- AES-256-GCM, nonce aleatório de 12 bytes por valor. Token: `v<n>:` + nonce + cifra (texto em base64 URL-safe; binário em bytes), onde `<n>` é a versão da chave.
- `FREENFSE_CHAVES="2:<nova>,1:<antiga>"`: a primeira grava, todas leem. `recriptografar` percorre o schema público e cada empresa, uma transação por campo, com `--dry-run`. Chave ausente ou malformada vira erro de sistema (`core.W001`/`core.E001`); mensagens de erro nunca incluem o valor.
- Campos criptografados não são filtráveis (só `isnull`): a busca por conteúdo cifrado exigiria cifra determinística, que vaza igualdade.
- A chave **não** é derivada de `SECRET_KEY`: trocar a chave de sessão não pode tornar os certificados ilegíveis.

### 6. Auditoria

- `LogAuditoria` (usuário, empresa, ação, alvo, IP, marca `master`, detalhes JSON) guarda **retratos** do e-mail e do CNPJ, para continuar legível se o cadastro mudar.
- Imutável no nível da aplicação (`save`/`delete` do modelo e queryset de inserção apenas). Triggers no PostgreSQL que impeçam `UPDATE`/`DELETE` pelo banco ficam para a fase de endurecimento.

## Consequências e limites conhecidos

- **O Google real não é testado automaticamente** (exigiria credenciais e rede externas). Os testes percorrem o fluxo completo com o provedor simulado (recusa, vínculo ao usuário cadastrado, restrição de domínio e 2FA); a conversa com o Google em si precisa de verificação manual na primeira instalação.
- **Ativar o 2FA exige reautenticar com a senha.** Quem entra só pelo Google e não tem senha precisa que o Master defina uma antes de configurar o 2FA.
- Atrás de uma borda HTTPS que esconda o IP real (CDN, balanceador), o limite por IP passa a valer para todos os usuários juntos; o limite por e-mail continua individual. Configure o cabeçalho de IP da borda se houver uma.
- Fora do escopo desta fase: desativar/regenerar o 2FA pela interface, API e tela de leitura da auditoria, uso da permissão `usuario.gerenciar` por administradores de empresa (hoje só o Master administra usuários e vínculos) e triggers de auditoria no banco.
- `COOKIES_SEGUROS` vem **desligado** por padrão para funcionar em HTTP local; em produção com HTTPS deve ser ligado junto com `PROXY_TLS` (ver `.env.example`). O system check `core.W002` avisa quando `DEBUG` e `COOKIES_SEGUROS` estão ambos desligados.
