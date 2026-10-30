# freenfse

Sistema para emissão e gestão de notas fiscais de serviços eletrônica que utiliza o ambiente nacional.

> Em construção. Requisitos e plano em [`docs/`](docs/); convenções em [`GUIDELINES.md`](GUIDELINES.md).

## Stack

Python 3.14 · Django 6.1 · Django REST Framework 3.18 · PostgreSQL 18 (schema por empresa, `django-tenants`) · Celery + Redis · React 19 · Vite · Tailwind 4. Decisão das versões: [ADR 0001](docs/adr/0001-versoes.md). Acesso, empresas e segurança: [ADR 0002](docs/adr/0002-acesso-e-seguranca.md).

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
