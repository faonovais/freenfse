# Verificação da Fase 6 (operação e entrega)

Os testes automatizados cobrem o código com as ferramentas de verdade (`pg_dump`, `pg_restore`, `age`, `nginx`) e um
PostgreSQL real, mas **não há como provar, em desenvolvimento, uma instalação numa VPS limpa nem o Docker/systemd reais**.
Esse é o **roteiro para o usuário** (parte 1 abaixo): instalação limpa numa VPS de teste e restauração de backup.

> **Cuidado:** use uma VPS **descartável**, a **produção restrita** e dados fictícios. Nunca cole `.env`, chaves, o `.pfx`,
> senhas ou XMLs reais em issues, PRs, mensagens ou logs. Destrua a VPS no fim.

## Parte 1 — Roteiro manual numa VPS de teste

### 0. Preparação
1. VPS Linux (Ubuntu 24.04, 2 vCPU, 4 GB) com um **domínio de teste** apontando para o IP dela. Portas 80 e 443 abertas.
2. Instale Docker e o plugin Compose ([docs.docker.com/engine/install](https://docs.docker.com/engine/install/)), `git` e `age`
   (`sudo apt install git age`), e baixe o repositório na branch da fase.
3. **No seu computador**, gere o par de chaves do backup: `age-keygen -o backup.key`. Guarde `backup.key` fora da VPS e anote
   a chave **pública** (a linha `Public key: age1…`).

### 1. Instalar (esperado: termina em "Pronto")
1. Veja o plano sem executar nada: `python3 instalador/instalar.py compose --dominio SEU.DOMINIO --tls letsencrypt --email VOCE@x.com --simular`.
2. Instale: `sudo python3 instalador/instalar.py compose --dominio SEU.DOMINIO --tls letsencrypt --email VOCE@x.com --chave-publica-backup age1… --email-master VOCE@x.com --usuario-bi`.
3. **Esperado:** nenhuma senha, chave ou segredo aparece na tela; o final mostra o endereço `https://SEU.DOMINIO`, o estado
   de saúde e os avisos (guardar `FREENFSE_CHAVES`, apagar `master.senha`).
4. `ls -l .env` → permissão `-rw-------`. `curl -s https://SEU.DOMINIO/api/saude/` → `status` `ok` ou `degradado`
   (`backup: sem_backup` até o primeiro backup é normal).
5. No navegador: cadeado válido, o `http://` redireciona para `https://`; nas ferramentas do navegador, os cookies de sessão
   estão marcados **Secure** e **HttpOnly**.

### 2. Rodar o instalador de novo (idempotência)
1. Antes: `grep '^SECRET_KEY=' .env | sha256sum` e o mesmo para `FREENFSE_CHAVES`. Rode o instalador outra vez (os mesmos
   parâmetros). **Esperado:** os dois hashes iguais, "Segredos já existentes mantidos", nenhum volume ou backup apagado, o sistema
   continua no ar.

### 3. Erros em linguagem simples
1. `docker compose stop backend`. Abra `https://SEU.DOMINIO/accounts/google/login/` → página "O sistema está indisponível…";
   `curl -s https://SEU.DOMINIO/api/versao/` → JSON `{"codigo":"indisponivel",…}` com HTTP 503. `docker compose start backend`.

### 4. Primeiro acesso
1. Entre como Master com a senha de `<dados>/master.senha`, configure o 2FA, troque a senha e **apague o arquivo**.

### 5. Dados cifrados em repouso
1. Faça o roteiro de emissão da Fase 3 (empresa de teste, certificado de teste, uma nota autorizada em produção restrita).
2. Leia a coluna **bruta**: `docker compose exec postgres psql -U freenfse -d freenfse -c "select left(encode(xml_nfse,'escape'),12) from empresa_<CNPJ>.fiscal_nfse where xml_nfse is not null limit 1"`
   → **começa com `v1:`** (nunca `<?xml`). `docker compose exec backend python manage.py verificar_cifragem` → "Todos os … valores
   conferidos estão cifrados."
3. Baixe o XML e o DANFSe pela tela: continuam abrindo normalmente.

### 6. Backup e restauração
1. `docker compose exec backend python manage.py fazer_backup` → "Backup feito". Em `<dados>/backups` há o `.dump.age` e o `.json`.
   `/api/saude/` passa a mostrar `backup: ok`.
2. **Copie** o `.dump.age` e o `.json` para fora da VPS (`scp`), como faria na rotina real.
3. Restaure num banco novo, com a chave privada (siga [`docs/chaves-e-backup.md`](chaves-e-backup.md), "Restaurar"):
   **Esperado:** "Restauração verificada no banco 'freenfse_restaurado'".
4. **Falhas esperadas** (cada uma deve recusar, com mensagem clara): (a) outra chave privada; (b) arquivo `.dump.age` alterado
   (um byte); (c) rodar com outra `FREENFSE_CHAVES` (`-e FREENFSE_CHAVES=1:<outra>`); (d) apagar o `.json`; (e) `--destino` de um
   banco que já existe.
5. (Opcional) Troque os nomes dos bancos como no manual, suba o sistema e confira que as notas continuam lá.

### 7. Alertas, BI e renovação
1. **Alertas:** configure `ALERTAS_SMTP_*` e `ALERTAS_EMAIL_PARA` no `.env` (caixa dedicada), `docker compose up -d`. Provoque a
   falha: troque `FREENFSE_BACKUP_DESTINATARIO` por um valor inválido e rode `fazer_backup` → o comando recusa e, pela tarefa
   agendada (`docker compose exec backend celery -A config call operacao.tasks.fazer_backup`), chega o e-mail "O backup do banco
   falhou". Restaure o valor certo.
2. **BI:** com a senha de `FREENFSE_BI_SENHA` (no `.env`), `psql -h 127.0.0.1 -U freenfse_bi -d freenfse -c 'select count(*) from bi.notas'`
   funciona; `select * from core_usuario` e `create table x(a int)` são **recusados**. Veja [`docs/bi.md`](bi.md).
3. **Renovação do certificado:** `docker run --rm -v <dados>/letsencrypt:/etc/letsencrypt -v <dados>/certbot-www:/var/www/certbot certbot/certbot renew --dry-run`
   → "Congratulations, all simulated renewals succeeded".
4. **Reinício:** `sudo reboot`. Em até 3 minutos `/api/saude/` volta a `ok` sem intervenção (`restart: unless-stopped`; o
   `agendador` pode levar ~2 minutos para voltar a `ok`).

### 8. Registre e destrua
Anote o que divergiu (mensagens, tempos, qualquer segredo que apareceu na tela — **isso seria um defeito grave**) e **destrua a VPS**.

## Parte 2 — Instalação nativa (opcional)

Mesma ideia, com `python3 instalador/instalar.py nativo …` numa VPS com Python 3.14, PostgreSQL 18, Redis, Nginx, git, age e
Node. Confira: `systemctl status freenfse-web freenfse-worker freenfse-beat`, `journalctl -u freenfse-web -n 20` (logs em JSON),
`freenfse-manage verificar_cifragem` e o mesmo roteiro das partes 1.4 a 1.7. **Este caminho tem menos cobertura automatizada**
(o instalador é testado com executor simulado e `nginx -t` real, mas systemd e PostgreSQL nativos só se provam aqui).
