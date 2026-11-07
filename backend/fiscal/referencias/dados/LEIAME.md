# Tabelas oficiais da NFS-e (NT 009) e da calculadora do IBS/CBS

Dados **públicos e oficiais** que o sistema consulta para decidir o que vai na DPS (issue #29). Nenhum
foi digitado à mão: cada arquivo é regravado por um comando a partir da fonte, e este documento
registra a origem, a data e o SHA-256. Os arquivos são lidos por `fiscal/referencias/` (sem rede,
sem banco).

| Arquivo | Para quê | Fonte | Comando |
|---|---|---|---|
| `localidade_incidencia.json` | Onde incide o ISSQN de cada serviço (município do prestador, local da prestação ou município do tomador): decide **qual convênio** vale para o `pAliq` | Anexo VI v1.04.01, aba `MUN.INCID_INFO.SERV.` | `importar_anexos_rtc` |
| `correlacao_indop.json` | Item da LC 116 + NBS → indicador da operação (`cIndOp`) → `cClassTrib`; sugere o `cIndOp` do serviço | Anexo VIII v01.02.00 (2026-10-26) | `importar_anexos_rtc` |
| `indop_local_fornecimento.json` | Onde fica o **local do fornecimento** de cada um dos 40 indicadores da operação: endereço do **adquirente/tomador**, do **destinatário** ou outro. Alimenta as regras E0239, E0243 e E0919 (issue #33) | Anexo VII v1.03.00 (NT 009), aba `cIndOp Public`, coluna `NFSeLocIncidIBS` | `importar_anexos_rtc --anexo-vii` |
| `classificacao_tributaria.json` | Classificação tributária (`cClassTrib`) com vigência, se vale para NFS-e e se **exige o grupo de IBS/CBS** (`ind_gIBSCBS`) | Dados abertos da calculadora do IBS/CBS (RFB/CGIBS) | `atualizar_classificacao_tributaria` |

Obtidos em **2026-11-04** (horário de Brasília), exceto o Anexo VII (2026-11-07).

## Anexos VI e VIII (NT SE/CGNFS-e 009/2026)

Publicados em <https://www.gov.br/nfse> › Biblioteca › Documentação técnica › RTC
(`https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/rtc/`).

| Arquivo oficial | SHA-256 do arquivo baixado |
|---|---|
| `anexovi-leiautesrn_rtc_ibscbs-v1-04-01-nt009.xlsx` | `103a150dd6f56ec8edcaa3a453b59a1b0e096d7cd5025d7bd06a387f141ddf39` |
| `anexo_viii-tabela-correlacao-v01-02-00-20261026.xlsx` | `12cc80bc92687856b47e961b98cdbaa3f8cae568c099b3ef71994e73482ac7d0` |

O plano da issue citava o Anexo VIII v1.01.00; o portal já publica a **v01.02.00** (2026-10-26), que é a
usada. Regravar: baixe os dois `.xlsx` e rode

```bash
python manage.py importar_anexos_rtc --anexo-vi <anexo VI>.xlsx --anexo-viii <anexo VIII>.xlsx --obtido-em AAAA-MM-DD
```

O comando **recusa** a carga se a planilha tiver forma inesperada (serviço com mais de uma localidade
marcada, item fora do formato, tabelas pequenas demais): é melhor falhar do que gravar uma regra
adivinhada. O Anexo VIII usa células mescladas; o leitor (`xlsx.py`) as expande.

## Anexo VII (NT SE/CGNFS-e 009/2026) — local do fornecimento do `cIndOp`

Obtido em **2026-11-07**, no mesmo endereço (`.../rtc/`):

| Arquivo oficial | SHA-256 do arquivo baixado |
|---|---|
| `anexovii-indop_ibscbs_v1-03-00-nt009.xlsx` | `95f30a44ee94adeea57fb92f3a0337b1e62fdc106f393e73894087889be9e5aa` |

```bash
python manage.py importar_anexos_rtc --anexo-vii <anexo VII>.xlsx --obtido-em AAAA-MM-DD
```

A classificação sai **somente da coluna estruturada `NFSeLocIncidIBS`** da aba `cIndOp Public`
(decisão da issue #33, [ADR 0011](../../../docs/adr/0011-enderecos-do-tomador-e-do-destinatario-pelo-cindop.md)):

| Classe | Valor da coluna | Indicadores | Regras |
|---|---|---|---|
| `adquirente` | Endereço do Tomador/Adquirente | 010106, 100101, 100301, 100501 | E0239 |
| `destinatario` | Endereço do Destinatário | 010103, 100102, 100201, 100302, 100401, 100502, 100601 | E0243 / E0919 |
| `outro` | os demais valores, `-` ou vazio | os outros 29 | nenhuma |

O texto livre do anexo (`Local do fornecimento a ser identificado no DFe`) **não classifica**. Seis indicadores
têm texto que cita adquirente ou destinatário e coluna estruturada sem endereço (070101, 010201, 010202,
090102, 110201, 130201); o ADR 0011 registra o caso a caso. Só o **130201** (transporte dutoviário de gás
natural) recebe um **aviso não bloqueante** na conferência, porque é o único que o Anexo VIII sugere a algum
serviço. O comando recusa a carga se a coluna trouxer um valor que o sistema não conhece, ou se uma classificação
não for mencionada pelo texto do próprio indicador.

### Localidade de incidência (Anexo VI)

| Regra | Serviços | Significado |
|---|---|---|
| `EP` | 277 | Estabelecimento do prestador (regra geral do caput do art. 3º da LC 116/2003) |
| `LP` | 58 | Local da prestação (exceções do art. 3º; inclui 20.01.01, que nunca é "águas marítimas", §3º) |
| `ET` | 1 | Estabelecimento do tomador (17.05.01, fornecimento de mão de obra) |
| `SEM_INCIDENCIA` | 1 | 99.01.01, serviço sem incidência de ISSQN e ICMS |

A aba não cita os incisos do art. 3º serviço a serviço; o sistema usa a classificação **da própria
tabela oficial** e não mapeia incisos à mão (mapear sem a fonte seria inventar regra fiscal).

### Anexo VIII

208 itens da LC 116 (os códigos especiais do grupo 99 aparecem pelo código completo, como `99.03.01`) e
997 pares item × NBS. Um mesmo par pode ter mais de um INDOP; nesse caso o sistema lista as opções e
não escolhe sozinho. A aba `REGRA OP NÃO ONE_EXT` traz o INDOP equivalente para adquirente no exterior.

## Classificação tributária (calculadora do IBS/CBS)

As regras E0859, E0860, E0958, E0960 e E0961 do Anexo VI mandam consultar a calculadora para saber se a
classificação do serviço exige o grupo de IBS/CBS. A URL citada no anexo é um endereço interno do
Serpro; o **mesmo caminho é público** no piloto oficial da RFB/CGIBS:

`https://piloto-cbs.tributos.gov.br/servico/calculadora-consumo/api/calculadora/dados-abertos/classificacoes-tributarias/cbs-ibs`

| Item | Valor |
|---|---|
| Versão da calculadora | aplicativo `1.6.2-a39944eb`, base `V0066` (2026-10-28), ambiente `apr` |
| Período pesquisado | 2026-01-01 a 2033-12-31 |
| Classificações | 173 (170 vigentes hoje + 3 encerradas) |
| Valem para NFS-e | 73: **43 exigem** o grupo IBS/CBS e 30 não |
| Encerradas | 220001, 220002, 220003 (só vigoram em 2026-01-01; nenhuma vale para NFS-e) |
| Listas consultadas | 101 datas; o SHA-256 de cada resposta está no campo `origem.sha256_das_listas` do arquivo |

A fonte **não informa o início nem o fim de vigência**: só devolve a lista das classificações vigentes numa
data. O comando amostra o período (o dia 1º de cada mês), descobre onde a lista muda e refina por busca
binária até o dia exato. Recusa a carga se uma classificação sair e voltar a vigorar, ou se o indicador
de NFS-e mudar dentro da vigência. **Antes de 2026-01-01 a tabela não informa vigência.**

```bash
python manage.py atualizar_classificacao_tributaria   # usa a rede; leva alguns minutos
```

Cuidado com a fonte: sob rajada, o firewall dela responde **HTTP 200 com uma página HTML "Request
Rejected"**. O comando valida cada resposta como JSON, espaça as chamadas, tenta de novo e nunca grava
resposta inválida. É um ambiente de **piloto**; confirme a classificação na produção restrita da Sefin
(roteiro de verificação da issue #29).

## SHA-256 dos arquivos deste diretório

| Arquivo | SHA-256 |
|---|---|
| `localidade_incidencia.json` | `68ade5da910d09d45d04887c847297ac0a50aebcd3ae07d9a638ede8cba978d1` |
| `correlacao_indop.json` | `a80780e3e3502a8c65be4e8769adbe006ccde4ab2c4a7738ebe7f07ed840c497` |
| `indop_local_fornecimento.json` | `1c2d4b5cf040f175a78499b091325586f015acd7f8a5cfabece05e53465454b6` |
| `classificacao_tributaria.json` | `3c667289bfec6a975e3054f2cc12fcf1db277d6aea5285172ded2c5614391604` |
