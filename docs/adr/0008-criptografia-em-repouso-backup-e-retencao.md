# ADR 0008 — Criptografia em repouso, backup e retenção (Fase 6, issue #9)

Status: aceito (implementado na Fase 6). Decisões do usuário que o motivam: issue #16 (XML com dados pessoais: criptografia em
repouso do banco e dos backups na Fase 6) e issue #18 (registros de envio de e-mail: 5 anos, com expurgo automático).

## Contexto

O freenfse guarda, por empresa (um schema PostgreSQL por empresa), os XMLs fiscais — DPS enviada, NFS-e autorizada, eventos e as
evidências brutas trocadas com a Sefin — e os cadastros de tomadores. Esses XMLs carregam CPF/CNPJ, nome, endereço, e-mail e
telefone do tomador. Até a Fase 5 só as **credenciais** eram cifradas (ADR 0002: AES-256-GCM, chaves versionadas em
`FREENFSE_CHAVES`, fora do banco). Um *dump* do banco, um backup copiado ou um disco devolvido expunham todos os XMLs.

## Inventário do que existe e como é tratado

| Classe | Onde | Tratamento |
|---|---|---|
| Credenciais | certificado A1, senhas e tokens de e-mail, conta de serviço do Drive | já cifradas (Fases 1, 2 e 4) |
| **Documentos fiscais completos** | `Nfse.xml_dps`, `Nfse.xml_nfse`, `EventoNfse.xml`, `EvidenciaFiscal.conteudo`, `DocumentoFiscal.xml`, `EventoFiscal.xml`, `XmlNaoReconhecido.xml` | **passam a ser cifradas (esta Fase)** |
| Dados operacionais e cadastrais | `Pessoa`, `Nfse.tomador_nome`/`tomador_documento`, os *snapshots* JSON (`tomador`, `servico`, `valores`…), `*.resumo`, `EnvioEmail.destinatarios` | **permanecem em claro** (ver "Limite aceito") |
| Arquivos temporários | ZIPs do download em lote (`exportacoes`) | em claro no volume, por no máximo 24 h; expurgo horário (Fase 4) |
| Cópias externas | Google Drive, anexos de e-mail | fora do controle do sistema; dependem da conta do cliente |

## Decisão 1 — Criptografia em repouso dos XMLs

**Recomendada e implementada: cifrar as colunas de XML na aplicação**, com os campos binários cifrados da Fase 1
(`CampoBinarioCriptografado`: AES-256-GCM, nonce aleatório por gravação, versão da chave no próprio valor).

Opções avaliadas:

| Opção | Vantagens | Riscos / por que não é a escolha |
|---|---|---|
| **A. Colunas cifradas na aplicação (escolhida)** | Portável (independe do disco, do provedor e da versão do PostgreSQL); protege *dump*, réplica, backup e acesso de DBA; reaproveita a chave, a rotação (`recriptografar`) e o código já testados; a chave nunca entra no banco nem em SQL | Não dá para filtrar por conteúdo do XML (ninguém filtra: chave, número, datas e valores têm colunas próprias em claro); custo de CPU na leitura/gravação (AES-GCM em hardware, desprezível para o volume); **perder a chave = perder os XMLs gravados** (mitigação: procedimento de guarda; a NFS-e autorizada pode ser reobtida da Sefin pela chave de acesso, a DPS não) |
| B. Criptografia de disco/volume (LUKS, volume cifrado do provedor) | Cobre tudo, inclusive os ZIPs temporários e os logs | Depende da infraestrutura de cada cliente (D15: servidor interno, VPS ou nuvem) — o instalador não consegue garantir; não protege *dump* lógico nem backup copiado; protege só contra o roubo do disco desligado. **Recomendada como camada adicional**, no checklist de produção |
| C. `pgcrypto` no banco | Nenhuma mudança de modelo | A chave passa em SQL e aparece em log do servidor/`pg_stat_statements`; fere o requisito de chave fora do banco. Descartada |
| D. TDE (forks do PostgreSQL) | Transparente | Não existe no PostgreSQL oficial; prende o cliente a um fork. Descartada |

