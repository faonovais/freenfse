# ADR 0007 — Ajustes da issue #20: IBS/CBS por empresa, Emissor, troca para produção e municípios

- **Status:** aceita; **seção 1 (IBS/CBS) revogada pela issue #29** (ver o aviso abaixo)
- **Data:** 2026-10-31
- **Decisões relacionadas:** issues #14, #16, #18 e #20, [ADR 0003](0003-cadastros-e-configuracao-fiscal.md), [ADR 0004](0004-nucleo-fiscal.md), [ADR 0005](0005-documentos.md), [ADR 0006](0006-modelos-e-agendamentos.md)

> **Seção 1 (IBS/CBS) revogada pela issue #29** — [ADR 0010](0010-paliq-e-ibs-cbs-pela-regra-oficial.md) §3. A opção "informar o IBS/CBS" e o `cIndOp` padrão **deixam de ser da empresa**: o grupo vai ou não pela classificação tributária do serviço (`ind_gIBSCBS`, regras E0859/E0860) e o `cIndOp` é do **serviço** (sugerido pelo Anexo VIII), com ajuste da nota e do modelo (nota > modelo > serviço). Da empresa fica só o `indDest` padrão. O texto desta seção é mantido como registro da decisão de 31/10/2026. As seções 2 (Emissor), 3 (troca para produção) e 4 (municípios) seguem valendo.

## Contexto

Quatro ajustes decididos pelo usuário depois das fases 3 a 5, reunidos na issue #20:

1. a **opção pelo IBS/CBS e o indicador da operação** são da empresa, não do serviço nem do modelo de NFS-e;
2. o perfil **Emissor** precisa **ver** os parâmetros fiscais e os dados do certificado (somente leitura);
3. a **troca para produção** deve exigir certificado válido e convênio do município vigente, além das proteções que já existiam;
4. o arquivo de **municípios** deve ser conferido com a tabela oficial do IBGE.

## Decisões

### 1. IBS/CBS: padrão da empresa, que o modelo e a nota herdam e podem sobrescrever

**O que mudou.** `ParametrosFiscais` ganhou três campos: `ibs_cbs_informar` (a opção; padrão desligada), `ibs_cbs_indicador_operacao` (o `cIndOp`, 6 dígitos; obrigatório quando a opção está ligada) e `ibs_cbs_indicador_destinatario` (o `indDest`; padrão `0`, "o próprio tomador"). O **modelo de NFS-e** e a **nota** herdam esses três valores e podem sobrescrevê-los. O serviço continua só com a classificação (NBS, CST, `cClassTrib`).

**Quem manda: nota/rascunho > modelo > empresa, campo a campo** (`fiscal.services.nfse.resolver_ibs_cbs`). Cada um dos três campos (`informar`, `cIndOp`, `indDest`) vale pelo primeiro nível que o define; um nível só muda os campos que preenche e herda o resto. Exemplo: um modelo que fixa só o `cIndOp` herda da empresa a opção e o `indDest`.

| Nível | Como "define" um campo | Como "herda" (volta a herdar) |
|---|---|---|
| **Nota** (`ibs_cbs` da entrada) | `informar` (`true`/`false`), `codigo_indicador_operacao`, `indicador_destinatario` | omitir ou deixar vazio |
| **Modelo** (`ibs_cbs_informar`, `ibs_cbs_indicador_operacao`, `ibs_cbs_indicador_destinatario`) | valor preenchido | `null` ou vazio |
| **Empresa** (parâmetros fiscais) | sempre define os três | — |

Regras que completam a tabela: (1) indicar o `cIndOp` num nível, sem dizer se informa, vale como "informar"; (2) o `informar` falso de um nível mais forte vence o verdadeiro de um mais fraco e vice-versa; (3) o `cIndOp` guardado pela empresa vale para o modelo/nota mesmo com a opção da empresa desligada (a opção diz se informa por padrão, não apaga o valor); (4) sem classificação no serviço, um pedido de informar vindo da **nota ou do modelo** é **erro** (é um pedido explícito) e o vindo da **empresa** vira **aviso** ("complete o cadastro do serviço"), sem travar a emissão.

**Herdar não é copiar.** O modelo não guarda o valor da empresa: campo vazio vale o da empresa **de quando o rascunho é gerado**. Mudar o padrão da empresa muda os rascunhos **futuros** dos modelos que herdam; não muda os modelos com valor próprio, os rascunhos já criados nem as notas emitidas (testes). A API do modelo devolve o valor próprio, o herdado (a empresa de agora) e o efetivo com a origem de cada campo; as opções e a conferência do modelo trazem o padrão e a origem.

**A prévia mostra o que vai na DPS e de onde veio cada campo.** `POST /notas/previa/` devolve `ibs_cbs`: `na_dps`, `origens` (por campo: `nota`, `modelo` ou `empresa`), indicador, destinatário, NBS, CST, `cClassTrib` e, quando não vai, o `motivo` (que diz de quem foi a decisão). A tela exibe a linha "IBS/CBS na DPS" com a origem entre parênteses. Ao conferir um rascunho existente, a tela informa o id dele (`rascunho`) para a conferência valer também o que o modelo dele definia.

**Cópia (snapshot) e rascunho ajustável.** O rascunho grava em `complementos`, como o resto da nota: `ibs_cbs` (o grupo efetivo, com `origens`), `ibs_cbs_nota` (o que a **nota** sobrescreveu, para a tela reabrir fiel — inclusive "não informar") e `ibs_cbs_modelo` (o que o **modelo** definia quando o rascunho nasceu). Assim o rascunho gerado pelo agendamento leva o valor efetivo e **continua ajustável** antes da aprovação: a edição resolve de novo com o ajuste novo da nota, o que o modelo definia (guardado no rascunho, sem consultar o app de agendamentos) e a empresa **de agora**. Quem edita vê na conferência o valor e a origem antes de emitir; a emissão usa a cópia gravada, nunca o parâmetro vivo, para que o que foi conferido seja exatamente o que sai. Apagar o ajuste da nota ("voltar a herdar") devolve o campo ao modelo e, na falta dele, à empresa.

