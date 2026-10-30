# Diretrizes de Desenvolvimento — freenfse

Referência técnica para colaboradores humanos e para o Claude Code (IA). Em caso de dúvida, preferir o padrão já existente no arquivo mais próximo do ponto de modificação. Este documento não é um tutorial de configuração de ambiente — isso fica no `README.md`.

> **Base:** convenções de desenvolvimento da Topo (backend, frontend e design system), adaptadas ao freenfse (Django 6.1, schema por empresa com empresa ativa por requisição, permissões por operação, domínio fiscal) e com as correções de `docs/design-system.md` §3 e §4 (botão e campo como `@utility`, fontes locais, tokens versionados). Os §§8–10 são específicos do freenfse. Decisões de origem: `docs/analise-requisitos.md` (D1–D23); fases: `docs/plano-implementacao.md`.

---

## 1. Visão Geral da Arquitetura

**Stack:**
- Backend: Python 3.14, Django 6.1 + Django REST Framework 3.18 (versões e evidência de compatibilidade: `docs/adr/0001-versoes.md`)
- Frontend: React 19 + Vite, Tailwind CSS 4, JavaScript (sem TypeScript)
- Async: Celery 5.6 + Redis 7
- Banco: PostgreSQL 18 com isolamento por schema, uma empresa por schema (`django-tenants`)
- Entrega: Nginx (SPA embutida) + Gunicorn
- Fiscal: biblioteca `freedfe` (ambiente nacional), isolada atrás de um gateway na camada de serviços

**Camadas (D1):**
```
Browser (React SPA)
       ↓ HTTPS
     Nginx
       ↓ proxy /api/, /_allauth/, /accounts/
  Django + DRF          ←→  Redis (fila Celery)
       ↓                         ↓
  PostgreSQL               Celery Worker
  ├── schema public        (emissão, lote, e-mail…)
  └── schema <empresa>
```

Dentro do backend: `models` → `services` → `api` → React.
- **`services`** concentra a regra de negócio e a regra fiscal, testável sem HTTP.
- **`api`** (views e serializers) só trata entrada, saída, validação e permissão.
- **React** apenas apresenta; não decide regra fiscal.

**Apps Shared vs Tenant:**

| SHARED_APPS (schema público) | TENANT_APPS (schema por empresa) |
|---|---|
| `core` — Empresa, Domínio, Usuário, vínculos, auditoria (e os apps de terceiros: allauth, sessões) | `cadastros` — pessoas, serviços |
| | `fiscal` — parâmetros, certificado, NFS-e, eventos |
| | `documentos` — lote, e-mail, Google Drive |
| | `agendamentos` — modelos, agendamentos, rascunhos |

**Regra de FK cross-schema:** modelos em SHARED_APPS não podem ter FK para modelos em TENANT_APPS e vice-versa. Usar campo primitivo como referência (ex.: `Nfse.emitida_por_email = EmailField()`).

---

## 2. Estrutura de Diretórios

```
backend/
├── config/           # settings.py, urls.py (root), celery.py, wsgi.py
├── core/             # models/ (Empresa, Usuario, Vinculo, LogAuditoria), permissoes.py, crypto.py, fields.py,
│                     # middleware.py, services/, auth/ (adapters, sinais), api/, management/commands/
├── cadastros/        # tenant
├── fiscal/           # tenant
├── documentos/       # tenant
└── agendamentos/     # tenant
```

Cada app com regra de negócio segue: `models.py`, `services/`, `api/` (`serializers.py`, `views.py`, `urls.py`), `tasks.py` (se houver) e `tests/`.

```
frontend/src/
├── api/              # Um arquivo JS por recurso HTTP (http.js, auth.js, admin.js, versao.js, …)
├── components/       # Componentes reutilizáveis — PascalCase
├── contexts/         # AuthContext, TemaContext, ConfirmacaoContext
├── hooks/            # Hooks customizados — prefixo use
├── pages/            # Telas mapeadas a rotas — PascalCase (admin/ = administração global do Master)
├── testes/           # Apoio dos testes: API falsa e montagem da SPA (não entra no build)
├── routes.jsx        # Árvore de rotas e guardas
└── utils/            # erros.js
frontend/public/fonts/  # Fontes locais + licenças OFL
docker/                 # Dockerfile.backend, Dockerfile.nginx, nginx.conf, entrypoint
docs/                   # requisitos, design system, plano, adr/
```

