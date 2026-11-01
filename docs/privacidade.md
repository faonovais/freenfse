# Privacidade e proteção de dados (LGPD)

Este documento diz **quais dados pessoais** o freenfse guarda, **para quê**, **por quanto tempo** e **como são
protegidos**. Ele é a base para a política de privacidade da empresa que usa o sistema.

## Quem é quem

* **Controlador:** a **empresa emissora** — é ela quem decide emitir a nota e quem responde perante o tomador e a lei.
* **Operador:** quem opera o freenfse para a empresa (a consultoria que instala e mantém o sistema).
* **Titulares:** os **tomadores** dos serviços (clientes) e as **pessoas que usam o sistema** (usuários).

## Base legal

* **Cumprimento de obrigação legal ou regulatória** (LGPD, art. 7º, II): emitir e guardar a NFS-e e seus XMLs.
* **Execução de contrato** (art. 7º, V): enviar a nota ao cliente por e-mail; manter o cadastro de clientes e serviços.
* **Legítimo interesse** (art. 7º, IX): registros de segurança, auditoria e alertas operacionais.

## Dados, finalidade e prazo

| Dado | Quem é o titular | Para quê | Prazo | Como sai do sistema |
|---|---|---|---|---|
| CPF/CNPJ, nome, endereço, e-mail e telefone do **tomador** (cadastro e cópia na nota) | tomador | emitir a NFS-e e relacionar-se com o cliente | enquanto o cadastro for útil; as **cópias nas notas** seguem a guarda fiscal | cadastro: pelo administrador; notas: não se apagam (obrigação legal) |
| **XML da DPS e da NFS-e**, eventos e evidências da Sefin | tomador e prestador | guarda fiscal | **mínimo de 5 anos**; **nenhum expurgo automático** | não há exclusão automática; só por decisão e procedimento do controlador após o prazo |
| **Registros de envio de e-mail** (destinatários, assunto, resultado) | tomador | provar e diagnosticar o envio | **5 anos**, depois **expurgo automático** diário | apagados pela rotina de retenção |
| **E-mail e nome dos usuários**, vínculo e perfil | usuário | acesso e controle de permissões | enquanto o vínculo existir | o usuário é **desativado**, não apagado (a trilha de auditoria depende dele) |
| **Trilha de auditoria** (quem, quando, o quê, IP) | usuário | segurança e prova | **5 anos**; sem expurgo automático (trilha imutável) | após o prazo, remoção manual documentada |
| **Logs técnicos** (saída padrão) | usuário | diagnóstico | rotação por tamanho (Compose: 5 × 10 MB por serviço) ou `journald` (14 dias) | rotação automática |
| **Backups cifrados** | todos os acima | recuperação de desastre | `FREENFSE_BACKUP_RETENCAO_DIAS` (padrão 14 dias) | apagados pela retenção |
| **ZIPs do download em lote** | tomador | entrega ao usuário que pediu | 24 horas | expurgo horário |
| **Cópias no Google Drive / anexos de e-mail** | tomador | entrega ao cliente e arquivo da empresa | sob controle da conta do Google / do destinatário | pela própria empresa |

O **certificado A1**, as senhas e os tokens **não são dados de titulares**, mas são segredos da empresa: ficam cifrados
no banco e nunca aparecem na API, nos logs nem nas views de BI.

## Como os dados são protegidos

* **Acesso por perfil** (Administrador, Emissor, Financeiro, Consulta) e **isolamento por empresa** (um *schema* do
  PostgreSQL para cada uma). Verificação em duas etapas obrigatória para o Master.
* **Criptografia em repouso** (AES-256-GCM, na aplicação) dos XMLs, das evidências e das credenciais; **backups cifrados**
  com chave separada ([`docs/chaves-e-backup.md`](chaves-e-backup.md)).
* **Dados em claro por necessidade:** nome e CPF/CNPJ do tomador e os cadastros ficam legíveis no banco porque o sistema
  precisa buscar, ordenar e exibir. A proteção deles é o controle de acesso, a cifragem dos backups e — recomendada — a
  criptografia de disco ([ADR 0008](adr/0008-criptografia-em-repouso-backup-e-retencao.md)).
* **Logs sem dado pessoal desnecessário:** CPF e e-mail são mascarados no log, e o log de acesso não registra a query
  string (onde filtros poderiam carregar um CPF).
* **BI com minimização:** as views não trazem XML nem credenciais; CPF de pessoa física sai mascarado e sem nome
  ([`docs/bi.md`](bi.md)).
* **Transporte:** HTTPS com cookies seguros e HSTS quando o instalador liga o TLS.

## Direitos do titular

O titular (tomador) pode pedir confirmação, acesso, correção e informações sobre o tratamento. Como a NFS-e é obrigação
legal, **dados que constam de nota emitida não podem ser eliminados** durante a guarda fiscal; o cadastro pode ser corrigido
ou desativado. As solicitações vão ao **controlador** (a empresa emissora); o operador apoia com o acesso e a correção.

## Incidentes

Em caso de suspeita de vazamento: isole o servidor, **troque todas as chaves e senhas** (veja a seção de rotação em
[`docs/chaves-e-backup.md`](chaves-e-backup.md)), preserve os logs e comunique o controlador, que avalia a comunicação à
ANPD e aos titulares (LGPD, art. 48).