**Migração sem perda.** `fiscal.0004_ibs_cbs_por_empresa` só acrescenta três colunas com padrão (opção desligada, indicador vazio, `indDest` 0) e `agendamentos.0002_ibs_cbs_no_modelo` só acrescenta três colunas anuláveis: **os modelos existentes continuam "herda da empresa"**. Nada é apagado, renomeado nem convertido, e **nada é inferido** das notas antigas: elas mantêm o grupo que elas mesmas levavam, e o serviço mantém a classificação. Testes: as migrações são só `AddField`; dados de antes sobrevivem à ida e à volta.

**Hipóteses e dívida de teste.** (a) O `indDest` padrão da empresa é `0` ("o próprio tomador"), o valor que a tela já usava desde a Fase 3: quem não mexer não muda de comportamento. (b) O comportamento de IBS/CBS da Fase 3 **não tinha nenhum teste** (validação, aviso, mapeamento à DPS); esta issue o cobre, inclusive com o XML assinado da DPS. (c) Esta seção **revoga, para o modelo**, a regra da Fase 5 "IBS/CBS fora do modelo" (ADR 0006), por decisão do usuário registrada na issue #20.

#### O que é por empresa, por serviço ou por operação (NT 009)

Conferido contra o montador de DPS da biblioteca (`freedfe` 0.3.0) e o XML gerado:

| Campo do grupo `IBSCBS` | Natureza | Onde fica / estado |
|---|---|---|
| `finNFSe` | constante (0, NFS-e regular) | fixo na biblioteca |
| `cIndOp` | **da operação** (ver alerta) | padrão da **empresa**, sobrescrito pelo **modelo** (operação recorrente) e, pontualmente, pela **nota** |
| `indDest`, `dest` | da operação/nota | `indDest` com o mesmo caminho (empresa → modelo → nota; padrão 0); `dest` não enviado |
| `indFinal`, `tpOper`, `gRefNFSe`, `tpEnteGov` | da operação / do tomador | **não enviados** hoje |
| `valores/trib/CST` e `cClassTrib` | **do serviço** | cadastro do serviço (NT 009: direto em `valores/trib`; o `gIBSCBS` é da NT 004) |
| `cCredPres`, `gTribRegular`, `gDif` | do serviço/operação | **não enviados** hoje; sem suporte na API do sistema |
| `cNBS` (em `serv/cServ`) | **do serviço** | cadastro do serviço; obrigatória quando há o grupo (E0322) |

> **Alerta (registrado, sem regra inventada).** O `cIndOp` é, pelo leiaute, atributo da **operação**: o DANFSe da biblioteca o exibe como "Indicador de Operação / Município de Incidência", e a Sefin devolve a localidade de incidência (`cLocalidadeIncid`) calculada a partir dele. Um único padrão por empresa só é correto para quem pratica **um tipo de operação**. A decisão do usuário (empresa → modelo → nota) é exatamente o que mitiga o risco: **o modelo de NFS-e é o lugar natural para fixar o `cIndOp` de uma operação recorrente** (cada tipo de operação, o seu modelo) e a nota ajusta o caso isolado; a prévia deixa a origem visível. Um indicador **por serviço** como sobreposição continua **não decidido** (e, com o modelo, talvez desnecessário). A biblioteca **não traz a tabela de `cIndOp`**: o sistema valida só o formato (6 dígitos). Confirmar a tabela e o comportamento por tipo de serviço na produção restrita é pendência de homologação.

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

- **`cIndOp` por empresa pode estar errado para quem tem operações de naturezas diferentes** (alerta acima). Mitigação: um modelo por tipo de operação com o `cIndOp` próprio, ajuste pontual na nota e prévia com a origem. Risco residual até a homologação.
- **Rascunho antigo mantém o padrão de quando nasceu**: quem muda o padrão e emite um rascunho de ontem emite com o valor de ontem. É deliberado (o que se confere é o que sai); ao **corrigir** o rascunho, os campos que a nota não sobrescreveu são resolvidos de novo (modelo guardado no rascunho + empresa de agora) e a conferência mostra o resultado e a origem antes de emitir.
- **Mudar o modelo não altera rascunhos já gerados**, só os próximos: o rascunho guarda o que o modelo definia ao nascer.
- **A troca para produção faz uma chamada à Sefin**: se o ambiente nacional estiver fora do ar, a troca espera (mensagem clara; tentar de novo em minutos). Em compensação, ninguém passa para produção com convênio que não existe.
- **O Emissor passa a ver a configuração de e-mail e de Drive** (sem credenciais). Quem não quiser pode remover `config.consultar` daquele vínculo (`permissoes_removidas`).

## Itens abertos e decisões que não são desta issue

1. **Tabela de `cIndOp` e seu comportamento por tipo de serviço**: confirmar na produção restrita; avaliar indicador por serviço como sobreposição.
2. **Retenção de PIS/COFINS** (bloqueada) e **`pAliq` por regime** (hipótese): inalterados.
3. **Criptografia em repouso dos XMLs**: Fase 6 (issue #9).
4. **Resultado de convênio por ambiente** (evolução discutida acima).
5. **Auditoria da troca recusada**: exigiria nova ação de auditoria.
