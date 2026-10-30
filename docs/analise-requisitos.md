# Análise crítica dos requisitos — freenfse

> Status: **requisitos iniciais fechados** (rev. 4) · Data: 2026-10-30
> Escopo: revisão dos requisitos iniciais, apontando inconsistências, lacunas e melhorias.
> Contexto: uso interno pela Topo, sem fins comerciais, código aberto (Apache 2.0).

## 0. Decisões registradas

| # | Decisão | Origem |
|---|---|---|
| D1 | Arquitetura **em camadas** com API REST (substitui "MVC") | Revisão 1 → aprovada |
| D2 | Backend em **Django** + Django REST Framework | Aprovada |
| D3 | Versões: a mais recente **estável** suportada pelas bibliotecas. Hoje: **Python 3.14**, **Django 6.1**, **PostgreSQL 18** (ver 1.2) | Aprovada |
| D4 | ~~Grupo econômico~~ → **Multiempresa isolado**: cada empresa tem seus próprios cadastros, sem compartilhamento (ver 3.5) | Revisada na rev. 3 |
| D5 | Biblioteca fiscal: **`topoconsultoria/freedfe` ≥ 0.3.0**, com persistência injetável e uso sem pasta (ver 1.5) | Concluída na freedfe 0.3.0 |
| D6 | Cobrança: **apenas emissão de boleto** (Banco Inter), com marcação manual da situação: em aberto, pago, cancelado (ver 4.2) | Aprovada |
| D7 | Haverá **endereço público** (HTTPS) para a aplicação | Informada |
| D8 | Autenticação via **OIDC**, sem dependência obrigatória do WorkOS (ver 1.4) | Aprovada |
| D10 | Um usuário pode operar **várias empresas**, com **perfil diferente em cada uma** (ver 3.5) | Aprovada |
| D11 | **NFS-e recebidas (tomadas)** entram no escopo, via ADN (ver 2.5) | Aprovada |
| D12 | Agendamento **gera rascunho** para aprovação; não emite sozinho (ver 3.2) | Aprovada |
| D13 | Recorrência: única, diária, semanal, mensal, anual (o "mensal" duplicado era erro) (ver 3.1) | Aprovada |
| D14 | Google Drive: **copiar XML e PDF** para uma pasta (ver 4.1) | Aprovada |
| D15 | Implantação em **servidor interno, VPS ou nuvem** (ver 5) | Aprovada |
| D16 | Isolamento por **schema** do PostgreSQL (`django-tenants`) (ver 3.5) | Aprovada |
| D17 | Feriado ou fim de semana: **executa na data mesmo assim** (ver 3.2) | Aprovada |
| D19 | Cancelamento/substituição de NFS-e com cobranças: o sistema **pergunta o que fazer** com cada forma de pagamento vinculada; NFS-e pode ter **várias formas de pagamento** (ver 4.2) | Aprovada |
| D20 | Boleto com **QR Code Pix** (BolePix) oferecido (ver 4.2) | Aprovada |
| D21 | Envio da NFS-e por e-mail **configurável** por empresa e por modelo (ver 4.3) | Aprovada |
| D22 | Perfis: Administrador, Emissor, Financeiro, Consulta + **Master** com acesso a várias empresas por alterador, como no padrão de referência da Topo (ver 3.6) | Aprovada |
| D23 | Login: **Google** + e-mail/senha com 2FA ligados na Topo; Microsoft e OIDC genérico disponíveis e desligados (ver 1.4) | Aprovada |
| D18 | Design system pelos design system da Topo; **logo por empresa** nos parâmetros; botão e campo centralizados (ver `docs/design-system.md`) | Aprovada |
| D9 | Sistema interno da Topo usado **apenas como referência** de padrões; sem dependência (ver 1.7) | Informada |

Legenda de severidade: **[A]** alta (bloqueia arquitetura ou gera risco fiscal/segurança) · **[M]** média · **[B]** baixa.

---

## 1. Inconsistências nas diretrizes técnicas

### 1.1 "Arquitetura MVC" × frontend React **[A]**
MVC clássico pressupõe que o servidor renderiza a *View*. Com React (SPA), a *View* fica no navegador e o backend vira uma **API**. Em Python, nenhum framework popular implementa MVC literalmente (Django usa MTV; FastAPI não impõe padrão).

**Sugestão:** substituir "MVC" por **arquitetura em camadas com API REST**:

| Camada | Responsabilidade | Equivalente MVC |
|---|---|---|
| `models` (ORM) | Entidades e persistência | Model |
| `services` (domínio) | Regras de negócio, orquestração da emissão, máquina de estados da NFS-e | Model (lógica) |
| `api` (views/serializers) | Entrada/saída HTTP, validação, permissões | Controller |
| React | Apresentação | View |

Regra: nenhuma regra fiscal em views/serializers nem no React. Tudo em `services`, testável sem HTTP.

### 1.2 Critérios de versão divergentes **[M]**
- Python: "versão mais popular".
- PostgreSQL: "versão mais recente compatível".