---

## 3. Nomenclatura

### 3.1 Python / Django

| Elemento | Convenção | Exemplos |
|---|---|---|
| Modelos | PascalCase, substantivo PT | `Empresa`, `Nfse`, `ParametrosFiscais` |
| Exceções | PascalCase, prefixo `Erro` | `ErroDeEmissao`, `ErroDeCertificado` |
| Serializers | PascalCase + sufixo `Serializer` | `NfseSerializer`, `PessoaListaSerializer` |
| ViewSets | PascalCase + sufixo `ViewSet` | `NfseViewSet`, `PessoaViewSet` |
| Choices | `TextChoices` aninhada, MAIÚSCULO | `Nfse.Situacao.AUTORIZADA` |
| Funções / métodos | snake_case, verbo PT | `emitir`, `cancelar`, `reconciliar_pendentes` |
| Variáveis | snake_case, PT | `competencia`, `valor_servico`, `chave_acesso` |
| Constantes de módulo | UPPER_SNAKE_CASE | `LIMITE_TENTATIVAS` |
| Campos de modelo | snake_case, PT | `criado_em`, `numero_dps`, `ativo` |
| Arquivos de teste | `test_<funcionalidade>.py` | `test_emissao.py`, `test_versao.py` |

### 3.2 JavaScript / React

| Elemento | Convenção | Exemplos |
|---|---|---|
| Componentes / Páginas | PascalCase | `ModalConfirmacao`, `SelectBusca` |
| Hooks customizados | camelCase + prefixo `use` | `useFormularioSujo`, `useConfirmacao` |
| Handlers de evento | prefixo `ao` + ação PT | `aoConfirmar`, `aoCancelar`, `aoMudar` |
| Variáveis / estado | camelCase PT | `carregando`, `salvando`, `snapshot` |
| Arquivos de API | camelCase por recurso | `versao.js`, `auth.js` |
| Constantes globais | UPPER_SNAKE_CASE | `LIMITE_EXIBICAO` |

Classes de botão e campo **não** são constantes locais: usam as `@utility` do `index.css` (ver §6.3).

---

## 4. Padrões do Backend

Estilo e lint: `ruff check .` e `ruff format --check .` em `backend/` (configuração em `ruff.toml`). Docstrings em português, estilo Google, na primeira linha do módulo e em classes e funções públicas cujo nome não é autoexplicativo.

### 4.1 Modelos Django

- `Meta.ordering` obrigatório em todo modelo com listagem
- `__str__` obrigatório, usando f-string descritiva
- Campos de auditoria padrão: `criado_em = DateTimeField(auto_now_add=True)`, `atualizado_em = DateTimeField(auto_now=True)`, `ativo = BooleanField(default=True)` quando fizer sentido desativar. Nunca apagar o que tem histórico fiscal
- Choices como `TextChoices` **aninhada** na classe — nunca como tuplas soltas fora do modelo

```python
class Nfse(models.Model):
    class Situacao(models.TextChoices):
        RASCUNHO   = "rascunho",   "Rascunho"
        ENVIANDO   = "enviando",   "Enviando"
        AUTORIZADA = "autorizada", "Autorizada"
        REJEITADA  = "rejeitada",  "Rejeitada"

    situacao = models.CharField(max_length=20, choices=Situacao, default=Situacao.RASCUNHO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"NFS-e #{self.pk} ({self.situacao})"
```

- Dados sensíveis (senha, token, certificado): `CampoTextoCriptografado` / `CampoBinarioCriptografado` de `core.fields` — nunca `TextField` simples. Não são filtráveis (só `isnull`)
- Parâmetros extensíveis: `JSONField` em vez de colunas separadas
- Migrações sempre em dia: `makemigrations --check` roda no CI

### 4.2 Serializers DRF

- `read_only_fields = ["criado_em", "atualizado_em"]` em todo `Meta`
- Campos write-only (segredo/senha): nunca retornados; indicar presença com `SerializerMethodField` (`possui_segredo`)
- Campo de display de choice junto ao campo de valor: `situacao_display = CharField(source="get_situacao_display", read_only=True)`
- Validação cruzada de campos: método `validate(atributos)` — não `validate_<campo>` quando os campos dependem entre si
- Nenhuma regra fiscal no serializer: delegar ao `services`

### 4.3 ViewSets DRF

