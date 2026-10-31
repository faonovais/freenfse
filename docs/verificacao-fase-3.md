# Verificação da Fase 3 (núcleo fiscal)

Os testes automatizados trocam o transporte HTTP da `freedfe` por uma **Sefin simulada** (`fiscal/tests/sefin_simulada.py`):
a biblioteca monta, assina e envia de verdade, mas nada sai para a rede. O que só um certificado A1 real e a
produção restrita podem confirmar está no roteiro manual abaixo.

> **Cuidado:** nunca cole o `.pfx`, a senha, chaves de acesso reais ou XMLs reais em issues, PRs, mensagens ou logs.
> Use **sempre a produção restrita**.

## Roteiro manual (produção restrita, certificado A1 real)

### Antes de começar
1. Siga o roteiro da Fase 2 até ter: empresa com o CNPJ do titular do certificado, município emissor, **convênio verificado** e certificado enviado.
2. Cadastre uma **pessoa** (tomador, com endereço e município) e um **serviço** vigente (código nacional, alíquota do ISS).
3. Confirme o selo "Produção restrita" no cabeçalho.

### 1. Emissão
1. **Notas fiscais › NFS-e emitidas › Nova nota**. Escolha o tomador, a competência, o serviço e o valor.
2. **Conferir a nota**: confira o cálculo (ISS, retenções, líquido), o ambiente e o leiaute (**NT 009** na produção restrita).
3. **Emitir nota** e confirme. Esperado: a tela acompanha "Enviando à Sefin…" e termina em **Autorizada**, com número, chave de acesso e leiaute.
4. **Baixar XML** e **Abrir DANFSe**: o PDF deve mostrar "NFS-e SEM VALIDADE JURÍDICA" (ambiente de teste).
5. Se a Sefin rejeitar: a tela mostra código, explicação, o que fazer e o texto original. Anote o código e **não** apague a nota.

### 2. Consulta
1. Na nota autorizada, **Atualizar pela Sefin**. Esperado: confirmação sem alterar a situação.

### 3. Teste de timeout (resultado incerto)
1. Com uma nota pronta para emitir, **desligue a internet** do servidor logo depois de clicar em **Emitir nota** (ou use `iptables`/bloqueio de saída para o host da Sefin).
2. Esperado: a nota fica **Resultado incerto**, com o aviso para não emitir de novo; **nenhum número novo é gasto**.
3. Religue a internet. Em até 5 minutos a rotina confere sozinha, ou clique **Conferir agora na Sefin**.
   - Se a Sefin tinha recebido a DPS: a nota passa a **Autorizada** sem nova emissão (confira na Sefin que há **uma** nota).
   - Se não tinha: segue incerta; clique **Tentar enviar de novo** e confirme. Esperado: **mesmo número de DPS**, autorizada.
4. Emita outra nota enquanto a primeira estiver incerta. Esperado: recusa explicando que há nota da série sem resultado confirmado.

### 4. Cancelamento
1. Na nota autorizada, **Cancelar nota**, escolha o motivo e escreva a justificativa (15 a 255 caracteres), confirme.
2. Esperado: a nota passa a **Cancelada** só depois da confirmação, com o evento listado; o DANFSe passa a ter marca d'água "CANCELADA".
3. Tente cancelar fora do prazo ou contra a regra do município, se o seu município tiver uma. Esperado: mensagem didática, nota segue autorizada.

### 5. Substituição
1. Em outra nota autorizada, **Emitir nota substituta a partir desta**, escolha o motivo.
2. Corrija o que for preciso no rascunho, **Emitir nota**. Esperado: a nova nota é autorizada e a original passa a **Substituída** (se não passar na hora, em até 5 minutos).

### 6. Permissões
1. Entre com um usuário de perfil **Consulta**: ele lista e abre notas, mas não vê "Nova nota", "Cancelar" nem "Substituir".

### 7. Pontos a confirmar (hipóteses)
- Se a Sefin rejeitar por alíquota (`pAliq`) ou por `totTrib`, registre o código: são hipóteses da ADR 0004 (§7).
- Anote o tempo real de resposta da emissão: a trava segura as demais emissões da empresa durante o `POST`.

