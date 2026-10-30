# ADR 0003 — Cadastros e configuração fiscal da empresa (Fase 2)

- **Status:** aceita
- **Data:** 2026-10-30
- **Decisões relacionadas:** D4 (multiempresa isolado), D18 (design system e logo), D22 (permissões), `docs/analise-requisitos.md` §2.4, §2.6, §3.4 e §3.7

## Contexto

A Fase 2 entrega o que a DPS precisa por empresa: municípios, pessoas, serviços com vigência, parâmetros fiscais, certificado A1 e logo. Esta ADR registra as escolhas que o plano não fechava e o que ficou de fora de propósito.

## Decisões

### 1. Município no schema público, referenciado por código

- `core.Municipio` (5.571 linhas) fica no schema **público**: é dado público e igual para todas as empresas, e copiá-lo para cada schema multiplicaria as linhas e a carga por empresa.
- Os modelos de empresa guardam só o **código IBGE** (`codigo_municipio`) e validam a existência por `core.services.municipios`. Não há chave estrangeira entre schemas (regra do `GUIDELINES.md` §1).
- A carga é o comando idempotente `carregar_municipios`, a partir de `core/dados/municipios_ibge.csv`; o `entrypoint` o executa a cada subida. Fonte, data e SHA-256 estão em `core/dados/LEIAME.md`.
- **Limite:** os servidores do IBGE não estavam acessíveis no ambiente de desenvolvimento; o arquivo veio de uma cópia pública (`kelvins/municipios-brasileiros`, MIT) do dado do IBGE. A integridade é conferida a cada execução dos testes (contagem, UFs, SHA-256 e dígito verificador). Antes de produção, confira o arquivo contra a tabela oficial do IBGE (procedimento no `LEIAME.md`).
- O dígito verificador **não** é exigido no carregamento: o próprio IBGE atribuiu 9 códigos fora da regra, e rejeitá-los excluiria municípios reais. A `freedfe` também não o exige.
- A busca por nome usa uma coluna normalizada (`nome_busca`, sem acento nem caixa) em vez da extensão `unaccent`, para não depender de privilégio no banco.

### 2. Pessoas

- Modelo alinhado à identificação e ao endereço da DPS: exatamente um entre CPF/CNPJ, NIF ou **motivo de ausência do NIF** (`cNaoNIF`: 0, 1 ou 2); endereço nacional (com IBGE) **ou** no exterior.
- PF e PJ nacionais exigem o endereço completo com município IBGE (a DPS o exige). Estrangeiro pode ficar sem endereço, mas, se informar, o conjunto precisa estar completo (como a `freedfe` valida).
- O documento é único por empresa (restrição condicional no banco, além da checagem amigável). CNPJ alfanumérico é aceito (decisão da Fase 1).
- E-mails de envio da nota: lista em JSON (normalizada, sem repetição, até 10). A `freedfe` recebe um único e-mail por parte; na Fase 3 será usado o primeiro.
- `PerfilPessoa` é tabela por empresa com os perfis padrão semeados na migração (cliente, fornecedor, intermediário); a empresa pode cadastrar outros.
- **Sem exclusão**: desativa-se (a pessoa vai ter histórico fiscal).

### 3. Cópia entre empresas

- É uma **operação explícita de cópia**, não um vínculo: depois dela os registros são independentes (teste dedicado).
- Exige acesso à origem (vínculo ativo ou Master) com `cadastro.consultar` e `cadastro.editar` no destino. Origem sem acesso, inexistente ou inativa devolve a **mesma 403** da Fase 1 (não revela quais empresas existem).
- Pessoas cujo documento (ou NIF) já existe no destino são ignoradas, cada uma com o motivo. A auditoria registra quantas foram copiadas, sem dados pessoais.

### 4. Serviços e vigência

- Cada linha é uma **versão** do serviço, identificado por (código nacional, código municipal). Versões **ativas** do mesmo serviço não podem se sobrepor (limites inclusivos); versão inativa não bloqueia.
- A checagem e a gravação rodam sob `pg_advisory_xact_lock` por serviço: sem ele haveria janela de corrida entre a verificação e a gravação. Escolhi isso em vez de uma `ExclusionConstraint`, que exigiria a extensão `btree_gist` (privilégio e instalação por schema).
- Alíquota do ISS limitada a 0–5% (LC 116/2003, art. 8º). Os percentuais de retenção são **padrões do cadastro**; o valor é calculado na emissão (Fase 3). NBS é obrigatória quando há IBS/CBS (E0322 da DPS).

### 5. Parâmetros fiscais e ambiente

- Uma linha por schema (`pk=1` com restrição no banco). O regime tributário escolhido define a opção pelo Simples da DPS (`opSimpNac`); ME/EPP exige o regime de apuração. O padrão é "Outro (não optante)": o estado inicial é consistente e o usuário precisa declarar o regime.
- Ambiente padrão: **produção restrita**. Trocar para produção exige permissão `config.editar`, `confirmar_producao: true` na API (a tela pede digitar `PRODUÇÃO`) e é auditado, nos dois sentidos.
- **Não** há bloqueio da troca por falta de certificado ou de convênio verificado: não foi pedido e a Fase 3 recusa emitir sem eles. Fica como possível endurecimento.
- O resultado do convênio é gravado com data, município e ambiente; vale como "atual" só enquanto município e ambiente não mudam.

