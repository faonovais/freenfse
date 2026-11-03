"""Provedor Microsoft Graph (`sendMail`) com aplicativo registrado e sem usuário.

Usa o fluxo *client credentials*.

O aplicativo precisa da permissão `Mail.Send` (aplicativo) concedida pelo administrador do
tenant. O remetente é uma caixa do próprio tenant (`/users/{remetente}/sendMail`).
"""

import base64

import requests

from documentos.services.email.base import ErroDeEnvio, MensagemEmail, ProvedorEmail

URL_TOKEN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"  # noqa: S105
URL_ENVIO = "https://graph.microsoft.com/v1.0/users/{remetente}/sendMail"
ESCOPO = "https://graph.microsoft.com/.default"
TEMPO_LIMITE = 30
# Um anexo acima disto exige sessão de upload; o sistema recusa com explicação em vez de falhar.
LIMITE_DE_ANEXO_BYTES = 3 * 1024 * 1024
STATUS_TEMPORARIOS = {408, 429, 500, 502, 503, 504}


class ProvedorGraph(ProvedorEmail):
    """Envia pelo Microsoft Graph. `sessao` é um `requests.Session` (os testes injetam um falso)."""

    nome = "graph"

    def __init__(self, *, tenant_id, client_id, client_secret, sessao=None):
        """Guarda os dados do aplicativo (o segredo só existe em memória)."""
        self._tenant, self._client_id, self._segredo = tenant_id, client_id, client_secret
        self._sessao = sessao or requests.Session()

    def _token(self):
        try:
            resposta = self._sessao.post(
                URL_TOKEN.format(tenant=self._tenant),
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._segredo,
                    "scope": ESCOPO,
                },
                timeout=TEMPO_LIMITE,
            )
        except requests.RequestException as erro:
            raise ErroDeEnvio(
                "Não foi possível falar com a Microsoft agora. O sistema tenta de novo sozinho.",
                detalhe=type(erro).__name__,
            ) from None
        if resposta.status_code in STATUS_TEMPORARIOS:
            raise ErroDeEnvio(
                "A Microsoft está indisponível agora. O sistema tenta de novo sozinho.",
                detalhe=f"Graph token HTTP {resposta.status_code}",
            )
        if resposta.status_code != 200:
            raise ErroDeEnvio(
                "A Microsoft recusou as credenciais do aplicativo. Confira o ID do tenant, o ID "
                "do aplicativo e o segredo (que pode ter expirado).",
                detalhe=f"Graph token HTTP {resposta.status_code}",
                temporario=False,
            )
        return resposta.json()["access_token"]

    @staticmethod
    def _corpo(mensagem):
        def pessoa(endereco):
            return {"emailAddress": {"address": endereco}}

        return {
            "message": {
                "subject": " ".join(mensagem.assunto.split()),
                "body": {
                    "contentType": "HTML" if mensagem.html else "Text",
                    "content": mensagem.html or mensagem.texto,
                },
                "toRecipients": [pessoa(d) for d in mensagem.destinatarios],
                "ccRecipients": [pessoa(c) for c in mensagem.copias],
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": nome,
                        "contentType": tipo,
                        "contentBytes": base64.b64encode(conteudo).decode("ascii"),
                    }
                    for nome, tipo, conteudo in mensagem.anexos
                ],
            },
            "saveToSentItems": True,
        }

    def enviar(self, mensagem: MensagemEmail):
        """Obtém o token do aplicativo e envia por `sendMail`; traduz as falhas."""
        for nome, _tipo, conteudo in mensagem.anexos:
            if len(conteudo) > LIMITE_DE_ANEXO_BYTES:
                raise ErroDeEnvio(
                    f"O anexo {nome} passa de 3 MB, o limite deste envio pela Microsoft. Desligue "
                    "esse anexo na configuração de e-mail.",
                    detalhe=f"anexo de {len(conteudo)} bytes",
                    temporario=False,
                )
        token = self._token()
        try:
            resposta = self._sessao.post(
                URL_ENVIO.format(remetente=mensagem.remetente),
                json=self._corpo(mensagem),
                headers={"Authorization": f"Bearer {token}"},
                timeout=TEMPO_LIMITE,
            )
        except requests.RequestException as erro:
            raise ErroDeEnvio(
                "Não foi possível falar com a Microsoft agora. O sistema tenta de novo sozinho.",
                detalhe=type(erro).__name__,
            ) from None
        if resposta.status_code in (200, 202):
            return
        if resposta.status_code in STATUS_TEMPORARIOS:
            raise ErroDeEnvio(
                "A Microsoft está indisponível ou limitou o uso agora. O sistema tenta de novo "
                "sozinho.",
                detalhe=f"Graph HTTP {resposta.status_code}",
            )
        raise ErroDeEnvio(
            "A Microsoft recusou o envio. Confira se o aplicativo tem a permissão Mail.Send "
            "(aplicativo) com consentimento do administrador e se a caixa do remetente existe.",
            detalhe=f"Graph HTTP {resposta.status_code}",
            temporario=False,
        )
