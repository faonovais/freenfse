# ADR 0011 — Endereços do tomador e do destinatário pelo `cIndOp` (issue #33)

Status: aceito (implementado na issue #33). Fecha os itens abertos 2 e 7 do [ADR 0010](0010-paliq-e-ibs-cbs-pela-regra-oficial.md)
(regras E0239, E0243 e E0919). Decisão do usuário em 2026-11-07, com a leitura do Anexo VII fechada pelo Supervisor na mesma data.

## Contexto

O Anexo VI v1.04.01 da NT SE/CGNFS-e 009/2026 manda a Sefin **rejeitar a DPS** quando o prestador emite (`tpEmit = 1`), o grupo de IBS/CBS é
obrigatório (`ind_gIBSCBS = 1`) e o `cIndOp` indica que o município de incidência é o do endereço de uma pessoa que **não** é identificada por
CPF ou CNPJ com endereço nacional:

| Regra | Condição sobre o `cIndOp` e o `indDest` | Quem precisa de CPF/CNPJ e endereço nacional |
|---|---|---|
| E0239 | local do fornecimento = endereço do **tomador/adquirente** | o tomador |
| E0243 | local = endereço do **destinatário** e `indDest = 0` (o destinatário é o próprio tomador) | o tomador |
| E0919 | local = endereço do **destinatário** e `indDest = 1` (outra pessoa) | o destinatário (`dest/end/endNac`) |
| E0901 | `cIndOp` não suportado para prestação de serviços | — |

Antes desta issue o sistema não conhecia o local do fornecimento de cada indicador e **não sabia quem era o destinatário** quando `indDest = 1`
(a DPS ia sem o grupo `dest`): as notas dos serviços com `cIndOp` de endereço (100301, 100302 etc.) para tomador estrangeiro ou sem endereço
nacional seriam rejeitadas pela Sefin.

## Decisões

### 1. Fonte: Anexo VII, **somente a coluna estruturada** `NFSeLocIncidIBS`

O local do fornecimento de cada um dos 40 indicadores vem do **Anexo VII v1.03.00 (NT 009)**, aba `cIndOp Public`, publicado em
<https://www.gov.br/nfse> › Biblioteca › Documentação técnica › RTC. Foi baixado em 2026-11-07 e gravado por
`importar_anexos_rtc --anexo-vii` em `backend/fiscal/referencias/dados/indop_local_fornecimento.json` (origem, URL, data e SHA-256 no próprio
JSON e no `LEIAME.md`).

| Item | Valor |
|---|---|
| Arquivo | `anexovii-indop_ibscbs_v1-03-00-nt009.xlsx` |
| SHA-256 do arquivo oficial | `95f30a44ee94adeea57fb92f3a0337b1e62fdc106f393e73894087889be9e5aa` |
| SHA-256 do JSON gerado | `1c2d4b5cf040f175a78499b091325586f015acd7f8a5cfabece05e53465454b6` |
| Obtido em | 2026-11-07 |

A classificação sai **apenas** da coluna `NFSeLocIncidIBS`, não do texto livre da coluna "Local do fornecimento a ser identificado no DFe":

| Classe | Valor da coluna | Indicadores |
|---|---|---|
| `adquirente` (E0239) | Endereço do Tomador/Adquirente | 010106, 100101, 100301, 100501 |
| `destinatario` (E0243/E0919) | Endereço do Destinatário | 010103, 100102, 100201, 100302, 100401, 100502, 100601 |
| `outro` (nenhuma regra) | os demais valores (`-`, vazio, "Local da Prestação", "Localidade do Imóvel", "Estabelecimento do Prestador/Fornecedor" etc.) | os outros 29 |

Motivo: é o campo que o anexo marca para a NFS-e; interpretar o texto livre seria adivinhar regra fiscal. O comando **recusa a carga** se a coluna
trouxer um valor que o sistema não conhece e se um indicador classificado como adquirente/destinatário não for mencionado pelo próprio texto
dele (proteção contra planilha deslocada).

### 2. Casos em que o texto cita adquirente/destinatário e a coluna estruturada não

Seis indicadores têm a coluna estruturada **sem endereço de pessoa**, mas texto que cita um deles. Decisão (Supervisor + usuário): classificar
como `outro`, **sem bloquear**:

| Indicador | Coluna `NFSeLocIncidIBS` | Texto do local do fornecimento | Tratamento |
|---|---|---|---|
| 130201 | `-` | Local do estabelecimento principal do adquirente | **`outro`, com aviso não bloqueante** (abaixo) |
| 090102 | `-` | Local do domicílio principal do adquirente (matriz)… | `outro`, sem aviso (o Anexo VIII não o sugere a nenhum serviço) |
| 110201 | `-` | Local do estabelecimento principal do adquirente… | `outro`, sem aviso (idem) |
| 010201 | `-` | Domicílio principal do destinatário | `outro`, sem aviso (idem) |
| 010202 | `-` | Domicílio principal do destinatário | `outro`, sem aviso (idem) |
| 070101 | `Local da Prestação` | Endereço fornecido para entrega do bem | `outro`, sem aviso |

**Aviso do 130201** (transporte dutoviário de gás natural; é o único dos seis que o Anexo VIII sugere a algum serviço): na conferência da nota,
quando o tomador **não** tem CPF/CNPJ e endereço nacional, aparece *"O texto do Anexo VII indica o endereço do adquirente para este indicador;
confira se o tomador tem CPF/CNPJ e endereço nacional, para evitar a rejeição E0239."* Nunca bloqueia; some quando o tomador atende. **A
confirmar com a Sefin em produção restrita** (roteiro e checklist): se ela aplicar a E0239 a esse indicador, o aviso vira bloqueio com uma
linha em `LOCAL_NFSE`.

### 3. "Fora da tabela" bloqueia (E0901); `indNFSe` vazio não

Um `cIndOp` que **não consta das 40 linhas** do Anexo VII é recusado com a regra E0901 (`ibs_cbs`), na conferência, na solicitação e no envio. O
critério **não** é a marca `indNFSe = S`: 11 indicadores não a têm (010104, 010105, 010201, 010202, 090101, 090102, 110101, 110201, 120101,
130101, 130201), e o Anexo VIII usa 080101, 130101 e 130201, que não são `indNFSe = S`. Bloquear por essa marca barraria serviços que o próprio
anexo sugere. Todo `cIndOp` que o Anexo VIII cita consta do Anexo VII (teste).

### 4. Função pura e aplicação

`fiscal/services/regras_de_endereco.py::avaliar(exige_grupo, codigo_indicador, indicador_destinatario, tomador, destinatario)` devolve as
**pendências** (regra, campo da tela, mensagem didática) e os **avisos**. Sem banco e sem rede. Só vale com o grupo de IBS/CBS na DPS
(`tpEmit = 1` é o único caso deste sistema); sem o grupo nenhuma regra se aplica.

- **"CPF ou CNPJ"** = pessoa física ou jurídica **nacional**, com documento válido (dígitos verificadores); estrangeiro **não** serve, mesmo com NIF.
- **"Endereço nacional"** = logradouro, número, bairro, CEP de 8 dígitos e município com código IBGE de 7 dígitos, sem campos de endereço no
  exterior. É o que o cadastro de pessoas já exige para PF/PJ (um teste confere que o que o cadastro aceita atende à regra e o inverso). Que o
  código IBGE **exista** é garantido pelo cadastro ao gravar (a função pura não consulta a tabela de municípios).
- Integração: `preparar` (prévia e rascunho) e `avaliar_ibs_cbs_da_nota`, usada em `solicitar_emissao` e em `executar_emissao`. Os erros entram
  pelo campo da tela (`tomador`, `destinatario`, `ibs_cbs`) com o **código da regra** e o que corrigir; a execução volta a nota a rascunho **sem
  enviar nada** à Sefin. Mensagem do destinatário ausente: a que traz a regra E0919 substitui a genérica de "destinatário faltando".

### 5. Destinatário na nota (decisão do usuário, 2026-11-07)

Com `indDest = 1` a nota **informa o destinatário**:

- É uma `Pessoa` do cadastro, escolhida na **nota**, no **modelo** de NFS-e ou herdada, nesta ordem: **nota > modelo** (modelo vazio = não define;
  a nota ainda escolhe). O rascunho gerado por agendamento carrega o destinatário do modelo.
- **Obrigatória** com `indDest = 1` (e só então); com `indDest = 0`, ou sem o grupo, é **descartada** com aviso na conferência.
- Vai na nota como **snapshot** (cópia dos dados do cadastro no momento do rascunho), como o tomador, e mudar o cadastro depois não muda a nota.
- Na DPS vai o grupo `IBSCBS/dest` da `freedfe` (CNPJ/CPF/NIF/`cNaoNIF`, `xNome` de até 150 caracteres e `end/endNac{cMun,CEP}` ou `endExt`); a
  biblioteca já expõe o grupo completo, então não foi preciso contornar a API. Um teste confere o XML **assinado**: `dest` presente com
  `indDest = 1` e ausente com `indDest = 0`.
- Persistência: `ModeloNfse.destinatario` (FK para `Pessoa`, `SET_NULL`), migração `agendamentos/0005`; a nota guarda `destinatario`,
  `destinatario_nota` e `destinatario_modelo` em `complementos` (a tela reabre fiel, como o IBS/CBS e o município da prestação).
- Rascunhos anteriores a esta issue com `indDest = 1` e sem destinatário são **barrados na solicitação**, com a mensagem de como corrigir.

## Consequências e riscos

- Notas de serviços com `cIndOp` de endereço (100301 e semelhantes) para **tomador estrangeiro** passam a ser bloqueadas com E0239. É o
  comportamento da Sefin; a saída é o indicador equivalente para adquirente no exterior (o Anexo VIII indica, por exemplo, 100302) ou outro tomador.
- **A leitura do Anexo VII é por um campo estruturado**: se a Sefin publicar nova versão, regravar com `importar_anexos_rtc --anexo-vii` e conferir
  o diff do JSON e do `LEIAME` (a carga falha em valor desconhecido).
- O aviso do 130201 é uma **hipótese a confirmar**: a Sefin pode aplicar ou não a E0239 a esse indicador.
- Não há consulta de rede nem de banco na regra: o código IBGE de cadastros antigos gravados sem passar pela validação não é conferido aqui.
- Seguem fora desta issue: `tribISSQN` não tributável, benefício municipal e PIS/COFINS (continua **bloqueado**).

## Itens abertos

1. Confirmar com a Sefin, em produção restrita, o comportamento do **130201** (aviso hoje) e se alguma outra linha do Anexo VII com texto de adquirente/
   destinatário sem a coluna estruturada gera E0239/E0243/E0919.
2. Revalidar o Anexo VII quando a NT publicar nova versão.