**Integridade.** O hash SHA-256 (`hash_xml_nfse`, `EventoNfse.hash_xml`, `sha256` das evidências) continua calculado sobre o **XML
em claro** (é o hash que a Sefin e o contador conhecem) e fica em coluna própria. O GCM autentica o conteúdo cifrado: alteração do
valor gravado vira erro, nunca um XML errado em silêncio. O download do XML confere o hash ao ler. Limite conhecido: o GCM usado na
Fase 1 não amarra o texto cifrado à linha; quem tem escrita no banco poderia trocar o valor cifrado de uma linha pelo de outra. A
conferência do hash na leitura detecta a troca para a NFS-e e os eventos (e `EvidenciaFiscal.ler` já conferia o hash).

**Migração.** Uma migração de dados por *schema* de empresa cifra o que está em claro (idempotente: o que já começa com `v<n>:`
é ignorado; falha de forma explícita se `FREENFSE_CHAVES` não estiver configurada, em vez de deixar XML em claro). O comando
`verificar_cifragem` lê a coluna **bruta** e acusa qualquer XML ainda em claro; o instalador o executa na verificação final.
A rotação de chave (`recriptografar`) passa a cobrir também essas colunas.

**Impacto.** A leitura é transparente (o campo devolve o XML em claro): download do XML, DANFSe (a biblioteca lê pelo repositório),
download em lote, cópia ao Drive e anexo de e-mail seguem iguais e têm teste que parte da coluna cifrada. Filtros `isnull` seguem
permitidos; filtro por valor é recusado pelo próprio campo.

## Limite aceito (e como mitigar)

Os dados da classe "operacionais e cadastrais" ficam **em claro**: o sistema precisa filtrar, ordenar, impor unicidade e exibir
nome e documento do tomador; cifrá-los inutilizaria a busca (o alternativo, um índice cego por HMAC, não resolve ordenação nem
exibição). Mitigações: backups sempre cifrados (Decisão 2); criptografia de disco recomendada (opção B); acesso por perfil e
isolamento por *schema*; as *views* de BI não trazem XML nem credenciais e mascaram o CPF (ADR 0009); retenção definida abaixo.
**Decisão em aberto para o usuário:** se for preciso cifrar também esses campos, o custo é perder a busca por eles; cifrar só o
*snapshot* `Nfse.tomador` sem cifrar o cadastro `Pessoa` daria proteção parcial e falsa sensação de segurança, por isso não foi feito.

## Decisão 2 — Backup cifrado com chave separada

- `pg_dump -Fc` do banco inteiro (todos os *schemas*: público + uma por empresa) sob um **instantâneo consistente**
  (`pg_export_snapshot` em transação `REPEATABLE READ`), de modo que as contagens do manifesto e o *dump* descrevem o mesmo momento.
- Cifra com **`age`** (ferramenta livre, um binário, formato auditado) para um **destinatário (chave pública X25519)**. O servidor
  guarda **só a chave pública**: quem invade o servidor lê o banco, mas **não** os backups antigos. A chave privada (identidade)
  fica **fora do servidor** e só é usada para restaurar. É uma chave **diferente e independente** de `FREENFSE_CHAVES`.
- Alternativas: `gpg` (keyring, agente e *trust model* trazem mais pontos de falha em automação); `age` com senha (a senha teria de
  ficar no servidor, equivalendo a guardar a chave junto do dado); cifrar com `FREENFSE_CHAVES` (proibido: mesma chave do dado, e
  perdê-la perderia banco **e** backup).
