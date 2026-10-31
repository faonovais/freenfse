# Verificação da issue #20 (IBS/CBS por empresa, Emissor, produção e municípios)

Os testes automatizados usam a Sefin simulada e o transporte HTTP falso do convênio: **nada sai para a rede**. O que só o
ambiente real confirma (o convênio de verdade em produção, o `cIndOp` aceito pela Sefin, a tabela do IBGE baixada hoje) está
no roteiro manual abaixo.

> **Cuidado:** use **sempre a produção restrita** (exceto no passo de troca para produção, que deve ser feito numa empresa de
> teste) e dados fictícios. Nunca cole certificado, chave de acesso, XML ou e-mail reais em issues, PRs, mensagens ou logs.

## Roteiro manual

### 1. IBS/CBS por empresa
1. Com um **serviço com classificação** (NBS, CST e `cClassTrib` preenchidos, em *Cadastros › Serviços*) e outro **sem**.
2. *Configuração fiscal › Parâmetros fiscais*, seção **IBS e CBS**: tente marcar *Informar o IBS/CBS nas notas desta empresa* e
   salvar **sem** indicador. Esperado: recusa dizendo para informar o indicador da operação padrão (6 dígitos).
3. Informe um indicador (ex.: o fornecido pelo contador) e salve. Esperado: salvo; ao reabrir, a opção e o indicador aparecem.
4. *Notas › Nova nota* com o serviço **com** classificação: o campo *Indicador da operação (IBS/CBS)* mostra a dica
   "Em branco: vale o padrão da empresa (…)". **Confira a nota** sem mexer: na conferência, a linha **IBS/CBS na DPS** mostra o
   indicador da empresa, o destinatário, NBS, CST e `cClassTrib`, com "(padrão da empresa)".
5. Digite outro indicador só nessa nota e confira de novo. Esperado: "(ajuste desta nota)" com o indicador digitado; a empresa
   continua com o padrão antigo.
6. Marque *Não informar o IBS/CBS nesta nota*. Esperado: os campos travam e a conferência diz "Não vai na nota. Você escolheu
   não informar…".
7. Com o serviço **sem** classificação e a opção da empresa ligada, confira a nota. Esperado: aviso "…o serviço não tem NBS, CST
   e classificação tributária: a nota sairá sem o grupo. Complete o cadastro do serviço."
8. Desligue a opção da empresa e confira a nota do serviço com classificação. Esperado: aviso de que a empresa não informa IBS/CBS.
9. **Emita** uma nota de teste com o grupo e abra o XML da DPS (*Baixar XML*/evidência): confira `IBSCBS/cIndOp`, `indDest`,
   `valores/trib/CST` e `cClassTrib` e `cNBS`. A Sefin deve autorizar. **Anote** se ela rejeitar o `cIndOp`: é a pendência de
   homologação do ADR 0007 (alerta sobre o `cIndOp` ser da operação).
10. *Agendamentos*: gere um rascunho de um modelo cujo serviço tem classificação. Esperado: o rascunho herda o padrão da empresa
    (conferir na tela do rascunho). Mude o padrão da empresa e confirme que o rascunho já criado **não** muda até ser salvo de novo.

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
| A. IBS/CBS por empresa | `fiscal/tests/test_ibs_cbs.py`, `test_migracao_ibs_cbs.py`, `agendamentos/tests/test_modelos.py`, `frontend/.../notas.test.jsx`, `fiscal.test.jsx` | padrão da empresa × ajuste pontual × "não informar"; validações; cópia (rascunho não muda com o padrão); XML assinado da DPS; prévia; prontidão; migração sem perda; herança pelo modelo; telas |
| B. Emissor | `core/tests/test_permissoes.py`, `fiscal/tests/test_parametros.py`, `test_certificado.py`, `documentos/tests/test_api_documentos.py`, `fiscal.test.jsx` | lê e não edita (parâmetros, certificado, e-mail, Drive, convênio, ambiente); nenhuma resposta traz segredo |
| C. Produção | `fiscal/tests/test_producao.py`, `test_parametros.py`, `test_convenio.py`, `fiscal.test.jsx` | uma prova por condição (certificado ausente/vencido/futuro/CNPJ/raiz, município, convênio não aderente/indefinido/futuro/ilegível/sem rede); ordem; nada gravado na recusa; sem rede antes da confirmação |
| D. Municípios | `core/tests/test_municipios_oficiais.py`, `test_municipios.py` | leitor da planilha, comparação, comando, XML sem entidades externas, grafias corrigidas |

