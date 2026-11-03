# Checklist de entrada em produção

Marque cada item **antes** de emitir a primeira nota com valor fiscal. Os itens bloqueantes (🔴) não devem ser pulados.

## 1. Servidor e segredos

- [ ] 🔴 Instalado pelo instalador (`docs/instalacao.md`) e `/api/saude/` responde `ok` (ou `degradado` só por motivo
      conhecido).
- [ ] 🔴 HTTPS ligado (`--tls letsencrypt` ou `proprio`) e o acesso por HTTP redireciona para HTTPS.
- [ ] 🔴 **`FREENFSE_CHAVES` guardada fora do servidor** (cofre + cópia impressa) e **chave privada do backup guardada fora
      do servidor**, em locais diferentes (`docs/chaves-e-backup.md`). Duas pessoas sabem onde estão.
- [ ] 🔴 O arquivo da chave privada do backup **não está** no servidor (apague o que o instalador gerou, depois de guardá-lo).
- [ ] O `.env` tem permissão 600 e o Master trocou a senha inicial, ativou o 2FA e o arquivo `master.senha` foi apagado.
- [ ] Disco/volume do servidor cifrado (recomendado) e firewall liberando apenas 80/443 (e o SSH de quem administra).
- [ ] SMTP do sistema configurado (`ALERTAS_SMTP_*`) para receber o alerta de backup; e-mail das notas por **SMTP com
      senha de aplicativo numa caixa dedicada** (sem delegação em todo o domínio do Gmail).

## 2. Backup

- [ ] 🔴 Um backup foi feito (`manage.py fazer_backup`) e aparece em `<dados>/backups`; `/api/saude/` mostra `backup: ok`.
- [ ] 🔴 **Restauração testada**: o comando `restaurar_backup` terminou com "Restauração verificada" num banco novo
      (`docs/chaves-e-backup.md`), usando as chaves tiradas do cofre.
- [ ] A cópia diária de `<dados>/backups` **para fora do servidor** está agendada e funcionando.
- [ ] Lembrete semestral de teste de restauração criado.

## 3. Roteiros em produção restrita (todos aprovados)

- [ ] 🔴 Fase 2 — cadastros, certificado e convênio: [`verificacao-fase-2.md`](verificacao-fase-2.md).
- [ ] 🔴 Fase 3 — emissão, consulta, **resultado incerto**, cancelamento e substituição:
      [`verificacao-fase-3.md`](verificacao-fase-3.md). Anote o resultado das hipóteses de `pAliq` e `totTrib`.
- [ ] Fase 4 — e-mail, Google Drive e download em lote: [`verificacao-fase-4.md`](verificacao-fase-4.md).
- [ ] Fase 5 — modelos, agendamentos e rascunhos: [`verificacao-fase-5.md`](verificacao-fase-5.md).
- [ ] Ajustes da issue #20 (IBS/CBS, Emissor, troca para produção, municípios): [`verificacao-issue-20.md`](verificacao-issue-20.md).
      Anote se a Sefin aceitou o `cIndOp` informado.
- [ ] Fase 6 — instalação limpa e restauração numa VPS de teste: [`verificacao-fase-6.md`](verificacao-fase-6.md).

## 4. Dados e regras fiscais

- [ ] 🔴 **Municípios:** a tabela do IBGE está carregada (5.571) e o **município emissor** da empresa está correto.
- [ ] 🔴 **Convênio** do município com a NFS-e Nacional verificado **em produção** (o sistema exige na troca).
- [ ] 🔴 **Retenção de PIS/COFINS continua BLOQUEADA** no sistema até o teste em produção restrita com a regra validada pelo
      contador. Se a empresa precisar reter PIS/COFINS, **não emita pelo sistema** até isso ser liberado.
- [ ] O serviço tem NBS, CST e classificação do IBS/CBS preenchidos, se a empresa informa IBS/CBS; o contador confirmou o
      indicador da operação (`cIndOp`).
- [ ] Alíquotas de ISS e retenções (ISS, IRRF, CSLL, INSS) conferidas pelo contador para cada serviço.

## 5. Troca para produção

- [ ] 🔴 Certificado A1 **válido** e com o CNPJ da empresa (o sistema confere).
- [ ] 🔴 Em **Parâmetros fiscais**, troque o ambiente para *Produção*. O sistema lista o que faltar, consulta o convênio
      **em produção** e pede para digitar `PRODUÇÃO`.
- [ ] Emitir uma **primeira nota de baixo valor** com o contador acompanhando; conferir XML e DANFSe.
- [ ] O selo "Produção restrita" sumiu do topo (indica que o ambiente é o de produção).

## 6. Privacidade

- [ ] A política de privacidade da empresa usa [`privacidade.md`](privacidade.md) como base.
- [ ] Quem acessa o BI (`docs/bi.md`) foi definido; o usuário de leitura tem senha forte guardada no cofre.
- [ ] Decisão registrada sobre CPF/nome de pessoa física no BI (padrão: mascarado/sem nome).
