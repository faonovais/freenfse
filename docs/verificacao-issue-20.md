# Verificação da issue #20 (IBS/CBS por empresa, Emissor, produção e municípios)

Os testes automatizados usam a Sefin simulada e o transporte HTTP falso do convênio: **nada sai para a rede**. O que só o
ambiente real confirma (o convênio de verdade em produção, o `cIndOp` aceito pela Sefin, a tabela do IBGE baixada hoje) está
no roteiro manual abaixo.

> **Cuidado:** use **sempre a produção restrita** (exceto no passo de troca para produção, que deve ser feito numa empresa de
> teste) e dados fictícios. Nunca cole certificado, chave de acesso, XML ou e-mail reais em issues, PRs, mensagens ou logs.

> **As seções 1 e 1b (IBS/CBS por empresa e no modelo) foram substituídas pela issue #29** — veja [`verificacao-issue-29.md`](verificacao-issue-29.md). As demais (Emissor, troca para produção, municípios) seguem valendo.

## Roteiro manual

### 1. IBS/CBS por empresa
1. Com um **serviço com classificação** (NBS, CST e `cClassTrib` preenchidos, em *Cadastros › Serviços*) e outro **sem**.
2. *Configuração fiscal › Parâmetros fiscais*, seção **IBS e CBS**: tente marcar *Informar o IBS/CBS nas notas desta empresa* e
   salvar **sem** indicador. Esperado: recusa dizendo para informar o indicador da operação padrão (6 dígitos).
3. Informe um indicador (ex.: o fornecido pelo contador) e salve. Esperado: salvo; ao reabrir, a opção e o indicador aparecem.
4. Em *Parâmetros fiscais* informe também o **destinatário padrão** (0 = o próprio tomador, 1 = outro) e salve. Esperado: ao
   reabrir, o valor aparece; um valor fora de 0/1 é recusado.
5. *Notas › Nova nota* com o serviço **com** classificação: o campo *Indicador da operação (IBS/CBS)* mostra a dica
   "Em branco: vale o padrão da empresa (…)" e o destinatário mostra a opção "Herdar (da empresa: sim/não)". **Confira a nota**
   sem mexer: na conferência, a linha **IBS/CBS na DPS** mostra o indicador, o destinatário, NBS, CST e `cClassTrib`, cada um
   dos dois primeiros com a sua origem entre parênteses ("padrão da empresa").
6. Digite outro indicador só nessa nota e confira de novo. Esperado: "(ajuste desta nota)" no indicador e "(padrão da
   empresa)" no destinatário; a empresa continua com o padrão antigo.
7. Marque *Não informar o IBS/CBS nesta nota*. Esperado: os campos travam e a conferência diz "Não vai na nota. Você escolheu
   não informar…".
8. Com o serviço **sem** classificação e a opção da empresa ligada, confira a nota. Esperado: aviso "…o serviço não tem NBS, CST
   e classificação tributária: a nota sairá sem o grupo. Complete o cadastro do serviço."
9. Desligue a opção da empresa e confira a nota do serviço com classificação. Esperado: aviso de que a empresa não informa IBS/CBS.
10. **Emita** uma nota de teste com o grupo e abra o XML da DPS (*Baixar XML*/evidência): confira `IBSCBS/cIndOp`, `indDest`,
    `valores/trib/CST` e `cClassTrib` e `cNBS`. A Sefin deve autorizar. **Anote** se ela rejeitar o `cIndOp`: é a pendência de
    homologação do ADR 0007 (alerta sobre o `cIndOp` ser da operação).

### 1b. IBS/CBS no modelo de NFS-e (nota > modelo > empresa)
1. *Modelos de NFS-e › Novo modelo*, seção **IBS e CBS**. Esperado: os dois seletores abrem em "Herdar da empresa (hoje: …)" e o
   indicador mostra a dica "Vazio: herda o da empresa (…)". Em *Conferir como ficaria hoje*, a linha de IBS/CBS mostra
   "Indicador … (da empresa) · destinatário … (da empresa)".
2. Preencha só o **indicador** do modelo (outro de 6 dígitos) e salve. Esperado: a conferência mostra "Indicador … (do modelo)"
   e o destinatário continua "(da empresa)". Indicar o `cIndOp` sem mexer em *Informar* equivale a informar. Um indicador de
   5 dígitos é recusado com a mensagem no campo.
