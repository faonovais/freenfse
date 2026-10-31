# Verificação da Fase 5 (modelos de NFS-e e agendamentos)

Os testes automatizados usam **relógio injetado** (nenhum depende do dia em que rodam) e a Sefin simulada da Fase 3: não há
rede. O dispatcher é exercitado com threads e conexões de verdade (várias instâncias ao mesmo tempo). O que só o ambiente real
confirma — o beat no ar, o e-mail chegando, a emissão em produção restrita — está no roteiro manual abaixo.

> **Cuidado:** use **sempre a produção restrita** e dados fictícios. Nunca cole certificado, chave de acesso, XML ou e-mail
> reais em issues, PRs, mensagens ou logs.

## Roteiro manual (produção restrita)

### Antes de começar
1. Empresa pronta para emitir (roteiro da Fase 3: certificado, município, convênio) com um tomador e um serviço vigente.
2. O **worker e o beat** do Celery no ar (`docker compose ps`): o beat dispara o dispatcher a cada minuto.
3. Opcional, para ver os avisos: e-mail da empresa configurado (roteiro da Fase 4) e o seu e-mail no usuário responsável.

### 1. Modelo de NFS-e
1. **Agendamentos › Modelos de NFS-e › Novo modelo**: nome, tomador, serviço, valor e, em *Informações complementares*,
   `Serviços referentes a {competencia}`. Salve.
2. Reabra o modelo e use **Conferir como ficaria hoje**. Esperado: tomador, competência (mês atual), totais e o texto com a
   competência preenchida.
3. Em **Modelos**, **Gerar rascunho agora**. Esperado: vai para **Rascunhos** com origem "Modelo …"; nada é enviado à Sefin.
4. Mude o valor no modelo e gere outro rascunho. Esperado: o primeiro rascunho **não muda**; o segundo vem com o valor novo.

### 2. Datas do agendamento (a prévia)
1. **Agendamentos › Novo agendamento**: *Mensal*, dia **31**. Esperado, na prévia: 31/01, **28/02** (ou 29 em bissexto), 31/03,
   **30/04**…
2. *Anual*, 29 de fevereiro: esperado **28/02** nos anos comuns e **29/02** nos bissextos.
3. *Semanal* com seg e qui, **a cada 2 semanas**: esperado, semanas alternadas. Troque "Termina" por *Em uma data* e por
   *Após N execuções*: só uma das duas formas vale por vez.
4. Datas em feriado ou fim de semana aparecem normalmente (não há calendário de feriados).

### 3. O dispatcher gera o rascunho na hora
1. Crie um agendamento **mensal no dia de hoje**, com a hora **daqui a 3 minutos** (horário de Brasília), responsável você.
2. Esperado, até 1 minuto depois da hora: um rascunho em **Rascunhos** com origem "Agendamento …", competência = mês atual; em
   **Histórico de execuções**, "Rascunho gerado"; o agendamento mostra 1 execução e a próxima data no mês seguinte; e-mail
   "Rascunho de NFS-e para aprovar" (se o e-mail estiver configurado).
3. Espere mais 2 minutos. Esperado: **nenhum segundo rascunho** para a mesma data.
4. Edite a hora do agendamento para daqui a 2 minutos (ainda hoje). Esperado: continua **um** rascunho (a data de hoje já
   foi executada); o histórico não ganha linha nova.

### 4. Falha não conta como execução
1. Em **Cadastros › Serviços**, encerre a vigência do serviço do modelo no mês passado. Em **Modelos** aparece o aviso "não
   conseguiria gerar um rascunho hoje".
2. Crie um agendamento com **2 execuções** (*Após N execuções*) e a hora daqui a 3 minutos. Esperado: no histórico, "Falhou" com
   o motivo ("não tem versão vigente…"); o contador **não** aumenta; e-mail de falha para o responsável e os administradores;
   a próxima data continua prevista.
3. Corrija a vigência e confira que a data seguinte gera normalmente.

### 5. Responsável sem acesso suspende o agendamento
1. Em **Administração › Vínculos**, desative o vínculo do responsável (ou tire dele a permissão de emitir).
2. Na hora do agendamento: esperado, situação **Suspenso** com o motivo, linha "Não executada (suspenso)" no histórico e
   e-mail ao administrador.
3. **Reativar** sem resolver o acesso é recusado com o motivo. Troque o responsável e reative: a próxima execução é a primeira
   data **futura**; as que passaram durante a suspensão **não** são geradas.

