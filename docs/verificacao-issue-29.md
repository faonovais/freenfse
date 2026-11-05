# Verificação da issue #29 (`pAliq` e IBS/CBS pela regra oficial)

Os testes automatizados usam a Sefin simulada (nenhum pacote sai para a rede) e **assinam a DPS de verdade**; eles conferem o XML que
chega à Sefin. O que só o ambiente real confirma está no roteiro manual abaixo. Decisões, fontes e limites: [ADR 0010](adr/0010-paliq-e-ibs-cbs-pela-regra-oficial.md);
origem e SHA-256 das tabelas oficiais: [`backend/fiscal/referencias/dados/LEIAME.md`](../backend/fiscal/referencias/dados/LEIAME.md).

> **Cuidado:** use **sempre a produção restrita** e dados fictícios. Nunca cole certificado, chave de acesso, XML ou e-mail reais em
> issues, PRs, mensagens ou logs.

## Roteiro manual (produção restrita, certificado A1 de teste)

Pré-requisito: empresa de teste com certificado válido, município emissor e **convênio verificado** (*Configuração fiscal › Parâmetros
fiscais › Verificar convênio*). Anote o que a verificação mostra (aderente e data de ativação): é a base das regras abaixo.

### Parte A — alíquota do ISS (`pAliq`)

Em cada caso, na **conferência da nota**, a linha *Alíquota do ISS na DPS* diz se vai, o código da regra e onde incide o ISSQN. Depois de
emitir, **baixe o XML da DPS/NFS-e** e confira se `pAliq` está presente ou ausente como a conferência disse.

1. **O defeito original — não optante num município conveniado.** Regime *Outro (não optante)*. Emita uma nota. Esperado: conferência
   *Não vai na nota (regra E0617)*; a nota é **autorizada**. (Antes da correção ela era rejeitada com E0617.)
2. **ME/EPP, ISSQN pelo Simples (apuração 1).** Sem retenção: *Não vai (E0625)*. Com o serviço marcado *ISS retido*: *Vai na nota (E0621)*, com
   a alíquota do cadastro. Reduza a alíquota do serviço para 1,5%: a conferência diz **Bloqueia o envio (E0621)** e a nota não é enviada.
3. **ME/EPP, ISSQN fora do Simples (apuração 2 ou 3).** Município conveniado: *Não vai (E0635)*.
4. **MEI.** Nunca vai (E0600).
5. **Regime especial de tributação (1 a 6).** Não vai (E0604). Em ME/EPP com a regra pedindo a alíquota, a emissão fica **bloqueada** como conflito.
6. **Competência anterior à ativação do convênio.** Se o município tem data de ativação conhecida, emita com competência anterior a ela
   (não optante): esperado *Vai na nota (E0619)*.
7. **Serviço 17.05.01 (mão de obra) com tomador de outro município.** O ISSQN incide no município do tomador: o envio consulta o convênio dele.
   Com a Sefin fora do ar e sem valor guardado, a nota volta a rascunho dizendo que não conseguiu confirmar o convênio.
8. **Registre** o que a consulta de convênio devolve (`aderenteAmbienteNacional`, `dataAtivacao`) para os municípios usados: o ADR 0010 assume que
   *aderente e ativação até a competência* é o "convênio ativo" da regra. Se a Sefin rejeitar uma nota que a conferência liberou (ou o contrário),
   anote o **código do erro**: é a hipótese a corrigir.

### Parte B — IBS/CBS

1. **Cadastro do serviço.** Em *Cadastros › Serviços*, informe código de tributação nacional, NBS, CST e classificação (exemplo: `01.01.01`,
   NBS `1.1502.10.00`, CST `000`, classificação `000001`). Clique em **Ver sugestão do indicador e situação da classificação**: a tela diz que a
   classificação **exige** o grupo e sugere o indicador do Anexo VIII (`100301`); **Usar 100301** e salve.
2. **Classificação que exige o grupo.** Emita uma nota: a conferência mostra *Indicador da operação 100301 (do serviço)*; a DPS leva o grupo
   `IBSCBS` com `cIndOp`, `CST` e `cClassTrib`. Anote se a Sefin autoriza.
