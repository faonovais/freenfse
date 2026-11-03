# Verificação da Fase 4 (documentos: lote, e-mail e Google Drive)

Os testes automatizados **não usam rede**: o Google (Drive e Gmail) é exercitado com respostas HTTP simuladas
(`HttpMockSequence`) e um Drive simulado em memória que atrasa a indexação como o real; o Microsoft Graph e o SMTP, com
dublês. O que só contas reais confirmam está no roteiro manual abaixo.

> **Cuidado:** nunca cole a chave JSON da conta de serviço, senhas, segredos de aplicativo, tokens nem notas reais em
> issues, PRs, mensagens ou logs. Use uma **pasta de teste** no Drive, uma **caixa de e-mail de teste** e a
> **produção restrita**.

## Roteiro manual

### Antes de começar
1. Tenha o ambiente do roteiro da Fase 3 funcionando (empresa pronta, certificado, convênio verificado) e **uma nota
   autorizada** na produção restrita. O worker **e o beat** do Celery precisam estar no ar (`docker compose ps`).
2. **Drive.** No Google Cloud: crie um projeto, ative a *Google Drive API*, crie uma **conta de serviço** e baixe a chave
   JSON. No Drive, crie a pasta `freenfse-teste`, **compartilhe-a com o e-mail da conta de serviço** como *Editor* e copie o
   ID (o trecho final de `drive.google.com/drive/folders/ESTE-TRECHO`).
3. **E-mail.** Uma caixa de teste e, conforme o provedor: SMTP com usuário e senha de aplicativo; **Gmail** exige Google
   Workspace com a *delegação em todo o domínio* da conta de serviço para o escopo `gmail.send`; **Microsoft 365** exige um
   aplicativo com a permissão `Mail.Send` (aplicativo) e consentimento do administrador.
4. Cadastre um tomador cujo e-mail seja o da caixa de teste, e outro com o nome `Teste <b>negrito</b> & Cia` (para conferir o
   escape).

### 1. E-mail da empresa
1. **Configuração fiscal › E-mail da empresa**. Escolha o provedor, informe remetente e credenciais, **Salvar configuração**.
2. Esperado: depois de salvar, o campo da senha volta **vazio**, com o texto "Configurada — deixe em branco para manter". A
   senha, o segredo e a chave **nunca** aparecem na tela nem na aba de rede do navegador.
3. **Enviar e-mail de teste** para a caixa de teste. Esperado: mensagem recebida; "E-mail de teste enviado para …".
4. Troque a senha por uma errada e repita o teste. Esperado: "O teste falhou" com a explicação em linguagem simples (sem
   o texto cru do provedor). Volte à senha certa.
5. Em **Assunto** digite `{xpto}` e salve. Esperado: recusa apontando a variável desconhecida. Corrija.

### 2. Envio manual
1. Abra a nota autorizada › **Envios da nota** › **Enviar por e-mail** (em branco: vai para os e-mails do tomador).
2. Esperado: a linha do histórico passa de "Na fila" para "Enviado"; a mensagem chega com o **XML e o PDF** anexos (confira
   também com um dos anexos desligado na configuração), o assunto e o corpo com as variáveis preenchidas e as **cópias fixas**.
3. Para o tomador `Teste <b>negrito</b> & Cia`: o nome aparece **literalmente**, sem negrito, no corpo em HTML.
4. **Reenviar** no histórico. Esperado: nova linha no histórico (a anterior continua).

### 3. Envio automático, falha e cancelamento
1. Ligue **Enviar automaticamente quando a nota for autorizada** e emita outra nota. Esperado: o e-mail sai sozinho e o
   histórico mostra "Ao autorizar". Emitir ou reenviar **não** deve gerar dois e-mails.
2. Desligue o acesso (senha errada) e emita uma nota. Esperado: o histórico mostra "Na fila" com "Tentativa 1 sem sucesso;
   nova tentativa em …" (1, 5, 30 min, 2 h, 6 h) e, depois da última, "Falhou" com o motivo. Corrija a senha e use **Reenviar**.