### 6. Gateway da freedfe

- `fiscal/gateway.py` é o único ponto de contato com a biblioteca (além da leitura do certificado). Os testes trocam só o transporte HTTP, então a `freedfe` roda de verdade, sem rede.
- `criar_servico_nfse` exige peças de persistência da emissão (numeração, travas, evidências, repositório) que só existem na Fase 3. Na Fase 2 elas eram preenchidas com objetos que **recusavam o uso** (`NaoDisponivelNaFase2`), para ninguém emitir por engano. A Fase 3 as substituiu por implementações reais em PostgreSQL ([ADR 0004](0004-nucleo-fiscal.md)) e o placeholder foi removido.
- Consultas: o cache de parâmetros é desligado (a verificação sempre consulta) e as repetições são curtas (1 s e 2 s), porque o usuário aguarda a requisição.
- **Limite:** a rota de convênio foi confirmada com A1 real na produção restrita pela própria biblioteca; as rotas de contribuinte e de serviço, segundo a documentação dela, não. Por isso, a falha ao obter o contribuinte só gera um aviso e não impede o resultado do convênio.

### 7. Certificado A1

- `.pfx` e senha em campos cifrados (binário e texto, Fase 1); **nunca** em disco e nunca devolvidos: a API só expõe metadados. Testes verificam que nem o `.pfx` (bruto, base64 ou hexadecimal) nem a senha aparecem em respostas, logs, auditoria e `repr`, e leem a coluna bruta do banco para provar a cifra.
- Validações no envio: senha, CNPJ do titular, validade (vencido ou ainda não vigente) e presença de CNPJ (certificado de pessoa física é recusado). O arquivo é limitado a 256 KB.
- **CNPJ:** por padrão, exige igualdade com o CNPJ da empresa. Um certificado de outro estabelecimento da **mesma raiz** (8 primeiros caracteres) só é aceito com opção explícita, que fica registrada e auditada. Justificativa: matriz e filiais costumam compartilhar o certificado (§3.7 dos requisitos), mas a regra da Sefin para o emitente (E0718) não pôde ser conferida sem um certificado real; por isso é escolha consciente e não o padrão.
- Um certificado por empresa; novo envio substitui o anterior.

### 8. Alertas de vencimento

- Tarefa diária (Celery beat, 06:40, America/Sao_Paulo) gera um alerta por faixa (30, 15 e 7 dias, e vencido) e por certificado; se a tarefa ficar dias parada, gera só a faixa atual. É idempotente.
- O envio por e-mail é da Fase 4: o ponto de extensão é o sinal `fiscal.services.vencimento.certificado_a_vencer`. Na tela, o aviso aparece no cabeçalho de todas as telas para qualquer usuário vinculado, e no cartão do certificado.

### 9. Logo

- PNG (até 512 KB e 2000×2000 pixels, validado pela assinatura e pelo cabeçalho com CRC) ou SVG (até 200 KB). O formato vem do **conteúdo**, não do nome nem do tipo informado.
- O SVG é reescrito por **lista de permissões**: só elementos e atributos conhecidos sobrevivem; scripts, eventos `on*`, `foreignObject`, animações, filtros, `href` externo, entidades XML e `url()` externo (inclusive escondido por escape de CSS) são removidos, e o que foi retirado é informado ao usuário e auditado. Foi preferido sanear a converter para PNG, que exigiria um renderizador como dependência.
- Guardado no schema da empresa. A entrega passa pela API autenticada, com `Content-Security-Policy: sandbox`, `nosniff` e `ETag`. O frontend busca o arquivo com o `X-Empresa` e o exibe por URL local, porque um `<img src>` direto não enviaria o cabeçalho.
- Sem logo escuro, usa-se o claro.

### 10. Permissões

- Nenhuma permissão nova. Cadastros usam `cadastro.consultar`/`editar`; parâmetros, certificado e logo usam `config.consultar`/`editar`.
- Consequência herdada da Fase 1: o perfil **Emissor não tem `config.consultar`**, então não vê parâmetros nem certificado. Para a interface funcionar para todos, a rota `identidade` (ambiente, versões do logo e situação resumida do certificado), o download do logo e a busca de municípios são abertas a **qualquer vinculado** (`QualquerVinculado`). Se o Emissor precisar ver os parâmetros, a mudança é conceder `config.consultar` a esse perfil.

## Consequências e limites

- **Verificação com certificado real em produção restrita não foi feita** (não há certificado no ambiente de desenvolvimento). Há um roteiro manual em `docs/verificacao-fase-2.md`.
- Os testes de backend passaram de 185 para 477 e a suíte ficou mais lenta (~4 min), porque cada teste de empresa cria e migra um schema. Se incomodar, o caminho é reutilizar schemas entre testes.
- Fora do escopo e **não executado**: consulta de CNPJ em fonte pública (opcional nos requisitos), `parametros_servico` municipal por serviço, incentivos fiscais, importação em lote de pessoas, e-mail de alerta (Fase 4).
