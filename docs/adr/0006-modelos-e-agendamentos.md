# ADR 0006 — Modelos de NFS-e e agendamentos (Fase 5)

- **Status:** aceita
- **Data:** 2026-10-31
- **Decisões relacionadas:** D12 (agendamento gera rascunho), D13 (recorrência), D17 (feriado e fim de semana executam), D21 (e-mail por modelo), D10 (responsável e vínculo), D4 (multiempresa isolado), `docs/analise-requisitos.md` §3.1–§3.3, [ADR 0004](0004-nucleo-fiscal.md), [ADR 0005](0005-documentos.md)

## Contexto

Quem fatura todo mês o mesmo serviço ao mesmo cliente não quer redigitar a nota. Mas **emitir sozinho é perigoso**: uma nota autorizada só se desfaz por cancelamento, e um valor, um tomador ou uma competência desatualizados viram nota errada. Por isso o desenho (D12) é: o agendamento só **prepara rascunhos**; quem tem `nfse.emitir` confere e aprova. Os critérios de projeto foram:

1. **Uma data, no máximo um rascunho**, mesmo com duas instâncias do beat, tarefa reentregue ou alguém editando o agendamento no meio do dia.
2. **Nada retroativo em massa.** Reativar um agendamento, ou o sistema voltar de uma queda, nunca despeja meses de rascunhos.
3. **Falha é visível e não conta.** O que não foi gerado fica no histórico, com o motivo, e avisa quem pode resolver.
4. **A nota é cópia.** Mudar o modelo, o cadastro ou o e-mail depois nunca altera uma nota já criada.

## Decisões

### 1. Estrutura (app `agendamentos`, schema da empresa)

| Modelo | Papel |
|---|---|
| `ModeloNfse` | a nota de referência: tomador, serviço, valores, texto, competência padrão e sobreposição de e-mail |
| `Agendamento` | repete um modelo; guarda regra, responsável, contador de execuções e `proxima_execucao` |
| `ExecucaoAgendamento` | histórico, **uma linha por data** (`UNIQUE (agendamento, data_execucao)`) |
| `OrigemNfse` | de que modelo e execução veio uma nota, com a **cópia** da sobreposição de e-mail |

O usuário vive no schema público: o responsável é guardado por `responsavel_id` + `responsavel_email` (sem chave estrangeira entre schemas). A regra de recorrência é uma função **pura** (`recorrencia.py`, sem banco e sem relógio): todos os testes de data injetam o instante.

### 2. Modelo e cópia (snapshot)

