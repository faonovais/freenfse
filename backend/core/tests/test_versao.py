import re
from pathlib import Path

from django.conf import settings
from rest_framework.test import APIClient

ARQUIVO_VERSION = Path(settings.BASE_DIR).parent / "VERSION"


def test_endpoint_versao_responde_sem_autenticacao():
    resposta = APIClient().get("/api/versao/")

    assert resposta.status_code == 200
    assert resposta.json() == {"versao": settings.VERSAO}


def test_endpoint_versao_aceita_head_para_verificacao_de_disponibilidade():
    resposta = APIClient().head("/api/versao/")

    assert resposta.status_code == 200


def test_endpoint_versao_recusa_escrita():
    resposta = APIClient().post("/api/versao/", {}, format="json")

    assert resposta.status_code == 405


def test_versao_vem_do_arquivo_version():
    conteudo = ARQUIVO_VERSION.read_text(encoding="utf-8").strip()

    assert settings.VERSAO == conteudo
    assert re.fullmatch(r"\d+\.\d+\.\d+", conteudo), "VERSION deve seguir MAJOR.MINOR.PATCH"
