# Chaves, backup e restauração

> **Em uma frase:** guarde **duas chaves fora do servidor** — a `FREENFSE_CHAVES` e a chave **privada** do backup — e
> teste uma restauração antes de emitir a primeira nota de verdade. Perder o servidor sem elas significa perder
> certificados, credenciais e XMLs, e não conseguir abrir nenhum backup.

## As duas chaves

| Chave | Para que serve | Onde está | O que acontece se perder |
|---|---|---|---|
| **`FREENFSE_CHAVES`** | Cifra no banco: certificados A1, senhas de e-mail/Drive e os **XMLs** das notas | no `.env` do servidor (`FREENFSE_CHAVES=1:…`) | o banco restaurado **não abre** certificados, credenciais nem XMLs. Os certificados precisam ser reenviados e as credenciais recadastradas; as NFS-e autorizadas podem ser reobtidas da Sefin pela chave de acesso, as DPS não |
| **Chave privada do backup** (age) | Abre os arquivos `.dump.age` | **só com você** (cofre/computador). O servidor guarda apenas a chave **pública** | **nenhum backup pode ser restaurado** |

São chaves **independentes de propósito**: quem invade o servidor lê o `.env` (e a `FREENFSE_CHAVES`), mas **não** consegue
abrir os backups antigos, porque a chave privada nunca esteve lá. E o contrário também vale.

**Restaurar exige as duas**: a privada para abrir o arquivo e a `FREENFSE_CHAVES` para o sistema ler os dados já cifrados
dentro dele.

## Como guardar (fora do servidor)

1. **Gerenciador de senhas** da empresa (cofre com acesso por pessoa), em dois itens separados: "freenfse — FREENFSE_CHAVES"
   e "freenfse — chave privada do backup". Cole o conteúdo inteiro do `.env` só se o cofre for confiável.
2. **Uma cópia impressa** de cada chave, em envelope lacrado, num cofre físico (a chave privada `age` e a `FREENFSE_CHAVES`
   são texto curto, cabem em uma folha).
3. **Duas pessoas** de confiança devem saber onde estão. Anote a data e a versão (`v1`, `v2`…).
4. **Nunca** em e-mail, chat, issue, repositório ou no próprio servidor (a privada do backup, em especial).

Marque no calendário: **a cada 6 meses, faça um teste de restauração** (abaixo) com as chaves tiradas do cofre, para
confirmar que as cópias estão boas.

## Backup

* **Quando:** todo dia às 02:30 (Brasília), pelo worker, mais o que você disparar à mão.
* **O que contém:** o banco inteiro (todos os *schemas*: o público e um por empresa), tirado num instantâneo consistente.
* **Cifra:** `age`, para a chave pública em `FREENFSE_BACKUP_DESTINATARIO`. O dump em claro **nunca** vai para o disco.
* **Onde fica:** `<dados>/backups/freenfse-AAAAMMDDTHHMMSSZ.dump.age` e, ao lado, `….json` (manifesto: momento, versões,
  SHA-256 e contagem de linhas por tabela — sem segredo nem dado pessoal).
* **Retenção:** `FREENFSE_BACKUP_RETENCAO_DIAS` (padrão 14). A limpeza só roda **depois** de um backup bem-sucedido e
  **nunca** apaga o mais recente.
* **Falhou?** Log crítico, e-mail de alerta (se o SMTP do sistema estiver configurado) e `backup: atrasado` em `/api/saude/`.

> **Um backup que fica só no servidor não protege de perder o servidor.** Copie `<dados>/backups` para fora, todo dia:
> outro disco, outro provedor, ou um bucket (`rclone`, `rsync`, `restic`…). Os arquivos já estão cifrados, então o destino
> não precisa ser confiável.

## Restaurar (sempre num banco NOVO, com conferência)

A restauração **nunca sobrescreve** o banco em uso: ela cria um banco novo, restaura nele e **confere**. Só depois você troca.

1. Traga o arquivo `.dump.age` **e o `.json`** (juntos) e a chave privada. No servidor, o `.env` precisa ter a
   `FREENFSE_CHAVES` do servidor de origem.
2. Rode (Compose; a chave privada precisa ser legível pelo UID 10001 só durante este comando):

   ```bash
   docker compose run --rm -e EXECUTAR_MIGRACOES=0 \
     -v /caminho/seguro/freenfse-backup.key:/run/identidade.key:ro \
     backend python manage.py restaurar_backup \
       /var/lib/freenfse/backups/freenfse-AAAAMMDDTHHMMSSZ.dump.age \
       --identidade /run/identidade.key --destino freenfse_restaurado
   ```

   Nativo: `freenfse-manage restaurar_backup ARQUIVO --identidade CHAVE --destino freenfse_restaurado`.
3. O comando só termina com sucesso se **tudo conferir**:
   * o SHA-256 do arquivo bate com o do manifesto (nada corrompido nem alterado);
   * a **contagem de linhas de cada tabela** bate com a do momento do backup;
   * uma amostra dos campos cifrados **abre** com a `FREENFSE_CHAVES` em uso.

   Se algo falhar, ele diz o quê, e o banco restaurado fica marcado como **NÃO VERIFICADO**
   (`\l+` mostra o comentário). Não use esse banco.
4. Para **colocar no ar** o banco restaurado (depois de verificado), pare o sistema e troque os nomes:

   ```bash
   docker compose stop nginx backend worker beat
   docker compose exec postgres psql -U freenfse -d postgres \
     -c 'ALTER DATABASE freenfse RENAME TO freenfse_antigo;' \
     -c 'ALTER DATABASE freenfse_restaurado RENAME TO freenfse;'
   docker compose up -d
   ```

   Guarde o `freenfse_antigo` até ter certeza; depois `DROP DATABASE freenfse_antigo;`.
5. Confira: `curl …/api/saude/` e `manage.py verificar_cifragem`.

## Rotação das chaves

* **`FREENFSE_CHAVES`:** `manage.py gerar_chave` gera a nova; coloque-a **na frente** (`2:<nova>,1:<antiga>`), reinicie,
  rode `manage.py recriptografar` (recifra certificados, credenciais **e XMLs**) e só então remova a antiga do `.env`.
  Guarde a nova no cofre **antes** de remover a antiga. Backups feitos com a chave antiga continuam precisando dela.
* **Chave do backup:** gere um par novo, troque `FREENFSE_BACKUP_DESTINATARIO` e reinicie. **Os backups antigos continuam
  exigindo a chave privada antiga**: não a descarte enquanto houver backup que dependa dela.
* **Se desconfiar que o servidor foi comprometido:** troque tudo (senha do banco, `SECRET_KEY`, `FREENFSE_CHAVES`, a
  senha do certificado A1 junto à autoridade certificadora e os acessos de e-mail/Drive) e gere um novo par de backup.

## Criptografia de disco (camada adicional)

A cifragem acima é **na aplicação** e vale em qualquer infraestrutura. Em produção, recomenda-se **também** cifrar o disco
ou o volume do servidor (LUKS, volume cifrado do provedor): ela cobre o que a aplicação não cobre — os ZIPs temporários do
download em lote, os cadastros em claro e os logs — contra o roubo do disco.
