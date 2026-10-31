# ADR 0005 — Documentos: download em lote, e-mail e Google Drive (Fase 4)

- **Status:** aceita
- **Data:** 2026-10-31
- **Decisões relacionadas:** D14 (Google Drive), D21 (e-mail), D4 (multiempresa isolado), D22 (permissões), `docs/analise-requisitos.md` §3.8, §4.1 e §4.3, [ADR 0002](0002-acesso-e-seguranca.md), [ADR 0004](0004-nucleo-fiscal.md)

## Contexto

Depois de autorizada, a nota precisa **chegar** às pessoas certas: o tomador (e-mail), a contabilidade (Drive) e quem faz a conferência do mês (lote). Os critérios de projeto desta fase foram três:

1. **Nada que sai do sistema pode atrapalhar a emissão.** Rede de terceiros (SMTP, Google, Microsoft) falha, demora e muda; a nota fiscal não pode depender disso.
2. **Credenciais de terceiros são o dado mais perigoso do banco.** Elas entram, ficam cifradas e **nunca voltam** (resposta, log, auditoria).
3. **O Google Drive aceita vários itens com o mesmo nome** e a listagem dele atrasa. Quem garante "uma pasta por caminho" e "um arquivo por nota" é o sistema, não o Drive.

## Decisões

### 1. Fronteira com a emissão: sinais que só enfileiram

`fiscal/signals.py` define `nfse_autorizada` e `nfse_evento_confirmado`, enviados com `send_robust` **depois** de a transição de situação ter sido gravada (a emissão nunca roda dentro de uma transação aberta: a trava de emissão recusa, ADR 0004). Os receptores (`documentos/receptores.py`) **só gravam o pedido e enfileiram uma tarefa Celery**; nenhuma chamada de rede acontece na hora da emissão. Uma exceção em qualquer receptor é registrada e **nunca** muda o resultado fiscal (`fiscal/tests/test_sinais.py`). O sinal `certificado_a_vencer` da Fase 2 ganhou um receptor que vira e-mail de alerta.

As retentativas ficam **gravadas nos próprios registros** (`proxima_tentativa`), e uma rotina a cada minuto (`despachar_pendentes`) retoma o que venceu, inclusive depois de uma queda do worker. Não há "tarefa agendada em memória" que se perde.

### 2. Download em lote (`documentos/services/exportacao.py`)

- **Pedido → tarefa → arquivo.** `POST /exportacoes/` valida filtros (período de emissão, competência, situação, tomador) e limites, grava `Exportacao` e responde 202. A tarefa monta o ZIP (`xml/`, `pdf/`, `resumo.csv`), atualiza `processadas` a cada nota (a tela mostra o progresso) e grava tamanho, nome e validade.
- **Limites** configuráveis por variável: 500 notas, 200 MB e 24 h de retenção por padrão. Estourar o limite de notas **recusa o pedido** com a explicação; estourar o de tamanho **interrompe** o lote com o motivo.
- **Onde fica o arquivo.** Em disco (`FREENFSE_EXPORTACOES_DIR/<schema>`, modo 0700), não no banco: ZIP de 200 MB no PostgreSQL pesa no backup e na replicação. Custo: backend (que entrega) e worker (que gera) precisam **enxergar a mesma pasta**. O Compose monta o volume `exportacoes` nos dois, e a imagem já traz a pasta com o dono certo. Numa implantação em mais de um servidor é preciso um volume compartilhado (ou trocar o armazenamento por objeto): **fica como item aberto**.
- **Acesso.** Só quem pediu baixa, **mesmo o Administrador e o Master não baixam o lote de outra pessoa**: o arquivo pode conter notas que a pessoa tinha direito de ver naquele momento. O download confere também que o vínculo com a empresa continua valendo e que o pedido não expirou. Cada baixa é auditada.
- **Nomes seguros.** O nome dentro do ZIP nunca vem cru do cadastro: `nome_seguro` remove barras, `..`, caracteres de controle e símbolos; colisões ganham sufixo. O CSV neutraliza fórmulas (`=`, `+`, `-`, `@`) com apóstrofo (injeção de planilha) e usa `;` e UTF-8 com BOM para abrir direto no Excel em português.
- **Expurgo.** Rotina a cada hora apaga o que passou da retenção e os arquivos sem registro.
- **PDF de nota cancelada/substituída.** O DANFSe vem da freedfe com os eventos conhecidos; se não puder ser gerado, o lote **não aborta**: o XML entra, o PDF fica de fora e a linha do CSV e o aviso do pedido dizem por quê.