```python
class PessoaViewSet(viewsets.ModelViewSet):
    """CRUD das pessoas (clientes, fornecedores…) da empresa ativa."""

    queryset = Pessoa.objects.all()
    serializer_class = PessoaSerializer
    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"list": "cadastro.consultar", "create": "cadastro.editar"}
```

- `permission_classes = [PermissaoPorOperacao]` (`core.api.permissions`) em todo viewset de tenant: a permissão é por **operação** (`nfse.emitir`, `nfse.cancelar`…), não por nível hierárquico. A ação sem entrada em `permissao_requerida` é **negada**, até para o Master (falha fechada)
- A administração global (empresas, usuários, vínculos) usa `PermissaoMaster` e fica em `/api/admin-global/`
- Ações não-CRUD com `@action`; retornar `{"sucesso": True/False, "erro": "..."}` para resultado ao frontend
- Capturar só exceções do domínio (`ErroDeEmissao`…) nas views; nunca `except Exception` genérico

### 4.4 URLs

```python
# cadastros/api/urls.py
router = DefaultRouter()
router.register("pessoas", PessoaViewSet, basename="pessoa")
urlpatterns = router.urls
```

- `DefaultRouter` por app; incluído em `config/urls.py` com prefixo `/api/<dominio>/`
- Nunca URL manual quando o Router já cobre — ações ficam em `@action`

### 4.5 Services

- Toda regra de negócio e orquestração vive em `services/`, em funções que recebem a empresa e o usuário **explicitamente**
- O acesso à `freedfe` passa por um único ponto (`GatewayNfse`, Fase 3), que se testa com um servidor Sefin falso
- Exceções do driver ou da biblioteca nunca sobem cruas: encapsular em exceção do domínio (`Erro…`)

### 4.6 Tasks Celery

- **Sempre** rodar dentro de `with schema_context(schema_name):`
- `schema_name` (e o usuário) passados como argumento explícito — nunca inferidos dentro da task
- Emissão: uma por vez por empresa/série (trava no PostgreSQL), com reconciliação antes de reenviar

```python
@shared_task
def emitir_nfse(nfse_id, schema_name):
    with schema_context(schema_name):
        nfse = Nfse.objects.get(pk=nfse_id)
        ...
```

### 4.7 Segurança

- Dados sensíveis: criptografia AES-256-GCM com chave fora do banco e versão da chave no valor (`core.crypto`, chaves em `FREENFSE_CHAVES`) — nunca `TextField` simples
- Permissões por operação, avaliadas pelo vínculo do usuário com a **empresa da requisição**; o papel Master é global e auditado
- Toda operação sensível (cancelar, substituir, trocar certificado) registra usuário **e** empresa na auditoria
- Nada de segredo em log, mensagem de erro ou resposta de API

### 4.8 Permissões, auditoria e criptografia (como usar)

**Nova permissão.** Registre-a em `core/permissoes.py` junto com os perfis que a recebem (o Administrador sempre a recebe). O nome segue `recurso.acao`; permissão fora do catálogo é recusada pelo vínculo:

```python
registrar_permissao("nfse.cancelar", "Cancelar NFS-e", perfis=[Perfil.EMISSOR])
```

**Nova rota de empresa.** Nenhuma configuração extra: qualquer `/api/` fora de `/api/versao/`, `/api/eu/` e `/api/admin-global/` já exige `X-Empresa` e vínculo. Não ative schema manualmente (`set_tenant`); a view recebe `request.empresa`, `request.perfil` e `request.permissoes`.

**Auditoria.** `core.services.auditoria.registrar(Acao.X, request=request, alvo="...", detalhes={...})` — usuário, empresa, IP e a marca `master` saem da requisição. Nunca coloque senha, token ou conteúdo de certificado em `detalhes`.

**Campo criptografado.** Declare o campo e use normalmente; a chave atual grava e todas as chaves leem. Rotação: nova chave na frente em `FREENFSE_CHAVES`, reiniciar, `python manage.py recriptografar` (use `--dry-run` antes) e só então retirar a chave antiga.

**Autenticação.** Não crie endpoint de login, cadastro ou senha: use o `allauth` headless (`/_allauth/browser/v1/`). Cadastro público fica fechado nos adapters de `core/auth/adapters.py`. O login social passa pelas mesmas etapas do login por senha, inclusive o 2FA: não crie atalho que abra a sessão a partir do provedor (a prova está em `core/tests/test_login_social_2fa.py`).

---

## 5. Multiempresa

