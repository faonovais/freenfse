"""Adaptadores reais do Google (Drive e Gmail) contra HTTP simulado: rota, parâmetros e erros.

`HttpMockSequence` (do próprio cliente do Google) responde no lugar da rede. Aqui se confere o que o
adaptador **pede** (URL, `supportsAllDrives`, corpo, propriedades) e como traduz cada erro.
"""

import base64
import email
import json
from urllib.parse import parse_qs, urlparse

import pytest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpMockSequence

from documentos.services.drive.cliente import ClienteDriveGoogle, ErroDrive, criar_servico_drive
from documentos.services.email.base import ErroDeEnvio, MensagemEmail
from documentos.services.email.gmail import ProvedorGmail, criar_servico_gmail
from documentos.tests.simulados import conta_de_servico_json


def _drive(*respostas):
    http = HttpMockSequence([({"status": str(s)}, c) for s, c in respostas])
    return ClienteDriveGoogle(build("drive", "v3", http=http, static_discovery=True)), http


def _consulta(uri):
    return {k: v[0] for k, v in parse_qs(urlparse(uri).query).items()}


PASTA = json.dumps(
    {
        "id": "RAIZ",
        "name": "Notas",
        "mimeType": "application/vnd.google-apps.folder",
        "capabilities": {"canAddChildren": True},
    }
)


def test_obter_pasta_pede_o_id_com_suporte_a_drives_compartilhados():
    cliente, http = _drive((200, PASTA))

    pasta = cliente.obter_pasta("RAIZ")

    assert pasta == {"id": "RAIZ", "nome": "Notas", "pode_escrever": True}
    uri = http.request_sequence[0][0]
    assert "/files/RAIZ" in uri and _consulta(uri)["supportsAllDrives"] == "true"


def test_arquivo_no_lugar_de_pasta_e_recusado():
    cliente, _ = _drive((200, '{"id": "A", "name": "x.txt", "mimeType": "text/plain"}'))

    with pytest.raises(ErroDrive, match="não de uma pasta"):
        cliente.obter_pasta("A")


def test_listar_escapa_o_nome_e_junta_as_paginas():
    primeira = json.dumps({"files": [{"id": "1", "name": "a"}], "nextPageToken": "P2"})
    segunda = json.dumps({"files": [{"id": "2", "name": "a", "appProperties": {"k": "v"}}]})
    cliente, http = _drive((200, primeira), (200, segunda))

    itens = cliente.listar("RAIZ", nome="d'Ouro\\", somente_pastas=True)

    assert [i["id"] for i in itens] == ["1", "2"] and itens[1]["propriedades"] == {"k": "v"}
    q = _consulta(http.request_sequence[0][0])["q"]
    assert "'RAIZ' in parents" in q and "trashed = false" in q
    assert "name = 'd\\'Ouro\\\\'" in q and "mimeType = 'application/vnd.google-apps.folder'" in q
    assert _consulta(http.request_sequence[1][0])["pageToken"] == "P2"


def test_criar_pasta_envia_tipo_e_pai():
    cliente, http = _drive((200, '{"id": "NOVA"}'))

    assert cliente.criar_pasta("2026", "RAIZ") == "NOVA"

    uri, metodo, corpo, _ = http.request_sequence[0]
    assert metodo == "POST"
    assert json.loads(corpo) == {
        "name": "2026", "mimeType": "application/vnd.google-apps.folder", "parents": ["RAIZ"],
    }  # fmt: skip


def test_enviar_arquivo_manda_o_conteudo_e_as_propriedades_de_reconhecimento():
    cliente, http = _drive((200, '{"id": "ARQ"}'))

    ident = cliente.enviar("a.xml", "RAIZ", b"<xml/>", "application/xml", {"freenfse_nota": "N"})

    assert ident == "ARQ"
    uri, metodo, corpo, _ = http.request_sequence[0]
    assert metodo == "POST" and _consulta(uri)["uploadType"] == "multipart"
    texto = corpo.decode() if isinstance(corpo, bytes) else corpo
    assert '"appProperties": {"freenfse_nota": "N"}' in texto and "<xml/>" in texto
    assert '"parents": ["RAIZ"]' in texto


def test_atualizar_usa_o_mesmo_file_id():
    cliente, http = _drive((200, '{"id": "ARQ"}'))

    cliente.atualizar("ARQ", b"novo", "application/pdf")

    uri, metodo, _corpo, _ = http.request_sequence[0]
    assert metodo == "PATCH" and "/files/ARQ" in uri


@pytest.mark.parametrize(
    ("status", "temporario", "nao_encontrado"),
    [
        (404, False, True),
        (403, False, False),
        (401, False, False),
        (429, True, False),
        (503, True, False),
    ],
)
def test_erros_do_drive_viram_mensagens_e_dizem_se_vale_tentar_de_novo(
    status, temporario, nao_encontrado
):
    cliente, _ = _drive((status, '{"error": {"message": "x"}}'))

    with pytest.raises(ErroDrive) as erro:
        cliente.obter_pasta("RAIZ")

    assert (erro.value.temporario, erro.value.nao_encontrado) == (temporario, nao_encontrado)
    assert f"HTTP {status}" in erro.value.detalhe


def test_o_servico_do_drive_e_do_gmail_nascem_da_conta_de_servico_sem_rede():
    conta = json.loads(conta_de_servico_json())

    assert criar_servico_drive(conta) is not None
    assert criar_servico_gmail(conta, "notas@empresa.test") is not None


# -- Gmail ---------------------------------------------------------------------------------


def _gmail(*respostas):
    http = HttpMockSequence([({"status": str(s)}, c) for s, c in respostas])
    return ProvedorGmail(build("gmail", "v1", http=http, static_discovery=True)), http


def _mensagem():
    return MensagemEmail(
        remetente="notas@empresa.test",
        nome_remetente="Empresa",
        destinatarios=["cli@tomador.test"],
        copias=["fin@empresa.test"],
        assunto="NFS-e 1",
        texto="corpo",
        html="<p>corpo</p>",
        anexos=[("a.xml", "application/xml", b"<xml/>")],
    )


def test_gmail_envia_o_mime_em_base64_pela_rota_de_envio():
    provedor, http = _gmail((200, '{"id": "m1"}'))

    provedor.enviar(_mensagem())

    uri, metodo, corpo, _ = http.request_sequence[0]
    assert metodo == "POST" and "/users/me/messages/send" in uri
    mime = email.message_from_bytes(base64.urlsafe_b64decode(json.loads(corpo)["raw"]))
    assert mime["To"] == "cli@tomador.test" and mime["Cc"] == "fin@empresa.test"
    assert mime["Subject"] == "NFS-e 1" and "notas@empresa.test" in mime["From"]
    assert [p.get_filename() for p in mime.walk() if p.get_filename()] == ["a.xml"]


@pytest.mark.parametrize(
    ("status", "temporario"), [(429, True), (503, True), (403, False), (400, False)]
)
def test_erros_do_gmail(status, temporario):
    provedor, _ = _gmail((status, "{}"))

    with pytest.raises(ErroDeEnvio) as erro:
        provedor.enviar(_mensagem())

    assert erro.value.temporario is temporario and f"HTTP {status}" in erro.value.detalhe


def test_o_erro_do_gmail_nao_vaza_o_corpo_da_resposta():
    provedor, _ = _gmail((403, '{"error": "token-secreto-123"}'))

    with pytest.raises(ErroDeEnvio) as erro:
        provedor.enviar(_mensagem())

    assert "token-secreto-123" not in erro.value.mensagem + erro.value.detalhe
    assert isinstance(HttpError, type)
