# Verificação da issue #33 (endereço do tomador e do destinatário pelo `cIndOp`)

Os testes automatizados usam a Sefin simulada (nenhum pacote sai para a rede) e **assinam a DPS de verdade**: eles conferem o XML que chega
à Sefin. O que só o ambiente real confirma está no roteiro manual abaixo. Decisões, fontes e limites:
[ADR 0011](adr/0011-enderecos-do-tomador-e-do-destinatario-pelo-cindop.md); origem e SHA-256 do Anexo VII:
[`backend/fiscal/referencias/dados/LEIAME.md`](../backend/fiscal/referencias/dados/LEIAME.md).

> **Cuidado:** use **sempre a produção restrita** e dados fictícios. Nunca cole certificado, chave de acesso, XML, CPF/CNPJ ou e-mail
> reais em issues, PRs, mensagens ou logs.

## Roteiro manual (produção restrita, certificado A1 de teste)

Pré-requisito: empresa de teste pronta para emitir (certificado válido, município emissor e convênio verificado), com um **serviço que exige o
grupo de IBS/CBS** (exemplo: item `01.01.01`, NBS `1.1502.10.00`, CST `000`, classificação `000001`). Use três pessoas fictícias:

- **T1** — tomador PJ do Brasil, com CNPJ e endereço completo;
- **T2** — tomador **estrangeiro** (com NIF e endereço no exterior);
- **T3** — tomador PJ do Brasil com o **endereço incompleto** (cadastre e, se a tela não deixar, use um cadastro antigo sem CEP).

### Parte A — local do fornecimento = endereço do tomador (E0239)

Serviço com o indicador **`100301`** (local = adquirente).

1. **Tomador T1.** Confira a nota: sem erro. Emita: a nota é **autorizada**; no XML da DPS baixado, `IBSCBS/cIndOp` é `100301`.
2. **Tomador T2 (estrangeiro).** *Conferir a nota* recusa e mostra junto do tomador *Regra E0239 da Sefin… o tomador é estrangeiro*. Nada é
   enviado.
3. **Tomador T3 (sem endereço nacional).** Mesma recusa, agora dizendo o que falta (*falta o CEP…*).
4. Com `indDest = 1` (*O destinatário é o próprio tomador?* = **Não**) e um destinatário válido, **T2 continua barrado** (E0239 olha o tomador).
5. Ajuste o indicador da nota para um que **não** seja de endereço (exemplo: `030101`): T2 passa na conferência.

### Parte B — local = endereço do destinatário (E0243 e E0919)

Serviço com o indicador **`100302`** (local = destinatário).

1. `indDest = 0` (o próprio tomador) com **T2**: recusa **E0243** no campo do tomador. Com T1: passa.
2. `indDest = 1`, tomador qualquer e **destinatário** estrangeiro ou sem endereço completo: recusa **E0919** no campo *Destinatário*. Com
   destinatário nacional completo: passa (o tomador pode ser estrangeiro).
3. `indDest = 1` **sem escolher o destinatário**: a tela pede *Escolha o destinatário no cadastro de pessoas* citando a E0919.

### Parte C — destinatário na nota, no modelo e no rascunho

1. Com `indDest = 1` e o grupo de IBS/CBS, a nota tem o campo **Destinatário** (obrigatório). Emita e **baixe o XML da DPS**: há `IBSCBS/dest` com
   o CNPJ/CPF (ou NIF), o nome e o endereço (`endNac` com `cMun` e `CEP`, ou `endExt`). Anote se a Sefin **autoriza**.
2. Com `indDest = 0` (ou serviço sem o grupo), o campo some e o XML **não tem** `dest`.
3. **Modelo.** Em *Modelos de NFS-e*, defina o *Destinatário (quando é outra pessoa)*. Gere um rascunho: nasce com o destinatário *do modelo*. Na
   nota, escolha outro: vale o da nota; *Voltar ao destinatário do modelo* volta. Modelo sem destinatário: cada nota escolhe.
4. **Agendamento.** O rascunho gerado por um agendamento de um modelo com destinatário já leva a pessoa.
5. Mude o endereço do destinatário no cadastro **depois** de gerar o rascunho: o rascunho continua com a cópia de antes (snapshot).
6. Rascunho antigo com *outra pessoa* e sem destinatário é **barrado na solicitação** com a mensagem de como corrigir.