3. Mude o **padrão da empresa** (indicador e destinatário, em *Parâmetros fiscais*) e reabra o modelo. Esperado: o indicador do
   modelo **não muda**; o destinatário (herdado) mostra o novo valor da empresa **na hora** — nada foi copiado para o modelo.
4. Em *Agendamentos*, gere um rascunho desse modelo. Esperado: o rascunho leva o indicador do modelo e o resto da empresa **de
   quando foi gerado**. Mude de novo o padrão da empresa: o rascunho já criado **não** muda até ser salvo de novo; um rascunho
   gerado depois já usa o novo padrão.
5. Abra o rascunho (mesma tela da nota) e ajuste só o destinatário; confira. Esperado: o destinatário aparece "(ajuste desta
   nota)" e o indicador "(do modelo)". Volte o destinatário a "Herdar (…)" e confira: a origem do destinatário volta a ser a
   do modelo ou da empresa.
6. No modelo, clique em **Voltar a herdar tudo da empresa** e salve. Esperado: os três campos voltam a "Herdar da empresa" e a
   conferência mostra tudo "(da empresa)".
7. No modelo, escolha *Informar o IBS/CBS › Não informar* com a opção da empresa ligada e gere o rascunho. Esperado: o rascunho
   sai **sem** o grupo e a conferência diz "Não vai na nota…" com o motivo do modelo; na tela da nota, o indicador mostra "O
   modelo não informa IBS/CBS por padrão" e digitar um indicador de 6 dígitos volta a informar **só nessa nota**.

### 2. Perfil Emissor
1. Entre como **Emissor** (sem `config.editar`). Esperado: o menu mostra *Configuração fiscal*; *Parâmetros fiscais* e
   *Certificado A1* abrem **somente leitura** (campos travados, sem *Salvar*, sem *Verificar convênio*, sem envio de certificado).
2. O certificado mostra titular, CNPJ e validade; **nunca** o arquivo nem a senha.
3. As telas de e-mail e Drive abrem somente leitura, sem credenciais (só "configurada").

### 3. Troca para produção (numa empresa de teste)
1. Empresa **sem certificado**: em *Parâmetros fiscais*, escolha *Produção* e salve. Esperado: **sem pedir** para digitar
   `PRODUÇÃO`, a tela lista o que falta (certificado) com o link *Resolver*.
2. Envie o certificado, **sem município**. Esperado: lista só o município.
3. Informe o município e tente de novo. Esperado: agora pede a confirmação digitada; digite `PRODUÇÃO`.
4. Se o município **não** tiver convênio em produção: recusa com "NÃO tem convênio… no ambiente de produção" e o ambiente
   **continua** em produção restrita (e a emissão de teste continua liberada).
5. Com convênio: a troca é feita e o convênio mostrado é o de **produção**, já "atual" (a emissão não fica bloqueada).
6. Certificado vencido ou com CNPJ de outra empresa (simulados no banco de teste): a troca é recusada com a mensagem
   correspondente. **Voltar** para produção restrita não exige nada.

### 4. Municípios (IBGE)
1. Baixe a tabela oficial: `curl -fsSLO https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip`
   (ou a versão vigente) e confira o SHA-256 contra o `core/dados/LEIAME.md`.
2. `python manage.py comparar_municipios_ibge DTB_2025.zip`. Esperado: "O arquivo versionado confere com a tabela oficial".
3. Se o IBGE publicar uma nova data-base, o comando lista iguais/diferentes/faltantes; `--gravar` corrige o CSV (revise o diff).

## O que os testes automatizados cobrem

| Item | Arquivos de teste | O que prova |
|---|---|---|
| A. IBS/CBS por empresa e no modelo | `fiscal/tests/test_ibs_cbs.py`, `test_migracao_ibs_cbs.py`, `agendamentos/tests/test_ibs_cbs_no_modelo.py`, `test_modelos.py`, `test_api.py`, `frontend/.../notas.test.jsx`, `fiscal.test.jsx`, `agendamentos.test.jsx` | prioridade nota > modelo > empresa campo a campo; vazio herda (a empresa de agora, nada copiado); "não informar" em cada nível; validações; rascunho guarda o padrão de quando nasceu; ajuste do rascunho; XML assinado da DPS; prévia com a origem de cada campo; prontidão; opções; migração sem perda (dois bancos); telas |
| B. Emissor | `core/tests/test_permissoes.py`, `fiscal/tests/test_parametros.py`, `test_certificado.py`, `documentos/tests/test_api_documentos.py`, `fiscal.test.jsx` | lê e não edita (parâmetros, certificado, e-mail, Drive, convênio, ambiente); nenhuma resposta traz segredo |
| C. Produção | `fiscal/tests/test_producao.py`, `test_parametros.py`, `test_convenio.py`, `fiscal.test.jsx` | uma prova por condição (certificado ausente/vencido/futuro/CNPJ/raiz, município, convênio não aderente/indefinido/futuro/ilegível/sem rede); ordem; nada gravado na recusa; sem rede antes da confirmação |
| D. Municípios | `core/tests/test_municipios_oficiais.py`, `test_municipios.py` | leitor da planilha, comparação, comando, XML sem entidades externas, grafias corrigidas |