## Verificação automatizada

Backend (precisa de PostgreSQL acessível conforme o `.env`) e frontend:

```bash
cd backend && ruff check . && ruff format --check . && pytest
cd ../frontend && npm run lint && npm test && npm run build
```

### Cobertura dos critérios da fase

| Critério | Onde está provado |
|---|---|
| Emissão autorizada guarda XML, hash e leiaute | `test_emissao.py` (autorizada, hash do repositório, DPS como evidência) |
| N emissões paralelas, mesma empresa e série: números distintos, sem lacuna, **um envio por vez** | `test_emissao_concorrente.py` (threads e conexões reais) + `persistencia/test_concorrencia.py` |
| Timeout e 5xx → incerta, sem reenviar | `test_emissao.py` (`timeout`, `5xx`, série bloqueada, recuperação de queda) |
| Reconciliação acha a nota já autorizada **sem novo POST** | `test_emissao.py::test_a_reconciliacao_acha_a_nota_ja_autorizada_sem_enviar_de_novo` (`total_de_posts == 1`) |
| Rejeição 4xx didática; reenvio reaproveita o número | `test_emissao.py` (código + explicação + o que fazer + texto original) |
| Cancelamento ok e recusado (prazo/regra do município) | `test_cancelamento_substituicao.py` |
| Substituição: nova nota referencia a original, que vira substituída só com o evento | `test_cancelamento_substituicao.py` |
| DANFSe com marca d'água quando cancelada/substituída | `test_cancelamento_substituicao.py` (situação que chega ao gerador) |
| Isolamento entre empresas e numeração independente | `persistencia/*`, `test_api_notas.py`, `test_emissao_concorrente.py` |
| Permissões (Consulta não emite; sem `nfse.cancelar` não cancela) | `test_api_notas.py` |
| Leiaute NT 004 antes de 01/12/2026 e NT 009 depois, na virada de Brasília | `test_leiaute.py` (data injetada; XML muda de fato) |
| Suíte de contrato do `EstadoEmissao` da freedfe | `persistencia/test_estado_emissao.py` |
| `freedfe` só entra pelo gateway, persistência e certificado | `test_fronteira_da_freedfe.py` |

### Mutações executadas (cada uma deve ser detectada por um teste)

Cada linha altera **uma** instrução do código de produção, roda os testes indicados e restaura o arquivo.

| # | Mutação | Resultado |
|---|---|---|
| M1 | remove o `SELECT … FOR UPDATE` da linha da série (`reservar_proximo`) | detectada: `test_reservas_paralelas_na_mesma_serie_geram_numeros_distintos_e_sem_lacuna` |
| M2 | a trava concede sempre (advisory lock que não exclui) | detectada: `test_a_trava_exclui_de_fato_duas_operacoes_da_mesma_empresa` |
| M3 | a reconciliação **reenvia** a DPS em vez de só consultar | detectada: `test_nota_nao_localizada_segue_incerta_ate_o_usuario_pedir_novo_envio` |
| M4 | o reenvio não reaproveita o número (numera de novo) | detectada: `test_novo_envio_manual_da_incerta_confere_antes_e_reaproveita_o_numero` |
| M5 | a máquina de estados não confere a tabela de transições | detectada: `test_toda_transicao_fora_da_tabela_e_recusada` |
| M6 | o cancelamento muda a nota antes da confirmação da Sefin | detectada: `test_cancelamento_confirmado_muda_a_nota_e_guarda_o_evento` |
| M7 | a permissão de cancelar passa a ser `nfse.consultar` | detectada: `test_consulta_le_mas_nao_cria_emite_cancela_nem_substitui` |
| M8 | o leiaute usa a data UTC em vez da de Brasília | detectada: `test_producao_troca_de_leiaute_em_1_de_dezembro_de_2026` (instante 02:59:59Z) |
| M9 | a original vira "substituída" sem o evento da Sefin | detectada: `test_substituta_referencia_a_original_que_vira_substituida` |

