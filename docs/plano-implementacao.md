# Plano de implementação — freenfse (Fases 0 a 6)

## Contexto

O freenfse está só com README, LICENSE e a documentação de requisitos (`docs/analise-requisitos.md`, decisões D1–D23, e `docs/design-system.md`). Os requisitos iniciais estão fechados e a dependência fiscal (`topoconsultoria/freedfe` 0.3.0) já oferece persistência injetável e uso sem pasta. Este plano transforma as decisões em entregas incrementais, cada uma utilizável e testável, usando a `freedfe` e os padrões de referência da Topo (ver regra abaixo).

**Fora deste plano (por decisão do usuário):** NFS-e recebidas via ADN (D11) e Cobranças/Banco Inter (D6, D19, D20). Viram issues no GitHub do freenfse (ver "Issues a registrar") e entram em plano posterior.

Ao aprovar: (1) salvar este plano em `docs/plano-implementacao.md` no branch `claude/freenfse-requirements-review-bjm9jg`; (2) abrir as duas issues no `faonovais/freenfse`.

## Premissas e convenções

- Stack (D2, D3, D16, D23): Python 3.14, Django 6.1 + DRF 3.18, PostgreSQL 18, `django-tenants` (schema por empresa), `django-allauth` (headless), Celery + Redis, React 19 + Vite + Tailwind 4 (JavaScript, sem TS), Vitest.
- **Risco de compatibilidade:** confirmar no bootstrap que `django-tenants` e `django-allauth` suportam Django 6.1. Se não suportarem, usar **Django 5.2 LTS** (registrar em ADR) — não forçar versões.
- Convenções: padrão de referência da Topo (nomes em PT, `TextChoices` aninhadas, `criado_em`/`atualizado_em`/`ativo`, ViewSets com `DefaultRouter`, `@action`, testes pytest), com as correções de `docs/design-system.md` §3 e §4 (botão/campo como `@utility`, fontes locais).
- **Referência privada:** padrões da Topo vêm de um sistema interno privado, usado **só como referência**, com acesso pontual autorizado pelo usuário e clone apagado após o uso. Nada interno dele é versionado; cabeçalho, quando houver, apenas "Baseado no design system da Topo". O freenfse não depende desse sistema.
- **Repositório público:** nenhum dado confidencial (credenciais, certificados, `.env`, dados pessoais) é versionado; gitleaks no CI.
- Arquitetura em camadas (D1): `models` → `services` (regra de negócio e orquestração) → `api` (serializers/viewsets) → React. Regra fiscal só em `services`.
- Cada fase termina com: `ruff`, `pytest`, `eslint`, `vitest` limpos no CI e um roteiro de verificação manual em produção restrita quando houver chamada à Sefin/ADN.

## Estrutura alvo do repositório

```
backend/
  config/            settings, urls, celery, hosts
  core/              Usuario, Empresa (tenant), Dominio, VinculoUsuarioEmpresa, crypto, fields,
                     permissões, middleware de empresa, auditoria, email/
  cadastros/         Pessoa, PerfilPessoa, Servico, Municipio (tenant)
  fiscal/            ParametrosFiscais, Certificado, persistência freedfe, NFS-e, eventos, DANFSe
  documentos/        download em lote, cópia ao Google Drive, envio de e-mail da nota
  agendamentos/      ModeloNfse, Agendamento, Rascunho
frontend/src/        api/, components/, contexts/, hooks/, pages/, utils/, index.css
docker/              Dockerfile.backend, Dockerfile.nginx, nginx.conf
installer/           instalador CLI (Docker ou nativo)
docs/                requisitos, design system, plano, ADRs
```

---

## Fase 0 — Bootstrap do projeto

**Objetivo:** esqueleto executável com CI.

