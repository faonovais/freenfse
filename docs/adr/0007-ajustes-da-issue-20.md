# ADR 0007 — Ajustes da issue #20: IBS/CBS por empresa, Emissor, troca para produção e municípios

- **Status:** aceita
- **Data:** 2026-10-31
- **Decisões relacionadas:** issues #14, #16, #18 e #20, [ADR 0003](0003-cadastros-e-configuracao-fiscal.md), [ADR 0004](0004-nucleo-fiscal.md), [ADR 0005](0005-documentos.md), [ADR 0006](0006-modelos-e-agendamentos.md)

## Contexto

Quatro ajustes decididos pelo usuário depois das fases 3 a 5, reunidos na issue #20:

1. a **opção pelo IBS/CBS e o indicador da operação** são da empresa, não do serviço nem do modelo de NFS-e;
2. o perfil **Emissor** precisa **ver** os parâmetros fiscais e os dados do certificado (somente leitura);
3. a **troca para produção** deve exigir certificado válido e convênio do município vigente, além das proteções que já existiam;
4. o arquivo de **municípios** deve ser conferido com a tabela oficial do IBGE.

## Decisões

### 1. IBS/CBS por empresa

**O que mudou.** `ParametrosFiscais` ganhou `ibs_cbs_informar` (a opção; padrão desligada) e `ibs_cbs_indicador_operacao` (o `cIndOp` padrão, 6 dígitos; obrigatório quando a opção está ligada). A nota **herda** esse padrão no momento em que nasce e pode **ajustá-lo pontualmente**. O serviço continua com a classificação (NBS, CST, `cClassTrib`).

**Quem manda, nesta ordem** (`fiscal.services.nfse._ibs_cbs`):

| Entrada da nota (`ibs_cbs`) | Padrão da empresa | Resultado |
|---|---|---|
| `{informar: false}` | qualquer | sem o grupo (escolha explícita, vale para esta nota) |
| `codigo_indicador_operacao` preenchido | qualquer | grupo com o indicador **da nota** (`origem: nota`) |
| ausente / só `indicador_destinatario` | ligado e com indicador | grupo com o indicador **da empresa** (`origem: empresa`) |
| `{informar: true}` | desligado | erro didático: informe o indicador na nota ou cadastre o padrão |
| ausente | desligado | sem o grupo |

Em qualquer linha que gere o grupo, o serviço precisa ter NBS, CST e `cClassTrib`. Sem classificação: ajuste explícito da nota é **erro** (como na Fase 3); padrão da empresa vira **aviso** ("complete o cadastro do serviço") e a nota sai sem o grupo. Aviso e não bloqueio porque um serviço realmente sem classificação não deve travar a emissão; quem não quer o aviso completa o cadastro ou desliga a opção.

**A prévia mostra o que vai na DPS.** `POST /notas/previa/` devolve `ibs_cbs`: `na_dps`, `origem`, indicador, destinatário, NBS, CST, `cClassTrib` e, quando não vai, o `motivo`. A tela exibe isso na linha "IBS/CBS na DPS". `GET /notas/prontidao/` devolve o padrão da empresa para a tela pré-preencher a dica.

**Cópia (snapshot).** O grupo resolvido é gravado em `complementos.ibs_cbs` (com `origem`) quando o rascunho nasce, como o resto da nota. Mudar o padrão da empresa depois **não altera** rascunhos já criados (nem os gerados por agendamento); salvar o rascunho de novo refaz a cópia. A emissão usa a cópia, nunca o parâmetro atual, para que o que foi conferido na prévia seja exatamente o que sai. O modelo de NFS-e continua sem campo de IBS/CBS e o rascunho dele herda o padrão da empresa (teste).

**Migração sem perda.** `0004_ibs_cbs_por_empresa` só acrescenta duas colunas com padrão (opção desligada, indicador vazio): não apaga, renomeia nem converte nada, e **não infere** o padrão a partir das notas antigas. Notas existentes mantêm o grupo que elas mesmas levavam, e o serviço mantém a classificação. Testes: a migração é apenas `AddField`; os dados de antes (parâmetros, nota com `ibs_cbs`, serviço classificado) sobrevivem à ida e à volta.

