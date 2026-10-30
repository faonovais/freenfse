"""Verificações do sistema que protegem a configuração de produção."""

from core.checks import verificar_cookies_seguros


def _ids(resultado):
    return [aviso.id for aviso in resultado]


def test_avisa_quando_nao_e_desenvolvimento_e_os_cookies_nao_exigem_https(settings):
    settings.DEBUG = False
    settings.COOKIES_SEGUROS = False

    assert _ids(verificar_cookies_seguros(None)) == ["core.W002"]


def test_nao_avisa_com_cookies_seguros_ligados(settings):
    settings.DEBUG = False
    settings.COOKIES_SEGUROS = True

    assert verificar_cookies_seguros(None) == []


def test_nao_avisa_em_desenvolvimento(settings):
    settings.DEBUG = True
    settings.COOKIES_SEGUROS = False

    assert verificar_cookies_seguros(None) == []