### 3. E-mail (`documentos/services/email/`)

- **Interface comum** `ProvedorEmail.enviar(MensagemEmail)` com três adaptadores: **SMTP** (`smtplib`, STARTTLS/SSL/sem criptografia), **Gmail API** (`users.messages.send`, conta de serviço com delegação em todo o domínio, `subject` = remetente) e **Microsoft Graph** (`/users/{remetente}/sendMail`, credencial de aplicativo). Cada adaptador traduz os erros do provedor para `ErroDeEnvio(mensagem, temporario)`: o **corpo da resposta do provedor nunca vai para a mensagem** (pode conter token).
- **Configuração por empresa** (`ConfiguracaoEmail`, uma linha por schema): provedor, remetente, SMTP, Graph, `envio_automatico`, `avisar_cancelamento`, anexos, cópias fixas, e-mails de alerta, assunto e corpo.
- **Credenciais** (`smtp_senha`, `graph_client_secret`, `gmail_conta_servico`) em `CampoTextoCriptografado`. A API só informa **se existem** (`credenciais_configuradas`). Salvar com a credencial ausente ou vazia **mantém** a atual; `null` a apaga. A auditoria registra só os **nomes** dos campos alterados.
- **Modelos de mensagem.** Variáveis `{numero_nfse}`, `{nome_tomador}`, `{valor}`, `{competencia}`, `{chave}` e as demais do registro `_VARIAVEIS` (extensível num ponto só). Variável desconhecida e chave sem fechar são **recusadas ao salvar**, com a lista completa dos problemas. No HTML, **todo** o texto é escapado, inclusive o do modelo: um nome de tomador com `<script>` não vira marcação. O assunto passa por `_linha_unica` (sem quebra de linha: evita injeção de cabeçalho).
- **Quando enviar.** Manual (padrão), automático ao autorizar e aviso de cancelamento, cada um ligável. O envio automático usa **chave de idempotência** (`auto:<nota>:autorizacao`): autorizar duas vezes (reentrega do sinal) não manda dois e-mails.
- **Destinatários.** E-mails de envio do tomador (cópia gravada na nota, snapshot da Fase 3) + cópias fixas; no envio manual dá para informar outros.
- **Anexos.** PDF e XML ligáveis. `configuracao_efetiva(configuracao, nfse)` aplica as sobreposições registradas por `registrar_sobreposicao`: é o **ponto de extensão do modelo de NFS-e**; a Fase 5 registra a sua função sem tocar neste módulo. Hoje nenhuma está registrada.
- **Fila e retentativa.** `EnvioEmail` por tentativa de envio. Falha **temporária** (rede, 429, 5xx) reagenda em 1 min, 5 min, 30 min, 2 h e 6 h (até 5 tentativas) e depois vira `falhou`; falha **permanente** (senha recusada, destinatário inválido, anexo grande demais) encerra na hora, com a explicação em linguagem simples. O reenvio manual cria um **novo** `EnvioEmail` (o histórico não é reescrito).
- **Semântica de entrega: pelo menos uma vez.** A tentativa é "reservada" por um `UPDATE` condicional antes de chamar o provedor (vale 10 min), então dois workers não enviam o mesmo registro ao mesmo tempo. Se o worker cair **depois** de o provedor aceitar e **antes** de gravar `enviado`, o registro volta a ser tentado e o tomador pode receber a mesma nota duas vezes. Preferi isso a perder um envio; o histórico mostra as duas tentativas.
- **E-mail de teste** e **alerta de certificado a vencer** (faixas da Fase 2; um e-mail por faixa e certificado, controlado por chave de idempotência).
- **Limite do Graph:** anexos até 3 MB pelo `sendMail` simples (acima disso a API exige sessão de upload). Está documentado na tela e o adaptador recusa com mensagem clara.