3. **Classificação sem tributação de IBS/CBS** (exemplo: CST `410`, classificação `410009`): a conferência diz *Não vai na nota (ind_gIBSCBS = 0)*;
   a nota é autorizada sem o grupo.
4. **Serviço que exige o grupo e não tem indicador.** Esvazie o indicador do serviço e crie uma nota: a mensagem pede para completar o cadastro
   (E0860) e nada é enviado.
5. **99.03** (`99.03.01`): o cadastro recusa um indicador que não comece por `02` (E0902).
6. **Classificação inválida:** uma que **não vale para NFS-e** (exemplo: `200003`) ou fora da tabela é recusada na conferência (E0958).
7. **Ajustes e prioridade.** Ajuste o indicador no *modelo* e, depois, na *nota*: vale a nota, depois o modelo, depois o serviço; a conferência
   mostra a origem de cada campo.
8. **Confirme a classificação** usada com o contador: a tabela vem do piloto da calculadora do IBS/CBS; se a Sefin rejeitar uma classificação
   que a tabela aceita (ou o contrário), anote o código do erro.

## O que os testes automatizados cobrem

| Regra | Onde | Como |
|---|---|---|
| E0600, E0604, E0617, E0619, E0621, E0625, E0628, E0631, E0635, E0640 | `fiscal/tests/test_aliquota_issqn.py` (regra pura, tabular) e `test_aliquota_na_emissao.py` | `pAliq` presente ou ausente **no XML assinado que chega à Sefin**, em cada caso |
| Mínimo de 1,8% (E0621/E0628) | os dois arquivos | 1,79 bloqueia, 1,80 e 1,81 passam, 0 bloqueia |
| Teto de 5% (E0595) | `test_aliquota_issqn.py` | 5 passa, 5,01 bloqueia |
| Convênio por data de competência | os dois arquivos | ativação futura, no próprio dia, anterior, sem data, não aderente, desconhecido |
| Município de incidência (EP, LP, ET) | os dois arquivos | tomador de outro município consulta o convênio dele; sem rede, volta a rascunho |
| E0859, E0860, E0960/E0961 | `fiscal/tests/test_ibs_cbs.py` | grupo e `cIndOp` presentes ou ausentes no XML conforme `ind_gIBSCBS` |
| E0958, E0959, E0902, E0322 | idem e `test_referencias_oficiais.py` | classificação inexistente, fora da vigência, que não vale para NFS-e; CST incoerente; 99.03; NBS faltando |
| Sugestão pelo Anexo VIII | `test_ibs_cbs.py`, `test_referencias_oficiais.py` | única, várias opções (não escolhe), item/NBS fora do anexo |
| Prioridade nota > modelo > serviço (`cIndOp`) | `test_ibs_cbs.py`, `agendamentos/tests/test_ibs_cbs_no_modelo.py` | por campo; chaves antigas (`informar`) ignoradas |
| Tabelas oficiais | `test_referencias_oficiais.py` | leitor de `.xlsx` com mesclagens, extratores (recusam forma inesperada), baixador contra uma fonte falsa (firewall HTML, nova tentativa, busca binária de vigência), SHA-256 do `LEIAME` |
| Rascunho antigo, migração, API | `test_ibs_cbs.py`, `test_migracao_ibs_cbs.py` | rascunho sem `cIndOp` é barrado; a migração não copia o `cIndOp` da empresa |

## Mutações (29 de 29 detectadas)

Cada mutação altera o código de propósito, roda **só os testes indicados** e restaura o arquivo. "Detectada" = pelo menos um teste falhou.
Antes de rodar, o executor confere que o trecho original aparece **exatamente uma vez** (senão a mutação seria um no-op silencioso).
Resultado de 2026-11-05: **nenhuma sobreviveu**. Nenhuma exigiu teste novo depois da rodada.