### Parte D — indicador fora da tabela e sem o grupo

1. Indicador `999999` (ajustado na nota): recusa **E0901** junto do campo do indicador.
2. Serviço cuja classificação **não exige** o grupo (exemplo: CST `410`, classificação `410009`) com **T2**: a nota passa e é autorizada **sem** o grupo
   (nenhuma das regras se aplica).

### Parte E — o caso do `130201` (confirmar com a Sefin)

Serviço de transporte dutoviário de gás natural (exemplo de uso: capacidade de saída do duto) com o indicador **`130201`**.

1. Tomador **T2** ou **T3**: a conferência mostra o **aviso** *O texto do Anexo VII indica o endereço do adquirente para este indicador; confira…
   E0239* e **não bloqueia**: a nota é enviada.
2. Com o tomador **T1**, o aviso some.
3. **Anote a resposta da Sefin** à nota enviada com T2/T3: se ela **rejeitar com E0239**, o aviso deve virar bloqueio (ADR 0011, item aberto 1);
   se **autorizar**, a leitura só pela coluna estruturada se confirma para este indicador.

## O que os testes automatizados cobrem

| Regra / requisito | Onde | Como |
|---|---|---|
| E0239, E0243, E0919 (função pura, tabular) | `fiscal/tests/test_regras_de_endereco.py` | tomador/destinatário PF, PJ, estrangeiro, sem endereço, com cada campo do endereço faltando; `indDest` 0 e 1; local adquirente/destinatário/outro; com e sem o grupo |
| Todos os 40 indicadores do Anexo VII | idem | cada indicador de adquirente exige o tomador; cada um de destinatário exige quem é destinatário; os 29 outros nunca bloqueiam |
| E0901 (fora da tabela) | idem e `test_regras_de_endereco_na_nota.py` | código inexistente, vazio, curto; indicadores **sem** a marca `indNFSe = S` não bloqueiam |
| Aviso do 130201 | idem | só o 130201; aparece com tomador estrangeiro/sem endereço/ausente, some com tomador completo, nunca bloqueia |
| Coerência com o cadastro de pessoas | `TestConsistenciaComOCadastro` | o que o cadastro aceita atende à regra e o que a regra recusa o cadastro não grava |
| Aplicação na prévia, no rascunho, na solicitação e no envio | `fiscal/tests/test_regras_de_endereco_na_nota.py` | erro no campo certo com o código da regra; rascunho barrado não é gravado; nota antiga é barrada de novo na solicitação e na execução (volta a rascunho, nada vai à Sefin); API |
| Destinatário: obrigatório com `indDest = 1`, descartado com 0, snapshot, nota > modelo, DPS assinada com/sem `dest` | `fiscal/tests/test_destinatario.py` | XML assinado recebido pela Sefin simulada |
| Destinatário no modelo e no rascunho do agendamento | `agendamentos/tests/test_destinatario_no_modelo.py` | herança, "voltar a herdar", rascunho gerado, API |
| Leitura do Anexo VII | `fiscal/tests/test_referencias_oficiais.py` | extrator com planilhas sintéticas (recusa valor novo, texto incoerente, código repetido, cabeçalho trocado), comando de importação, **amostras conferidas com o texto oficial**, 4/7/29, SHA-256 no `LEIAME`, todo `cIndOp` do Anexo VIII consta do VII |
| Telas | `notas.test.jsx`, `agendamentos.test.jsx` | seletor de destinatário (aparece só com "Não"), erro junto do campo, aviso do 130201, destinatário do modelo |

## Mutações (38 de 38 detectadas)

Cada mutação altera o código de propósito, roda **só os testes indicados** e restaura o arquivo. "Detectada" = pelo menos um teste falhou. Antes
de rodar, o executor confere que o trecho original aparece **exatamente uma vez** (senão a mutação seria um no-op silencioso). Resultado de
2026-11-07: **uma sobreviveu na primeira rodada (B2) e exigiu um teste novo**; depois dele, nenhuma sobrevive.