**Regra de ouro:** toda query em TENANT_APP deve executar dentro de um schema de empresa ativo.

- A empresa ativa vem do cabeçalho `X-Empresa` **por requisição** (D10), validada contra o vínculo do usuário — **nunca** da sessão e nunca do domínio. Com duas abas abertas, a sessão faria uma aba emitir no CNPJ errado
- Em views: garantido por `EmpresaPorCabecalhoMiddleware`, que também define `request.empresa`, `request.perfil` e `request.permissoes`. Sem acesso, sempre a mesma resposta 403 (`sem_acesso_a_empresa`), seja a empresa inexistente, inativa ou sem vínculo
- Em tasks Celery: `with schema_context(schema_name):` explícito
- Em fixtures de teste: `with schema_context(empresa.schema_name):`

**Proibições:**
- FK entre SHARED_APP e TENANT_APP é **proibida** — usar `EmailField` ou ID primitivo como referência
- `connection.set_tenant()` nunca é chamado manualmente fora do middleware

**Migrações de TENANT_APPS:**
```
python manage.py makemigrations <app>     # cria a migration
python manage.py migrate_schemas          # aplica no schema público e em todas as empresas
```

---

## 6. Padrões do Frontend

### 6.1 Design System — Tokens de Cor

A fonte dos tokens é `frontend/src/index.css` + `docs/design-system.md`, ambos versionados. Os testes (`design-tokens.test.js`) leem só arquivos do repositório.

| Classe Tailwind | Valor | Uso |
|---|---|---|
| `text-accent` / `bg-accent` | `#ff5900` | Botões primários, `focus:border-accent` |
| `bg-gray-100 dark:bg-[#121212]` | — | Fundo de página (no componente raiz) |
| `bg-white dark:bg-gray-900` | — | Cards, formulários, painéis |
| `border-gray-200 dark:border-gray-800` | — | Todas as bordas |
| `text-gray-800 dark:text-gray-300` | — | Texto principal |
| `text-gray-600 dark:text-gray-400` | — | Labels, texto secundário |
| `text-gray-900 dark:text-gray-100` | — | Títulos dentro de cards/modais |

**Paleta de dados (`--color-data-1…6`).** Rampa laranja uniforme, separada por luminosidade: `#ffd0a8`, `#ffab6b`, `#ff8534`, `#ff5900` (= accent), `#cc4300`, `#8f2f00`. Disponível como `bg-data-1…6` / `text-data-1…6`. Séries de contagem usam o neutro `--grafico-neutro` (tema-aware: `#d1d5db` no claro, `#e5e7eb` no escuro).

**Estados semânticos** (reaproveitam as cores da escala de severidade do design system da Topo): `estado-sucesso` `#16a34a` (autorizada, paga), `estado-atencao` `#ca8a04` (em aberto, incerta), `estado-alerta` `#ea580c` (certificado perto de vencer), `estado-erro` `#dc2626` (rejeitada), `estado-neutro` `#6b7280` (cancelada). Não dependem só da cor: acompanhar de texto ou ícone.

### 6.2 Tipografia

- **Títulos** (`h1–h6`): Poppins 900, `letter-spacing: -0.025em` (automático via CSS base — não repetir a classe)
- **Grupos do menu lateral**: classe utilitária `titulo-grupo-menu` (Poppins 600, 12 px, maiúsculas)
- **Body e itens de menu**: Source Code Pro — peso **300** no tema claro e **400** no escuro; padrão do body, não declarar explicitamente
- **Títulos de modal**: `text-lg text-gray-900 dark:text-gray-100` — nunca `text-accent`
- **Fontes locais** (Poppins 600/900; Source Code Pro 300/400/600) em `frontend/public/fonts/`, via `@font-face`, com as licenças OFL. **Nada** do Google Fonts nem de outro CDN

### 6.3 CSS e Styling

- Dark mode via classe `.dark` no `<html>` — gerenciado pelo `TemaContext`; nunca usar `prefers-color-scheme` em CSS inline
- **Botão e campo não são redeclarados por tela.** Use as `@utility` do `index.css`: `botao`, `botao-leve`, `botao-perigo` e `campo`. Mudar o visual muda em um único lugar
- Outros utilitários compartilhados: `botao-acao-grid` (botão de tabela, largura fixa), `celula-acoes` (contêiner dos botões da coluna "Ações") e `titulo-grupo-menu`

