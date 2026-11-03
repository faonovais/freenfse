# Manual do usuário

Este manual explica, em linguagem simples, como usar o freenfse no dia a dia. Os nomes entre aspas são os que aparecem no
menu e nos botões da tela.

> **Importante:** enquanto a empresa estiver em **Produção restrita** (o selo aparece no topo da tela), as notas são **de
> teste** e não têm valor fiscal. A troca para a produção é uma decisão do administrador e tem um passo a passo próprio
> (veja "Antes de emitir notas de verdade", no fim).

## 1. Primeiro acesso

1. Abra o endereço do sistema e entre com o **e-mail** que o administrador cadastrou e a senha, ou com sua conta Google, se
   essa opção estiver ligada.
2. Quem é **Master** (administrador geral) precisa configurar a **verificação em duas etapas** na primeira entrada: instale um
   aplicativo autenticador no celular, leia o QR Code e digite o código de 6 dígitos. Depois, use o código a cada entrada.
   Você pode ver ou ajustar isso em **Conta › Verificação em duas etapas**.
3. Troque a senha inicial. Se o instalador deixou um arquivo `master.senha`, peça a quem instalou para apagá-lo.

Não há cadastro público: só entra quem o Master cadastrou em **Administração › Usuários** e vinculou a uma empresa em
**Administração › Vínculos**.

### Quem pode fazer o quê

| Perfil | Pode |
|---|---|
| **Administrador** | tudo na empresa: configuração fiscal, certificado, e-mail, Drive, usuários da empresa e as demais ações |
| **Emissor** | emitir, cancelar e substituir notas; editar cadastros, modelos e agendamentos; enviar notas por e-mail/Drive e baixar em lote; **ver** a configuração (sem alterar) |
| **Financeiro** | consultar notas, cadastros e a configuração; enviar notas por e-mail/Drive e baixar em lote |
| **Consulta** | só consultar notas, cadastros, configuração e histórico de envios |

O **Master** cuida das empresas, dos usuários e dos vínculos (menu **Administração**).

## 2. Escolher a empresa

Se você trabalha com mais de uma empresa, use o seletor **Empresa ativa** no topo. Tudo o que você vê (notas, cadastros,
configuração) é da empresa escolhida. Cada aba do navegador pode ficar com uma empresa diferente.

## 3. Preparar a empresa para emitir (feito uma vez, pelo Administrador)

No menu **Configuração fiscal**:

1. **Parâmetros fiscais** — regime tributário, **série** da DPS, **município emissor** e o **ambiente** (comece em *Produção
   restrita*). Clique em **Verificar convênio**: o sistema confere se o município aderiu à NFS-e Nacional. Se a empresa
   informa IBS/CBS, preencha também o indicador da operação (quem cuida da contabilidade informa o código de 6 dígitos).
2. **Certificado A1** — envie o arquivo `.pfx` e a senha. O CNPJ do certificado precisa ser o da empresa. O sistema avisa
   por e-mail quando faltarem 30, 15 e 7 dias para vencer. **A senha e o arquivo nunca ficam visíveis depois de enviados.**
3. **Logo da empresa** — a imagem que aparece no DANFSe.

Em **Cadastros**:

4. **Pessoas** — os tomadores (seus clientes): documento (CPF/CNPJ), nome, endereço com município e e-mail para envio.
5. **Serviços** — o serviço que você presta: código de tributação nacional, descrição, alíquota do ISS e o período de
   vigência.

## 4. Emitir uma nota

1. **Notas fiscais › NFS-e emitidas › Nova nota**.
2. Escolha o **tomador**, a **competência** (mês de referência), o **serviço** e o **valor**. Se houver retenções ou
   desconto, preencha-os.
3. Clique em **Conferir a nota**. A tela mostra tudo já calculado (ISS, retenções, valor líquido), o ambiente e eventuais
   avisos. **Leia com atenção** — depois de autorizada, a nota não se corrige: só se cancela ou se substitui.
4. Clique em **Emitir nota** e confirme. Em produção, a confirmação lembra que a nota tem valor fiscal.
5. A tela acompanha: **Enviando à Sefin…** e depois **Autorizada**, com o número e a chave de acesso.

### As situações da nota