| # | Mutação | Regra | Testes que a pegam |
|---|---|---|---|
| C1 | ignora o `indDest` (E0243 vale sempre; E0919 some) | E0243/E0919 | `test_regras_de_endereco` |
| C2 | troca adquirente por destinatário na leitura da tabela | E0239/E0243 | idem |
| C3 | aceita estrangeiro como se fosse nacional | E0239/E0243/E0919 | idem |
| C4 | aceita endereço incompleto (logradouro, número, bairro, CEP, município) | idem | idem |
| C5 | aceita CEP ausente ou curto | idem | idem |
| C6 | aceita município ausente ou de 6 dígitos | idem | idem |
| C7 | aplica as regras mesmo sem o grupo de IBS/CBS (função pura) | todas | idem |
| C8 | idem, na integração com a nota | todas | `test_regras_de_endereco_na_nota`, `test_destinatario` |
| C9 | o aviso do 130201 vira bloqueio | 130201 | `test_regras_de_endereco` |
| C10 | o aviso do 130201 aparece mesmo com o tomador completo | 130201 | idem |
| C11 | `cIndOp` fora da tabela deixa de bloquear | E0901 | idem |
| C12 | critério errado: indicador sem a marca `indNFSe = S` conta como fora da tabela | E0901 | idem |
| C13 | E0919 olha o tomador em vez do destinatário | E0919 | idem |
| C14 | E0239 olha o destinatário em vez do tomador | E0239 | idem |
| C15 | CNPJ do tomador PJ não é conferido | E0239/E0243/E0919 | idem |
| C16 | CPF do tomador PF não é conferido | idem | idem |
| C17 | endereço no exterior em PF/PJ é aceito | idem | idem |
| C18 | o aviso vale para todo indicador cujo texto cita o adquirente | 130201 | idem |
| C19 | a mensagem da E0919 não substitui a genérica de destinatário faltando | E0919 | `test_regras_de_endereco_na_nota`, `test_destinatario` |
| C20 | a prévia/rascunho não aplica as regras | todas | idem |
| C21 | a solicitação e o envio não reaplicam as regras | todas | idem |
| C22 | a solicitação ignora os erros de IBS/CBS | todas | idem |
| C23 | a execução ignora os erros de IBS/CBS (nota autorizada em vez de voltar a rascunho) | todas | idem |
| C24 | dado do JSON: 100301 deixa de ser do adquirente | E0239 | `test_regras_de_endereco` |
| C25 | dado do JSON: 100302 passa a ser do adquirente | E0243/E0919 | idem |
| A1 | extrator: "Endereço do Destinatário" vira adquirente | Anexo VII | `test_referencias_oficiais` |
| A2 | extrator: valor desconhecido na coluna não é recusado | Anexo VII | idem |
| A3 | extrator: classificação não é conferida com o texto | Anexo VII | idem |
| A4 | extrator: indicador repetido não é recusado | Anexo VII | idem |
| B1 | a DPS não leva o grupo `dest` | `indDest = 1` | `test_destinatario` |
| B2 | a DPS leva o `dest` mesmo com `indDest = 0` | `indDest = 0` | `test_destinatario` — **pegou só depois do teste novo** `test_se_o_padrao_da_empresa_muda_para_o_proprio_tomador_a_dps_sai_sem_dest` |
| B3 | com `indDest = 1` o destinatário deixa de ser obrigatório | `indDest = 1` | idem |
| B4 | o destinatário escolhido com `indDest = 0` não é descartado | `indDest = 0` | idem |
| B5 | prioridade trocada: o modelo vale mais que a nota | nota > modelo | idem |
| B6 | corrigir o rascunho perde o destinatário do modelo | herança | idem |
| B7 | o rascunho do agendamento não leva o destinatário do modelo | agendamento | `test_destinatario_no_modelo` |
| B8 | destinatário inativo é aceito | cadastro | `test_destinatario` |
| B9 | nome do destinatário acima de 150 caracteres é aceito | DPS `xNome` | idem |

Execução de 2026-11-07: suíte completa do backend verde (1.822 testes, nenhum ignorado), `ruff` limpo, `makemigrations --check` sem pendência, frontend
com ESLint limpo e testes verdes.
