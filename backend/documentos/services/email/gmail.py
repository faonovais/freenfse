"""Provedor Gmail API: conta de serviço do Google com delegação em todo o domínio.

O remetente é o usuário delegado (`subject`): a conta de serviço envia **em nome dele**, sem
senha e sem token que expire quando alguém sai da empresa. Exige que um administrador do Google
Workspace autorize a conta de serviço para o escopo `gmail.send`.
"""

import base64

from googleapiclient.errors import HttpError

from documentos.services.email.base import ErroDeEnvio, MensagemEmail, ProvedorEmail, montar_mime

ESCOPO = "https://www.googleapis.com/auth/gmail.send"
STATUS_TEMPORARIOS = {408, 429, 500, 502, 503, 504}


def criar_servico_gmail(conta_servico, remetente):
    """Cliente `gmail v1` autenticado como a conta de serviço, em nome de `remetente`."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credenciais = service_account.Credentials.from_service_account_info(
        conta_servico, scopes=[ESCOPO], subject=remetente
    )
    return build("gmail", "v1", credentials=credenciais, cache_discovery=False)


class ProvedorGmail(ProvedorEmail):
    """Envia pela Gmail API. `servico` é o cliente do Google (os testes injetam um simulado)."""

    nome = "gmail"

    def __init__(self, servico):
        """Guarda o cliente `gmail v1` já autenticado."""
        self._servico = servico

    def enviar(self, mensagem: MensagemEmail):
        """Monta o MIME, envia por `users.messages.send` e traduz as falhas da API."""
        bruto = base64.urlsafe_b64encode(montar_mime(mensagem).as_bytes()).decode("ascii")
        try:
            self._servico.users().messages().send(userId="me", body={"raw": bruto}).execute()
        except HttpError as erro:
            status = erro.resp.status
            if status in STATUS_TEMPORARIOS:
                raise ErroDeEnvio(
                    "O Gmail está indisponível ou limitou o uso agora. O sistema tenta de novo "
                    "sozinho.",
                    detalhe=f"Gmail HTTP {status}",
                ) from None
            raise ErroDeEnvio(
                "O Gmail recusou o envio. Confira se a conta de serviço foi autorizada para "
                "enviar e-mail em nome do remetente (delegação em todo o domínio).",
                detalhe=f"Gmail HTTP {status}",
                temporario=False,
            ) from None
        except OSError as erro:
            raise ErroDeEnvio(
                "Não foi possível falar com o Gmail agora. O sistema tenta de novo sozinho.",
                detalhe=type(erro).__name__,
            ) from None
