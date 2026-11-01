# Manual de instalação

Este manual instala o freenfse em um servidor interno, uma VPS ou uma máquina na nuvem — o sistema não depende de
nenhum serviço específico de nuvem. Há dois caminhos, ambos pelo mesmo instalador:

| Caminho | Quando usar | O que precisa no servidor |
|---|---|---|
| **Docker Compose** (recomendado) | Quase sempre: menos peças para cuidar, atualização simples | Linux com Docker e o plugin Compose |
| **Nativo** (systemd + Nginx + Gunicorn) | Servidor onde não se pode usar Docker | Python 3.14, PostgreSQL 18, Redis, Nginx, git, age, Node 22 |

> **Antes de começar, leia [`docs/chaves-e-backup.md`](chaves-e-backup.md).** Duas chaves precisam ficar **fora do
> servidor**; sem elas, perder o servidor significa perder certificados, credenciais, XMLs e a possibilidade de
> restaurar backups.

## 1. O que você precisa ter

* Um servidor Linux (2 vCPU e 4 GB de RAM atendem a operação de uma empresa pequena; os tetos de memória do Compose
  são ajustáveis no `.env`).
* **Saída HTTPS** para a Sefin/ADN e para os serviços de Google (Drive/Gmail), se usados. A entrada pública (porta 80/443)
  só é necessária se o sistema for acessado pela internet.
