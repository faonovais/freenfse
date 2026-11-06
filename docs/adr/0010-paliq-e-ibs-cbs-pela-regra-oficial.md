# ADR 0010 — `pAliq` e IBS/CBS pela regra oficial da NT 009 (issue #29)

Status: aceito (implementado na issue #29). **Revisa** o [ADR 0004](0004-nucleo-fiscal.md) §7 (hipótese do `pAliq`),
**revoga** o [ADR 0007](0007-ajustes-da-issue-20.md) §1 (IBS/CBS como padrão da empresa) e o trecho do
[ADR 0006](0006-modelos-e-agendamentos.md) que o complementava.

## Contexto

Um comentário na issue #16 apontou duas decisões do sistema que geram rejeição na Sefin. As regras foram conferidas **no texto
original** do Anexo VI v1.04.01 da NT SE/CGNFS-e 009/2026 (aba `RN DPS_NFS-e`) e batem com a tabela da issue #29.

1. **`pAliq`**: `gateway.py::_informa_aliquota` decidia só pelo regime do prestador. A regra oficial depende também do
   **convênio do município de incidência do ISSQN na data de competência** e da **retenção do ISSQN**. O caso grave: um
   prestador não optante num município conveniado enviava `pAliq` e tinha **todas as notas rejeitadas (E0617)**. Nenhum teste
   olhava o `pAliq` no XML, por isso o defeito passou.
2. **IBS/CBS**: a decisão de 31/10 (ADR 0007) fez da **empresa** a dona da opção "informar" e do `cIndOp`. A regra oficial é outra:
   o grupo e o `cIndOp` são obrigatórios (`ind_gIBSCBS = 1`, E0860/E0960) ou proibidos (`= 0`, E0859/E0961) conforme a
   **classificação tributária (cClassTrib) do serviço na data de competência**; o `cIndOp` é da operação/serviço.

Decisão do usuário (2026-11-04), com plano aprovado em 2026-11-05: corrigir as duas coisas e retirar o padrão de IBS/CBS da empresa.

## Decisões

### 1. Fontes oficiais versionadas, sem digitação à mão

Três tabelas em `backend/fiscal/referencias/dados/`, cada uma regravada por um comando e documentada (origem, data, SHA-256) em
`LEIAME.md` (mesmo padrão da tabela de municípios, ADR 0003):

| Tabela | Fonte | Comando |
|---|---|---|
| Localidade de incidência do ISSQN por serviço | Anexo VI, aba `MUN.INCID_INFO.SERV.` | `importar_anexos_rtc` |
| Item da LC 116 + NBS → INDOP → cClassTrib | Anexo VIII **v01.02.00 (2026-10-26)** | `importar_anexos_rtc` |
| Classificação tributária com vigência e `ind_gIBSCBS` | Dados abertos da calculadora do IBS/CBS (RFB/CGIBS) | `atualizar_classificacao_tributaria` |

**Arquivos oficiais e tabelas geradas** (obtidos em 2026-11-04, horário de Brasília; o `LEIAME.md` da pasta tem a origem completa):

| Arquivo | SHA-256 |
|---|---|
| Anexo VI v1.04.01 (`anexovi-leiautesrn_rtc_ibscbs-v1-04-01-nt009.xlsx`) | `103a150dd6f56ec8edcaa3a453b59a1b0e096d7cd5025d7bd06a387f141ddf39` |
| Anexo VIII **v01.02.00 de 2026-10-26** (`anexo_viii-tabela-correlacao-v01-02-00-20261026.xlsx`; **substitui a v1.01.00 do plano**) | `12cc80bc92687856b47e961b98cdbaa3f8cae568c099b3ef71994e73482ac7d0` |
| `localidade_incidencia.json` | `68ade5da910d09d45d04887c847297ac0a50aebcd3ae07d9a638ede8cba978d1` |
| `correlacao_indop.json` | `a80780e3e3502a8c65be4e8769adbe006ccde4ab2c4a7738ebe7f07ed840c497` |
| `classificacao_tributaria.json` (calculadora piloto, app 1.6.2-a39944eb) | `3c667289bfec6a975e3054f2cc12fcf1db277d6aea5285172ded2c5614391604` |

**Condições da fonte da classificação** (aprovadas pelo Supervisor): a tabela vem do ambiente **piloto** da calculadora
(`piloto-cbs.tributos.gov.br`), fica **versionada no repositório** com vigência, data de obtenção, SHA-256 e URL, e **nada consulta a
calculadora na hora de emitir** (sem dependência de rede nem do firewall). O baixador é só ferramenta de atualização. Por ser piloto, a
tabela **deve ser revalidada antes da produção** (item do checklist de produção e da issue #27); se a RFB publicar a tabela de `cClassTrib`
em outra fonte oficial (por exemplo uma planilha), a **comparação entra nessa revalidação**. `cClassTrib` desconhecido, fora da vigência na data
de competência ou que não vale para NFS-e **bloqueia a emissão com mensagem (E0958)**; nunca é presumido.

O que a fonte real mostrou, diferente do que o plano supunha (comunicado ao Supervisor antes de seguir):

- **Anexo VIII**: o portal já publica a v01.02.00, mais nova que a v1.01.00 citada no plano; usada a vigente. Ele é feito de
  **células mescladas** (cada valor vale para um intervalo de linhas): o leitor de `.xlsx` (só biblioteca padrão) as expande.
  Os códigos especiais do grupo 99 (`99.03.01` etc.) aparecem pelo código completo, não pelo item.
- **`ind_gIBSCBS`**: a URL que o Anexo VI cita nas E0859/E0860 é um endereço **interno do Serpro**; o mesmo caminho é público no
  **piloto** da RFB/CGIBS (`piloto-cbs.tributos.gov.br`, domínio gov.br, ambiente `apr`). É a fonte usada; por ser piloto, a
  classificação precisa ser confirmada na produção restrita (roteiro). A fonte devolve **vigência real** (as classificações 220001–220003
  só vigoram em 01/01/2026) mas não informa início/fim: o comando amostra o período e refina por busca binária até o dia exato.
- **Firewall da fonte**: sob rajada ele responde **HTTP 200 com uma página HTML "Request Rejected"**. O baixador valida cada resposta como
  JSON, espaça as chamadas, tenta de novo e nunca grava resposta inválida.
- **Localidade de incidência**: o próprio Anexo VI traz a tabela por `cTribNac` (277 no estabelecimento do prestador, 58 no local da
  prestação, 1 no estabelecimento do tomador, 1 sem incidência). Foi usada como fonte primária **no lugar de mapear o art. 3º da LC 116
  inciso a inciso**: mapear sem a fonte seria inventar regra fiscal. A aba não cita os incisos serviço a serviço; o sistema cita o art. 3º e o §3º
  (serviço 20.01.01, nunca "águas marítimas") que a própria aba referencia.

### 2. `pAliq`: uma regra única e pura

`fiscal/services/aliquota_issqn.py::decidir_aliquota(opcao_simples, regime_apuracao, regime_especial, convenio_ativo, iss_retido)`:

| Prestador | Condição | `pAliq` | Regra |
|---|---|---|---|
| MEI | qualquer | proibido | E0600 |
| Qualquer | regime especial 1 a 6 | proibido | **E0604** (não está na tabela da issue; consta do Anexo VI) |
| Não optante | convênio ativo | proibido | E0617 |
| Não optante | convênio não ativo e `regEspTrib` 0 | obrigatório | E0619 |
| ME/EPP, `regApTribSN` 1 | convênio ativo, com retenção | obrigatório, mínimo 1,8% | E0621 |
| ME/EPP, `regApTribSN` 1 | convênio ativo, sem retenção | proibido | E0625 |
| ME/EPP, `regApTribSN` 1 | convênio não ativo, com retenção | obrigatório, mínimo 1,8% | E0628 |
| ME/EPP, `regApTribSN` 1 | convênio não ativo, sem retenção | proibido | E0631 |
| ME/EPP, `regApTribSN` 2 ou 3 | convênio ativo | proibido | E0635 |
| ME/EPP, `regApTribSN` 2 ou 3 | convênio não ativo | obrigatório | E0640 |
| Qualquer | alíquota acima de 5% | bloqueia | E0595 |

`aplicar_ao_valor` transforma a decisão no que vai na DPS: proibida → sem `pAliq` (mesmo que o serviço tenha alíquota); obrigatória →
a alíquota do cadastro do serviço, e **a emissão é bloqueada** com mensagem didática e o código da regra se ela faltar ou ficar abaixo do mínimo.

**Município de incidência** (`municipio_de_incidencia`): pela tabela do Anexo VI. Estabelecimento do prestador → município do emissor;
local da prestação → o **município da prestação da nota** (decisão 4); estabelecimento do tomador → município do tomador. Serviço que a
tabela não traz, ou caso que não dá para resolver (tomador sem município brasileiro, serviço "sem incidência"), usa a **regra geral**
(município do prestador) e **avisa na prévia**. Serviço do local da prestação **sem** município da prestação não segue: a emissão é bloqueada.

**Convênio ativo na competência** (`convenio_ativo_na_data`): aderente **e** data de ativação menor ou igual à competência (ativação no
próprio dia já vale). Aderente sem data de ativação conhecida vale como ativo. A consulta é por município: para o emissor usa-se a última
verificação da Fase 2 (sem rede); para os outros municípios, a consulta ao ambiente nacional **com o cache de 24 h** da empresa. Sem resposta
e sem valor guardado, a decisão fica **indeterminada e a emissão é bloqueada**, sem adivinhar.

**Quando decide**: a prévia mostra a decisão e o código da regra (`complementos.aliquota_issqn`); a solicitação da emissão bloqueia o que já
dá para decidir sem rede; o **envio** refaz a avaliação com o certificado aberto (consulta o convênio do outro município) e, se não puder
decidir, a nota **volta a rascunho** com a mensagem e nada vai à Sefin.

### 3. IBS/CBS decidido pela classificação do serviço

- `Servico.codigo_indicador_operacao` (cIndOp), sugerido pelo Anexo VIII (item da LC 116 + NBS). O sistema **nunca escolhe** quando o
  anexo indica mais de um INDOP; lista as opções. Validação: 6 dígitos e **E0902** (`cTribNac` 99.03 exige `02XXXX`); o CST deve ser o
  prefixo do `cClassTrib` (**E0959**). Avisos (não bloqueiam): `cIndOp` ou `cClassTrib` que o Anexo VIII não associa ao item e à NBS do serviço;
  tomador do exterior (o anexo indica outro INDOP para adquirente no exterior).
- Saem `ParametrosFiscais.ibs_cbs_informar` e `ibs_cbs_indicador_operacao` e `ModeloNfse.ibs_cbs_informar`. Fica o `indDest` padrão da empresa.
  **A migração não copia o `cIndOp` da empresa para os serviços** (o Anexo VIII é quem sugere); serviço cuja classificação exige o grupo e
  que não tem `cIndOp` **bloqueia a emissão**, pedindo para completar o cadastro.
- **Prioridade**: `cIndOp` nota > modelo > serviço; `indDest` nota > modelo > empresa. A origem de cada campo aparece na prévia.
- **Decisão automática** (`fiscal/services/nfse.py::_ibs_cbs`), na data de competência: sem `cClassTrib` no serviço → sem grupo; classificação
  que não consta, não vigora ou **não vale para NFS-e** → erro (E0958); `ind_gIBSCBS = 0` → sem grupo (E0859/E0961), com aviso se a nota ou
  o modelo tinham ajustado o `cIndOp`; `= 1` → exige NBS, CST e `cClassTrib` (E0322) e o `cIndOp` (E0860).
- A mesma avaliação roda **na solicitação e no envio, a partir do snapshot da nota**: um rascunho anterior à regra, para um serviço que
  agora exige o grupo, não segue sem `cIndOp`.

### 4. Município da prestação: um dado da nota (decisão do usuário, 2026-11-06)

Primeiro o plano mandava usar o município do emissor como local da prestação, com aviso. O usuário decidiu **criar o campo**:

- **Onde está**: na **nota** (`codigo_municipio_prestacao`, guardado em `complementos`, sem coluna nova), no **modelo de NFS-e**
  (`ModeloNfse.codigo_municipio_prestacao`, migração `agendamentos/0004`) e, portanto, no **rascunho**. Vazio = herda.
- **Prioridade** (`fiscal/services/local_prestacao.py`): **nota > modelo > município do emissor**. O padrão é o emissor **de agora**; nada
  é copiado para o modelo. O rascunho guarda o que a nota ajustou (`municipio_prestacao_nota`), o que o modelo definia
  (`municipio_prestacao_modelo`) e o resultado com a origem (`local_prestacao`), como no IBS/CBS.
- **Na DPS**: é o `cLocPrestacao` (antes, `gateway.py` gravava sempre o município do emissor). Vale para **todo** serviço.
- **Na regra da alíquota**: só pesa nos serviços cujo ISSQN é devido no **local da prestação** (aba MUN.INCID_INFO.SERV.): o convênio
  consultado, na data de competência, é o do município da prestação. Os serviços do estabelecimento do prestador (EP), do tomador (ET,
  17.05.01) e o 990101 **não mudam**: nesses o campo só consta da nota, e a prévia avisa quando ele difere do emissor.
- **Validação**: o código precisa ser de um município da tabela do IBGE (7 dígitos); só os dígitos valem. Rascunhos anteriores à
  correção não guardam nada e caem no município do emissor, o que a DPS sempre informou.
- **Conferência**: mostra o município da prestação com a origem (da nota, do modelo, padrão), e, na linha da alíquota, o município de
  incidência. Sem município (emissor não definido), o serviço do local da prestação é bloqueado com mensagem, nunca presumido.

## O que o Anexo VI não decide (tratado sem inventar regra; avisado ao Supervisor)

1. **Não optante, convênio não ativo, `regEspTrib` 9 ("outros")**: E0619 exige com `regEspTrib` 0 e E0604 proíbe de 1 a 6; o 9 fica sem regra.
   Tratado como **facultativo**: a alíquota vai se o serviço tiver, sem bloquear a falta.
2. **Regime especial 1 a 6 (E0604) junto de uma regra que exige a alíquota** (ME/EPP em E0621/E0628/E0640): o anexo não diz qual vence.
   Tratado como **conflito: a emissão é bloqueada** com a explicação (emitir pelo emissor oficial ou revisar os parâmetros).
3. **O que é "convênio ativo"**: a regra fala em município com situação "ATIVO" no Sistema Nacional; a consulta de parâmetros traz
   `aderenteAmbienteNacional` e `dataAtivacao`, e a `freedfe` registra que a semântica desses campos **não tem documentação oficial**. A leitura
   adotada (aderente e ativação até a competência) é a mesma que a Fase 2 já usava para liberar a emissão. **Hipótese a confirmar na produção restrita.**
4. **Grupo de IBS/CBS sem classificação no serviço**: não há regra no anexo que o torne obrigatório; a nota sai sem o grupo, com a explicação.
5. **Competência anterior a 2026-01-01**: a tabela da calculadora não informa vigência antes disso; a nota sai sem o grupo, com aviso.
6. **Local da prestação** diferente do município do emissor: resolvido pela decisão 4 (a nota passou a ter o município da prestação).
7. **Regras que ligam o `cIndOp` ao endereço do tomador e ao destinatário** (E0239, E0243, E0919): fora do escopo da issue; ficam como
   pendência (podem rejeitar notas de serviços cujo `cIndOp` indica o município do adquirente quando o tomador não tem endereço completo).
8. **Prestador com regime diferente na data de competência**: usa-se o regime dos parâmetros de agora.
9. **`tribISSQN` diferente de "tributável"** (imunidade, exportação, não incidência; E0602) e **benefício municipal** (E0612, `tpBM`): o
   sistema só emite serviço tributável e não envia benefício, então essas regras não se aplicam; a condição de benefício das E0621/E0625 é sempre satisfeita.

## Consequências e riscos

- **A tabela de classificação é de um piloto** e muda: regravar com `atualizar_classificacao_tributaria` quando a calculadora publicar nova
  versão. O `LEIAME` registra a versão da calculadora usada.
- **Quem tinha o `cIndOp` configurado na empresa o perde** (decisão do usuário): precisa preencher o `cIndOp` dos serviços cuja classificação exige o grupo.
- **Rascunhos antigos** de serviços que agora exigem o grupo são barrados na solicitação, com a mensagem de como corrigir.
- Os testes antigos de IBS/CBS usavam a classificação `200003`, que a tabela oficial **não aceita para NFS-e** (E0958): nunca teriam passado na Sefin.
- Falha de rede na consulta do convênio de **outro** município bloqueia aquela nota (nunca a de município do emissor, que usa a verificação gravada).

## Itens abertos

1. Confirmar na produção restrita: o convênio de verdade (campos `aderenteAmbienteNacional`/`dataAtivacao`), a aceitação do `cIndOp` sugerido e
   a classificação do piloto (roteiro em `docs/verificacao-issue-29.md`).
2. Regras E0239/E0243/E0919 (endereço do tomador e destinatário conforme o `cIndOp`).
3. `tribISSQN` não tributável (imunidade, exportação); benefício municipal.
4. Retenção de PIS/COFINS continua **bloqueada** (sem regra na tabela).
5. **Revalidar a classificação tributária antes da produção** (tabela do piloto), comparando com outra fonte oficial se a RFB publicar uma.