São critérios diferentes e o primeiro não é verificável. **Sugestão:** um único critério, registrado em ADR: *a versão estável mais recente suportada por todas as dependências críticas* (framework web, `lxml`, `signxml`/`xmlsec`, `cryptography`, `psycopg`) e com ao menos uma *patch release*. Fixar versões no `Dockerfile`/`pyproject.toml` e revisar semestralmente.
**Decidido (D3), verificado em 2026-10-30:**

| Componente | Versão | Motivo |
|---|---|---|
| Python | 3.14 | Django 6.1 declara suporte a 3.12–3.14. O 3.15 ainda não consta no Django. |
| Django | 6.1.x | Última estável. **Não é LTS**: o suporte termina depois do 6.2 (LTS, previsto para abril/2027). Planejar a migração para o 6.2 LTS. |
| Django REST Framework | 3.18.x | Suporta Django 6.1 e Python 3.14. |
| psycopg | 3.3.x | Driver recomendado pelo Django (psycopg 3). |
| PostgreSQL | 18.x | O 19 ainda está em *release candidate*. Django 6.1 exige PostgreSQL 15+. |
| freedfe | ≥ 0.2.0 | Python 3.9+, sem conflito. |

Alternativa conservadora: Django 5.2 LTS (suporte mais longo, mas fica uma versão atrás). Como o projeto é interno e novo, a opção acima é adequada se a atualização para o 6.2 LTS entrar no plano.

### 1.3 Escolha do framework backend (não definida) **[A]**
| Critério | Django + DRF | FastAPI + SQLAlchemy + Alembic |
|---|---|---|
| ORM, migrações, auth, permissões | Nativos | Montagem manual |
| Admin pronto (suporte/cadastros) | Sim | Não |
| Async nativo | Parcial | Sim |
| Volume de código "cola" | Baixo | Alto |
| Aderência a "MVC"/OO | Alta (MTV) | Depende do projeto |

Para um sistema CRUD-intensivo, multiempresa, com permissões granulares e jobs agendados, **recomendo Django + Django REST Framework**. A emissão de NFS-e é I/O pontual e não justifica async como requisito. **Decidido (D2).**

### 1.4 "Preferência por software livre" × WorkOS **[A]**
WorkOS é SaaS proprietário. Em um projeto open source, torná-lo obrigatório:
- obriga qualquer outro usuário do projeto a ter conta WorkOS;
- cria dependência externa para **login** (com internet instável, ninguém entra no sistema);
- mistura autenticação com autorização se usarmos o RBAC do WorkOS.

**O que é OIDC.** *OpenID Connect* é o protocolo aberto de login usado por Google, Microsoft, WorkOS, Keycloak e outros. Funciona assim: o freenfse redireciona o usuário para o provedor de identidade, que autentica (senha, MFA, SSO) e devolve um *token* assinado dizendo quem é a pessoa. O freenfse confia nesse token e nunca guarda senhas. Como o protocolo é padrão, trocar de provedor é mudar configuração (URL, *client id*, *secret*), não código. Biblioteca sugerida: `mozilla-django-oidc` ou `django-allauth` (ambas livres).

**Decidido (D8): OIDC, com WorkOS opcional.** Com OIDC o WorkOS deixa de ser obrigatório: ele vira apenas um dos provedores possíveis.

**Estratégia recomendada: `django-allauth`** (MIT), padrão já usado na Topo:
- login por **Google** e **Microsoft** (OIDC/OAuth 2.0 direto com o provedor que a empresa já usa, sem intermediário pago);
- provedor **OpenID Connect genérico** do allauth (`openid_connect`) para quem quiser WorkOS, Keycloak ou Authentik, só por configuração;
- e-mail + senha com **2FA TOTP** e códigos de recuperação (`allauth.mfa`) como alternativa e acesso de emergência;
- modo *headless* (API JSON) para a SPA React, padrão já validado na Topo.

| Opção | Custo | Dependência externa para logar | Observação |
|---|---|---|---|
| allauth + Google/Microsoft (recomendada) | zero | provedor de e-mail da empresa | padrão já usado na Topo |
| allauth + Keycloak/Authentik | infraestrutura própria | nenhuma (*self-hosted*) | mais um serviço para operar; só vale com muitos sistemas |
| allauth + WorkOS (OIDC) | plano gratuito atual cobre uso interno (verificar) | WorkOS | proprietário; aceitável como opção, não como requisito |

**Autorização (perfis e permissões) fica 100% no freenfse**, por empresa.

**Decidido (D23):** na instalação da Topo ficam ligados **login com Google** e **e-mail/senha com 2FA**; Microsoft e OIDC genérico ficam disponíveis por configuração, desligados. Regras:
- **sem autocadastro**: login social só entra se o e-mail já estiver cadastrado como usuário (o administrador cria o usuário e os vínculos antes);
- opção de restringir o login Google a domínios permitidos (ex.: domínio da Topo), configurável na instalação.

### 1.5 Biblioteca `freedfe` (topoconsultoria/freedfe, v0.2.0) **[A]**
Pública, Apache 2.0, Python 3.9+, dependências mínimas (`cryptography`, `lxml`; `reportlab` para o DANFSe). Cobre boa parte do núcleo fiscal:

| Requisito do freenfse | Situação na freedfe |
|---|---|
| Emissão (DPS → Sefin) | Sim, com máquina de estados (`pendente → enviada → autorizada/rejeitada/incerta`) e reconciliação antes de reenviar (idempotência) |
| Consulta por chave e eventos | Sim |
| Cancelamento | Sim (evento 101101) |
| Substituição | Sim, via `Dps.substituicao` (a Sefin gera o 105102) |
| IBS/CBS, NBS | Sim (NT 009), em subconjunto; casos não cobertos entram por "XML pronto" |
| DANFSe | Gerado localmente (NT 008), com QR Code e marca d'água de cancelada/substituída |
| NFS-e tomadas (ADN por NSU) | Sim (`sincronizar`) |
| Convênio do município e parâmetros municipais | Sim (`convenio`, `parametros_servico`, `verificar_pre_emissao`) |
| Certificado A1 em memória | Sim (`CertificadoA1(conteudo_pfx: bytes, senha)`), compatível com guardar o `.pfx` criptografado no banco |

**Uso em aplicação web — resolvido na freedfe 0.3.0** (PR #3, commits `c3db15e` e `3484dcd`):

| Ponto levantado na rev. 2 | Situação na 0.3.0 |
|---|---|
| Estado de emissão e numeração em JSON | Contrato `EstadoEmissao` (ABC) com `reservar_proximo(serie)` atômico e `descartar`; implementação em arquivo continua padrão |
| Trava de arquivo | Contrato `Trava` (`__enter__`/`__exit__`); `TravaArquivo` padrão |
| NSU do ADN em arquivo | Contrato `EstadoSequenciaNsu` |
| Dependência de `pasta` | `criar_servico_nfse(...)` em `freedfe.nfse.fabrica`, sem disco; contratos também para `Auditoria`, `CacheParametros` e `ArmazenamentoEvidencias` |
| DANFSe só em arquivo | `ServicoNfse.danfse_bytes(chave)` |
| Chave privada em PEM temporário | No Linux, PEM em `memfd` (memória, `MFD_CLOEXEC`, 0600); arquivo temporário só como alternativa. Manter `/tmp` em `tmpfs` no contêiner como garantia |

**O que fica a cargo do freenfse:** implementar no PostgreSQL (ORM do Django, por schema de empresa) `EstadoEmissao`, `Trava` (*advisory lock* por empresa/série), `EstadoSequenciaNsu`, `Auditoria`, `CacheParametros`, `ArmazenamentoEvidencias` e `RepositorioDocumentos`, validando cada um com os testes de contrato da biblioteca.

Pontos ainda válidos:
- **Leiaute muda em 30/11/2026**: a biblioteca usa NT 004 em produção até essa data e NT 009 depois (seleção automática). O freenfse deve guardar o leiaute usado em cada nota e testar a virada em produção restrita antes de dezembro.
- **Instalação via Git**: fixar por *tag*/commit (≥ 0.3.0) no `pyproject.toml`; publicar no PyPI quando estabilizar.

**Sugestão geral:** no freenfse, isolar o uso da freedfe atrás de uma interface (`NfseGateway`) na camada de serviços, para testar com *mock* (a freedfe já traz `servidor_sefin_falso` nos testes) e absorver mudanças da biblioteca num único ponto.

### 1.6 Design system **[M]**
Identidade visual baseada no design system da Topo, especificada e versionada em `docs/design-system.md`. Fontes Poppins e Source Code Pro (licença OFL) **auto-hospedadas** — não carregar do Google Fonts (privacidade/LGPD e funcionamento offline).

---

### 1.7 Padrões de referência da Topo **[M]**
A Topo tem outro sistema interno com a mesma stack (Django + DRF, React + Vite + Tailwind, PostgreSQL, Celery + Redis), usado **apenas como referência** de padrões. O freenfse **não depende** dele em nenhum nível (código, build ou execução); o acesso de leitura é pontual, autorizado pelo usuário, e o clone é apagado após o uso. Nada interno daquele sistema é versionado aqui.

Padrões adotados no freenfse a partir dessa referência:
- autenticação com `django-allauth` *headless* (e-mail/senha, Google, Microsoft, 2FA TOTP);
- criptografia AES-256-GCM de credenciais com chave fora do banco — no freenfse, **com versão da chave** para permitir rotação;
- provedores de e-mail SMTP, Gmail API e Microsoft Graph atrás de uma interface comum;
- cálculo de recorrência de agendamentos (única, diária, semanal, mensal, "a cada N", período, limite de execuções, último dia do mês, fuso `America/Sao_Paulo`) com *dispatcher* único no Celery beat;
- tema claro/escuro/sistema e design system (ver `docs/design-system.md`);
- isolamento por schema com `django-tenants` e `schema_context` nas tarefas;
- instalador (Docker Compose ou nativo com systemd + Nginx), Nginx + Gunicorn;
- convenções de código (nomes em PT, `TextChoices` aninhadas, campos de auditoria, ViewSets com `DefaultRouter`, pytest).

Diferenças definidas para o freenfse: permissões por operação (3.6), empresa ativa por requisição (D10), JavaScript sem TypeScript, fontes locais, versões da D3.

## 2. Inconsistências e lacunas fiscais (NFS-e Padrão Nacional)

### 2.1 "DANFE" está incorreto **[M]**
DANFE é o documento auxiliar da **NF-e** (mercadorias). Para NFS-e o correto é **DANFSe**. Corrigir no texto, na UI e no código. Decidir:
- usar o DANFSe oficial retornado pela API nacional (layout oficial, mas dependente da disponibilidade do serviço), ou
- gerar localmente seguindo o layout oficial (independente, mas exige manutenção).
**Adotado:** gerar localmente com a `freedfe` (NT 008) e guardar; o oficial fica como conferência/fallback.

### 2.2 Emissão = envio de DPS **[M]**
No padrão nacional, o contribuinte envia a **DPS** (Declaração de Prestação de Serviço) e a Sefin Nacional gera a NFS-e. Consequências de modelagem:
- a numeração **série + número da DPS** é controlada pelo emitente → precisa de sequência transacional por empresa/série (com *lock*), crítica quando agendamentos rodam em paralelo;
- **idempotência**: em *timeout* após o envio, consultar a DPS antes de reenviar, para não gerar nota duplicada;
- guardar XML da DPS assinada, resposta e NFS-e autorizada, com *hash*.

### 2.3 Substituição e cancelamento **[M]**
- Substituição não é uma "edição": é a emissão de nova DPS referenciando a chave substituída, o que gera evento de cancelamento por substituição da original. A UI deve tratar como "emitir nota substituta a partir desta".
- Cancelamento tem prazo e regras municipais; fora do prazo, pode exigir pedido de análise fiscal. O sistema deve exibir o motivo da rejeição em linguagem simples e o caminho alternativo.
- Efeito nas cobranças vinculadas: o sistema **pergunta o que fazer** com cada uma (D19, ver 4.2).

### 2.4 Reforma tributária (IBS/CBS) não aparece nos requisitos **[A]**
O leiaute da DPS passou a contemplar grupos de IBS/CBS e classificação tributária. "Parâmetros fiscais" e "serviço (código, descrição)" são insuficientes. O cadastro de serviço precisa, no mínimo, de:
- código de tributação nacional (item/subitem LC 116 + desdobro);
- código de tributação municipal (quando houver);
- código NBS;
- classificação tributária / CST de IBS e CBS;
- alíquota de ISS e regras de retenção (ISS, IR, CSLL, PIS, COFINS, INSS);
- descrição padrão.

Os parâmetros fiscais da empresa precisam de: regime tributário (Simples, MEI, Lucro Presumido/Real), regime especial, opção pelo Simples, incentivos, município de incidência padrão, série da DPS, ambiente (produção restrita × produção), certificado.
Recomendo **versionar** regras fiscais com vigência (data início/fim), pois mudam ao longo da transição 2026–2033.

### 2.5 Consulta: só notas emitidas ou também as recebidas? **[A — escopo]**
O ambiente nacional distribui documentos por NSU (ADN) também ao **tomador**. Para a Topo, importar NFS-e **tomadas** (fornecedores) tem valor operacional direto (escrituração, integração com a contabilidade). Definir se entra no escopo inicial — muda o modelo de dados (nota emitida × recebida).

**Decidido (D11): entra.** Desenho:
- `ServicoNfse.sincronizar` da `freedfe` (ADN por NSU) executado por empresa, agendado no Celery beat, com o certificado da própria empresa;
- estado de NSU por empresa no PostgreSQL (contrato `EstadoSequenciaNsu` da `freedfe` 0.3.0);
- modelo único de documento com **direção** (`emitida` / `recebida`) para reaproveitar consulta, DANFSe, XML, download em lote e cópia ao Drive; eventos de cancelamento/substituição recebidos atualizam a situação da nota;
- permissão própria (`nfse_recebida.consultar`) e filtro por prestador, competência e situação.

### 2.6 Adesão do município **[M]**
Confirmar a situação do município de cada empresa no Emissor Nacional e se há particularidades (códigos municipais, retenções). O sistema deve validar isso no cadastro da empresa.

### 2.7 Guarda de documentos **[M]**
XML deve ser mantido pelo prazo legal (referência usual: 5 anos fiscais). O **banco/armazenamento do sistema é a fonte primária**; Google Drive é cópia. Não depender do Drive para guarda legal.

---

## 3. Inconsistências nos cadastros e funcionalidades

### 3.1 Recorrência com "mensal" duplicado **[B]**
**Decidido (D13):** o segundo "mensal" foi erro. Frequências: **única, diária, semanal, mensal, anual**. Implementação seguindo o padrão de recorrência de referência (cobre única, diária, semanal, mensal, "a cada N", período e limite de execuções), acrescentando **anual** (dia e mês fixos; 29/02 → 28/02 em ano não bissexto). O "a cada N" pode ficar disponível sem custo extra.

### 3.2 "Data de fim" **e** "número de execuções" **[M]**
Conflito de semântica. Opções: mutuamente exclusivos (padrão RFC 5545) ou "o que ocorrer primeiro". Recomendo **mutuamente exclusivos** na UI, mais didático.

**Regras adotadas:**
- **Execução (D12):** o agendamento **gera um rascunho** de NFS-e a partir do modelo e notifica os responsáveis. A emissão é sempre um ato de usuário com permissão `nfse.emitir`, inclusive aprovação em lote de vários rascunhos.
- **Feriado e fim de semana (D17):** executa na data calculada, sem calendário de feriados.
- Dia 29/30/31 em meses curtos: último dia do mês (como no padrão de referência da Topo).
- Fuso: `America/Sao_Paulo`.
- Data de fim e número de execuções: mutuamente exclusivos.
- **Competência:** padrão = mês da execução, editável no rascunho.
- **Valor:** vem do modelo e é editável no rascunho (reajustes ficam a cargo de quem aprova; sem índice automático nesta versão).
- **Rascunho não aprovado:** permanece pendente, com alerta diário aos responsáveis; nunca é emitido nem descartado automaticamente. Gerar o próximo rascunho não depende de o anterior ter sido aprovado.
- **Falha ao gerar o rascunho** (ex.: modelo inválido, pessoa inativa): registra o erro, notifica e tenta de novo na execução seguinte; não conta como execução realizada.

### 3.3 Modelo de NFS-e × agendamento **[B]**
Explicitar: agendamento **referencia** um modelo (tomador, serviço, valores, retenções, texto). Alterar o modelo afeta execuções futuras, nunca notas já emitidas (copiar dados no momento da emissão — *snapshot*).

### 3.4 Pessoas e perfis **[M]**
- Pessoa × perfil deve ser N:N (a mesma pessoa pode ser cliente e fornecedor). OK como requisito, só formalizar.
- Faltam: tomador estrangeiro (NIF/sem documento), inscrição municipal, endereço com **código IBGE do município** (obrigatório na DPS), e-mails múltiplos para envio da nota.
- **Decidido (D4):** cadastro de pessoas é **por empresa**, isolado. A mesma pessoa atendida por duas empresas é cadastrada nas duas. Para reduzir retrabalho, oferecer **importação/cópia de cadastro** de outra empresa à qual o usuário tenha acesso (operação explícita, não vínculo).
- Validação de CPF/CNPJ (dígito verificador) e, opcionalmente, consulta de CNPJ em fonte pública para reduzir erro de cadastro.

### 3.5 Multiempresa: qual o significado? **[A]**
- **(a)** várias empresas (CNPJs) de **uma** organização — caso da Topo;
- **(b)** várias organizações independentes (multi-tenant).

**Decidido (D4, rev. 3): multiempresa isolado.** Grupo econômico fica fora por enquanto. Cada empresa tem seus próprios cadastros (pessoas, serviços, modelos, agendamentos, parâmetros, certificado, conta bancária, numeração), sem compartilhamento.

Duas formas de isolar:

| Critério | Schema por empresa (`django-tenants`, como no padrão de referência da Topo) | Coluna `empresa_id` + filtro (opcional: RLS) |
|---|---|---|
| Isolamento | Forte (físico por schema) | Lógico; depende de disciplina ou RLS |
| Aderência ao padrão de referência | Alto (middleware, tasks, testes) | Baixo |
| Usuário em várias empresas | Precisa de vínculo usuário × empresa no schema público e troca de empresa na sessão | Natural |
| Relatório consolidado entre empresas | Difícil (consulta por schema) | Simples |
| Migrações | Rodam em todos os schemas (`migrate_schemas`) | Uma vez |
| Backup/restauração de uma empresa | Simples (`pg_dump -n`) | Exige filtro |

**Recomendação:** `django-tenants` (schema por empresa), pelo isolamento e por já ser o padrão operado na Topo. No freenfse, o usuário deve poder ter **vínculo com várias empresas, com perfil próprio em cada uma** (tabela de vínculo no schema público) e escolher a empresa ativa na interface.

**Decidido (D10): usuário com várias empresas e perfil por empresa.** Desenho:

- **Schema público:** `Usuario` (sem empresa e sem perfil próprios), `Empresa` (tenant) e `VinculoUsuarioEmpresa` (usuário, empresa, perfil, permissões ajustadas, ativo, criado/atualizado por). Unicidade em (usuário, empresa).
- **Empresa ativa por requisição, não por sessão.** A SPA envia a empresa em cada chamada (cabeçalho `X-Empresa` ou prefixo de rota `/api/empresas/<id>/...`); o middleware valida o vínculo ativo e só então ativa o schema. Guardar a empresa ativa só na sessão é arriscado: com duas abas abertas, trocar de empresa numa aba faria a outra **emitir NFS-e no CNPJ errado**.
- **Interface:** empresa ativa sempre visível no topo (nome + CNPJ), com cor ou selo distinto para ambiente de **produção restrita**. Troca de empresa pede confirmação se houver formulário alterado (`useFormularioSujo`).
- **Permissões:** avaliadas sempre pelo vínculo da empresa da requisição. Um usuário pode ser Administrador na empresa A e só Consulta na B.
- **Tarefas assíncronas** (emissão, lote, e-mail, agendamentos): recebem empresa e usuário explicitamente e rodam com `schema_context`, como no padrão de referência da Topo. Agendamento guarda o usuário responsável; se o vínculo dele for desativado, o agendamento é suspenso e o administrador é avisado.
- **Auditoria:** registra usuário **e** empresa em toda operação.
- **"Copiar cadastro de outra empresa"** (3.4): exige vínculo ativo nas duas empresas e permissão de leitura na origem e de escrita no destino.
- **Administrador global** (cria empresas e vínculos): papel separado, fora dos perfis de empresa.

### 3.6 Usuários e perfis de acesso **[M]**
"Configuração personalizada de operações" precisa de forma:
- permissão = **ação × recurso × empresa** (ex.: "cancelar NFS-e" na empresa X). Um modelo hierárquico simples não atende: usar permissões nomeadas (ex.: `nfse.emitir`, `nfse.cancelar`, `cobranca.marcar_pago`) agrupadas em perfis;
- **perfis predefinidos (D22):** Administrador, Emissor, Financeiro e Consulta, atribuídos **por empresa** no vínculo (D10), + ajuste de permissões por usuário;
- **Master (D22):** papel global, fora dos perfis de empresa:
  - acessa **todas as empresas** pelo **alterador de empresa** no topo da tela, sem precisar de vínculo;
  - atua com todas as permissões na empresa escolhida, cria empresas, usuários e vínculos;
  - a empresa escolhida vale **por aba/requisição** (D10), não pela sessão;
  - toda ação do Master é auditada com marcação própria; recomendável exigir 2FA para esse papel.
- usuários comuns com vínculo em mais de uma empresa usam o **mesmo alterador**, listando só as empresas vinculadas;
- operações sensíveis (cancelar, substituir, trocar certificado, alterar credenciais bancárias) registradas em trilha de auditoria.

### 3.7 Certificado A1 **[A]**
- Armazenar `.pfx` e senha **criptografados**; nunca em disco em claro, nunca no Google Drive.
- Validar no upload: senha, CNPJ do certificado × CNPJ da empresa, validade.
- Alertas de vencimento (30/15/7 dias) por e-mail e na tela.
- Permitir um certificado servir várias empresas quando aplicável (ex.: mesma raiz de CNPJ), com regra explícita.

### 3.8 Download em lote **[B]**
Deve ser tarefa assíncrona (gera ZIP em segundo plano e notifica), com filtros (período, competência, tomador, situação) e limite de tamanho. Incluir planilha-resumo (CSV) junto com XML/PDF facilita conferência contábil.

---

## 4. Integrações

### 4.1 Google Drive — finalidade não definida **[M]**
**Decidido (D14): somente gravação — copiar XML e PDF para uma pasta.** Leitura fica fora do escopo.
- Autenticação: **conta de serviço** com acesso a um **Drive compartilhado** (não expira quando alguém sai da empresa). Credencial da conta de serviço criptografada, por empresa.
- **Configuração por empresa:**
  - **ID da pasta raiz** no Google Drive (o identificador que aparece na URL da pasta). Ao salvar, o sistema confere se a conta de serviço tem acesso de escrita a ela e mostra o nome da pasta encontrada.
  - **Dois modelos com as mesmas variáveis:** um para as **subpastas** (separadas por `/`; cada `/` cria um nível) e outro para o **nome do arquivo** (sem `/`; a extensão `.xml`/`.pdf` é acrescentada pelo sistema):

    | Variável | Conteúdo | Formato |
    |---|---|---|
    | `{ano}` | Ano da data de emissão da NFS-e | `2026` |
    | `{mes}` | Mês da data de emissão | `01`–`12` (2 dígitos) |
    | `{dia}` | Dia da data de emissão | `01`–`31` (2 dígitos) |
    | `{numero_nfse}` | Número da NFS-e | sem zeros à esquerda |
    | `{nome_emitente}` | Razão social do prestador (emitente) | texto normalizado (ver abaixo) |
    | `{cnpj_emitente}` | CNPJ (ou CPF) do prestador | só dígitos |
    | `{chave}` | Chave de acesso da NFS-e (50 posições) | só dígitos — sugerida para garantir nome único |

    Exemplo:
    - subpastas: `{ano}/{mes}/{cnpj_emitente} - {nome_emitente}`
    - arquivo: `NFSe {numero_nfse} - {dia}{mes}{ano}`
    - resultado: `2026/10/11222333000181 - EMPRESA EXEMPLO LTDA/NFSe 123 - 30102026.xml` e `.pdf`
  - **Regras do modelo:**
    - data de referência = **data de emissão** da NFS-e (não a competência);
    - em notas **recebidas**, o emitente é o fornecedor; em **emitidas**, a própria empresa. Assim o mesmo modelo serve para as duas;
    - texto das variáveis normalizado: remove `/` e `\`, caracteres de controle e espaços duplicados, limita a 100 caracteres;
    - validação ao salvar: variáveis desconhecidas, chaves sem fechamento ou nível vazio (`//`) são recusados, com **pré-visualização** usando uma nota real da empresa;
    - modelo de subpastas vazio grava direto na pasta raiz;
    - modelo de arquivo vazio usa o padrão `{chave}`.
  - **Unicidade do nome do arquivo:** a combinação *subpastas + arquivo* precisa identificar uma única nota; senão uma nota sobrescreve outra. Regra de validação ao salvar: o caminho completo deve conter `{chave}` **ou** `{numero_nfse}` junto com `{cnpj_emitente}` (o número só é único por emitente, e notas recebidas de fornecedores diferentes podem ter o mesmo número). Se, mesmo assim, já existir na pasta um arquivo com o mesmo nome **de outra nota**, o sistema acrescenta ` (2)`, ` (3)`… e registra o aviso.
  - **Eventos** (cancelamento, substituição): mesmo nome do arquivo da nota com sufixo, ex.: `NFSe 123 - 30102026_cancelamento.xml`. O PDF da nota é **substituído** pelo que tem a marca d'água.
- **Criação das pastas:** o Drive aceita pastas com nomes repetidos no mesmo nível, então a busca e a criação precisam ser controladas pelo sistema: cache de `caminho → ID da pasta` por empresa no banco (com unicidade) e trava por empresa durante a criação, para duas cópias simultâneas não criarem a mesma pasta duas vezes.
- **Mudança do modelo:** vale só para cópias novas; arquivos já gravados não são movidos. "Reenviar ao Drive" usa o modelo vigente.
- Gatilhos: autorização (emitidas), sincronização do ADN (recebidas) e eventos (cancelamento/substituição: grava o XML do evento e **substitui** o PDF pelo que tem a marca d'água).
- Execução em fila, com retentativa; o `fileId` de cada arquivo fica gravado para sobrescrever em vez de duplicar.
- Ação manual "reenviar ao Drive" por nota e por período.
- O Drive é **cópia**; a guarda legal continua no banco do sistema (2.7).

### 4.2 Banco Inter **[A — escopo]**
- A API exige **certificado mTLS do próprio Inter** + OAuth (client credentials) → mais uma credencial a criptografar.
- **Decidido (D6): apenas emissão de boleto**, com situação marcada manualmente pelo usuário: **em aberto**, **pago**, **cancelado**. Sem conciliação nem contas a receber.
- Regras para a marcação manual não gerar inconsistência:
  - "Cancelado" no freenfse **não** cancela no banco por si só. Oferecer duas ações distintas: **"Cancelar no banco"** (chama a API do Inter e marca cancelado) e **"Marcar como cancelado"** (registro manual, para boleto já baixado por fora), com aviso de que o boleto continua pagável se não for cancelado no banco;
  - "Pago" registra data e usuário; reverter para "em aberto" só com permissão específica e auditoria;
  - toda mudança de situação vai para a trilha de auditoria.
- Com o endereço público (D7), o **webhook** do Inter passa a ser viável. Fica como evolução opcional para sugerir/automatizar a marcação de "pago", sem mudar o modelo.
- Expansão para outros bancos: interface `ProvedorCobranca` (padrão *Strategy*), com o Inter como primeira implementação.
- **Boleto com QR Code Pix (D20):** oferecido na emissão do boleto Inter (BolePix), quando a conta permitir; a linha digitável e o QR Code saem no PDF e no e-mail.
- **Várias formas de pagamento por NFS-e (D19):** a nota tem uma ou mais **cobranças** (parcelas), cada uma com forma de pagamento, valor, vencimento e situação (em aberto, pago, cancelado):

  | Forma | Integração |
  |---|---|
  | Boleto Inter (com ou sem Pix) | Emissão e cancelamento pela API |
  | Pix, transferência, cartão, dinheiro, outros | Registro manual (sem integração nesta versão) |

  Validação: a soma das cobranças não pode passar do valor líquido da nota (aviso se for menor). As formas de pagamento são controle interno do freenfse, não fazem parte da DPS.
- **Cancelamento ou substituição da NFS-e (D19): o sistema pergunta o que fazer** com cada cobrança vinculada, numa tela de confirmação antes de concluir:

  | Situação da cobrança | Opções oferecidas |
  |---|---|
  | Boleto em aberto | Cancelar no banco · Marcar como cancelado · Manter em aberto · *(substituição)* transferir para a nota substituta |
  | Outra forma em aberto | Marcar como cancelada · Manter · *(substituição)* transferir |
  | Já paga | Manter como paga (com **alerta** de nota cancelada com pagamento recebido) · *(substituição)* transferir |
  | Já cancelada | Nenhuma ação |

  A escolha é registrada na auditoria. Se o cancelamento da NFS-e for rejeitado pela Sefin, nenhuma ação nas cobranças é executada (as ações só rodam depois da confirmação do evento).

### 4.3 E-mail **[A]**
Autenticação SMTP com usuário/senha está em descontinuação/restrição no Microsoft 365 e no Gmail. Para funcionar de forma estável:
- **Gmail**: Gmail API ou SMTP com XOAUTH2 (OAuth 2.0);
- **Microsoft 365**: Microsoft Graph (`sendMail`) com OAuth 2.0;
- **SMTP genérico**: mantido para outros provedores.
Também faltam: modelos de mensagem com variáveis, fila com retentativa, registro de envio por nota (para quem, quando, resultado) e reenvio manual.

**Decidido (D21): envio configurável** por empresa, com sobreposição por modelo de NFS-e:
- **quando:** manual (padrão) ou automático ao autorizar; cancelamento pode avisar o cliente (configurável);
- **o que anexar:** PDF, XML e boletos em aberto, cada um ligável/desligável;
- **para quem:** e-mails do tomador cadastrados para envio de nota (3.4) + cópias fixas (ex.: financeiro);
- **mensagem:** modelo com variáveis (ex.: `{numero_nfse}`, `{nome_tomador}`, `{valor}`, `{vencimento}`), por empresa;
- provedor de envio (SMTP, Gmail API, Microsoft Graph) configurado por empresa.

### 4.4 Criptografia de credenciais e chaves **[A]**
Definir o modelo de ameaça: o objetivo é que um *dump* do banco não exponha certificados, senhas e tokens.
- Criptografia simétrica autenticada (AES-GCM ou Fernet da biblioteca `cryptography`), com **chave mestra fora do banco** (variável de ambiente/secret do Docker; KMS opcional).
- Suporte a **rotação de chave** (ex.: `MultiFernet`) e identificação da versão da chave em cada registro.
- Procedimento documentado de backup da chave mestra (perdê-la = recadastrar todos os certificados e credenciais).
- Nunca registrar credenciais em logs; mascarar na UI.

---

## 5. Requisitos não funcionais ausentes

| Tema | Sugestão |
|---|---|
| Implantação (D15) | Servidor interno, VPS ou nuvem, sem depender de serviço específico de nuvem: Docker Compose ou instalação nativa (systemd + Nginx), seguindo o padrão de instalador da Topo. Arquivos em volume local; chave mestra em variável de ambiente/secret. Saída HTTPS para Sefin/ADN, Inter, Google e provedores de login é obrigatória; entrada pública só é necessária para acesso externo e webhook do Inter (opcional). |
| Processamento assíncrono | Emissão, lote, e-mail, Drive e agendamentos em fila. **Celery + Redis**, padrão já operado na Topo (ver 1.7), com *dispatcher* único no Celery beat para os agendamentos. |
| Máquina de estados da NFS-e | `rascunho → enviando → autorizada → cancelada/substituída`, `rejeitada`, `erro_comunicacao`. Transições só pela camada de serviço. |
| Auditoria | Trilha imutável: quem, quando, o quê, de qual IP; payloads enviados/recebidos da Sefin. |
| Ambientes | Produção restrita (testes) × produção por empresa, com aviso visual forte na UI quando em teste. |
| LGPD | CPF e dados de pessoas físicas: base legal (obrigação legal), controle de acesso, política de retenção. |
| Backup | Rotina de backup do PostgreSQL + teste de restauração; chave mestra guardada separadamente. |
| Observabilidade | Logs estruturados, healthcheck, alerta de falhas de emissão e de agendamentos. |
| Qualidade | `ruff`, `mypy`, `pytest`, testes de integração contra produção restrita; ESLint + Vitest no frontend (JavaScript, como no padrão de referência da Topo; ver 1.7); CI no GitHub Actions. |
| Acessibilidade | Contraste nos dois temas (WCAG AA), navegação por teclado. |
| Dados para BI | Views ou exportação estruturada (notas, itens, retenções, cobranças) para alimentar Stage/DW sem acessar tabelas transacionais diretamente. |

---

## 6. Proposta de priorização (MVP em fases)

1. **Fundação:** autenticação (allauth/OIDC), empresas (schema), vínculos usuário × empresa e perfis, criptografia, certificado A1, parâmetros fiscais, auditoria, temas.
2. **Núcleo fiscal:** pessoas, serviços, emissão/consulta/cancelamento/substituição em produção restrita, DANFSe, XML, download em lote.
3. **Produtividade:** modelos de NFS-e, agendamentos (com aprovação), envio de e-mail.
4. **Integrações:** notas recebidas via ADN, Google Drive (cópia de XML/PDF), Banco Inter (emissão de boleto).

Justificativa: o risco técnico e fiscal está na fase 2; integrações dependem de a emissão estar estável.

---

## 7. Questões em aberto (precisam de decisão)

1. ~~Multiempresa~~ → decidido: isolado por empresa (D4, rev. 3).
2. ~~Cadastro de pessoas~~ → por empresa, isolado (D4).
3. ~~Recorrência~~ → "mensal" duplicado era erro (D13).
4. ~~Modo do agendamento~~ → gera rascunho (D12).
5. ~~NFS-e recebidas~~ → entram (D11).
6. ~~Google Drive~~ → copiar XML e PDF (D14).
7. ~~Cobrança~~ → apenas emissão + marcação manual (D6).
8. ~~Biblioteca fiscal~~ → `freedfe` com estado injetável (D5).
9. ~~Design system como pacote~~ → não é pacote; tokens versionados em `docs/design-system.md`.
10. ~~Endereço público / implantação~~ → haverá (D7); interno, VPS ou nuvem (D15).
11. ~~Usuário em várias empresas~~ → sim, com perfil por empresa (D10).
12. ~~Isolamento~~ → por schema (D16).
13. ~~Feriado/fim de semana~~ → executa mesmo assim (D17).
14. ~~Design system~~ → design system da Topo, logo por empresa, botão/campo centralizados (D18).

**Não há questões abertas para os requisitos iniciais.** A dependência da `freedfe` (contratos injetáveis e uso sem pasta) foi resolvida na versão 0.3.0.
