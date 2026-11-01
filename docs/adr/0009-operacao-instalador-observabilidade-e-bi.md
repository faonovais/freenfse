# ADR 0009 — Instalador, observabilidade e BI (Fase 6, issue #9)

Status: aceito (implementado na Fase 6). Complementa o [ADR 0008](0008-criptografia-em-repouso-backup-e-retencao.md).

## Contexto

O sistema precisa ser instalável por quem não é desenvolvedor, em servidor interno, VPS ou nuvem (D15), operar sem
vigilância constante (baixa maturidade e infraestrutura limitada dos clientes) e alimentar o BI sem dar acesso às tabelas
transacionais.

## Decisão 1 — Instalador em Python, Compose como caminho principal

* **Python, só biblioteca padrão** (`instalador/instalar.py`): roda em qualquer servidor com Python 3, sem instalar nada
  antes e sem o ecossistema do projeto. É testável (executor simulado, `--simular`), ao contrário de um script de shell.
  Alternativas: shell (difícil de testar e de manter idempotente), Ansible/Terraform (dependência pesada e curva de
  aprendizado para o perfil dos clientes).
* **Dois modos:** Docker Compose (recomendado: poucas peças, atualização por `git pull` + reexecução) e nativo
  (systemd + Nginx + Gunicorn + worker + beat) para onde não se usa Docker.
* **Segredos:** o `.env` nasce de `.env.example`, com `SECRET_KEY`, `FREENFSE_CHAVES`, senha do banco e do BI aleatórios,
  permissão 600, gravação atômica. Nenhum segredo é impresso (tudo passa por uma máscara) nem vai na linha de comando
  (`docker compose exec -e NOME` herda o valor do ambiente do processo; a senha do papel do PostgreSQL vai como
  **verificador SCRAM** pela entrada padrão do `psql`).
* **Idempotência:** um segredo que já existe **nunca** é trocado (trocar `FREENFSE_CHAVES` tornaria ilegíveis os dados
  cifrados; trocar `SECRET_KEY` derruba as sessões); volumes e backups nunca são apagados; domínio, pasta de dados e chave
  pública de backup já configurados são reaproveitados numa nova execução sem parâmetros.
* **HTTPS:** Let's Encrypt (certbot, desafio HTTP-01 pela porta 80; o instalador sobe primeiro em HTTP, obtém o certificado e
  troca a configuração do Nginx) ou certificado próprio. Ligar o HTTPS liga junto `COOKIES_SEGUROS`, `PROXY_TLS`,
  `CSRF_TRUSTED_ORIGINS` e o HSTS, para o login não entrar em loop.
* **PostgreSQL no Compose** continua em volume nomeado do Docker: trocar para uma pasta do host numa reinstalação deixaria
  os dados antigos órfãos. A pasta de dados (`--dados`) guarda backups, certificados e o estado do instalador.
* **Limites assumidos:** o instalador foi testado com executor simulado e o Nginx real em teste; **não** foi exercitado
  numa VPS limpa nem com Docker/systemd reais neste ambiente de desenvolvimento. O roteiro de VPS
  ([`docs/verificacao-fase-6.md`](../verificacao-fase-6.md)) é a prova que falta e fica com o usuário.

## Decisão 2 — Nginx com trechos comuns e erros em linguagem simples

`locais.conf` (rotas, cabeçalhos, erros) é compartilhado entre HTTP, HTTPS e o modo nativo. Erros gerados pelo Nginx viram
página amigável em português para o navegador (`/accounts/`, SPA) e **JSON no formato dos erros do sistema**
(`{codigo, detalhe}`) para `/api/` e `/_allauth/`; respostas de erro do próprio sistema passam sem alteração. Sem HTTP/2:
diretiva diferente entre versões do Nginx (1.24 das distribuições × 1.30 da imagem); ganho irrelevante neste volume.

## Decisão 3 — Observabilidade

* **Logs JSON de uma linha**, com máscara obrigatória no formatador **e** no filtro: valores reais dos segredos da
  instalação, pares `senha=`/`token:`, `Bearer`, URLs com senha, chaves privadas, **CPF e e-mail**. A máscara é a última
  etapa, então nenhuma chamada de log precisa lembrar dela. Limite: é heurística (regex); um segredo sem formato
  reconhecível e que não seja valor da instalação passaria — por isso o código não deve registrar credenciais em primeiro lugar.
  O log de acesso do Gunicorn não leva a query string (filtros podem carregar CPF).
* **`GET /api/saude/`** (público): `banco`, `redis`, `worker`, `agendador`, `backup`, cada um em uma palavra. 503 só quando
  banco ou Redis caem; worker, agendador ou backup com problema só *degradam* (200). Não expõe versão nem endereço nem erro.
* **Agendador (beat):** uma tarefa a cada minuto grava um batimento no Redis; a sonda `verificar_batimento` serve de
  `healthcheck` do contêiner (pendência da issue #10). O batimento prova a cadeia beat → fila → worker; se o worker cai, o
  beat também aparece como não saudável — é uma sonda da cadeia, não só do beat.
* **Alertas por e-mail:** por empresa, pelo e-mail configurado dela (Fase 4) — nota sem resposta da Sefin há mais de 2 h
  (texto manda **não** emitir de novo) e resumo diário de falhas permanentes de e-mail/Drive, sem dado do tomador, uma vez
  por problema; certificado a vencer e agendamento com erro já existiam (Fases 2 e 5). Da **plataforma** (backup que falhou
  ou atrasou): como não pertence a nenhuma empresa, sai por um SMTP do sistema (`ALERTAS_SMTP_*`) para
  `ALERTAS_EMAIL_PARA` ou os Master; sem SMTP, log CRITICAL e `backup` em `/api/saude/`. Se o e-mail da empresa é justamente o
  que está falhando, o resumo de falhas não chega — o problema fica no log e na tela de envios.

## Decisão 4 — Views para BI

* Schema `bi` com `empresas`, `notas`, `servicos`, `retencoes` e `eventos`, consolidando as empresas (`UNION ALL`) com
  `empresa_id`/`empresa_cnpj`; grão e chaves em [`docs/bi.md`](../bi.md). Sem XML, hash, credenciais nem texto livre.
* Usuário de banco **somente leitura** (`default_transaction_read_only`, `NOINHERIT`, sem criação, `statement_timeout`), que só
  enxerga `bi`; senha como verificador SCRAM. As views só existem se alguém as criou (`criar_usuario_bi`/`atualizar_views_bi`)
  e se atualizam quando nasce uma empresa e a cada subida. Os *schemas* das empresas nunca são apagados
  (`auto_drop_schema = False`), então as views não quebram por remoção.
* **Minimização:** CPF de pessoa física sai mascarado e sem nome; pessoa jurídica sai completa. **Decisão em aberto** para o
  usuário (ampliar a exposição é trocar uma linha na view, mas é uma decisão de privacidade).
* As views leem as tabelas operacionais: para BI pesado, o caminho é materializar no Stage do DW ou usar réplica de leitura.

## Riscos

* `/api/saude/` é público por desenho (monitores externos); só devolve palavras de estado.
* O `healthcheck` do beat faz o `docker compose up --wait` esperar o primeiro batimento (até ~2 min depois de o worker subir).
* Ligar o instalador a um domínio errado faz o Let's Encrypt falhar; o instalador para com a causa e pode ser repetido.
