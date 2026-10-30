# freenfse

Sistema para emissão e gestão de notas fiscais de serviços eletrônica que utiliza o ambiente nacional.

> Em construção. Requisitos e plano em [`docs/`](docs/); convenções em [`GUIDELINES.md`](GUIDELINES.md).

## Stack

Python 3.14 · Django 6.1 · Django REST Framework 3.18 · PostgreSQL 18 (schema por empresa, `django-tenants`) · Celery + Redis · React 19 · Vite · Tailwind 4. Decisão das versões: [ADR 0001](docs/adr/0001-versoes.md).

## Subir com Docker Compose

```bash
cp .env.example .env
```

Preencha `SECRET_KEY` e `POSTGRES_PASSWORD` no `.env` (o arquivo explica como gerar cada uma e **não** é versionado). Depois:

```bash
docker compose up --build
```

```bash
curl http://localhost:8080/api/versao/
```

A interface fica em `http://localhost:8080/` (porta definida por `HTTP_PORT`).

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
