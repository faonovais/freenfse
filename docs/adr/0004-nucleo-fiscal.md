# ADR 0004 — Núcleo fiscal: emissão, consulta, cancelamento e substituição (Fase 3)

- **Status:** aceita
- **Data:** 2026-10-30
- **Decisões relacionadas:** D4 (multiempresa isolado), D22 (permissões), `docs/analise-requisitos.md` §1.5, §2.1–§2.4 e §5, [ADR 0003](0003-cadastros-e-configuracao-fiscal.md)

## Contexto

A Fase 3 é a que pode **emitir uma nota duplicada ou com número repetido**. O critério de projeto foi: nenhuma falha de rede, queda de processo ou clique duplo pode gerar uma segunda nota; e, quando não for possível saber o que a Sefin fez, o sistema **pergunta** a ela, nunca reenvia por conta própria. A `freedfe` já implementa a máquina de estados e a reconciliação; a aplicação fornece a persistência que ela exige e a camada de negócio por cima.

## Decisões

### 1. Persistência da freedfe em PostgreSQL, por schema (`fiscal/persistencia/`)

Todas as tabelas vivem no schema de cada empresa; nenhuma consulta enxerga outra empresa (teste dedicado por peça).

| Contrato da freedfe | Implementação | Observação |
|---|---|---|
| `EstadoEmissao` | `EstadoEmissaoPostgres` + `EmissaoDps`, `SerieDps` | passa por inteiro na suíte de contrato da própria biblioteca |
| `Trava` | `TravaPostgres` | advisory lock **de sessão**, conexão dedicada |
| `ArmazenamentoEvidencias` | `ArmazenamentoEvidenciasPostgres` + `EvidenciaFiscal` | nunca sobrescreve; hash conferido na leitura |
| `RepositorioDocumentos` | `RepositorioDocumentosPostgres` + `DocumentoFiscal`, `EventoFiscal` | XML original e SHA-256 conferido ao ler |
| `EstadoSequenciaNsu` | `EstadoSequenciaNsuPostgres` | pronto para o ADN (fase futura) |
| `CacheParametros` | `CacheParametrosPostgres` | TTL de 24 h; sem rede usa o valor vencido |
| `Auditoria` | `AuditoriaPostgres` + `AuditoriaFiscal` | descarta binário e corta texto longo: **nunca XML** |

**Numeração.** `reservar_proximo` roda numa transação que trava (`SELECT ... FOR UPDATE`) a linha da série em `SerieDps` e só então calcula `max(numero)+1`. Escolhi a **linha-cadeado** em vez de travar as linhas de `EmissaoDps` porque, numa série vazia, não há linha para travar; e em vez de `pg_advisory_xact_lock` porque a linha é visível, auditável e some junto com o schema. Como defesa em profundidade há `UNIQUE (emitente, serie, numero)`: se alguém remover o cadeado, a segunda gravação **falha em vez de duplicar**. Lacunas só nascem de reserva descartada com número posterior já reservado, o que a trava de emissão impede.

**Trava de emissão.** A trava dura todo o `POST` à Sefin (até `timeout_emissao`, 60 s). Uma trava de transação obrigaria a manter uma transação aberta durante a chamada HTTP, e o estado `ENVIADA`, gravado **antes** do envio, não estaria confirmado se o processo caísse. Por isso: `pg_try_advisory_lock` de sessão numa **conexão dedicada** (cópia da conexão do Django, em autocommit), em laço com prazo (60 s por tentativa; o Celery reagenda a cada 10 s, até 30 vezes). A chave é `blake2b("freenfse:<schema>:<recurso>")`: empresas diferentes nunca disputam. Se o processo morre, o PostgreSQL encerra a sessão e a trava cai na hora (não há trava "abandonada" para expirar). Se a **conexão** cair no meio do envio, a trava também cai sem aviso; a proteção, então, é o `ENVIADA` já confirmado e a regra "consultar antes de reenviar". A trava recusa rodar dentro de uma transação aberta (exceto nos testes).

