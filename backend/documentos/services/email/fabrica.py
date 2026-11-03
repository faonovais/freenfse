"""Escolhe e monta o provedor de e-mail da empresa a partir da configuração."""

from documentos.models import ConfiguracaoEmail
from documentos.services.credenciais import CredencialInvalida, ler_conta_de_servico
from documentos.services.email.base import ErroDeEnvio
from documentos.services.email.gmail import ProvedorGmail, criar_servico_gmail
from documentos.services.email.graph import ProvedorGraph
from documentos.services.email.smtp import ProvedorSmtp

P = ConfiguracaoEmail.Provedor


def pontos_de_troca():
    """Fábricas dos clientes externos. Os testes trocam estas entradas por versões simuladas."""
    return {
        "smtp": None,  # `smtplib` real
        "gmail": criar_servico_gmail,
        "graph": None,  # `requests.Session` real
    }


def criar_provedor(configuracao, trocas=None):
    """Provedor pronto para enviar, ou `ErroDeEnvio` didático se a configuração não permite."""
    trocas = {**pontos_de_troca(), **(trocas or {})}
    if configuracao.provedor == P.NENHUM or not configuracao.remetente_email:
        raise ErroDeEnvio(
            "O envio de e-mail não está configurado. Escolha o provedor e o remetente em "
            "Configuração › E-mail.",
            temporario=False,
        )
    if configuracao.provedor == P.SMTP:
        if not configuracao.smtp_host:
            raise ErroDeEnvio(
                "Informe o servidor SMTP na configuração de e-mail.", temporario=False
            )
        return ProvedorSmtp(
            host=configuracao.smtp_host,
            porta=configuracao.smtp_porta,
            seguranca=configuracao.smtp_seguranca,
            usuario=configuracao.smtp_usuario,
            senha=configuracao.smtp_senha,
            fabrica=trocas["smtp"],
        )
    if configuracao.provedor == P.GMAIL:
        try:
            conta = ler_conta_de_servico(configuracao.gmail_conta_servico)
        except CredencialInvalida as erro:
            raise ErroDeEnvio(str(erro), temporario=False) from None
        return ProvedorGmail(trocas["gmail"](conta, configuracao.remetente_email))
    if configuracao.provedor == P.GRAPH:
        if not (
            configuracao.graph_tenant_id
            and configuracao.graph_client_id
            and configuracao.graph_client_secret
        ):
            raise ErroDeEnvio(
                "Informe o ID do tenant, o ID do aplicativo e o segredo do Microsoft Graph.",
                temporario=False,
            )
        return ProvedorGraph(
            tenant_id=configuracao.graph_tenant_id,
            client_id=configuracao.graph_client_id,
            client_secret=configuracao.graph_client_secret,
            sessao=trocas["graph"],
        )
    raise ErroDeEnvio("Provedor de e-mail desconhecido.", temporario=False)