**Hipóteses e dívida de teste.** (a) O padrão do destinatário (`indDest`) fica **por nota**, com valor `0` ("o próprio tomador") quando não informado — é o padrão da tela desde a Fase 3. (b) O comportamento de IBS/CBS da Fase 3 **não tinha nenhum teste** (validação, aviso, mapeamento à DPS); esta issue o cobre, inclusive com o XML assinado da DPS.

#### O que é por empresa, por serviço ou por operação (NT 009)

Conferido contra o montador de DPS da biblioteca (`freedfe` 0.3.0) e o XML gerado:

| Campo do grupo `IBSCBS` | Natureza | Onde fica / estado |
|---|---|---|
| `finNFSe` | constante (0, NFS-e regular) | fixo na biblioteca |
| `cIndOp` | **da operação** (ver alerta) | padrão da **empresa** + ajuste **pontual** na nota |
| `indDest`, `dest` | da operação/nota | `indDest` por nota (padrão 0); `dest` não enviado |
| `indFinal`, `tpOper`, `gRefNFSe`, `tpEnteGov` | da operação / do tomador | **não enviados** hoje |
| `valores/trib/CST` e `cClassTrib` | **do serviço** | cadastro do serviço (NT 009: direto em `valores/trib`; o `gIBSCBS` é da NT 004) |
| `cCredPres`, `gTribRegular`, `gDif` | do serviço/operação | **não enviados** hoje; sem suporte na API do sistema |
| `cNBS` (em `serv/cServ`) | **do serviço** | cadastro do serviço; obrigatória quando há o grupo (E0322) |

> **Alerta (registrado, sem regra inventada).** O `cIndOp` é, pelo leiaute, atributo da **operação**: o DANFSe da biblioteca o exibe como "Indicador de Operação / Município de Incidência", e a Sefin devolve a localidade de incidência (`cLocalidadeIncid`) calculada a partir dele. Um único padrão por empresa só é correto para quem pratica **um tipo de operação**; uma empresa com serviços de naturezas diferentes precisará do **ajuste pontual** em cada nota (ou, no futuro, de um indicador por serviço como sobreposição — **não decidido aqui**). A decisão do usuário (padrão da empresa + ajuste pontual) é mantida e é exatamente o que mitiga o risco; a prévia deixa a origem visível. A biblioteca **não traz a tabela de `cIndOp`**: o sistema valida só o formato (6 dígitos). Confirmar a tabela e o comportamento por tipo de serviço na produção restrita é pendência de homologação.

### 2. Perfil Emissor com `config.consultar`

`config.consultar` passou a ser do Emissor (catálogo em código, `core/permissoes.py`; sem migração de dados). Ele lê os parâmetros fiscais e os metadados do certificado (titular, CNPJ, validade); **nunca** o `.pfx` nem a senha. Continua sem `config.editar`: não altera nada, não envia nem remove certificado, não verifica convênio e não troca de ambiente.

**Efeito colateral aceito:** a mesma permissão libera ao Emissor a **leitura** da configuração de e-mail e de Drive — que só devolve se há credencial (`credenciais_configuradas`), nunca o valor — e a prévia do caminho do Drive, que só lê. Os testes cobrem que nenhuma resposta traz segredo. Isso substitui a consequência registrada no ADR 0003 e no ADR 0005 (a rota `identidade`, aberta a qualquer vinculado, continua como estava).

### 3. Troca para produção

Além de `config.editar`, da confirmação (`confirmar_producao`, que a tela pede digitando `PRODUÇÃO`) e da auditoria, a troca exige:

1. **certificado A1 enviado, em vigor** (nem vencido nem "ainda não vale") **e com o CNPJ conferido**: o da empresa, ou o de outro estabelecimento da mesma raiz **só se autorizado** no envio (`mesma_raiz_autorizada`). A regra de CNPJ é a mesma do envio do certificado (`divergencia_de_cnpj`);
2. **município emissor** informado;
3. **convênio do município vigente em produção**, consultado **na hora da troca**: o município aderiu e a data de ativação (quando informada) já chegou. Resposta indefinida, data ilegível ou consulta que falha **não liberam** (na dúvida, a troca não é feita).