| Situação | O que significa | O que fazer |
|---|---|---|
| Rascunho | ainda não foi enviada | revise e **Emitir nota** |
| Enviando à Sefin | em andamento | aguarde alguns segundos |
| **Autorizada** | emitida com sucesso | baixe o XML e o DANFSe |
| Rejeitada | a Sefin recusou | leia o motivo e o que fazer; **Corrigir nota** e emita de novo |
| **Resultado incerto** | a internet caiu na hora do envio e o sistema não sabe se a Sefin recebeu | **não emita outra nota**. Aguarde até 5 minutos (o sistema confere sozinho) ou clique **Conferir agora na Sefin** |
| Cancelada / Substituída | a nota foi desfeita | a nota continua guardada |
| Descartada | rascunho descartado | — |

Se uma nota ficar mais de 2 horas sem resposta definitiva, o sistema manda um **alerta por e-mail** ao administrador.

## 5. Baixar, cancelar e substituir

Abra a nota na lista **NFS-e emitidas**:

* **Baixar XML** e **DANFSe** (o PDF da nota).
* **Cancelar nota** — escolha o motivo e escreva a justificativa (de 15 a 255 caracteres). A nota só passa a *Cancelada*
  depois que a Sefin confirmar; o município pode ter prazo e regras próprias.
* **Emitir nota substituta a partir desta** — para corrigir uma nota: o sistema cria um rascunho com os mesmos dados; você
  ajusta, emite, e a original vira *Substituída* quando a nova for autorizada.

## 6. Notas que se repetem: modelos e agendamentos

Para cobranças mensais, por exemplo:

1. **Agendamentos › Modelos de NFS-e** — crie um modelo com tomador, serviço, valor e texto. Use **Conferir como ficaria
   hoje** para ver o resultado e **Gerar rascunho agora** para testar.
2. **Agendamentos › Agendamentos** — escolha o modelo, a frequência (mensal, a cada N semanas, anual…), o dia, a hora e o
   responsável. A tela mostra as **próximas datas**.
3. Na data, o sistema cria um **rascunho** (nunca emite sozinho). Vá em **Agendamentos › Rascunhos**, revise e
   **Aprovar selecionados** (um a um ou em lote); cada nota segue o fluxo normal de emissão. Você pode **Descartar** com
   um motivo.
4. **Histórico de execuções** mostra o que cada agendamento fez, inclusive falhas e o porquê.

Todo dia às 08:20 o sistema avisa por e-mail os rascunhos que ainda esperam aprovação.

## 7. Baixar várias notas de uma vez

**Documentos › Download em lote**: escolha o período e a situação e peça o lote. O sistema monta um arquivo ZIP (XML, PDF e
uma planilha-resumo) e avisa quando estiver pronto. O arquivo fica disponível por **24 horas**.

## 8. Enviar as notas ao cliente e guardar no Drive

Em **Envio de documentos**:

* **E-mail da empresa** — configure o remetente. **Recomendado:** provedor **SMTP** com **senha de aplicativo** numa caixa
  dedicada (ex.: `notas@suaempresa.com.br`). Use **Enviar e-mail de teste**. Você escolhe se o envio é manual ou
  automático ao autorizar, se avisa o cliente no cancelamento e quais anexos (PDF/XML) vão.
* **Google Drive** — copia XML e PDF para uma pasta compartilhada com a conta de serviço. A tela mostra um exemplo do
  nome e da pasta antes de salvar.

Na nota, **Envios da nota** mostra cada e-mail e cada cópia (enviado, na fila, falhou e por quê) e permite **reenviar**.

## 9. Quando algo não funciona

| Mensagem ou situação | O que fazer |
|---|---|
| "O sistema está indisponível por alguns instantes" | aguarde 1 minuto e tente de novo; se passar de 10 minutos, avise quem cuida do servidor |
| Nota em **Resultado incerto** | não emita de novo; use **Conferir agora na Sefin** |
| Nota **Rejeitada** | leia o motivo, corrija o dado indicado e emita de novo |
| Aviso de **certificado a vencer** | peça o novo certificado e envie em **Certificado A1** antes do vencimento |
| "Envios com falha" por e-mail | confira a senha de aplicativo e o endereço do cliente em **E-mail da empresa** |

## 10. Antes de emitir notas de verdade

Quem decide a ida para a **Produção** é o Administrador, que precisa seguir a lista de conferência
([`docs/checklist-producao.md`](checklist-producao.md)). Na troca, o sistema exige: certificado válido com o CNPJ da
empresa, município informado e **convênio confirmado em produção**; ele lista o que falta e pede para você digitar
`PRODUÇÃO` para confirmar.