| # | Mutação | Regra | Testes que a pegam |
|---|---|---|---|
| A1 | convênio ativo/não ativo invertido | E0617/E0619/E0635/E0640 | `test_aliquota_issqn`, `test_aliquota_na_emissao` |
| A2 | ignora a retenção do ISSQN (ME/EPP pelo Simples) | E0621/E0625/E0628/E0631 | idem |
| A3 | remove o mínimo de 1,8% | E0621/E0628 | idem |
| A4 | mínimo com `<=` (1,80 deixaria de passar) | E0621/E0628 | `test_aliquota_issqn` |
| A5 | ignora a data de ativação do convênio | E0617/E0619 | `test_aliquota_issqn`, `test_aliquota_na_emissao` |
| A6 | ativação no próprio dia da competência ainda não vale | E0617/E0619 | idem |
| A7 | remove a proibição do regime especial 1 a 6 | E0604 | idem |
| A8 | MEI deixa de ser tratado | E0600 | idem |
| A9 | não optante com convênio ativo passa a exigir a alíquota | E0617 | idem |
| A10 | município de incidência é sempre o do emissor | LC 116 art. 3º | idem |
| A11 | gateway envia `pAliq` sempre (volta ao defeito original) | E0617 | `test_aliquota_na_emissao` |
| A12 | alíquota obrigatória sem valor não bloqueia | E0621/E0628/E0619/E0640 | `test_aliquota_issqn`, `test_aliquota_na_emissao` |
| A13 | a solicitação de emissão não aplica o bloqueio | E0621/E0628 | `test_aliquota_na_emissao` |
| A14 | convênio consultado é o do emissor, não o de incidência | LC 116 art. 3º | `test_aliquota_na_emissao` |
| A15 | teto de 5% removido | E0595 | `test_aliquota_issqn` |
| A16 | E0604 contra exigência deixa de ser conflito | E0604 × E0621/E0619 | `test_aliquota_issqn`, `test_aliquota_na_emissao` |
| B1 | ignora o `ind_gIBSCBS` (sempre manda o grupo) | E0859/E0961 | `test_ibs_cbs` |
| B2 | `ind_gIBSCBS` invertido | E0859/E0860 | idem |
| B3 | o `cIndOp` do serviço deixa de ser lido | E0860 | `test_ibs_cbs`, `test_ibs_cbs_no_modelo` |
| B4 | prioridade trocada: o serviço vale mais que a nota | nota > modelo > serviço | idem |
| B5 | E0902 (99.03 exige 02XXXX) ignorada | E0902 | `test_ibs_cbs`, `test_referencias_oficiais` |
| B6 | classificação que não vale para NFS-e é aceita | E0958 | `test_ibs_cbs` |
| B7 | CST incoerente com a classificação é aceito | E0959 | idem |
| B8 | vigência da classificação ignorada | E0958 | idem |
| B9 | rascunho antigo não é revalidado na solicitação | E0860 | idem |
| B10 | `cIndOp` obrigatório ausente não bloqueia | E0860 | idem |
| B11 | competência anterior à tabela oficial não é tratada | — (aviso) | idem |
| B12 | E0902 removida do cadastro do serviço | E0902 | idem |
| B13 | ajuste de `cIndOp` sem tributação deixa de avisar | E0961 | idem |

O executor das mutações é um script de uso local (não versionado); a lista acima é a especificação para repeti-las.

## Atualização da issue #27

Itens do checklist que esta correção altera:

- Trocar *"Ajustes da #20: IBS/CBS por empresa e no modelo, troca para produção"* por: roteiro da #20 (Emissor, troca para produção, municípios)
  **mais** [`verificacao-issue-29.md`](verificacao-issue-29.md) (`pAliq` e IBS/CBS pelo serviço).
- *"`pAliq` e `totTrib`"*: `pAliq` agora segue as regras E0600 a E0640 (confirmar o convênio na produção restrita, Parte A); `totTrib` segue como estava.
- *"Indicador da operação (cIndOp)"*: agora é **do serviço**, sugerido pelo Anexo VIII; a tabela oficial está versionada. Confirmar a aceitação pela Sefin (Parte B).