- **Granularidade.** A freedfe pede a trava com o recurso `emissao_nfse` (um por empresa), não por série. Fica **mais restritivo que o pedido** ("uma por vez por empresa e série"): uma emissão por vez por empresa. Para o volume típico do agronegócio é aceitável; o custo é que um `POST` lento (até 60 s) segura as demais emissões da empresa.

### 2. Domínio: `Nfse` separada do registro da biblioteca

`EmissaoDps` é o livro-razão técnico da biblioteca (um registro por DPS); `Nfse` é o que o usuário vê. A ligação é gravada **na própria reserva** do número (`EmissaoDps.nfse`), então nunca existe DPS sem dona, mesmo se o processo cair logo depois.

- **Snapshot.** Tomador, serviço (a versão vigente na competência), valores e totais são **copiados** para a nota ao criar o rascunho. Editar o cadastro depois não altera a nota (teste). A nota guarda também o leiaute usado, o ambiente, o XML da DPS enviada, o XML da NFS-e e o SHA-256.
- **Duplicação consciente.** O XML da NFS-e existe em `Nfse.xml_nfse` e em `DocumentoFiscal.xml`. Os dois são gravados na mesma operação e um teste confere que os hashes coincidem; a cópia em `Nfse` evita acoplar a tela e o download ao formato interno da biblioteca.
- **XML em claro no banco**, com hash. Contém dados pessoais do tomador (LGPD); a proteção de repouso é do banco e dos backups, não da aplicação. Fica registrado como risco a tratar na implantação.

### 3. Máquina de estados (`fiscal/services/nfse_estados.py`)

```
rascunho → enviando → autorizada → cancelada | substituída
                 ↘ rejeitada → enviando (reenvio com o MESMO número)
                 ↘ incerta   → autorizada | enviando (só pela retomada, que consulta antes)
                 ↘ rascunho  (a DPS foi recusada localmente; nada chegou à Sefin)
```

A situação só muda por `transicionar()`, que relê a linha com `FOR UPDATE` (vale o estado do **banco**, não o da instância), confere a tabela e grava `TransicaoNfse`. `Nfse.save()` recusa alterar `situacao` por atribuição direta. Toda transição fora da tabela é testada (matriz completa).

### 4. Resultado incerto: nunca reenviar sem consultar

- Timeout e 5xx → `incerta`. A única ação automática é **consultar** (HEAD/GET na Sefin): rotina periódica a cada 5 min (`reconciliar_notas_incertas`), que também resolve notas presas em `enviando` há mais de 10 min (processo que caiu): o registro de emissões, confirmado antes do envio, diz o que houve.
- "Tentar enviar de novo" reaproveita o **mesmo número e o mesmo Id**; a biblioteca consulta a Sefin antes (e o E0014 vira reconciliação). Nenhum número é gasto.
- Enquanto há nota `enviada`/`incerta` numa série, **a numeração automática dessa série é bloqueada** (regra da biblioteca, reforçada na solicitação com mensagem clara). Custo operacional: uma nota incerta pausa as emissões novas da série até ser resolvida; a conferência automática e o botão "Conferir agora" existem para encurtar isso.
- A tarefa Celery usa `acks_late` e é idempotente: reentrega não reenvia (nota que não está `enviando` é ignorada; nota com DPS no registro passa pela conferência).
- `reconciliar(descartar_nao_localizada=True)` da biblioteca **não** é exposto: descartar uma DPS que a Sefin ainda esteja processando permitiria duplicar.

### 5. Leiaute

A biblioteca escolhe pela data de **recebimento** (Brasília): produção usa a NT 004 até 30/11/2026 e a NT 009 a partir de 01/12/2026; produção restrita usa sempre a NT 009. Para **gravar o leiaute realmente usado**, o gateway calcula com a mesma regra pública (`VersaoLeiaute.selecionar`) e o passa explicitamente a `emitir`. Há testes na virada (`2026-12-01 02:59:59Z` ainda é NT 004 porque em Brasília é 30/11 23:59:59) e que o XML enviado muda de fato (ordem de `cNBS`/`xDescServ`, `vDedRed` × `vAjusteBC`).

