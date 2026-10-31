"""Os três provedores de e-mail pela interface comum, com as APIs simuladas (sem rede)."""

import base64
import email
import smtplib

import pytest

from documentos.services.email.base import ErroDeEnvio, MensagemEmail, montar_mime
from documentos.services.email.gmail import ProvedorGmail
from documentos.services.email.graph import LIMITE_DE_ANEXO_BYTES, ProvedorGraph
from documentos.services.email.smtp import ProvedorSmtp
from documentos.tests.simulados import (
    SEGREDO_DE_TESTE,
    ServicoGmailFalso,
    ServidorSmtpFalso,
    SessaoGraphFalsa,
)


def _mensagem(**extra):
    dados = {
        "remetente": "notas@empresa.test",
        "nome_remetente": "Empresa Alfa",
        "destinatarios": ["cli@tomador.test", "cli2@tomador.test"],
        "copias": ["fin@empresa.test"],
        "assunto": "NFS-e nº 15",
        "texto": "Segue a nota.",
        "html": "<p>Segue a nota.</p>",
        "anexos": [
            ("nota.xml", "application/xml", b"<xml/>"),
            ("nota.pdf", "application/pdf", b"%PDF-1.4 ficticio"),
        ],
    }
    dados.update(extra)
    return MensagemEmail(**dados)


# -- SMTP ----------------------------------------------------------------------------------


def _smtp(servidor, seguranca="starttls", usuario="notas@empresa.test"):
    return ProvedorSmtp(
        host="smtp.exemplo.test", porta=587, seguranca=seguranca, usuario=usuario,
        senha=SEGREDO_DE_TESTE, fabrica=servidor,
    )  # fmt: skip


def test_smtp_usa_starttls_autentica_e_envia_para_todos_os_destinatarios():
    servidor = ServidorSmtpFalso()

    _smtp(servidor).enviar(_mensagem())

    assert servidor.eventos == [
        "conectou", "starttls", ("login", "notas@empresa.test", SEGREDO_DE_TESTE), "fechou",
    ]  # fmt: skip
    enviada = servidor.mensagens[0]
    assert enviada["de"] == "notas@empresa.test"
    assert enviada["para"] == ["cli@tomador.test", "cli2@tomador.test", "fin@empresa.test"]
    nomes = [p.get_filename() for p in enviada["mime"].walk() if p.get_filename()]
    assert nomes == ["nota.xml", "nota.pdf"]


def test_smtp_ssl_direto_nao_faz_starttls_e_sem_usuario_nao_autentica():
    servidor = ServidorSmtpFalso()

    _smtp(servidor, seguranca="ssl", usuario="").enviar(_mensagem())

    assert "starttls" not in servidor.eventos
    assert not any(isinstance(e, tuple) for e in servidor.eventos)


@pytest.mark.parametrize(
    ("falha", "temporario", "trecho"),
    [
        (smtplib.SMTPAuthenticationError(535, b"x"), False, "recusou o usuário ou a senha"),
        (smtplib.SMTPRecipientsRefused({"cli@tomador.test": (550, b"x")}), False, "destinatários"),
        (smtplib.SMTPSenderRefused(553, b"x", "notas@empresa.test"), False, "remetente"),
        (smtplib.SMTPServerDisconnected("caiu"), True, "tenta de novo"),
        (TimeoutError("lento"), True, "tenta de novo"),
        (ConnectionRefusedError("recusada"), True, "tenta de novo"),
    ],
)
def test_erros_do_smtp(falha, temporario, trecho):
    with pytest.raises(ErroDeEnvio) as erro:
        _smtp(ServidorSmtpFalso(falha=falha)).enviar(_mensagem())

    assert erro.value.temporario is temporario and trecho in erro.value.mensagem


def test_o_erro_do_smtp_nao_vaza_a_senha():
    with pytest.raises(ErroDeEnvio) as erro:
        _smtp(
            ServidorSmtpFalso(falha=smtplib.SMTPAuthenticationError(535, SEGREDO_DE_TESTE.encode()))
        ).enviar(_mensagem())

    assert SEGREDO_DE_TESTE not in erro.value.mensagem + erro.value.detalhe + repr(erro.value)


