"""Provedor SMTP genérico (STARTTLS, SSL ou sem criptografia), com usuário e senha."""

import smtplib

from documentos.services.email.base import ErroDeEnvio, MensagemEmail, ProvedorEmail, montar_mime

TEMPO_LIMITE = 30


class ProvedorSmtp(ProvedorEmail):
    """Envia por um servidor SMTP.

    `fabrica` cria a conexão (`smtplib.SMTP`/`SMTP_SSL` por padrão); os testes trocam por um
    servidor falso, sem rede.
    """

    nome = "smtp"

    def __init__(self, *, host, porta, seguranca, usuario, senha, fabrica=None):
        """Guarda os dados da conexão (a senha só existe em memória)."""
        self._host, self._porta, self._seguranca = host, porta, seguranca
        self._usuario, self._senha = usuario, senha
        self._fabrica = fabrica or self._conexao_padrao

    def _conexao_padrao(self):
        classe = smtplib.SMTP_SSL if self._seguranca == "ssl" else smtplib.SMTP
        return classe(self._host, self._porta, timeout=TEMPO_LIMITE)

    def enviar(self, mensagem: MensagemEmail):
        """Conecta, autentica e envia; traduz as falhas do SMTP."""
        mime = montar_mime(mensagem)
        todos = [*mensagem.destinatarios, *mensagem.copias]
        try:
            with self._fabrica() as servidor:
                if self._seguranca == "starttls":
                    servidor.starttls()
                if self._usuario:
                    servidor.login(self._usuario, self._senha or "")
                servidor.send_message(mime, from_addr=mensagem.remetente, to_addrs=todos)
        except smtplib.SMTPAuthenticationError as erro:
            raise ErroDeEnvio(
                "O servidor de e-mail recusou o usuário ou a senha. Confira os dados do SMTP "
                "(muitos provedores exigem uma senha de aplicativo).",
                detalhe=f"SMTP {erro.smtp_code}",
                temporario=False,
            ) from None
        except smtplib.SMTPRecipientsRefused as erro:
            raise ErroDeEnvio(
                "O servidor recusou um ou mais destinatários. Confira os endereços de e-mail.",
                detalhe=f"destinatários recusados: {', '.join(erro.recipients)}"[:300],
                temporario=False,
            ) from None
        except smtplib.SMTPSenderRefused as erro:
            raise ErroDeEnvio(
                "O servidor recusou o remetente. Use um remetente autorizado por esse servidor.",
                detalhe=f"SMTP {erro.smtp_code}",
                temporario=False,
            ) from None
        except (smtplib.SMTPException, OSError, TimeoutError) as erro:
            raise ErroDeEnvio(
                "Não foi possível falar com o servidor de e-mail agora. O sistema tenta de novo "
                "sozinho.",
                detalhe=f"{type(erro).__name__}",
            ) from None