- `backend/`: projeto Django com `django-tenants` (SHARED_APPS: `core`; TENANT_APPS: demais), `django-environ`, `psycopg`, DRF, Celery (`config/celery.py`), `requirements.txt` + `requirements-dev.txt` com versões fixadas, `pytest.ini` com `testpaths` explícitos.
- `frontend/`: Vite + React 19 + Tailwind 4; `index.css` conforme `docs/design-system.md` (tokens, `.dark`, utilitários) + `@utility botao|botao-leve|botao-perigo|campo` + `@font-face` local (Poppins 600/900, Source Code Pro 300/400/600 em `public/fonts/`).
- `docker-compose.yml`: `postgres:18`, `redis:7`, backend, worker, beat, nginx.
- CI GitHub Actions: ruff, pytest (com PostgreSQL de serviço), eslint, vitest, build do frontend.
- `VERSION` como fonte única, `GUIDELINES.md` do freenfse (convenções acima), ADR das versões.
- `freedfe` fixada por tag/commit ≥ 0.3.0 com extras `nfse`.

**Pronto quando:** `docker compose up` sobe a aplicação vazia; CI verde; endpoint `/api/versao/`.

## Fase 1 — Fundação: acesso, empresas e segurança

**Objetivo:** login, multiempresa isolada, permissões e criptografia.

Backend:
- `core.Empresa` (TenantMixin, `auto_create_schema`) + `Dominio`; `core.Usuario` sem empresa/perfil próprios; `is_master` (D22).
- `VinculoUsuarioEmpresa` (usuário, empresa, perfil, permissões extras/removidas, ativo; único por par).
- Permissões nomeadas (`nfse.emitir`, `nfse.cancelar`, `cadastro.editar`, `config.editar`, …; catálogo extensível para as permissões futuras de notas recebidas e cobranças) e perfis padrão Administrador, Emissor, Financeiro, Consulta (D22); `PermissaoPorOperacao` (DRF) com `permissao_requerida` por ação.
- **Middleware de empresa por requisição (D10):** lê `X-Empresa`, valida vínculo ativo (ou Master), ativa o schema; nunca da sessão.
- Autenticação (D8, D23): `django-allauth` headless + Google + e-mail/senha + MFA TOTP; Microsoft e `openid_connect` instalados e desligados; **sem autocadastro** (adapter recusa e-mail não cadastrado); restrição opcional de domínio. Incluir bloqueio por tentativas de login e expiração de sessão.
- Criptografia: AES-256-GCM com campo de modelo criptografado, **com versão da chave** no token (`v<n>:` + nonce + cifra), chaves `FREENFSE_CHAVES` (atual + antigas) e comando `recriptografar`. Campo binário criptografado para `.pfx`.
- Auditoria: `LogAuditoria` (usuário, empresa, ação, alvo, IP, marca `master`, detalhes JSON).
- API de administração (Master): empresas, usuários, vínculos.

Frontend:
- Componentes base de `docs/design-system.md` §5: `TemaContext`, `SeletorTema`, `ModalConfirmacao`, `ConfirmacaoContext`, `useFormularioSujo`, `SelectBusca`, `SelectMultiBusca`, `CabecalhoColuna`, `useGridLocal`, `PainelColapsavel`, `BotaoAjuda`, `api/http.js`, `utils/erros.js`.
- `Layout` e `AuthContext`: **alterador de empresa** (empresas vinculadas; todas para o Master) com a empresa ativa **por aba** (estado da aba + `X-Empresa` em `http.js`), nome/CNPJ sempre visíveis, selo de produção restrita.
- Telas: login (Google + e-mail/2FA), configuração de 2FA, administração de empresas/usuários/vínculos.

**Pronto quando:** Master cria duas empresas e um usuário com perfis diferentes em cada; o usuário alterna empresas em duas abas sem vazamento; testes cobrem isolamento de schema, negação sem vínculo, login social sem cadastro recusado, rotação de chave.

## Fase 2 — Cadastros e configuração fiscal da empresa

**Objetivo:** tudo o que a DPS precisa, por empresa.