### 6. Aprovação em lote
1. Tenha 3 rascunhos (dois do modelo e um criado à mão, este com o tomador inativado de propósito para recusar).
2. **Rascunhos**: *Selecionar todos* › **Aprovar selecionados** › confirme. Esperado: resultado **por item** (enviado ou
   recusado, com o motivo); os enviados mudam para "Autorizada" com o número, sem a tela travar; uma recusa não impede os outros.
3. Confira na Sefin (ou no emissor oficial, em produção restrita) que cada nota foi emitida **uma única vez**.
4. Entre como perfil **Consulta**: vê os rascunhos, mas não há seleção, aprovar, editar nem descartar.

### 7. Descartar
1. **Descartar** um rascunho sem motivo: recusado. Com motivo: some de **Rascunhos** e da lista **NFS-e emitidas**; filtrando
   a situação "Descartada" ele aparece, e o histórico da nota guarda o motivo.

### 8. Alerta diário e queda do sistema
1. O alerta sai às 08:20 (Brasília). Para ver na hora:
   `docker compose exec backend python manage.py shell -c "from agendamentos import tasks; print(tasks.alertar_rascunhos_pendentes())"`.
   Esperado: um e-mail por responsável com a contagem por agendamento; rodar de novo no mesmo dia **não** repete.
2. Queda: com `FREENFSE_AGENDAMENTO_TOLERANCIA_HORAS=0` no `.env`, reinicie o backend e o worker; crie um agendamento para daqui
   a 2 minutos, **pare o beat** por 3 minutos e religue. Esperado: "Não executada (atraso)" no histórico e **nenhum** rascunho
   para essa data. Volte a variável ao padrão (12).

### 9. Várias empresas
1. Troque a empresa ativa: modelos, agendamentos, histórico e rascunhos de uma empresa **não** aparecem na outra.

### 10. Pontos a confirmar (hipóteses do ADR 0006)
- Anote o tempo que um lote de rascunhos leva para ser autorizado na produção restrita (as emissões saem uma a uma).
- Confirme com o contador se "competência = mês da execução" ou "mês anterior" é o padrão certo para o seu cliente típico.

## Mutações

Cada mutação troca trechos do código por uma versão errada e roda os testes dos arquivos indicados: o teste precisa **falhar**
("detectada"). Depois os arquivos são restaurados.

Rodada de 2026-10-31: **26 mutações, todas detectadas** (24 da lista inicial + 2 análogas criadas ao fechar a lacuna abaixo).

**Obrigatórias do Supervisor:** sem a trava/`UNIQUE` do dispatcher → o teste de idempotência reprova (D1, D2 e D3); fuso em UTC → o teste da virada reprova (F1); sem o clamp do último dia → o teste reprova (F2).

