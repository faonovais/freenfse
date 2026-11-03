# freenfse

Sistema para emissão e gestão de notas fiscais de serviços eletrônica que utiliza o ambiente nacional.

> Em construção. Requisitos e plano em [`docs/`](docs/); convenções em [`GUIDELINES.md`](GUIDELINES.md).

## Stack

Python 3.14 · Django 6.1 · Django REST Framework 3.18 · PostgreSQL 18 (schema por empresa, `django-tenants`) · Celery + Redis · React 19 · Vite · Tailwind 4. Decisão das versões: [ADR 0001](docs/adr/0001-versoes.md). Acesso, empresas e segurança: [ADR 0002](docs/adr/0002-acesso-e-seguranca.md). Cadastros e configuração fiscal: [ADR 0003](docs/adr/0003-cadastros-e-configuracao-fiscal.md).

## Subir com Docker Compose

```bash
cp .env.example .env
```

Preencha `SECRET_KEY`, `POSTGRES_PASSWORD` e `FREENFSE_CHAVES` no `.env` (o arquivo explica como gerar cada uma e **não** é versionado). Depois:

```bash
docker compose up --build
```

```bash
curl http://localhost:8080/api/versao/
```

A interface fica em `http://localhost:8080/` (porta definida por `HTTP_PORT`).

## Primeiro acesso

Não há cadastro público: só entra quem o administrador (**Master**) cadastrou. O primeiro Master é criado pela linha de comando:

```bash
docker compose exec backend python manage.py createsuperuser
```

Entre com esse e-mail e senha. Como o Master precisa de verificação em duas etapas, o sistema leva direto à configuração (aplicativo autenticador + códigos de recuperação). Depois, em **Administração**, cadastre as empresas, os usuários e os vínculos (qual perfil cada usuário tem em cada empresa).

### Login com Google (opcional)

1. No console do Google Cloud, crie uma credencial OAuth do tipo *aplicativo da Web*.
2. Cadastre como URI de redirecionamento autorizada `https://<seu-dominio>/accounts/google/login/callback/`.
3. Preencha `AUTH_GOOGLE_CLIENT_ID` e `AUTH_GOOGLE_CLIENT_SECRET` no `.env` e reinicie o `backend`.

O botão "Entrar com Google" só aparece quando as duas variáveis estão preenchidas. O login social **não cria contas**: o e-mail do Google precisa estar cadastrado pelo Master e verificado pelo Google. `AUTH_DOMINIOS_PERMITIDOS` restringe os domínios aceitos. Microsoft e OpenID Connect estão instalados, mas desligados por padrão.

### Configuração fiscal da empresa

Depois de criar a empresa e o vínculo, o Administrador da empresa configura, em **Configuração fiscal**: parâmetros
(regime, série da DPS, município emissor e ambiente — o padrão é a **produção restrita**), certificado A1 e logo; e, em
**Cadastros**, pessoas e serviços. Os municípios do IBGE são carregados sozinhos na subida do backend
(`carregar_municipios`). O roteiro para validar com um certificado real está em
[`docs/verificacao-fase-2.md`](docs/verificacao-fase-2.md).

### Emissão de NFS-e

Com a empresa pronta (certificado, município e **convênio verificado**), o Emissor usa **Notas fiscais › NFS-e emitidas**:
escolhe o tomador e o serviço vigente na competência, informa os valores, **confere** o cálculo e envia. A emissão roda
na fila (Celery), **uma por vez por empresa**, e a tela acompanha o resultado.

- Se a Sefin não responder (timeout, 5xx), a nota fica **"resultado incerto"**: o sistema só *consulta* a Sefin (a cada 5
  minutos ou em "Conferir agora") e **nunca reenvia por conta própria**. "Tentar enviar de novo" reaproveita o mesmo número.
- O leiaute da DPS segue a data: **NT 004** em produção até 30/11/2026 e **NT 009** depois (produção restrita: sempre NT 009).
- Cancelamento e substituição só mudam a nota depois que a Sefin confirma o evento.
- O DANFSe é gerado na hora (com marca d'água se a nota estiver cancelada ou substituída); o XML original fica guardado com hash.

O roteiro para validar tudo isto com um certificado real, incluindo o teste de timeout, está em
[`docs/verificacao-fase-3.md`](docs/verificacao-fase-3.md); as decisões, em [`docs/adr/0004-nucleo-fiscal.md`](docs/adr/0004-nucleo-fiscal.md).

### Chaves de criptografia

`FREENFSE_CHAVES` guarda as chaves que cifram dados sensíveis (certificados, senhas, tokens). Gere uma com `docker compose run --rm backend python manage.py gerar_chave` e use o formato `1:<chave>`. **Guarde-a fora do servidor e do repositório**: sem ela, o que foi cifrado não pode ser recuperado. A rotação de chaves está descrita no `.env.example`.

## Desenvolvimento

Backend (precisa de PostgreSQL 18 acessível conforme o `.env`):

```bash
cd backend
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest
```

Frontend:

```bash
cd frontend
npm ci
npm run lint && npm test && npm run build
```

## Segurança

O repositório é público: configuração só por variáveis de ambiente, nenhum segredo, certificado ou dado real versionado. O CI roda `gitleaks`. Detalhes em [`GUIDELINES.md`](GUIDELINES.md) §7.

## Licença

Apache 2.0 — ver [`LICENSE`](LICENSE).