As mutações estão na última seção deste arquivo.

## Mutações (alterar o código de propósito para o teste falhar)

Cada mutação troca um trecho de produção, roda os testes do item e restaura o arquivo; o resultado esperado é o teste **falhar**.
**73 mutações, 73 detectadas.** Duas (N9 e P2) **sobreviveram na primeira rodada**; acrescentei os testes que faltavam (`5cf70b3`) e as reexecutei: detectadas. Depois de cada lote conferiu-se que o `git status` voltou a ficar limpo.

### B. Perfil Emissor

| # | Mutação | Teste que a detectou |
|---|---|---|
| B1 | Emissor perde config.consultar | `test_emissor_le_os_parametros_mas_nao_altera` |
| B2 | Emissor ganha config.editar | `test_emissor_le_os_parametros_mas_nao_altera` |

### C. Troca para produção

| # | Mutação | Teste que a detectou |
|---|---|---|
| C1 | sem certificado libera | `test_sem_certificado_nao_troca_e_nao_consulta_a_rede` |
| C2 | certificado vencido libera | `test_certificado_invalido_nao_libera_a_troca[vencido]` |
| C3 | certificado ainda não vigente libera | `test_certificado_invalido_nao_libera_a_troca[ainda_nao_vale]` |
| C4 | CNPJ do certificado não conferido | `test_certificado_invalido_nao_libera_a_troca[cnpj_de_outra_empresa]` |
| C5 | mesma raiz sempre autorizada | `test_certificado_invalido_nao_libera_a_troca[mesma_raiz_nao_autorizada]` |
| C6 | sem município libera | `test_sem_municipio_emissor_nao_libera` |
| C7 | convênio não aderente libera | `test_convenio_sem_vigencia_em_producao_nao_libera[nao_aderente]` |
| C8 | convênio indefinido libera | `test_avaliar_convenio_em_producao[convenio7-convenio_indefinido]` |
| C9 | ativação futura libera | `test_convenio_sem_vigencia_em_producao_nao_libera[ativacao_futura]` |
| C10 | ativação hoje bloqueia | `test_convenio_com_ativacao_hoje_ja_e_vigente` |
| C11 | data ilegível libera | `test_avaliar_convenio_em_producao[convenio5-convenio_data_ilegivel]` |
| C12 | consulta na produção restrita | `test_troca_consulta_o_convenio_de_producao_e_ja_o_deixa_valido` |
| C13 | consulta que falha libera a troca | `test_convenio_sem_vigencia_em_producao_nao_libera[sem_rede]` |
| C14 | troca sem confirmação | `test_sem_confirmacao_nada_vai_para_a_rede` |
| C15 | rede antes da confirmação | `test_sem_confirmacao_nada_vai_para_a_rede` |
| C16 | convênio gravado como da restrita | `test_troca_consulta_o_convenio_de_producao_e_ja_o_deixa_valido` |
| C17 | confirmação antes das pendências locais | `test_pendencia_local_vem_antes_do_pedido_de_confirmacao` |
| C18 | verificar convênio grava a linha inteira | `test_verificar_o_convenio_nao_desfaz_uma_troca_feita_durante_a_consulta` |
| C19 | mensagem sem numeração | `test_tudo_o_que_falta_vem_junto_numerado_e_com_a_tela_para_resolver` |
| C20 | outra raiz aceita com autorização | `test_certificado_invalido_nao_libera_a_troca[cnpj_de_outra_empresa]` |
| C21 | CNPJ sensível a caixa | `test_divergencia_de_cnpj[ab12cd34000195-AB12CD34000195-False-True]` |
| C22 | salva só os campos tocados: perde campo | `test_recusa_nao_altera_o_que_estava_gravado` |

### A. IBS/CBS por empresa e no modelo

