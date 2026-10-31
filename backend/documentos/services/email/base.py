"""Interface comum dos provedores de e-mail (SMTP, Gmail API e Microsoft Graph).

Quem envia (`documentos.services.envio_email`) fala só com `ProvedorEmail`; cada provedor traduz
a mensagem para o seu protocolo e traduz as falhas para `ErroDeEnvio`, dizendo se vale tentar de
novo (`temporario=True`: rede, limite de uso, serviço fora do ar) ou não (`False`: senha recusada,
destinatário inexistente, anexo grande demais).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ErroDeEnvio(Exception):
    """Falha ao enviar. `mensagem` é para o usuário; `detalhe` é técnico e sem segredos."""

    def __init__(self, mensagem, *, detalhe="", temporario=True):
        """Guarda a explicação, o detalhe técnico curto e se a falha pode passar sozinha."""
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhe = detalhe[:500]
        self.temporario = temporario


@dataclass
class MensagemEmail:
    """Mensagem pronta para sair. Os anexos são `(nome, tipo_mime, bytes)`."""

    remetente: str
    destinatarios: list
    assunto: str
    texto: str
    html: str = ""
    copias: list = field(default_factory=list)
    nome_remetente: str = ""
    anexos: list = field(default_factory=list)


class ProvedorEmail(ABC):
    """Contrato de um provedor: envia uma mensagem ou levanta `ErroDeEnvio`."""

    nome = ""

    @abstractmethod
    def enviar(self, mensagem: MensagemEmail) -> None:
        """Envia a mensagem. Levanta `ErroDeEnvio` se não conseguir."""


def montar_mime(mensagem):
    """Monte o MIME (texto, HTML e anexos) de SMTP e Gmail, com cabeçalhos sem quebra de linha."""
    from email.message import EmailMessage
    from email.utils import formataddr

    def sem_quebra(texto):
        return " ".join(str(texto).split())

    mime = EmailMessage()
    mime["Subject"] = sem_quebra(mensagem.assunto)
    mime["From"] = formataddr((sem_quebra(mensagem.nome_remetente), sem_quebra(mensagem.remetente)))
    mime["To"] = ", ".join(sem_quebra(d) for d in mensagem.destinatarios)
    if mensagem.copias:
        mime["Cc"] = ", ".join(sem_quebra(c) for c in mensagem.copias)
    mime.set_content(mensagem.texto)
    if mensagem.html:
        mime.add_alternative(mensagem.html, subtype="html")
    for nome, tipo, conteudo in mensagem.anexos:
        principal, _, secundario = tipo.partition("/")
        mime.add_attachment(conteudo, maintype=principal, subtype=secundario, filename=nome)
    return mime