- `Municipio` (código IBGE, nome, UF) carregado por comando de gestão a partir de arquivo versionado.
- `Pessoa` (CPF/CNPJ com dígito verificador, estrangeiro com NIF, inscrição municipal, endereço com IBGE, e-mails de envio de nota) + `PerfilPessoa` N:N (cliente, fornecedor, intermediário…). Ação "copiar de outra empresa" (exige vínculo nas duas).
- `Servico`: código de tributação nacional, municipal, NBS, CST/cClassTrib IBS/CBS, alíquota ISS, retenções, descrição, **vigência** (início/fim).
- `ParametrosFiscais`: regime tributário, opção Simples/regime de apuração, série da DPS, ambiente (produção restrita × produção), município emissor; botão "verificar convênio" usando `ServicoNfse.convenio` / `parametros_contribuinte` da `freedfe`.
- `CertificadoA1`: upload `.pfx` + senha (criptografados), validação com `freedfe.certificado.CertificadoA1` (senha, CNPJ do titular × empresa, validade), alertas de vencimento 30/15/7 dias (task diária).
- Logo da empresa (D18): claro/escuro, PNG/SVG sanitizado, exibido no cabeçalho.

**Pronto quando:** uma empresa de teste fica com cadastro completo, certificado de produção restrita validado e convênio do município verificado.

## Fase 3 — Núcleo fiscal: emissão, consulta, cancelamento, substituição

**Objetivo:** emitir NFS-e com segurança de numeração e rastreabilidade.

- **Persistência da `freedfe` em PostgreSQL** (`fiscal/persistencia/`), por schema de empresa, implementando os contratos: `EstadoEmissao` (`reservar_proximo` em transação com `SELECT … FOR UPDATE`), `Trava` (`pg_advisory_xact_lock` por recurso), `EstadoSequenciaNsu`, `Auditoria`, `CacheParametros`, `ArmazenamentoEvidencias`, `RepositorioDocumentos`. Validar com `freedfe/tests/contrato_estado_emissao.py` (e equivalentes) importados nos testes do freenfse.
- `GatewayNfse` (camada de serviços): monta o serviço com `freedfe.nfse.fabrica.criar_servico_nfse` e certificado descriptografado em memória; único ponto de contato com a biblioteca.
- Modelo `Nfse` (campo direção já criado, só `emitida` usada nesta etapa — evita migração quando as recebidas entrarem; situação, chave, número, competência, valores, tomador, **leiaute usado**, XML), `EventoNfse`; máquina de estados `rascunho → enviando → autorizada → cancelada/substituída`, `rejeitada`, `incerta`.
- Emissão via Celery (uma por vez por empresa/série pela trava), reconciliação periódica de `incerta` (`reconciliar_pendentes`); cancelamento (motivos, mensagens didáticas das rejeições municipais); substituição como "emitir nota substituta a partir desta" (`Dps.substituicao`).
- DANFSe com `ServicoNfse.danfse_bytes` (gerado sob demanda, não armazenado); XML guardado no banco.
- Telas: lista com filtros, emissão (formulário guiado), detalhe com eventos, cancelar/substituir com confirmação.
- **Virada de leiaute 30/11/2026:** teste específico em produção restrita com NT 009; nota guarda o leiaute.

**Pronto quando:** em produção restrita, emitir, consultar, cancelar e substituir funcionam; teste de concorrência (N emissões paralelas) sem número repetido; timeout simulado vira `incerta` e é reconciliado sem duplicar.

## Fase 4 — Documentos: lote, e-mail e Google Drive

- **Download em lote:** task gera ZIP (XML + PDF + CSV-resumo) por filtros, com limite e notificação; arquivo temporário com expurgo.
- **E-mail (D21):** provedores SMTP, Gmail API e Microsoft Graph atrás de interface comum, com configuração **por empresa**; modelos de mensagem com variáveis; configuração de quando enviar (manual padrão / automático ao autorizar / aviso de cancelamento) e anexos (PDF, XML; o anexo de boletos entra com a issue de cobranças), sobreponível por modelo de NFS-e; `EnvioEmail` (registro por nota) e reenvio manual.
- **Google Drive (D14):** conta de serviço criptografada por empresa; **ID da pasta raiz** validado ao salvar; modelos de subpastas e de nome de arquivo com `{ano} {mes} {dia} {numero_nfse} {nome_emitente} {cnpj_emitente} {chave}`; validação de unicidade (`{chave}` ou `{numero_nfse}`+`{cnpj_emitente}`), pré-visualização; cache `caminho → ID` com unicidade + trava por empresa; gatilhos (autorização e eventos; notas recebidas entram com a issue correspondente); sufixo de evento; substituição do PDF com marca d'água; "reenviar ao Drive". Cliente: `google-api-python-client`.

