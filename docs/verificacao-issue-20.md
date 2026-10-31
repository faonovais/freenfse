# Verificação da issue #20 (IBS/CBS por empresa, Emissor, produção e municípios)

Os testes automatizados usam a Sefin simulada e o transporte HTTP falso do convênio: **nada sai para a rede**. O que só o
ambiente real confirma (o convênio de verdade em produção, o `cIndOp` aceito pela Sefin, a tabela do IBGE baixada hoje) está
no roteiro manual abaixo.

> **Cuidado:** use **sempre a produção restrita** (exceto no passo de troca para produção, que deve ser feito numa empresa de
> teste) e dados fictícios. Nunca cole certificado, chave de acesso, XML ou e-mail reais em issues, PRs, mensagens ou logs.

## Roteiro manual

### 1. IBS/CBS por empresa
1. Com um **serviço com classificação** (NBS, CST e `cClassTrib` preenchidos, em *Cadastros › Serviços*) e outro **sem**.
2. *Configuração fiscal › Parâmetros fiscais*, seção **IBS e CBS**: tente marcar *Informar o IBS/CBS nas notas desta empresa* e
   salvar **sem** indicador. Esperado: recusa dizendo para informar o indicador da operação padrão (6 dígitos).
3. Informe um indicador (ex.: o fornecido pelo contador) e salve. Esperado: salvo; ao reabrir, a opção e o indicador aparecem.
4. *Notas › Nova nota* com o serviço **com** classificação: o campo *Indicador da operação (IBS/CBS)* mostra a dica
   "Em branco: vale o padrão da empresa (…)". **Confira a nota** sem mexer: na conferência, a linha **IBS/CBS na DPS** mostra o
   indicador da empresa, o destinatário, NBS, CST e `cClassTrib`, com "(padrão da empresa)".
5. Digite outro indicador só nessa nota e confira de novo. Esperado: "(ajuste desta nota)" com o indicador digitado; a empresa
   continua com o padrão antigo.
6. Marque *Não informar o IBS/CBS nesta nota*. Esperado: os campos travam e a conferência diz "Não vai na nota. Você escolheu
   não informar…".
7. Com o serviço **sem** classificação e a opção da empresa ligada, confira a nota. Esperado: aviso "…o serviço não tem NBS, CST
   e classificação tributária: a nota sairá sem o grupo. Complete o cadastro do serviço."
8. Desligue a opção da empresa e confira a nota do serviço com classificação. Esperado: aviso de que a empresa não informa IBS/CBS.
9. **Emita** uma nota de teste com o grupo e abra o XML da DPS (*Baixar XML*/evidência): confira `IBSCBS/cIndOp`, `indDest`,
   `valores/trib/CST` e `cClassTrib` e `cNBS`. A Sefin deve autorizar. **Anote** se ela rejeitar o `cIndOp`: é a pendência de
   homologação do ADR 0007 (alerta sobre o `cIndOp` ser da operação).
10. *Agendamentos*: gere um rascunho de um modelo cujo serviço tem classificação. Esperado: o rascunho herda o padrão da empresa
    (conferir na tela do rascunho). Mude o padrão da empresa e confirme que o rascunho já criado **não** muda até ser salvo de novo.

### 2. Perfil Emissor
1. Entre como **Emissor** (sem `config.editar`). Esperado: o menu mostra *Configuração fiscal*; *Parâmetros fiscais* e
   *Certificado A1* abrem **somente leitura** (campos travados, sem *Salvar*, sem *Verificar convênio*, sem envio de certificado).
2. O certificado mostra titular, CNPJ e validade; **nunca** o arquivo nem a senha.
3. As telas de e-mail e Drive abrem somente leitura, sem credenciais (só "configurada").

### 3. Troca para produção (numa empresa de teste)
1. Empresa **sem certificado**: em *Parâmetros fiscais*, escolha *Produção* e salve. Esperado: **sem pedir** para digitar
   `PRODUÇÃO`, a tela lista o que falta (certificado) com o link *Resolver*.
2. Envie o certificado, **sem município**. Esperado: lista só o município.
3. Informe o município e tente de novo. Esperado: agora pede a confirmação digitada; digite `PRODUÇÃO`.
4. Se o município **não** tiver convênio em produção: recusa com "NÃO tem convênio… no ambiente de produção" e o ambiente
   **continua** em produção restrita (e a emissão de teste continua liberada).
5. Com convênio: a troca é feita e o convênio mostrado é o de **produção**, já "atual" (a emissão não fica bloqueada).
6. Certificado vencido ou com CNPJ de outra empresa (simulados no banco de teste): a troca é recusada com a mensagem
   correspondente. **Voltar** para produção restrita não exige nada.

### 4. Municípios (IBGE)
1. Baixe a tabela oficial: `curl -fsSLO https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/2025/DTB_2025.zip`
   (ou a versão vigente) e confira o SHA-256 contra o `core/dados/LEIAME.md`.
2. `python manage.py comparar_municipios_ibge DTB_2025.zip`. Esperado: "O arquivo versionado confere com a tabela oficial".
3. Se o IBGE publicar uma nova data-base, o comando lista iguais/diferentes/faltantes; `--gravar` corrige o CSV (revise o diff).

## O que os testes automatizados cobrem

| Item | Arquivos de teste | O que prova |
|---|---|---|
| A. IBS/CBS por empresa | `fiscal/tests/test_ibs_cbs.py`, `test_migracao_ibs_cbs.py`, `agendamentos/tests/test_modelos.py`, `frontend/.../notas.test.jsx`, `fiscal.test.jsx` | padrão da empresa × ajuste pontual × "não informar"; validações; cópia (rascunho não muda com o padrão); XML assinado da DPS; prévia; prontidão; migração sem perda; herança pelo modelo; telas |
| B. Emissor | `core/tests/test_permissoes.py`, `fiscal/tests/test_parametros.py`, `test_certificado.py`, `documentos/tests/test_api_documentos.py`, `fiscal.test.jsx` | lê e não edita (parâmetros, certificado, e-mail, Drive, convênio, ambiente); nenhuma resposta traz segredo |
| C. Produção | `fiscal/tests/test_producao.py`, `test_parametros.py`, `test_convenio.py`, `fiscal.test.jsx` | uma prova por condição (certificado ausente/vencido/futuro/CNPJ/raiz, município, convênio não aderente/indefinido/futuro/ilegível/sem rede); ordem; nada gravado na recusa; sem rede antes da confirmação |
| D. Municípios | `core/tests/test_municipios_oficiais.py`, `test_municipios.py` | leitor da planilha, comparação, comando, XML sem entidades externas, grafias corrigidas |

As **mutações** (alterar o código de propósito para ver o teste falhar) estão registradas na seção final deste arquivo.