- **O que a restauração exige:** (1) a identidade `age` para abrir o arquivo; (2) a `FREENFSE_CHAVES` para a aplicação ler os XMLs
  e as credenciais restaurados — o *dump* guarda esses campos já cifrados. **Sem a segunda, o banco volta mas XMLs e certificados
  não abrem.** Por isso o procedimento manda guardar as duas fora do servidor, em locais diferentes, e a restauração confere que a
  `FREENFSE_CHAVES` informada abre uma amostra dos campos cifrados.
- Manifesto (`.json` ao lado do arquivo, sem segredo nem dado pessoal): momento, versão do app, versões do `pg_dump`, destinatário,
  SHA-256 do arquivo cifrado e contagem de linhas por tabela.
- **Restauração com conferência obrigatória:** decifra, restaura num banco **novo** (recusa banco existente e não vazio), compara a
  contagem de linhas de cada tabela com o manifesto e decifra uma amostra dos campos cifrados. Qualquer divergência termina com
  erro e o banco restaurado é sinalizado como não verificado. Teste automatizado: backup → banco novo → dados conferidos.
- **Retenção configurável** (`FREENFSE_BACKUP_RETENCAO_DIAS`, padrão 14): a limpeza só roda **depois** de um backup bem-sucedido
  e nunca remove o mais recente.
- **Agendamento** pelo Celery beat (02:30, Brasília) com o mesmo código do comando `fazer_backup`. Falha de backup: log crítico,
  alerta por e-mail aos destinatários de plataforma e estado "degradado" no endpoint de saúde. Cópia para fora do servidor
  (outro disco, outro provedor) é responsabilidade do cliente e está no manual de instalação.
- Risco: o backup fica no mesmo servidor até ser copiado para fora; o manual trata como obrigatório para produção.

## Decisão 3 — Retenção e LGPD

| Dado | Prazo | Mecanismo |
|---|---|---|
| XML da DPS, da NFS-e, eventos e evidências | **≥ 5 anos (guarda fiscal)** | **nenhum expurgo automático**; teste com relógio avançado garante que o expurgo não toca documento fiscal |
| Registros de envio de e-mail (`EnvioEmail`) | **5 anos**, depois expurgo automático (decisão #18) | tarefa diária; só apaga registro de envio, nunca a nota |
| ZIPs do download em lote | 24 h | expurgo horário (Fase 4) |
| Trilha de auditoria (`LogAuditoria`) | 5 anos; sem expurgo automático nesta Fase | trilha imutável por desenho; remoção manual e documentada após o prazo |
| Logs da aplicação (saída padrão) | 14 dias de rotação | Compose: `json-file` com `max-size`/`max-file`; nativo: `journald` com `MaxRetentionSec` |
| Backups | `FREENFSE_BACKUP_RETENCAO_DIAS` (padrão 14) | limpeza após backup bem-sucedido |

Base legal: cumprimento de obrigação legal e regulatória pelo controlador (guarda de documento fiscal) e execução do serviço
contratado; os registros de e-mail e de auditoria têm finalidade de segurança e de prova. A página de privacidade
(`docs/privacidade.md`) lista os dados, a finalidade e o prazo, e diz como o titular pede informações (o controlador é a empresa
emissora; o freenfse é o operador).

## Consequências e riscos

- Um segredo a mais para guardar fora do servidor (a identidade do backup) e um deles (`FREENFSE_CHAVES`) passa a proteger também os
  XMLs — a perda é mais grave que antes. O manual de instalação e o checklist de produção tratam disso como item bloqueante.
- A migração roda em cada *schema*; em bases grandes pode levar minutos (cifra linha a linha em lotes).
- A chave de backup pública no servidor não protege contra um invasor que **troque** o destinatário para uma chave dele: o
  manifesto registra o destinatário usado e a verificação do instalador compara com o configurado.
- Tamanho: AES-GCM acrescenta 28 bytes por valor; irrelevante frente ao XML.
- Dados em claro (classe "operacionais") continuam expostos a quem lê o banco; mitigações acima e decisão em aberto.