3. Ligue **Avisar o tomador quando a nota for cancelada** e cancele uma nota. Esperado: e-mail de aviso ("Aviso de
   cancelamento").
4. **Alerta de certificado:** em **Avisos do sistema** informe um e-mail; com o certificado a ≤ 30 dias de vencer, a rotina
   diária (06:40) manda o alerta. Para ver na hora: `docker compose exec backend python manage.py shell -c "from
   fiscal.services import vencimento; vencimento.verificar_certificados()"`. Esperado: um e-mail por faixa (30, 15, 7 dias) e
   por certificado, sem repetir.

### 4. Google Drive
1. **Configuração fiscal › Google Drive**. Marque **Copiar as notas ao Google Drive**, escolha o arquivo JSON, informe o ID da
   pasta `freenfse-teste` e salve. Esperado: "Pasta confirmada: freenfse-teste"; a chave não reaparece (só o e-mail da conta de
   serviço).
2. Teste os erros: um ID inexistente; uma pasta **não** compartilhada com a conta de serviço; um arquivo que não é JSON de
   conta de serviço. Esperado: mensagens claras, **nada é salvo**.
3. Modelos: subpastas `{ano}/{mes}` e arquivo `NFSe_{numero_nfse}_{cnpj_emitente}`. **Ver exemplo com uma nota real**.
   Esperado: pasta e arquivos coerentes com a nota.
4. Tente salvar o arquivo como `nota` (sem `{chave}` nem `{numero_nfse}`+`{cnpj_emitente}`), `{xpto}`, `{ano` e subpastas
   `a//b`. Esperado: recusa, **todos** os problemas listados de uma vez.

### 5. Cópia ao Drive
1. Com **Copiar automaticamente** ligado, emita uma nota. Esperado: em instantes, `2026/10/NFSe_<n>_<cnpj>.xml` e `.pdf`
   na pasta de teste; a nota mostra os dois arquivos como "Enviado".
2. Emita **3 notas em sequência rápida**. Esperado: **uma única** pasta de ano e **uma única** de mês (sem duplicatas) e
   seis arquivos.
3. **Colisão:** crie manualmente na pasta do mês um arquivo com o nome que a próxima nota usará e emita. Esperado: a nota
   grava `… (2).xml` e mostra o aviso "Já existia outro arquivo com este nome".
4. **Cancele** uma nota. Esperado: o **mesmo** PDF (mesmo arquivo) passa a ter a marca d'água "CANCELADA" e o XML do
   evento aparece ao lado, com o sufixo do evento.
5. Apague um arquivo no Drive e use **Reenviar ao Drive** na nota. Esperado: o arquivo volta. Em **Reenviar um período ao
   Drive** informe o mês e confira a contagem na fila.
6. Apague a pasta do mês no Drive e reenvie. Esperado: o sistema recria a pasta sozinho.

### 6. Download em lote
1. **Documentos › Download em lote**. Peça o mês com todas as situações. Esperado: barra de progresso, aviso na tela
   "O download em lote nº … está pronto" e botão **Baixar ZIP**.
2. Abra o ZIP: pastas `xml/` e `pdf/` e `resumo.csv` (abre no Excel com acentos corretos e `;` como separador). O CSV
   confere com as notas (número, valores, situação). Nenhum nome de arquivo tem barras ou caracteres estranhos.
3. Limites: com `FREENFSE_LOTE_MAX_NOTAS=2`, peça um período com 3 notas. Esperado: recusa dizendo quantas notas e qual o
   limite.
4. Entre com **outro usuário** da mesma empresa: ele **não** vê nem baixa o lote do primeiro (nem o Administrador).
5. Expurgo: com `FREENFSE_LOTE_RETENCAO_HORAS=1`, depois de uma hora o lote passa a "Expirada" e o arquivo some da pasta
   `exportacoes`.

### 7. Permissões
1. Perfil **Consulta**: vê o histórico de envios e a configuração, mas **não** vê os botões de enviar/reenviar, o download em
   lote nem consegue salvar a configuração.
2. Perfil **Emissor**: envia e reenvia, baixa lotes, mas não vê as telas de configuração (issue #14).

### 8. Pontos a confirmar (hipóteses do ADR 0005)
- Gmail: a delegação em todo o domínio é aceita para o escopo `gmail.send` com a chave da conta de serviço.
- Drive: o escopo `drive` enxerga a pasta compartilhada com a conta de serviço também em **Drives compartilhados**
  (o cliente envia `supportsAllDrives`).
- Microsoft Graph: anexos de até 3 MB; confirme o tamanho típico do PDF.
- Anote o tempo de uma cópia ao Drive (a trava por empresa serializa as cópias).

## Mutações

Cada mutação troca **uma linha** do código por uma versão errada e roda os testes dos arquivos indicados: o teste precisa
**falhar** ("detectada"). Depois o arquivo é restaurado.

Rodada de 2026-10-31: **20 de 20 mutações detectadas** (nenhuma sobrevivente). 

| # | O que foi quebrado (uma linha) | Arquivo | Teste que falhou |
|---|---|---|---|
| M1 | sem a trava da empresa ao criar pastas/arquivos no Drive (cada arquivo com a sua trava) | `documentos/services/drive/envio.py` | `test_copias_simultaneas_ao_mesmo_caminho_novo_criam_cada_pasta_uma_so_vez` |
| M2 | sem o cache caminho→ID de pastas (identidade só pela listagem do Drive, que atrasa) | `documentos/services/drive/envio.py` | `test_copias_simultaneas_ao_mesmo_caminho_novo_criam_cada_pasta_uma_so_vez` |
| M3 | sem a regra de unicidade do caminho ({chave} ou {numero_nfse}+{cnpj_emitente}) | `documentos/services/drive/caminhos.py` | `test_previa_do_drive_valida_e_mostra_uma_nota_real` |
| M4 | normalização que deixa passar '/' e '\' nos nomes do Drive | `documentos/services/drive/caminhos.py` | `test_caminho_da_nota_usa_a_data_de_emissao_em_brasilia_e_normaliza` |
| M5 | nome ocupado por outra nota é sobrescrito em vez de ganhar ' (2)' | `documentos/services/drive/envio.py` | `test_nome_repetido_de_outra_nota_recebe_sufixo_e_aviso` |
| M6 | reenvio não sobrescreve pelo fileId (cria cópia nova) | `documentos/services/drive/envio.py` | `test_arquivo_proprio_gravado_antes_da_queda_e_reaproveitado` |
| M7 | serializa a senha do SMTP na resposta da configuração de e-mail | `documentos/api/serializers.py` | `test_as_credenciais_de_email_ficam_cifradas_e_nunca_voltam` |
| M8 | serializa a chave da conta de serviço na resposta da configuração do Drive | `documentos/api/serializers.py` | `test_a_conta_de_servico_do_drive_fica_cifrada_e_so_o_email_volta` |
| M9 | senha do SMTP gravada em claro (campo sem criptografia) | `documentos/models.py` | `test_as_credenciais_de_email_ficam_cifradas_e_nunca_voltam` |
| M10 | chave da conta de serviço do Drive gravada em claro | `documentos/models.py` | `test_a_conta_de_servico_do_drive_fica_cifrada_e_so_o_email_volta` |
| M11 | valor da credencial vai para a auditoria da alteração de e-mail | `documentos/api/views.py` | `test_as_credenciais_de_email_ficam_cifradas_e_nunca_voltam` |
| M12 | download em lote visível/baixável por outra pessoa da mesma empresa | `documentos/api/views.py` | `test_outro_usuario_da_mesma_empresa_nao_baixa_nem_ve_o_pedido` |
| M13 | serviço de download não confere quem pediu | `documentos/services/exportacao.py` | `test_so_quem_pediu_baixa_e_a_baixa_e_auditada` |
| M14 | nome de arquivo do ZIP sem neutralizar caracteres perigosos (path traversal) | `documentos/services/exportacao.py` | `test_nome_seguro_nunca_tem_separador_controle_nem_ponto_duplo[../../etc/passwd]` |
| M15 | CSV sem neutralizar fórmulas (injeção de planilha) | `documentos/services/exportacao.py` | `test_tomador_malicioso_nao_escapa_do_zip_nem_vira_formula` |
| M16 | limite de notas do lote ignorado | `documentos/services/exportacao.py` | `test_limite_de_quantidade_recusa_o_pedido_sem_gerar_nada` |
| M17 | e-mail em HTML sem escapar o conteúdo das variáveis | `documentos/services/envio_email.py` | `test_variaveis_com_html_e_quebras_de_linha_sao_neutralizadas` |
| M18 | anexo em PDF sempre anexado (ignora a configuração) | `documentos/services/envio_email.py` | `test_os_anexos_seguem_a_configuracao[False-True-esperado2]` |
| M19 | falha temporária de e-mail nunca reagenda (sem retentativa) | `documentos/services/envio_email.py` | `test_falha_temporaria_reagenda_com_espera_crescente_e_depois_envia` |
| M20 | e-mail automático ao autorizar ignora a configuração (envia sempre) | `documentos/receptores.py` | `test_reenvio_manual_cria_um_novo_registro_com_os_mesmos_destinatarios` |

No M3 e no M20 a execução parou (`-x`) no primeiro teste a falhar; os testes dedicados também os detectam (`test_drive_caminhos.py::test_regra_de_unicidade_chave_ou_numero_com_cnpj` e `test_email_envio.py::test_sem_envio_automatico_nada_e_enfileirado`, conferidos à parte). Cada mutação troca uma linha, roda os testes dos arquivos indicados e restaura o arquivo; o script e a lista de mutações da rodada não são versionados.