O primeiro lote desta seção (20 mutações) foi feito antes da herança em três níveis e mirava código que deixou de existir; ele
foi **descartado e refeito** sobre o código final. As três mutações dele que continuam válidas (validação e gravação dos
parâmetros da empresa) foram **reexecutadas** (S1–S3).

#### Resolução nota > modelo > empresa e DPS

| # | Mutação | Teste que a detectou |
|---|---|---|
| N1 | inverte a prioridade (empresa > modelo > nota) | `test_ajuste_pontual_vale_mais_que_o_padrao_da_empresa` |
| N2 | modelo vale mais que a nota | `test_a_nota_vale_mais_que_o_modelo_que_vale_mais_que_a_empresa` |
| N3 | o modelo é ignorado | `test_o_modelo_vale_mais_que_a_empresa_campo_a_campo` |
| N4 | a nota é ignorada | `test_ajuste_pontual_vale_mais_que_o_padrao_da_empresa` |
| N5 | opção da empresa sempre ligada | `test_empresa_sem_opcao_e_servico_sem_classificacao_segue_sem_grupo_e_sem_aviso` |
| N6 | indDest da empresa ignorado | `test_vazio_nao_define_nada_e_a_empresa_de_agora_e_que_vale` |
| N7 | cIndOp da empresa ignorado | `test_nota_herda_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| N8 | cIndOp não implica informar | `test_ajuste_pontual_vale_mais_que_o_padrao_da_empresa` |
| N9 | destinatário vazio vira valor (erro) | `test_destinatario_vazio_herda_da_empresa_em_vez_de_virar_erro[nota]` (**sobreviveu; teste criado**) |
| N10 | informar de tipo errado aceito | `test_valor_invalido_em_qualquer_nivel_e_recusado[nota0-verdadeiro ou falso]` |
| N11 | destinatário inválido no nível aceito | `test_indicador_do_destinatario_so_pode_ser_0_ou_1[x]` |
| N12 | 'não informar' ignorado | `test_empresa_sem_opcao_e_servico_sem_classificacao_segue_sem_grupo_e_sem_aviso` |
| N13 | indicador sem validar 6 dígitos | `test_indicador_da_nota_precisa_ter_6_digitos[12345]` |
| N14 | serviço sem classificação passa | `test_empresa_com_opcao_e_servico_sem_classificacao_avisa_para_completar_o_cadastro` |
| N15 | pedido do modelo/nota vira só aviso | `test_classificacao_sem_nbs_nao_conta_como_servico_classificado` |
| N16 | rascunho não guarda o que o modelo definia | `test_modelo_que_nao_informa_manda_o_rascunho_sem_o_grupo_e_diz_o_motivo` |
| N17 | rascunho não guarda o ajuste da nota | `test_rascunho_do_agendamento_pode_ser_ajustado_antes_da_aprovacao` |
| N18 | editar o rascunho esquece o modelo | `test_rascunho_do_agendamento_pode_ser_ajustado_antes_da_aprovacao` |
| N19 | preparar não repassa o modelo | `test_modelo_com_valor_proprio_vale_mais_que_a_empresa_so_nos_campos_dele` |
| N20 | ajuste da nota guarda campos vazios | `test_o_ajuste_da_nota_guardado_so_tem_o_que_a_nota_definiu` |
| N21 | DPS ignora o grupo da nota | `test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| N22 | DPS com indicador fixo | `test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| N23 | DPS com destinatário fixo | `test_dps_assinada_leva_o_ajuste_pontual_e_nao_o_padrao` |

#### API da nota, da empresa e do rascunho

| # | Mutação | Teste que a detectou |
|---|---|---|
| P1 | a prévia ignora o rascunho em edição | `test_previa_do_rascunho_mostra_cada_campo_com_a_origem` |
| P2 | a prontidão esconde o indDest da empresa | `test_prontidao_expoe_o_padrao_da_empresa_para_a_tela_preencher` (**sobreviveu; asserção criada**) |
| P3 | a prévia não mostra o que vai na DPS | `test_previa_mostra_o_que_vai_na_dps_com_a_origem` |
| P4 | modelo de dados aceita indDest inválido | `test_destinatario_padrao_da_empresa_so_aceita_0_ou_1` |
| P5 | parâmetros não gravam o indDest | `test_administrador_muda_o_destinatario_padrao_da_empresa` |
| S1 | padrão ligado sem indicador aceito | `test_ligar_a_opcao_sem_indicador_e_recusado_com_a_explicacao` |
| S2 | indicador padrão com 5 dígitos aceito | `test_indicador_padrao_da_empresa_tem_6_digitos[12345]` |
| S3 | parâmetros não gravam a opção de informar | `test_administrador_liga_a_opcao_com_o_indicador_e_a_mudanca_e_auditada` |

#### Modelo de NFS-e (herança)

| # | Mutação | Teste que a detectou |
|---|---|---|
| F1 | o modelo COPIA o valor da empresa em vez de herdar | `test_api_do_modelo_mostra_o_proprio_o_herdado_da_empresa_e_o_efetivo_com_a_origem` |
| F2 | o rascunho ignora o que o modelo define | `test_modelo_com_valor_proprio_vale_mais_que_a_empresa_so_nos_campos_dele` |
| F3 | a API do modelo não grava os campos de IBS/CBS | `test_api_sobrescrever_e_voltar_a_herdar_campo_a_campo` |
| F4 | cIndOp do modelo sem normalizar os dígitos | `test_api_sobrescrever_e_voltar_a_herdar_campo_a_campo` |
| F5 | modelo aceita cIndOp com tamanho errado | `test_api_recusa_indicador_e_destinatario_invalidos_no_modelo[ibs_cbs_indicador_operacao-12345-6 dígitos]` |
| F6 | o efetivo do modelo ignora o que o modelo define | `test_api_sobrescrever_e_voltar_a_herdar_campo_a_campo` |
| F7 | conferir o modelo não mostra o IBS/CBS | `test_api_conferir_o_modelo_mostra_o_ibs_cbs_com_a_origem_de_cada_campo` |
| F8 | as opções não trazem o padrão da empresa | `test_api_opcoes_traz_o_padrao_de_ibs_cbs_da_empresa_de_agora` |
| F9 | o valor herdado mostra outro indDest | `test_api_opcoes_traz_o_padrao_de_ibs_cbs_da_empresa_de_agora` |

### D. Municípios (IBGE)

| # | Mutação | Teste que a detectou |
|---|---|---|
| D1 | comparação ignora a UF | `test_comparar_conta_iguais_diferentes_faltantes_e_a_mais` |
| D2 | igual mesmo com nome diferente | `test_comparar_conta_iguais_diferentes_faltantes_e_a_mais` |
| D3 | faltante vira a mais | `test_comparar_conta_iguais_diferentes_faltantes_e_a_mais` |
| D4 | UF do código não conferida | `test_planilha_inconsistente_e_recusada_com_a_linha[linhas1-não bate]` |
| D5 | repetido aceito | `test_planilha_inconsistente_e_recusada_com_a_linha[linhas2-repetido]` |
| D6 | código sem 7 dígitos aceito | `test_planilha_inconsistente_e_recusada_com_a_linha[linhas0-Curto]` |
| D7 | XML com entidades resolvidas | `test_entidade_externa_do_xml_nao_e_resolvida` |
| D8 | gravação sem ordenar | `test_gravar_csv_escreve_o_formato_do_arquivo_versionado` |
| D9 | sem data-base | `test_le_a_planilha_dentro_do_zip_com_data_base_e_hashes` |

Observações honestas:

- **C1** foi detectada por um erro 500 na primeira rodada (sem a pendência, o código seguia para o certificado inexistente e quebrava). A pedido do Supervisor, a consulta do convênio ganhou uma segunda trava (`_consultar_convenio` recusa quando não há certificado) com teste próprio (`test_sem_certificado_a_consulta_nao_sai_nem_se_a_conferencia_local_deixar_passar`); reexecutada, a C1 agora falha pela recusa explícita (400 `producao_nao_liberada` com `convenio_nao_verificado` no lugar de `sem_certificado`), não por exceção.
- Uma mutação do arquivo de testes da issue #24 (certificado de teste no relógio real) só é detectada quando o relógio do processo é avançado; ver o roteiro da #24 no PR #17.
- **Não foram feitas mutações nas telas desta issue** (Parâmetros e emissão guiada): elas têm testes de comportamento (Vitest), mas a sabotagem de propósito só foi aplicada ao backend. É uma lacuna conhecida.
- **N9 e P2 sobreviveram** ao primeiro lote: eram caminhos que a tela usa (`""` para "Herdar" e o indDest da prontidão) e que os testes não pisavam. Foram tratados como lacuna de teste, não de código, e só entraram na contagem depois de detectados.
- A tabela **S** reaproveita três mutações do lote antigo; a S3 teve o trecho reescrito porque a lista de campos editáveis ganhou o `indDest`.