| # | O que foi quebrado | Onde | Teste que falhou |
|---|---|---|---|
| D1 | dispatcher sem a trava de linha (SELECT FOR UPDATE SKIP LOCKED) | `services/agenda.py` | `test_varias_instancias_ao_mesmo_tempo_geram_um_unico_rascunho` |
| D2 | sem o UNIQUE (agendamento, data_execucao) no banco | `migrations/0001_fase_5.py` | `test_mudar_a_hora_depois_da_execucao_do_dia_nao_gera_um_segundo_rascunho` |
| D3 | sem a trava E sem o UNIQUE (idempotência removida por inteiro) | `migrations/0001_fase_5.py, services/agenda.py` | `test_mudar_a_hora_depois_da_execucao_do_dia_nao_gera_um_segundo_rascunho` |
| F1 | fuso UTC no lugar de America/Sao_Paulo | `recorrencia.py` | `test_gera_o_rascunho_na_data_e_hora_do_agendamento_e_nao_antes` |
| F2 | sem o clamp do último dia do mês (31 → 30/28/29, 29/02 → 28/02) | `recorrencia.py` | `test_dia_31_vira_o_ultimo_dia_do_mes_em_mes_curto` |
| R1 | data de fim e limite de execuções aceitos juntos | `recorrencia.py` | `test_agendamento_invalido_volta_400_apontando_o_campo[ajuste0-max_execucoes]` |
| R2 | "a cada N" semanas ignorado (toda semana) | `recorrencia.py` | **sobreviveu** na primeira rodada (ver abaixo) |
| R3 | feriado/fim de semana pulados (só dias úteis) | `recorrencia.py` | `test_gera_o_rascunho_na_data_e_hora_do_agendamento_e_nao_antes` |
| E1 | falha de geração conta como execução realizada | `services/agenda.py` | `test_falha_ao_gerar_registra_notifica_e_nao_conta_a_execucao` |
| E2 | responsável sem acesso não suspende o agendamento | `services/agenda.py` | `test_responsavel_sem_acesso_suspende_o_agendamento_e_avisa_o_administrador[_desativar_vinculo-n\xe3o tem mais v\xednculo ativo]` |
| E3 | suspensão sem avisar o administrador | `services/agenda.py` | `test_responsavel_sem_acesso_suspende_o_agendamento_e_avisa_o_administrador[_desativar_vinculo-n\xe3o tem mais v\xednculo ativo]` |
| E4 | falha de geração sem notificar | `services/agenda.py` | `test_falha_ao_gerar_registra_notifica_e_nao_conta_a_execucao` |
| E5 | tolerância de atraso ignorada (datas muito atrasadas geram rascunho) | `services/agenda.py` | `test_data_muito_atrasada_vira_aviso_e_so_a_mais_recente_gera` |
| E6 | reativar dispara retroativamente (primeira data depois de dez anos atrás) | `services/agenda.py` | `test_reativar_vale_so_a_proxima_data_futura_sem_disparo_retroativo` |
| E7 | responsável sem nfse.emitir aceito | `services/agenda.py` | `test_responsavel_sem_acesso_suspende_o_agendamento_e_avisa_o_administrador[_sem_permissao-n\xe3o tem mais permiss\xe3o para emitir notas]` |
| S1 | e-mail do modelo lido ao vivo (não é cópia): mudar o modelo muda a nota emitida | `services/modelos.py` | `test_alterar_o_modelo_depois_da_emissao_nao_muda_a_nota_emitida` |
| S2 | serviço do modelo usado sem buscar a versão vigente na competência | `services/modelos.py` | `test_usa_a_versao_do_servico_vigente_na_competencia` |
| S3 | competência do mês anterior ignorada | `services/modelos.py` | `test_competencia_do_mes_anterior` |
| L1 | lote para na primeira recusa | `services/rascunhos.py` | `test_o_lote_nao_para_numa_recusa_e_explica_cada_item` |
| L2 | aprovação em lote aceita nota que não é rascunho | `services/rascunhos.py` | `test_o_lote_nao_para_numa_recusa_e_explica_cada_item` |
| L3 | descarte sem exigir motivo | `services/rascunhos.py` | `test_descartar_exige_motivo_e_guarda_no_historico` |
| L4 | aprovar em lote exige só nfse.consultar | `api/views.py` | `test_cada_perfil_so_faz_o_que_pode` |
| L5 | rascunho descartado continua na lista padrão de notas | `fiscal/api/notas.py` | `test_descartar_com_motivo_tira_o_rascunho_da_lista_e_das_notas` |
| L6 | alerta diário repetido no mesmo dia (chave sem a data) | `services/avisos.py` | `test_alerta_diario_agrupa_por_responsavel_e_nao_repete_no_mesmo_dia` |
| R2 (reforçada) | alinhamento do "a cada N semanas" ignorado | `recorrencia.py` | `test_a_cada_n_semanas_continua_alinhado_ao_inicio_ao_retomar_no_meio_da_serie` |
| R2b | alinhamento do "a cada N meses" ignorado | `recorrencia.py` | `test_a_cada_n_meses_continua_alinhado_ao_inicio_ao_retomar_no_meio_da_serie` |
| R2c | alinhamento do "a cada N dias" ignorado | `recorrencia.py` | `test_o_gerador_so_devolve_datas_a_partir_do_pedido_e_alinhadas_ao_inicio` |

**Uma sobrevivente na primeira rodada (R2) e o que ela mostrou.** Ignorar o alinhamento do "a cada N semanas" passou em todos os testes: eles sempre calculavam a série **a partir do início**, onde o alinhamento é trivial. O defeito só aparece quando o cálculo **retoma no meio da série** (depois de uma execução, ou ao reativar). Foram acrescentados testes que retomam no meio para semanas e meses, e um teste de contrato do gerador (`datas_da_serie` só devolve datas a partir do pedido e alinhadas ao início, também para dias e anos). As duas mutações análogas (R2b, R2c) nasceram desse achado.

**Duas camadas, dois testes.** A trava e o `UNIQUE` do dispatcher são independentes (defesa em profundidade), então cada uma tem o seu teste: sem a trava, a segunda instância fica **esperando** a primeira (D1, threads reais com a geração pausada no meio); sem o `UNIQUE`, mudar a hora depois da execução do dia gera um segundo rascunho na mesma data (D2); sem as duas, várias instâncias geram vários (D3).

Cada mutação troca trechos do código, roda os testes dos arquivos indicados e restaura os arquivos. O script e a lista não são versionados.

