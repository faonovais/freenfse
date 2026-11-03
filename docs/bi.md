# Dados para BI (schema `bi`)

O freenfse expõe os dados das notas para BI por **views** em um schema de leitura (`bi`), sem
precisar dar acesso às tabelas das empresas. Fluxo recomendado (arquitetura da Topo):
`Fonte → Stage → DW → DM → Modelo Semântico → Relatórios` — estas views são a **fonte** do Stage;
a modelagem dimensional, o histórico (SCD) e as regras de negócio ficam no DW, não aqui.

## Como acessar

1. Quem instala cria o usuário de leitura (uma vez):

   ```bash
   FREENFSE_BI_SENHA='<senha de 16+ caracteres>' python manage.py criar_usuario_bi
   ```

   No Docker Compose: `docker compose exec -e FREENFSE_BI_SENHA=... backend python manage.py criar_usuario_bi`.
   A senha nunca é exibida; o PostgreSQL recebe só o verificador SCRAM-SHA-256.
2. Conecte a ferramenta de BI (Power BI, por exemplo, conector PostgreSQL) ao banco do freenfse com o usuário
   `freenfse_bi` (nome em `FREENFSE_BI_USUARIO`). O `search_path` dele já é `bi`.
3. As views se atualizam sozinhas quando nasce uma empresa e a cada subida do backend
   (`atualizar_views_bi --se-existir`). Para forçar: `python manage.py atualizar_views_bi`.

O usuário é **somente leitura** (`default_transaction_read_only`, sem `INSERT/UPDATE/DELETE/CREATE`),
sem `SUPERUSER`/`CREATEDB`/`CREATEROLE`, com limite de 10 conexões, `statement_timeout` de 120 s e sem
acesso às tabelas das empresas nem ao schema público (usuários, sessões, credenciais).

## Modelo

Todas as views trazem `empresa_id` e `empresa_cnpj` (consolidam todas as empresas). Chave de junção entre
views: **(`empresa_id`, `nota_id`)** — `nota_id` só é único dentro da empresa.

| View | Grão (uma linha por…) | Chave | Para que serve |
|---|---|---|---|
| `bi.empresas` | empresa | `empresa_id` | cadastro mínimo (CNPJ, razão social, ativa) |
| `bi.notas` | NFS-e (rascunho, autorizada, cancelada…) | `empresa_id`, `nota_id` | faturamento, ISS, situação, competência, tomador (pseudonimizado), nota substituída (`nota_substituida_id`) |
| `bi.servicos` | nota (a DPS tem um serviço) | `empresa_id`, `nota_id` | receita por serviço/código de tributação, NBS e classificação do IBS/CBS |
| `bi.retencoes` | nota × tipo de retenção com valor > 0 | `empresa_id`, `nota_id`, `tipo` | retenções de ISS (só se retido), IRRF, CSLL e INSS |
| `bi.eventos` | evento fiscal (cancelamento, substituição…) | `empresa_id`, `evento_id` | auditoria de cancelamentos |

Valores monetários são `numeric` (reais, duas casas). `competencia` é a data do primeiro dia do mês.
`situacao` usa os mesmos códigos da API (`rascunho`, `enviando`, `autorizada`, `rejeitada`, `incerta`,
`cancelada`, `substituida`, `descartada`) — filtre por `autorizada` para faturamento.

**PIS/COFINS** não aparecem em `bi.retencoes`: a retenção continua bloqueada até a validação do contador.

## O que NÃO está nas views (de propósito)

* XML de qualquer espécie, hash do XML, certificado, senhas, tokens, credenciais de e-mail e Drive;
* texto livre (descrição do serviço, informações complementares): pode conter dado pessoal;
* e-mail e telefone do tomador;
* **tomador pessoa física:** o CPF sai **mascarado** (`***456789**`: só os 6 dígitos do meio) e o **nome não sai**;
  pessoa jurídica sai com CNPJ e razão social. A chave `tomador_documento` mascarada serve para contar
  clientes distintos com pequeno risco de colisão.

> **Decisão em aberto (usuário):** esta é a minimização de dados (LGPD) adotada por padrão. Se o negócio
> precisar do CPF completo ou do nome da pessoa física no BI, é uma mudança de uma linha na definição da
> view (`operacao/bi.py`), mas amplia a exposição de dado pessoal e deve ser decidida e registrada.

## Observações para o DW

* Carga incremental: use `atualizada_em` (em `bi.notas`) e `criado_em` (em `bi.eventos`).
* As views leem as tabelas operacionais diretamente: consultas pesadas devem rodar fora do horário de
  emissão, ou sobre uma réplica de leitura do PostgreSQL.
* Recomenda-se materializar no Stage em vez de ligar o relatório direto nas views.