**Pronto quando:** nota autorizada aparece no Drive na pasta/nome do modelo; cancelamento troca o PDF e grava o XML do evento; e-mail chega com anexos configurados; lote de um mês baixa completo.

## Fase 5 — Modelos de NFS-e e agendamentos

- `ModeloNfse` (tomador, serviço, valores, retenções, texto, configuração de e-mail). Emissão copia os dados (snapshot).
- `Agendamento` (D12, D13, D17): cálculo de recorrência (única, diária, semanal, mensal, "a cada N", início/fim, limite de execuções, último dia do mês, fuso) + **anual** (29/02 → 28/02); fim e execuções mutuamente exclusivos; executa em feriado/fim de semana.
- Dispatcher único no Celery beat varrendo todas as empresas, gerando **rascunhos** com competência = mês da execução; falha não conta execução; responsável com vínculo inativo suspende o agendamento.
- Tela de rascunhos: edição, aprovação individual e em lote (exige `nfse.emitir`), alerta diário de pendentes.

**Pronto quando:** agendamento mensal gera rascunho na data, aprovação em lote emite; testes do cálculo de datas.

## Fase 6 — Operação e entrega

- Instalador CLI (Docker Compose ou nativo systemd + Nginx) (D15) e páginas de erro do Nginx.
- Backup do PostgreSQL com teste de restauração; procedimento da chave mestra; `/tmp` em `tmpfs` nos contêineres.
- Healthcheck, logs estruturados, alertas de falha de emissão/agendamento/ADN/Drive.
- LGPD (base legal, retenção), guarda de XML ≥ 5 anos.
- Views para BI (notas, itens, retenções) em schema de leitura.
- Documentação de usuário em linguagem didática e manual de instalação.

**Pronto quando:** instalação limpa em VPS de teste pelo instalador, restauração de backup validada.

---

## Dependências entre fases

0 → 1 → 2 → 3 → {4, 5} → 6. As fases 4 e 5 podem correr em paralelo após a 3.

## Verificação (aplicada em todas as fases)

- CI: `ruff check`, `pytest` (com PostgreSQL 18 e schemas de teste via `schema_context`), `npm run lint`, `npm test`, `npm run build`.
- Testes de contrato da `freedfe` contra as implementações PostgreSQL (Fase 3).
- Testes de isolamento: requisição sem vínculo, `X-Empresa` de outra empresa, duas abas com empresas diferentes.
- Roteiro manual em **produção restrita** (certificado de teste) ao fim das Fases 2 e 3; pasta de teste no Drive na Fase 4.
- Execução da aplicação pela skill `run`/Playwright (Chromium pré-instalado) para checar telas nos dois temas.

## Entrega

Um branch e um PR por fase (Fase 0 a 6), cada um com CI verde e roteiro de verificação descrito no PR.

## Issues a registrar (fora deste plano)

Abertas no `faonovais/freenfse` após a aprovação, com o escopo já decidido em `docs/analise-requisitos.md`:

1. **NFS-e recebidas (tomadas) via ADN** — D11, §2.5: sincronização periódica por empresa com `ServicoNfse.sincronizar` e `EstadoSequenciaNsu` em PostgreSQL; `Nfse` com direção `recebida`; eventos atualizam situação; telas e permissão `nfse_recebida.consultar`; reaproveita DANFSe, XML, lote e Drive. Depende das Fases 3 e 4.
2. **Cobranças e Banco Inter** — D6, D19, D20, §4.2: `Cobranca` (várias formas por NFS-e, situação em aberto/pago/cancelado); `ProvedorCobranca` + `ProvedorInter` (mTLS, OAuth, boleto com QR Code Pix, cancelamento); marcação manual; fluxo que **pergunta o que fazer** com cada cobrança ao cancelar/substituir a NFS-e (após confirmação da Sefin); anexo de boletos no e-mail; webhook opcional. Depende das Fases 3 e 4.