As mutações estão na última seção deste arquivo.

## Mutações (alterar o código de propósito para o teste falhar)

Cada mutação troca um trecho de produção, roda os testes do item e restaura o arquivo; o resultado esperado é o teste **falhar**.
**53 mutações, 53 detectadas, nenhuma sobrevivente.** Depois de cada lote conferiu-se que o `git status` voltou a ficar limpo.

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

### A. IBS/CBS por empresa

| # | Mutação | Teste que a detectou |
|---|---|---|
| A1 | padrão da empresa vale mais que o ajuste da nota | `test_ajuste_pontual_vale_mais_que_o_padrao_da_empresa` |
| A2 | opção desligada é ignorada | `test_opcao_desligada_ignora_o_indicador_guardado` |
| A3 | 'não informar' é ignorado | `test_nao_informar_nesta_nota_tira_o_grupo_mesmo_com_o_padrao_ligado` |
| A4 | indicador sem validar 6 dígitos | `test_indicador_da_nota_precisa_ter_6_digitos[12345]` |
| A5 | destinatário sem validar | `test_indicador_do_destinatario_so_pode_ser_0_ou_1[2_0]` |
| A6 | destinatário ausente vira 1 | `test_nota_herda_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| A7 | ajuste sem classificação do serviço passa | `test_empresa_com_opcao_e_servico_sem_classificacao_avisa_para_completar_o_cadastro` |
| A8 | origem sempre 'nota' | `test_nota_herda_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| A9 | pedir informar sem indicador passa | `test_pedir_para_informar_sem_nenhum_indicador_e_erro_didatico` |
| A10 | classificação sem exigir NBS | `test_classificacao_sem_nbs_nao_conta_como_servico_classificado` |
| A11 | padrão ligado sem indicador aceito (modelo) | `test_ligar_a_opcao_sem_indicador_e_recusado_com_a_explicacao` |
| A12 | indicador padrão com 5 dígitos aceito | `test_indicador_padrao_da_empresa_tem_6_digitos[12345]` |
| A13 | prontidão não expõe o padrão | `test_prontidao_expoe_o_padrao_da_empresa_para_a_tela_preencher` |
| A14 | prévia não mostra o que vai na DPS | `test_previa_mostra_o_que_vai_na_dps_com_a_origem` |
| A15 | DPS ignora o grupo da nota | `test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| A16 | DPS com indicador fixo | `test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| A17 | DPS com CST fixo | `test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| A18 | DPS com cClassTrib fixo | `test_dps_assinada_leva_o_grupo_com_o_padrao_da_empresa_e_a_classificacao_do_servico` |
| A19 | DPS com destinatário fixo | `test_dps_assinada_leva_o_ajuste_pontual_e_nao_o_padrao` |
| A20 | parâmetros não gravam a opção | `test_administrador_liga_a_opcao_com_o_indicador_e_a_mudanca_e_auditada` |

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

- **C1** foi detectada por um erro 500, não por uma recusa: sem a pendência, o código seguiria para o certificado inexistente e quebraria. O teste falha do mesmo jeito, mas o sintoma é uma exceção.
- Uma mutação do arquivo de testes da issue #24 (certificado de teste no relógio real) só é detectada quando o relógio do processo é avançado; ver o roteiro da #24 no PR #17.
- **Não foram feitas mutações nas telas desta issue** (Parâmetros e emissão guiada): elas têm testes de comportamento (Vitest), mas a sabotagem de propósito só foi aplicada ao backend. É uma lacuna conhecida.