# -- Gmail ---------------------------------------------------------------------------------


def test_gmail_envia_o_mime_completo_pela_api():
    servico = ServicoGmailFalso()

    ProvedorGmail(servico).enviar(_mensagem())

    usuario, corpo = servico.enviados[0]
    assert usuario == "me"
    mime = email.message_from_bytes(base64.urlsafe_b64decode(corpo["raw"]))
    assert mime["To"] == "cli@tomador.test, cli2@tomador.test" and mime["Cc"] == "fin@empresa.test"
    assert [p.get_filename() for p in mime.walk() if p.get_filename()] == ["nota.xml", "nota.pdf"]


# -- Microsoft Graph -----------------------------------------------------------------------


def _graph(sessao):
    return ProvedorGraph(
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        client_secret=SEGREDO_DE_TESTE,
        sessao=sessao,
    )


def test_graph_pede_o_token_do_aplicativo_e_envia_pelo_send_mail():
    sessao = SessaoGraphFalsa()

    _graph(sessao).enviar(_mensagem())

    token, envio = sessao.chamadas
    assert "/11111111-1111-1111-1111-111111111111/oauth2/v2.0/token" in token["url"]
    assert token["data"]["grant_type"] == "client_credentials"
    assert token["data"]["scope"] == "https://graph.microsoft.com/.default"
    assert envio["url"].endswith("/users/notas@empresa.test/sendMail")
    assert envio["headers"]["Authorization"] == "Bearer token-ficticio"
    mensagem = envio["json"]["message"]
    assert [d["emailAddress"]["address"] for d in mensagem["toRecipients"]] == [
        "cli@tomador.test", "cli2@tomador.test",
    ]  # fmt: skip
    assert [c["emailAddress"]["address"] for c in mensagem["ccRecipients"]] == ["fin@empresa.test"]
    assert mensagem["body"]["contentType"] == "HTML"
    anexos = {a["name"]: base64.b64decode(a["contentBytes"]) for a in mensagem["attachments"]}
    assert anexos == {"nota.xml": b"<xml/>", "nota.pdf": b"%PDF-1.4 ficticio"}


@pytest.mark.parametrize(
    ("status_token", "status_envio", "temporario", "trecho"),
    [
        (401, 202, False, "recusou as credenciais"),
        (503, 202, True, "indisponível"),
        (200, 403, False, "Mail.Send"),
        (200, 429, True, "limitou"),
        (200, 500, True, "indisponível"),
    ],
)
def test_erros_do_graph(status_token, status_envio, temporario, trecho):
    with pytest.raises(ErroDeEnvio) as erro:
        _graph(SessaoGraphFalsa(status_token, status_envio)).enviar(_mensagem())

    assert erro.value.temporario is temporario and trecho in erro.value.mensagem


def test_graph_recusa_anexo_acima_de_3_mb_antes_de_chamar_a_rede():
    sessao = SessaoGraphFalsa()
    grande = ("grande.pdf", "application/pdf", b"0" * (LIMITE_DE_ANEXO_BYTES + 1))

    with pytest.raises(ErroDeEnvio) as erro:
        _graph(sessao).enviar(_mensagem(anexos=[grande]))

    assert erro.value.temporario is False and "3 MB" in erro.value.mensagem
    assert sessao.chamadas == []


# -- MIME ----------------------------------------------------------------------------------


def test_cabecalhos_nao_aceitam_quebra_de_linha_injetada():
    mime = montar_mime(
        _mensagem(assunto="Nota\r\nBcc: espiao@mal.test", nome_remetente="Empresa\nX-Mau: 1")
    )

    assert mime["Bcc"] is None and mime["X-Mau"] is None
    assert "\n" not in mime["Subject"] and "\r" not in mime["Subject"]
