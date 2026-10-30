# Roteiro de verificação manual da Fase 2

Os testes automatizados não usam certificado real nem falam com o ambiente nacional da NFS-e. Este roteiro
cobre o que só um certificado A1 real e a internet podem confirmar. Use **sempre a produção restrita**.

> **Cuidado:** nunca cole o `.pfx`, a senha ou o conteúdo deles em issues, PRs, mensagens ou logs.

## Antes de começar

1. Suba o ambiente (`docker compose up --build`) e entre como Master ([README](../README.md#primeiro-acesso)).
2. Crie a empresa com o **CNPJ do titular do certificado** que vai testar e um usuário Administrador para ela.
3. Entre como esse usuário e escolha a empresa no topo da tela.

## 1. Município e parâmetros

1. **Configuração fiscal › Parâmetros fiscais**.
2. Escolha o regime (e, se ME/EPP, o regime de apuração), a série da DPS e o município emissor **pelo nome**.
3. Confirme que o ambiente é **Produção restrita (testes)** e que o selo "Produção restrita" aparece no cabeçalho.
4. Salve. Esperado: confirmação sem erro.

## 2. Certificado A1

1. **Configuração fiscal › Certificado A1**.
2. Envie o `.pfx` com a senha errada. Esperado: recusa com mensagem sobre a senha, e a senha some do campo.
3. Envie com a senha certa. Esperado: titular, CNPJ e validade exibidos. O arquivo e a senha **não** aparecem.
4. Se o CNPJ do titular for de outro estabelecimento da mesma raiz, a tela pede a opção "mesma raiz de CNPJ".
5. Confira no banco que `fiscal_certificado.arquivo_pfx` e `senha` começam com `v1:` (cifrados).

## 3. Convênio do município

1. Em **Parâmetros fiscais**, clique em **Verificar convênio do município**.
2. Esperado: mensagem sobre a adesão do município e a data da verificação.
3. Desconecte a internet e repita. Esperado: mensagem clara de falha, mantendo o último resultado.
4. Mude o município ou o ambiente: o resultado anterior passa a ser marcado como de "outro município ou ambiente".

> A biblioteca `freedfe` documenta que a rota de convênio foi validada com certificado real; as rotas de
> contribuinte e de serviço não. Se a consulta do contribuinte falhar, a tela mostra um aviso e mantém o convênio.

## 4. Logo

1. **Configuração fiscal › Logo da empresa**. Envie um PNG e confira o logo no cabeçalho.
2. Envie um SVG que contenha `<script>` ou `onload`. Esperado: aviso dizendo o que foi removido.
3. Alterne o tema (claro/escuro): sem logo escuro, o claro é usado.

## 5. Alerta de vencimento

1. Com um certificado que vence em até 30 dias, rode a tarefa: `docker compose exec backend python manage.py shell -c "from fiscal.tasks import verificar_vencimento_certificados as t; print(t())"`.
2. Esperado: `1` na primeira vez e `0` nas seguintes; aviso visível no cabeçalho para os usuários da empresa.

## 6. Troca para produção (só com autorização)

A troca para **Produção** faz as notas terem valor fiscal. Não é necessária para validar a Fase 2; se for
testar, confirme que a tela exige digitar `PRODUÇÃO` e volte para produção restrita em seguida.