### 6. Cancelamento e substituição

- **Cancelamento:** motivo (1, 2 ou 9) e justificativa (15 a 255). Síncrono na requisição, para o usuário ver a recusa na hora; a nota só vira `cancelada` **depois que o evento aparece** nos eventos da Sefin. Recusas (prazo, regra do município, E0840) viram mensagem didática; resposta perdida vira "continua autorizada, consulte a nota". O pedido de **análise fiscal** ao município não existe na API pública da biblioteca: a mensagem orienta procurar a prefeitura, e se ela deferir, o evento chega pela consulta. Permissão `nfse.cancelar`; auditado, inclusive a recusa.
- **Substituição:** "emitir nota substituta a partir desta" cria um rascunho com os mesmos dados (`subst`: `chSubstda`, motivo 01–05 ou 99 com texto de 15 a 255). A original só vira `substituída` quando a Sefin registra o evento 105102 (se não registrar na hora, a rotina periódica confirma depois). Permissão `nfse.substituir`, exigida também para emitir a substituta.

### 7. Cálculo e DPS

- `Decimal` com arredondamento "meio para cima"; ISS sobre a base (valor − desconto incondicionado − dedução); retenções de IR, CSLL e INSS sobre a mesma base; ISS retido reduz o líquido. A regra de arredondamento de cada prefeitura pode divergir; se divergir, a Sefin devolve a rejeição e a regra muda num lugar só (`calculo.py`).
- **Retenção de PIS/COFINS no serviço bloqueia a emissão** com explicação: a semântica de `tpRetPisCofins`/CST não está confirmada, e enviar valores incorretos seria pior que não emitir.
- **IBS/CBS:** o `Servico` não tem o indicador da operação (`cIndOp`), obrigatório no grupo. O grupo só é enviado se o usuário informar o indicador na emissão; caso contrário a prévia avisa que a nota segue sem ele. **Decisão pendente** (ver abaixo).
- `pAliq` é informado só para não optante, ou ME/EPP com ISSQN fora do Simples; MEI nunca. **Hipótese a confirmar** em produção restrita.
- `totTrib`: "não informado" por padrão; ME/EPP pode informar o percentual do Simples.

### 8. Mensagens

`mensagens_sefin.py` traduz os códigos conhecidos (E0006, E0008, E0014, E0016, E0031, E0037, E0128, E0160, E0188, E0315, E0322, E0710/E0712, E0718, E0824, E0840, E1229) em explicação + o que fazer; código desconhecido recebe orientação genérica e **o texto original da Sefin é sempre preservado**.

### 9. Fronteira com a biblioteca

A `freedfe` só é importada em `fiscal/gateway.py`, `fiscal/persistencia/` (que implementa os contratos dela) e `fiscal/services/certificado.py`; um teste confere via AST. O certificado é aberto em memória só no momento do uso.

### 10. Permissões e API

`nfse.consultar` (listar, detalhe, prontidão, consultar, conferir, XML, DANFSe), `nfse.emitir` (rascunho, prévia, emitir), `nfse.cancelar`, `nfse.substituir`. A API devolve `acoes` por nota (o que o usuário pode fazer agora); a interface só as exibe, e o servidor as exige de novo.

## Itens abertos e decisões que não são desta fase

1. **`cIndOp` no cadastro de serviço** (IBS/CBS): propõe-se um campo no `Servico`; depende de confirmar os valores válidos da tabela de operações.
2. **Retenção de PIS/COFINS** na DPS: confirmar a semântica antes de liberar.
3. **`pAliq`** por regime: confirmar na produção restrita (roteiro manual).
4. **Pedido de análise fiscal para cancelamento** (evento próprio): fora da API pública da biblioteca; hoje é orientação.
5. **Criptografia em repouso dos XMLs**: tratar na implantação (banco/backups).
6. Rotina de **retenção** (quanto tempo guardar XML e evidências) pertence à fase de conformidade.