**Ordem e atomicidade.** (1) pendências locais (itens 1 e 2) → (2) confirmação → (3) consulta ao vivo do convênio em produção → (4) gravação. Cada recusa devolve `producao_nao_liberada` com a **lista numerada** do que falta e a tela para resolver cada item (`pendencias`), e **não grava nada** (ambiente e convênio guardado ficam como estavam). A consulta de rede roda **fora** da transação. Passando, o resultado da consulta é gravado junto com a troca: a empresa nasce em produção com o convênio válido para o ambiente e o município atuais (antes, a troca deixava a emissão bloqueada até uma nova verificação).

**Por que consultar na hora, e não exigir uma verificação prévia.** O convênio é por ambiente e o sistema guarda **um** resultado por empresa. Exigir "verificado em produção" antes da troca obrigaria a verificar em produção estando em produção restrita, o que apagaria o resultado da restrita e bloquearia a emissão de teste. Consultar na troca evita reestruturar o armazenamento por ambiente. **Alternativa não adotada:** guardar um resultado por ambiente (permitiria "pré-verificar" produção e mostrar as duas situações na tela); fica como evolução se o fluxo pedir.

**A tela** tenta o `PATCH` sem confirmação primeiro: se a produção não está liberada, mostra a lista do que falta **antes** de pedir que se digite `PRODUÇÃO`.

**Correção vizinha.** `verificar_convenio` gravava a linha inteira dos parâmetros após a chamada de rede e podia desfazer uma troca de ambiente feita por outra pessoa no meio. Agora grava só os campos do convênio (teste com a alteração concorrente simulada).

**Não feito:** a recusa não gera registro de auditoria próprio (a ação nova exigiria migração no `core`); fica no log de aplicação. Tolerância de tempo da consulta é a da biblioteca.

### 4. Tabela de municípios (IBGE)

O `core/dados/municipios_ibge.csv` foi conferido com a tabela **oficial** do IBGE (DTB 2025, `geoftp.ibge.gov.br`, data-base 31/12/2025): 5.571 municípios oficiais, 5.540 iguais, **31 com o nome diferente (corrigidos)**, nenhum faltante, nenhum a mais, nenhum código nem UF divergente. Origem, data, SHA-256 do arquivo e da planilha e a tabela das 31 correções estão em `backend/core/dados/LEIAME.md`. O comando `manage.py comparar_municipios_ibge <arquivo> [--gravar]` repete a conferência (sem rede: o arquivo é baixado antes) e o leitor valida a planilha (código de 7 dígitos, UF coerente com o código, sem repetidos, XML sem entidades externas). Se o IBGE não puder ser acessado, **não se usa outra fonte**: a conferência fica como pendência.

## Consequências e riscos

- **`cIndOp` por empresa pode estar errado para quem tem operações de naturezas diferentes** (alerta acima). Mitigação: ajuste pontual e prévia com a origem. Risco residual até a homologação.
- **Rascunho antigo mantém o padrão de quando nasceu**: quem muda o padrão e emite um rascunho de ontem emite com o valor de ontem. É deliberado (o que se confere é o que sai); a tela de correção do rascunho refaz a cópia ao salvar.
- **A troca para produção faz uma chamada à Sefin**: se o ambiente nacional estiver fora do ar, a troca espera (mensagem clara; tentar de novo em minutos). Em compensação, ninguém passa para produção com convênio que não existe.
- **O Emissor passa a ver a configuração de e-mail e de Drive** (sem credenciais). Quem não quiser pode remover `config.consultar` daquele vínculo (`permissoes_removidas`).

## Itens abertos e decisões que não são desta issue

1. **Tabela de `cIndOp` e seu comportamento por tipo de serviço**: confirmar na produção restrita; avaliar indicador por serviço como sobreposição.
2. **Retenção de PIS/COFINS** (bloqueada) e **`pAliq` por regime** (hipótese): inalterados.
3. **Criptografia em repouso dos XMLs**: Fase 6 (issue #9).
4. **Resultado de convênio por ambiente** (evolução discutida acima).
5. **Auditoria da troca recusada**: exigiria nova ação de auditoria.