- Gerar uma nota a partir do modelo (manual, "Gerar rascunho agora", ou pelo agendamento) passa por `fiscal.services.nfse.criar_rascunho`, o mesmo caminho do rascunho digitado: a nota recebe a **cópia** do tomador, do serviço e dos valores. Alterar o modelo muda **os próximos** rascunhos; um rascunho já criado e uma nota emitida não mudam (testes com a nota autorizada na Sefin simulada).
- **Serviço por vigência.** O modelo aponta para uma versão do serviço, mas o rascunho usa a versão **vigente na competência** com os mesmos códigos de tributação. A reforma tributária muda classificação por vigência (ADR 0003); assim o modelo não quebra na virada e, se não houver versão vigente, a falha explica "cadastre a vigência em Cadastros › Serviços".
- **Retenções vêm do serviço.** O modelo guarda os valores; ISS, IR, CSLL e INSS são calculados sobre a cópia do serviço, como em qualquer nota. Não há retenção "do modelo" separada (evita duas fontes para o mesmo número).
- **Texto com variáveis.** As informações complementares aceitam `{competencia}`, `{mes}`, `{ano}` e `{data_execucao}` (mesmo analisador do e-mail e do Drive: variável desconhecida e chave solta são recusadas ao salvar).
- **Competência padrão:** mês da execução (D12) ou mês anterior (serviço cobrado no mês seguinte). Editável no rascunho.
- **Modelo inativo pode ficar incompleto**; ativo precisa gerar um rascunho válido hoje. Alterar só o e-mail de um modelo com o serviço vencido não é bloqueado (a prova de geração só roda quando o campo alterado afeta a geração).
- **IBS/CBS não é do modelo.** A opção pelo IBS/CBS e o indicador da operação são **da empresa** (parâmetros fiscais; decisão do usuário nas issues #14, #16 e #18), não do serviço nem do modelo. Por isso o modelo **não tem** campo de IBS/CBS: o rascunho nasce com o padrão que a emissão já aplica, e a mudança para o nível da empresa é a tarefa da issue #20 (depois desta fase).

### 3. Sobreposição de e-mail por modelo (D21)

O modelo guarda, por campo, "igual à empresa" (nulo/vazio) ou um valor próprio: enviar automaticamente, avisar cancelamento, anexar PDF, anexar XML, assunto, texto e cópias fixas (lista vazia = sem cópias; nulo = herda). A função registrada em `envio_email.registrar_sobreposicao` (ponto de extensão da Fase 4) lê a **cópia gravada em `OrigemNfse.email` no nascimento do rascunho**, não o modelo: mudar o e-mail do modelo depois não muda o e-mail de uma nota existente (teste que compara a configuração efetiva antes e depois).

### 4. Recorrência (`recorrencia.py`)

- **Frequências:** única, diária, semanal (dias da semana), mensal (dia do mês) e anual (dia e mês), mais o "a cada N" dias, semanas ou meses (`intervalo`, de 1 a 365; única e anual têm intervalo fixo 1). O intervalo conta **a partir da data de início**: a semana (segunda a domingo) e o mês do início são a "rodada zero".
- **Dia 29/30/31 em mês curto** vale o último dia; **29/02 em ano comum** vale 28/02. É a mesma regra: o dia é limitado ao tamanho do mês (uma única função).
- **Feriado e fim de semana executam** (D17); não há calendário de feriados.
- **Fim da série:** data de fim (inclusive) **ou** número de execuções, nunca os dois (validado no código e por `CHECK` no banco). Execução única não tem fim.
- **Fuso:** a hora é a de `America/Sao_Paulo`; o instante é gravado em UTC. O **dia** da execução e a competência são os de Brasília: às 23:30 de 31/10 (02:30 UTC de 01/11) a competência é **outubro** (teste dedicado; trocar o fuso para UTC o reprova). O Brasil não tem horário de verão desde 2019; o módulo usa `zoneinfo` mesmo assim.
- **Próxima execução** é sempre a primeira ocorrência **estritamente depois** de um instante dado; se a hora de hoje já passou, é a de amanhã (mesmo com limite de 1 execução).

### 5. Dispatcher único e idempotência

Uma tarefa no beat (`despachar_agendamentos`, a cada minuto) varre todas as empresas ativas, cada uma no seu `schema_context`; a falha de uma empresa é registrada e **não para as outras**. Para cada agendamento vencido, `processar`:

1. abre uma transação e trava a linha do agendamento com `SELECT … FOR UPDATE SKIP LOCKED`: **quem chega em segundo pula em vez de esperar**;
2. insere `ExecucaoAgendamento (agendamento, data)`; o `UNIQUE` transforma a segunda inserção da mesma data em `IntegrityError`, tratado num ponto de salvamento como "data já executada" (só avança a próxima data);
3. gera o rascunho e a origem; atualiza o contador e a próxima data; tudo na mesma transação.

São **duas proteções independentes**, e há um teste que exige cada uma: sem a trava, a segunda instância fica **esperando** a primeira (teste com threads reais e a geração pausada no meio); sem o `UNIQUE`, editar a hora de um agendamento depois da execução do dia ("hoje às 10:00" voltaria a ser futuro) gera um segundo rascunho na mesma data; sem as duas, cinco instâncias simultâneas geram vários. Um erro inesperado na geração vira falha da data (log + aviso), nunca derruba o laço dos demais agendamentos.

### 6. Falha, suspensão e avisos

- **Falha ao gerar** (modelo inativo ou inválido, tomador inativo/removido, serviço sem vigência, erro inesperado): a data fica `falhou` com a explicação, **não conta como execução realizada**, e o agendamento tenta de novo na **próxima data da série** (não a cada minuto). Em execução única, o agendamento termina com o motivo. Notifica o responsável e os administradores.
- **Responsável sem acesso** (vínculo inativo, sem `nfse.emitir`, usuário desativado ou removido): o agendamento é **suspenso**, a data fica `suspensa` e os **administradores** são avisados. Master pode ser responsável (tem todas as permissões); perfis sem `nfse.emitir` são recusados ao salvar.
- **Avisos por e-mail** usam a Fase 4 (`EnvioEmail` sem nota, com chave de idempotência por agendamento e data): rascunho gerado, falha, suspensão, data perdida e o alerta diário. Se a empresa não configurou o e-mail, **nada some**: tudo continua no histórico e na lista de agendamentos (o e-mail é reforço).

### 7. Política de atraso e de reativação (nada retroativo)

- **Criar, editar a regra ou reativar** valem a partir de **agora**: a próxima data é a primeira **futura**. O que passou durante uma suspensão **não** é gerado depois. Renomear um agendamento não recalcula a data (uma data vencida e ainda não processada continua pendente).
- **Sistema fora do ar.** Uma data só é executada com até `FREENFSE_AGENDAMENTO_TOLERANCIA_HORAS` de atraso (padrão **12 h**, limitado a **23 h** no código para ser menor que o menor intervalo, 1 dia, e nunca gerar mais de uma data por passagem). Datas mais antigas viram **um único** registro `perdida` ("N data(s) puladas"), sem rascunho e sem contar como execução; a data mais recente dentro da tolerância ainda é executada na mesma passagem. O responsável é avisado e pode gerar à mão pelo modelo ("Gerar rascunho agora"). **Risco assumido:** uma queda de mais de 12 h sobre uma data mensal a perde; é a troca por nunca despejar rascunhos em massa.

### 8. Rascunhos: aprovar, descartar e alertar

- **Aprovação em lote** (`POST /rascunhos/aprovar/`, exige `nfse.emitir`, até 100 por vez): cada nota passa por `emissao.solicitar_emissao` — **o mesmo caminho da emissão manual** (prontidão da empresa, regra "nota substituta exige `nfse.substituir`", bloqueio de série com nota incerta) — e a emissão vai para a fila existente, uma por vez por empresa. Devolve **resultado por item**; uma recusa nunca para o lote. O resultado final (autorizada, rejeitada, incerta) vem da própria emissão; a tela acompanha pela situação das notas.
- **Descarte com motivo = nova situação final `descartada`** na máquina de estados da Fase 3 (só `rascunho → descartada`). Escolhi isso em vez de colunas novas porque o histórico de transições já guarda motivo, usuário e hora, e a matriz de transições inválidas ganha o caso de graça. Descartadas saem da lista padrão de notas e só aparecem ao filtrar por "descartada". É a **única mudança no núcleo fiscal** (junto de `preparar(hoje=)`, abaixo).
- **Rascunho nunca é emitido nem apagado sozinho** (teste: semanas de alertas sem ninguém aprovar não mudam nada).
- **Alerta diário** (08:20 de Brasília): um e-mail por responsável com a contagem por agendamento dos rascunhos **gerados por agendamento** ainda pendentes (rascunho criado à mão não entra: ninguém o "esperava"); chave de idempotência por responsável e dia.
- Qualquer pessoa com `nfse.emitir` pode aprovar, não só o responsável: o responsável é quem é avisado e quem precisa poder emitir.

### 9. Permissões e mudanças em fases anteriores

Novas: `agendamento.consultar` (Emissor, Financeiro, Consulta) e `agendamento.editar` (Emissor; Administrador tem todas). Aprovar, editar e descartar rascunhos usam `nfse.emitir`; listar usa `nfse.consultar`.

Mudanças fora do app novo, todas pequenas e cobertas por testes: `fiscal` ganha `Situacao.DESCARTADA` (+ migração) e `preparar(dados, hoje=)` (a competência é validada contra a **data da execução**, não contra o relógio do servidor, o que também torna os testes determinísticos); `documentos` ganha `registrar_aviso_avulso` e dois tipos de e-mail; `core` ganha ações de auditoria.

## Consequências e riscos

- **Execuções "perdidas"** por queda longa (§7), com aviso e a saída manual pelo modelo.
- **Uma instância do beat por padrão**: duas são seguras (idempotência), mas gastam consultas; o `SKIP LOCKED` faz a segunda pular sem esperar.
- **Aprovação em lote enfileira N emissões**, que a Sefin recebe uma por vez; um lote grande demora (a tela acompanha). Uma nota que ficar "incerta" **bloqueia a numeração da série** (regra da Fase 3, [ADR 0004](0004-nucleo-fiscal.md) §4): as seguintes não são numeradas por cima dela até a conferência com a Sefin resolver.
- **Valores não reajustam sozinhos** (decisão do requisito): quem aprova confere e corrige o valor no rascunho.
- **Mudar a regra recalcula a próxima data a partir de agora**: mudar a hora de hoje para uma hora futura "re-arma" o dia, mas o `UNIQUE` impede o segundo rascunho da mesma data.

## Itens abertos e decisões que não são desta fase

1. **IBS/CBS por empresa** (issue #20): o modelo herdará o padrão da empresa, sem campo próprio.
2. **Calendário de feriados** (D17 manda executar mesmo assim; um dia pode pedir "dia útil").
3. **Central de notificações** dentro do sistema (hoje: e-mail + histórico + avisos nas telas).
4. **Aprovação por dupla** (quem gerou não aprova): não pedido.
5. **Tolerância de atraso por agendamento** (hoje é uma só, por ambiente).
6. **Reajuste automático de valor** (índice): fora desta versão.