### 4. Google Drive (`documentos/services/drive/`)

- **Conta de serviço por empresa**, JSON cifrado (`ConfiguracaoDrive.conta_servico`); a API devolve só o `client_email`. Ao salvar, o sistema **valida o ID da pasta raiz**: é pasta, a conta de serviço tem permissão de escrita, e o nome da pasta é gravado e exibido.
- **Modelos de caminho** (`caminhos.py`): `modelo_subpastas` (níveis separados por `/`) e `modelo_arquivo`, com `{ano} {mes} {dia} {numero_nfse} {nome_emitente} {cnpj_emitente} {chave}`. Cada valor é **normalizado** (sem `/` nem `\`, sem caracteres de controle, espaços repetidos colapsados, máximo de 100 caracteres). `validar` devolve **todos** os erros de uma vez: variável desconhecida, chave sem fechar, nível vazio, barra no nome do arquivo e **unicidade**.
- **Regra de unicidade:** o caminho completo precisa conter `{chave}` **ou** `{numero_nfse}` junto com `{cnpj_emitente}`. Sem isso duas notas diferentes cairiam no mesmo nome e uma sobrescreveria a outra. Subpastas vazias gravam na raiz; nome de arquivo vazio usa `{chave}`.
- **Data de referência = data de emissão** (não a competência): é a data que o contador enxerga na nota, e não muda se a competência for corrigida.
- **Pré-visualização** com uma nota real da empresa (a mais recente ou a escolhida), mostrando pasta, XML, PDF e o XML de um evento.
- **Pastas sem duplicar (a decisão mais delicada).** A identidade de uma pasta é o **cache `PastaDrive(caminho → ID)` com `UNIQUE`**, não a listagem do Drive, que pode demorar a mostrar o que acabou de ser criado. A criação roda sob uma **trava por empresa** (`core/travas.TravaDeSessao`, advisory lock de sessão, a mesma peça da trava de emissão da Fase 3). Duas cópias simultâneas ao mesmo caminho novo: a primeira cria e grava no cache; a segunda espera a trava e lê o cache. Se a pasta do cache sumiu do Drive (404), o cache do caminho e do que está abaixo é descartado e o passo é refeito uma vez. **Removendo a trava ou o cache o teste de concorrência (threads reais, Drive simulado com atraso de indexação) falha**: ver mutações M1 e M2.
- **Arquivos.** O sistema marca o que grava com `appProperties` (`freenfse_nota`, `freenfse_papel`) e guarda o `fileId` em `ArquivoDrive`. Reenviar **atualiza o mesmo `fileId`** (é assim que o PDF é trocado pelo da nota cancelada, com marca d'água). Se já existe, na pasta, um arquivo com o nome de **outra** nota, este recebe `" (2)"`, `" (3)"`… e a nota fica com um aviso visível na tela. O `ArquivoDrive` é salvo **ainda sob a trava**, para o próximo a entrar já enxergar o nome.
- **Gatilhos.** Autorização: XML e PDF. Evento confirmado: XML do evento (nome com sufixo do tipo) e **troca do PDF** pelo novo. "Reenviar ao Drive" por nota e por período (até o limite do lote, pela data de emissão).
- **Retentativa.** A mesma lógica do e-mail (temporário reagenda; permanente encerra com explicação). A notícia ao usuário é o aviso e a situação por arquivo na tela da nota.
- **Escopo `drive`** (e não `drive.file`): a pasta raiz é criada por uma pessoa, fora do aplicativo, e `drive.file` só enxerga o que o próprio aplicativo criou. O acesso fica limitado ao que for **compartilhado com a conta de serviço**, que é só a pasta raiz.

### 5. Permissões

Três permissões novas, registradas no catálogo central (`documentos/permissoes.py`):

| Permissão | Quem tem | O que permite |
|---|---|---|
| `documentos.consultar` | Emissor, Financeiro, Consulta (e Administrador) | ver o histórico de envios da nota |
| `documentos.exportar` | Emissor, Financeiro (e Administrador) | pedir e baixar lotes |
| `documentos.enviar` | Emissor, Financeiro (e Administrador) | enviar/reenviar por e-mail e ao Drive |

A **configuração** (e-mail, Drive, e-mail de teste) reaproveita `config.consultar` (ler e pré-visualizar) e `config.editar` (alterar, testar): credenciais não são decisão do Emissor. Consequência já conhecida (issue #14): o Emissor não tem `config.consultar`, então não vê as telas de configuração. Todas as rotas usam `PermissaoPorOperacao` (falha fechada) e o isolamento é o do schema.

### 6. Dependências novas

`google-api-python-client` e `google-auth` (Apache-2.0) para Drive e Gmail; `requests` (Apache-2.0) para o Graph. Escolhi as bibliotecas oficiais do Google em vez de HTTP manual porque cuidam de renovação de token, paginação e retentativa de transporte, e o Graph por `requests` porque são só duas chamadas (token e `sendMail`): `msal` traria mais dependências do que o necessário. Todas fixadas em `requirements.txt` com os pacotes transitivos. Os testes não usam rede: o Google é exercitado com `HttpMockSequence` (confere URL, `supportsAllDrives`, corpo e propriedades) e o Graph e o SMTP com dublês.

## Consequências e riscos

- **Credenciais de terceiros no banco**, cifradas com a mesma chave da aplicação. Vazar a chave expõe SMTP, Graph e as contas de serviço; a rotação é a do ADR 0002. Nenhuma credencial aparece em resposta, log ou auditoria (testes, incluindo leitura da coluna crua).
- **Gmail exige delegação em todo o domínio** (Google Workspace); contas Gmail pessoais não servem. SMTP com senha de aplicativo é a alternativa e está disponível.
- **Entrega "pelo menos uma vez"** do e-mail (§3): duplicidade rara em queda do worker no instante da confirmação.
- **Uma trava por empresa para o Drive** serializa a criação de pastas/nomes de uma empresa. O envio do conteúdo do arquivo também ocorre sob a trava (para o nome ficar visível ao próximo): uma empresa com muitos arquivos grandes copia um por vez. Para o volume típico (algumas notas por dia, XML e PDF pequenos) é aceitável; o custo está medido nos testes de concorrência, não em produção.
- **Lote em disco local** (§2): exige volume compartilhado entre backend e worker.
- **Avisos na tela só dentro da página do lote.** A notificação "pronto para baixar" aparece enquanto a pessoa está na tela de download em lote (ela acompanha sozinha); não há central de notificações global.
- **Cópia ao Drive não é backup.** Quem apagar o arquivo no Drive não aciona nada; o sistema só reenvia quando solicitado.

## Itens abertos e decisões que não são desta fase

1. **Armazenamento compartilhado dos lotes** para implantações com mais de um servidor.
2. **Sobreposição de envio por modelo de NFS-e**: o ponto de extensão existe (`registrar_sobreposicao`); a Fase 5 registra a função.
3. **Anexo de boleto no e-mail** (§4.3 do plano) e **notas recebidas** (issues #1 e #2): fora do escopo; o desenho já aceita outro tipo de anexo.
4. **Central de notificações** (aviso global "seu lote ficou pronto").
5. **Retenção dos registros de envio** (`EnvioEmail`, `ArquivoDrive`): pertence à fase de conformidade.
6. **Verificação com contas reais** (Google, Microsoft, SMTP): só no roteiro manual de `docs/verificacao-fase-4.md`.