* Um **domínio** apontando para o servidor (para o certificado Let's Encrypt) ou o certificado da sua própria autoridade.
* Para o backup: uma **chave pública `age`** (veja o item 4) e um lugar **fora do servidor** para copiar os backups.
* Para os alertas: uma caixa de e-mail dedicada (veja o item 6).

## 2. Instalar por Docker Compose

```bash
git clone https://github.com/faonovais/freenfse.git
cd freenfse
```

Instalação **com HTTPS pelo Let's Encrypt**, chave de backup gerada, primeiro Master e usuário de BI:

```bash
sudo python3 instalador/instalar.py compose \
  --dominio nfse.suaempresa.com.br \
  --tls letsencrypt --email ti@suaempresa.com.br \
  --dados /var/lib/freenfse \
  --gerar-chave-backup /root/freenfse-backup.key \
  --email-master voce@suaempresa.com.br \
  --usuario-bi
```

Sem os parâmetros, o instalador **pergunta** domínio, tipo de HTTPS, e-mail do certificado e pasta de dados. Veja
`python3 instalador/instalar.py --help`. Para **só ver o plano, sem executar nada**, acrescente `--simular`.

O que ele faz, em ordem: confere Docker e Compose; cria as pastas de dados; gera o `.env` (permissão 600) com
`SECRET_KEY`, `FREENFSE_CHAVES`, senha do banco e senha do BI **aleatórias**; sobe a pilha; obtém o certificado e liga o
HTTPS (com `COOKIES_SEGUROS` e `PROXY_TLS`); cria o Master e o usuário de BI; espera `/api/saude/` responder; confere que
nenhum dado sensível ficou em claro (`verificar_cifragem`). **Nenhum segredo é impresso** nem passado na linha de
comando.

Opções de HTTPS:

* `--tls nenhum` — só HTTP (rede interna, ou atrás de um balanceador que já faz HTTPS).
* `--tls letsencrypt` — exige domínio **público** e a porta 80 livre; renova sozinho (script em
  `<dados>/renovar-certificado.sh`, agendado em `/etc/cron.d` quando se roda como root).
* `--tls proprio --certificado cert.pem --chave-privada chave.pem` — para servidor interno com a sua autoridade.

### O que fica onde

| Item | Local |
|---|---|
| Configuração e segredos | `freenfse/.env` (permissão 600, **fora do Git**) |
| Banco, Redis, ZIPs temporários | volumes do Docker (`freenfse_postgres_data`, …) |
| **Backups cifrados** | `<dados>/backups` (bind no host; copie para fora do servidor) |
| Certificados Let's Encrypt | `<dados>/letsencrypt` |
| Senha inicial do Master | `<dados>/master.senha` (permissão 600): troque a senha, ative o 2FA e **apague o arquivo** |

### Rodar de novo (atualizar)

O instalador é **idempotente**: pode ser executado quantas vezes quiser. Ele **nunca** troca um segredo que já existe,
nunca apaga volumes nem backups e reaproveita o certificado válido. Para atualizar o sistema:

```bash
git pull
sudo python3 instalador/instalar.py compose      # reaproveita domínio, dados e chaves do .env
```

## 3. Instalar de forma nativa

Pré-requisitos (Debian/Ubuntu; o instalador confere e lista o que faltar):

```bash
# PostgreSQL 18 e o cliente: repositório oficial PGDG (https://www.postgresql.org/download/linux/)
sudo apt install postgresql-18 postgresql-client-18 redis-server nginx git age certbot
# Python 3.14: ainda não vem nas distribuições; use uv (https://docs.astral.sh/uv/) ou pyenv
# Node 22 (https://nodejs.org) — ou compile o frontend em outro computador e use --frontend-pronto
```

```bash
sudo python3 instalador/instalar.py nativo --dominio nfse.suaempresa.com.br --tls letsencrypt \
  --email ti@suaempresa.com.br --python python3.14 --gerar-chave-backup /root/freenfse-backup.key
```

Cria o usuário de sistema `freenfse`, o ambiente virtual, o banco, as unidades `freenfse-web`, `freenfse-worker` e
`freenfse-beat` (com endurecimento do systemd: `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`…), o site do Nginx
e o atalho `freenfse-manage` para rodar comandos do `manage.py` no ambiente certo.

## 4. Backup e chaves (obrigatório para produção)

O backup é cifrado com `age` para uma **chave pública**. O servidor só guarda a pública; a **privada** (identidade) fica
com você. Duas formas:

1. **Recomendado:** gere o par no **seu computador** (`age-keygen -o backup.key`), guarde `backup.key` em um cofre e passe
   só a chave pública: `--chave-publica-backup age1…`.
2. `--gerar-chave-backup ARQUIVO`: o instalador gera o par no servidor e grava a **privada** em `ARQUIVO`. Você **deve**
   copiá-la para fora do servidor e apagá-la de lá.

Backup, retenção, restauração, rotação e guarda das chaves: **[`docs/chaves-e-backup.md`](chaves-e-backup.md)**.

## 5. Primeiro acesso

Abra o endereço mostrado no final da instalação, entre com o e-mail do Master e a senha de `<dados>/master.senha`, e
configure a verificação em duas etapas (obrigatória para o Master). O passo a passo para o usuário está em
[`docs/manual-do-usuario.md`](manual-do-usuario.md); a lista de conferência antes de emitir notas de verdade, em
[`docs/checklist-producao.md`](checklist-producao.md).

## 6. E-mail: use SMTP com senha de aplicativo numa caixa dedicada

Decisão do usuário (issue #18). Para enviar as notas por e-mail (e receber os alertas), configure o provedor
**SMTP** em *Envio de documentos › E-mail da empresa*, com uma **caixa dedicada** (ex.: `notas@suaempresa.com.br`) e uma
**senha de aplicativo** (Gmail: conta com verificação em duas etapas › Senhas de app).

> **Alerta sobre a delegação no Gmail.** A Gmail API com *delegação em todo o domínio* dá à conta de serviço permissão
> para agir como **qualquer usuário** do domínio. Se a chave dessa conta vazar, o estrago é de todo o domínio. A
> documentação recomenda **não** usar a delegação: prefira SMTP com senha de aplicativo numa caixa só para as notas. A
> Gmail API continua disponível na tela, mas por sua conta e risco.

Para os **alertas da plataforma** (backup que falhou ou atrasou) configure no `.env` o SMTP do sistema
(`ALERTAS_SMTP_*`, `ALERTAS_EMAIL_PARA`), idealmente a mesma caixa dedicada. Sem isso o alerta fica no log (CRITICAL) e em
`/api/saude/`.

## 7. Operação do dia a dia

| Quero… | Faça |
|---|---|
| Ver se está tudo bem | `curl https://seu.dominio/api/saude/` → `status: ok` (ou `degradado`, com o item que precisa de atenção) |
| Ver os logs | Compose: `docker compose logs -f backend worker beat` · Nativo: `journalctl -u freenfse-web -f` (logs em JSON, sem segredos) |
| Fazer um backup agora | Compose: `docker compose exec backend python manage.py fazer_backup` · Nativo: `freenfse-manage fazer_backup` |
| Conferir que nada está em claro | `… manage.py verificar_cifragem` |
| Girar a chave de criptografia | `… manage.py gerar_chave`, coloque a nova **na frente** de `FREENFSE_CHAVES`, reinicie, rode `… manage.py recriptografar` e só então remova a antiga |
| Dar acesso ao BI | `docs/bi.md` |
| Reiniciar | Compose: `docker compose restart` · Nativo: `systemctl restart freenfse-web freenfse-worker freenfse-beat` |

### Logs e retenção

Compose: 5 arquivos de 10 MB por serviço (rotação automática). Nativo: o `journald` — defina `MaxRetentionSec=14day` em
`/etc/systemd/journald.conf`. Os logs da aplicação **não contêm segredos, CPF nem e-mail**; o log de acesso do Gunicorn
**não registra a query string**. Veja a política completa em [`docs/privacidade.md`](privacidade.md).

## 8. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Página "O sistema está indisponível…" | backend reiniciando ou parado | aguarde 1 minuto; se persistir, veja os logs do `backend` |
| `/api/saude/` com `worker: falha` | worker parado ou Redis fora | `docker compose ps`; reinicie o `worker` |
| `agendador: atrasado` | `beat` parado (ou worker fora) | reinicie `beat`; veja `docker compose logs beat` |
| `backup: nao_configurado` | sem chave pública | informe `FREENFSE_BACKUP_DESTINATARIO` no `.env` e reinicie |
| `backup: atrasado` | último backup com mais de 30 h | veja `docker compose logs worker`; rode `fazer_backup` à mão |
| Let's Encrypt recusa o certificado | domínio não aponta para o servidor, ou porta 80 fechada | confira o DNS e o firewall; rode o instalador de novo |
| Login em loop depois de ligar o HTTPS | `COOKIES_SEGUROS`/`PROXY_TLS` desalinhados | o instalador ajusta os dois juntos; rode-o de novo |