```jsx
<button className="botao" type="submit">Emitir</button>
<button className="botao-leve" type="button" onClick={aoCancelar}>Cancelar</button>
<button className="botao-perigo" type="button" onClick={aoExcluir}>Excluir</button>
<input className="campo" value={nome} onChange={aoMudar} />
```

- O texto do botão primário é `text-gray-900` sobre o accent (contraste 5,6:1, WCAG AA). **Não** trocar por branco (3,1:1, reprovado para texto pequeno)
- Sem bibliotecas de componentes UI externas (modais, selects e comboboxes implementados na mão)
- Estilo ou código reaproveitado do design system da Topo leva o cabeçalho `Baseado no design system da Topo`, **sem** caminho nem commit de repositório privado

### 6.4 Componentes

- Componentes são apresentacionais quando possível; estado de servidor fica na Page
- Props de callback: prefixo `ao<Ação>` (`aoConfirmar`, `aoCancelar`, `aoMudar`)
- Sem PropTypes; sem TypeScript — confiar na convenção de nomes
- Foco gerenciado com `useRef` + `useEffect` ao abrir modal
- Acessibilidade: `role="dialog" aria-modal="true"` em modais; contraste AA nos dois temas; navegação por teclado

### 6.5 Gestão de Estado

- Estado local: `useState`; sem Redux ou Zustand
- Contextos globais: `AuthContext` → `useAuth()` (usuário, empresas vinculadas, empresa ativa, permissões); `TemaContext` → `useTema()` (claro/escuro/sistema); `ConfirmacaoContext` → `useConfirmacao()` (modal imperativo)
- A **empresa ativa vive por aba** (estado da aba, enviada em `X-Empresa`), nunca em `localStorage` compartilhado entre abas
- `confirmar(opcoes)` retorna `Promise<boolean>`: substituto de `window.confirm`
- Proteção de formulário sujo: comparar o estado atual com um snapshot da abertura e passar o resultado a `useFormularioSujo(sujo)`

### 6.6 Camada de API

- Um arquivo por recurso em `src/api/`
- Toda chamada passa por um cliente HTTP único que retorna `{ ok, status, dados }`
- Nunca fazer `throw` na camada de API
- Erros humanizados, em linguagem didática, por `mensagemErro(resposta)` de `utils/erros.js`

### 6.7 Roteamento

- `createBrowserRouter` + `RouterProvider` em `App.jsx` (data router obrigatório para `useBlocker`)
- Árvore de rotas em `routes.jsx` (`App.jsx` aceita um roteador em memória para testes). Guardas: `RotaProtegida` (autenticação e 2FA obrigatório) e `RotaMaster`
- A defesa real é no backend — os guards do frontend apenas evitam exibir telas inacessíveis
- Ao deprecar uma rota: manter `<Navigate to="..." replace />` em vez de remover a entrada

---

## 7. Testes

- Backend: `pytest` + `pytest-django` — rodar com `pytest` na raiz de `backend/`, contra PostgreSQL real
- `pytest.ini` lista `testpaths` explicitamente; ao criar novo app com testes, adicionar o caminho
- Nomenclatura: arquivo `test_<funcionalidade>.py`, função `def test_<o que verifica>()`
- Frontend: `npm test` (Vitest) em `frontend/`, arquivos `*.test.js(x)` ao lado do módulo; `npm run lint` (ESLint). Telas são testadas com a SPA inteira sobre uma API falsa (`src/testes/`); consultas por papel e nome acessível, não por classe CSS
- O backend de testes usa `config.settings_testes` (cache em memória, hash de senha rápido, chaves fictícias e o app `apoio_testes`, que existe só para exercitar o isolamento por schema e os campos criptografados). Fixtures prontas em `backend/conftest.py`: `empresa_a`, `empresa_b`, `master`, `usuario`, `vincular`, `cliente_de`
- `core/tests/test_contrato_frontend.py` resolve no URLconf real todas as rotas citadas em `frontend/src/api/`: um caminho errado na SPA reprova o backend, já que os testes do frontend usam API falsa

**Fixture de empresa:**

```python
@pytest.fixture
def empresa(db):
    """Empresa de teste com schema próprio migrado."""
    empresa = Empresa(nome="Empresa Teste", schema_name="empresa_teste")
    empresa.save()
    yield empresa
    empresa.delete(force_drop=True)
```

