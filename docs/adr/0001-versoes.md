# ADR 0001 — Versões da stack

- **Status:** aceita
- **Data:** 2026-10-30
- **Decisões relacionadas:** D3 (versões), D2 (Django + DRF), D16 (schema por empresa) em `docs/analise-requisitos.md`

## Contexto

D3 definiu usar a versão estável mais recente que **todas** as dependências críticas suportam: Python 3.14, Django 6.1, DRF 3.18 e PostgreSQL 18. O plano de implementação (Fase 0) manda confirmar, antes de fixar, que `django-tenants` e `django-allauth` suportam Django 6.1 e, se não suportarem, usar Django 5.2 LTS em vez de forçar versões.

## Decisão

**Manter Django 6.1.** Não foi necessário o recuo para o 5.2 LTS.

| Componente | Versão fixada | Onde |
|---|---|---|
| Python | 3.14 (testado com 3.14.6) | `python:3.14-slim`, CI |
| Django | 6.1.2 | `backend/requirements.txt` |
| Django REST Framework | 3.18.3 | idem |
| django-tenants | 4.0.1 | idem |
| django-allauth | 65.21.0 (verificado; entra na Fase 1) | — |
| psycopg | 3.3.6 (`psycopg[binary]`) | `backend/requirements.txt` |
| PostgreSQL | 18 (testado com 18.6) | `postgres:18`, CI |
| Celery / redis-py / Redis | 5.6.3 / 6.4.0 / 7 | `backend/requirements.txt`, `redis:7` |
| Gunicorn | 26.2.0 | `backend/requirements.txt` |
| freedfe | 0.3.0, fixada pelo commit `56ea16a6c4b44248a19e7472fce4f9237e3060a8` (extra `nfse`: lxml 6.1.3, reportlab 5.1.0, pillow 13.0.0; cryptography 50.0.2) | `backend/requirements.txt` |
| Node (frontend) | 22 (engines ≥ 22.22.2, exigido pelo jsdom 30) | `package.json`, CI |
| React / Vite / Tailwind / Vitest / ESLint | 19.3.1 / 8.3.5 / 4.3.3 / 5.0.5 / 10.13.0 | `frontend/package.json` |

Todas as dependências diretas e transitivas do backend estão fixadas (`requirements*.in` → `requirements*.txt`, gerados com `uv pip compile --python-version 3.14`). O frontend usa versões exatas e `package-lock.json`.

## Evidência de compatibilidade com Django 6.1

### 1. Metadados no PyPI (consultados em 2026-10-30)

| Pacote | Versão | Declaração relevante |
|---|---|---|
| django-tenants | 4.0.1 | `Requires-Dist: django<6.2,>=5.2`; classificador Django 6.1 |
| django-allauth | 65.21.0 | classificadores Django 4.2 a 6.1 e Python 3.11 a 3.14 |
| djangorestframework | 3.18.3 | classificadores Django 5.2 a 6.1 e Python 3.10 a 3.15 |
| Django | 6.1.2 | `Requires-Python: >=3.12`; classificadores 3.12 a 3.14 |

### 2. Teste prático (Python 3.14.6, Django 6.1.2, PostgreSQL 18.6)

Os classificadores não bastam: `django-tenants` e Celery não listam Python 3.14. Por isso foram executados:

- **django-tenants + django-allauth** em ambiente descartável, com `allauth.account`, `allauth.socialaccount` + provedor Google, `allauth.mfa` e `allauth.headless` ao lado do `django_tenants`: `manage.py check` sem problemas; `migrate_schemas --shared` aplicou todas as migrações; a criação de uma empresa criou o schema e aplicou as migrações das apps de tenant; a rota headless resolveu.
- **Backend do projeto**: `pytest` (10 testes) contra PostgreSQL 18.6, incluindo criação e remoção do schema de uma `Empresa`.
- **Celery 5.6.3 em Python 3.14**: no Docker Compose, `celery inspect ping` responde e a task `core.tasks.ping` executada no worker retorna `pong`; o `beat` sobe sem erros.
- **Gunicorn 26.2.0**: sobe e atende `/api/versao/` atrás do Nginx.
- **freedfe 0.3.0 em Python 3.14**: a resolução de dependências conclui sem conflito com os pins existentes (só acrescenta `lxml`, `reportlab`, `pillow`, `cryptography` e transitivas), todas com wheels para 3.14. A versão instalada é 0.3.0 e os pontos de entrada usados pelo plano (`freedfe.nfse.fabrica.criar_servico_nfse`, `freedfe.certificado.CertificadoA1`) importam; `core/tests/test_dependencias.py` guarda isso.

## Consequências

- Django 6.1 **não é LTS**: o suporte termina pouco depois do 6.2 LTS (previsto para abril/2027). A migração para o 6.2 LTS deve entrar no planejamento do primeiro semestre de 2027.
- Revisar as versões semestralmente, aplicando o mesmo critério (D3).
- O Gunicorn 26 cria um socket de controle em `$HOME`; o contêiner roda sem home, então o `CMD` usa `--no-control-socket`.
- A `freedfe` é instalada por **commit**, não por tag: o repositório dela não publica tags. Por isso o `Dockerfile.backend` usa um estágio de build com `git`, que não vai para a imagem final. Trocar para uma tag ou para o PyPI quando a biblioteca publicar uma versão.
- Se uma dependência futura deixar de suportar Django 6.1, a regra de recuo do plano continua valendo: usar Django 5.2 LTS e registrar um novo ADR.