```python
def test_cadastra_pessoa(empresa):
    with schema_context(empresa.schema_name):
        pessoa = Pessoa.objects.create(...)
        assert Pessoa.objects.count() == 1
```

- `with schema_context(empresa.schema_name):` ao criar dados e ao verificar resultados
- Tasks Celery: chamar a função diretamente (ou `.apply()`) — sem `CELERY_TASK_ALWAYS_EAGER`
- Testes de isolamento são obrigatórios: requisição sem vínculo, `X-Empresa` de outra empresa, duas abas com empresas diferentes
- **Toda correção e toda feature deve incluir teste de regressão**
- **Verificar que toda a suíte passa antes de concluir qualquer alteração**

---

## 8. Contêineres e Configuração

- `docker compose up` sobe `postgres:18`, `redis:7`, `backend` (aplica `migrate_schemas`), `worker`, `beat` e `nginx` (serve a SPA e repassa `/api/`, `/_allauth/` e `/accounts/`). Em desenvolvimento, `docker compose up -d postgres redis` e o backend roda no host
- PostgreSQL e Redis são publicados só em `127.0.0.1`. Só o Nginx publica porta na interface externa
- Cada contêiner tem teto de memória ajustável pelo `.env` (`MEM_LIMIT_*`); os padrões são iniciais e devem ser recalibrados com carga real
- Imagens rodam sem root. Arquivos `.env` nunca entram na imagem (`.dockerignore`)
- Cabeçalhos de segurança HTTP são definidos no Nginx (fonte única). Mídia por empresa nunca é servida direto pelo Nginx
- Configuração **somente** por variáveis de ambiente (`django-environ`). Nenhuma senha padrão: `SECRET_KEY` e `POSTGRES_PASSWORD` são obrigatórios; `FREENFSE_CHAVES` é obrigatória assim que houver dado cifrado em produção
- Dependências do backend: editar `requirements*.in` e regerar os `.txt` com `uv pip compile --python-version 3.14`; sempre versões fixadas. A `freedfe` é fixada por commit (o repositório não publica tags), e por isso o `Dockerfile.backend` instala as dependências num estágio de build com `git`

---

## 9. Segurança e Dados Públicos

O repositório é **público**. **Nunca** versionar:

- credenciais, senhas, tokens, chaves de API e chaves de criptografia;
- certificados (`.pfx`, `.p12`, `.pem`, `.key`) e arquivos `.env` reais;
- dados pessoais (CPF, nomes, e-mails reais) e dados reais de empresas ou clientes.

Regras:

1. Configuração só por variáveis de ambiente. Versione apenas `.env.example`, com valores fictícios ou vazios e um comentário por variável.
2. O `.gitignore` cobre `.env*` (exceto `.env.example`), certificados e chaves, mídia/uploads, backups e dumps.
3. Testes usam só dados fictícios: CNPJ/CPF de teste **válidos no dígito verificador** e nomes genéricos. Certificados de teste são **gerados em tempo de teste**, nunca commitados.
4. Nada de segredo em logs, mensagens de commit, PRs, issues ou documentação.
5. O CI roda **gitleaks** no histórico e na árvore e falha o build se encontrar segredo (`.gitleaks.toml`). Não existe allowlist por padrão.
6. Se um segredo vazar: revogar/rotacionar primeiro; reescrever o histórico é secundário.
7. Ao reaproveitar código de um repositório **privado** da Topo, levar só o que é genérico (tokens, utilitários, padrões de Docker/Nginx, convenções) e reescrever os comentários em termos do freenfse: sem nomes de clientes, domínios ou hosts, números de issues internas, regras de negócio de outros produtos, configurações específicas de implantação, URLs internas ou credenciais.

---

## 10. Versão e Fluxo

- `VERSION` (raiz) é a **fonte única**, no formato `MAJOR.MINOR.PATCH`. O backend lê o arquivo (`settings.VERSAO`, exposto em `GET /api/versao/`); o frontend lê no build (`__VERSAO_APP__`). A `version` do `package.json` é ignorada de propósito (`0.0.0`). Alterar a versão = alterar só o `VERSION`.
- Um branch e um PR por fase do plano, com CI verde e roteiro de verificação no PR. O PR referencia a issue da fase (`Closes #N`).
- Commits objetivos, em português, referenciando a issue (`Refs #N`) e sem dados sensíveis.
- Não forçar versões de dependências que ainda não suportam a stack decidida: registrar em ADR (`docs/adr/`).
