"""Logo da empresa: PNG/SVG, saneamento de SVG malicioso, entrega segura e identidade."""

import base64
import hashlib
import struct
import zlib

import pytest
from django_tenants.utils import schema_context

from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal import logo as logos
from fiscal.models import LogoEmpresa

LOGO = "/api/fiscal/logo/{tema}/"
IDENTIDADE = "/api/fiscal/identidade/"
pytestmark = pytest.mark.django_db


def png(largura=64, altura=32):
    """Gera um PNG mínimo e válido (cabeçalho, um pixel de dados e IEND)."""

    def bloco(tipo, dados):
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo))

    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 0, 0, 0, 0)
    linhas = zlib.compress((b"\x00" + b"\x80" * largura) * altura)
    return (
        logos.ASSINATURA_PNG + bloco(b"IHDR", ihdr) + bloco(b"IDAT", linhas) + bloco(b"IEND", b"")
    )


SVG_BOM = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" width="40" height="40">'
    b'<title>Logo</title><defs><linearGradient id="g"><stop offset="0" stop-color="#ff5900"/>'
    b'</linearGradient></defs><rect width="10" height="10" fill="url(#g)"/>'
    b'<circle cx="5" cy="5" r="3" style="fill:#fff;stroke:#000"/></svg>'
)


def svg(corpo, raiz_extra=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 10 10" {raiz_extra}>{corpo}</svg>'
    ).encode()


def _enviar(api, tema, arquivo):
    return api.put_arquivo(LOGO.format(tema=tema), arquivo, nome="logo")


# --- PNG ----------------------------------------------------------------------------------


def test_png_valido_e_guardado_e_entregue_igual(api_de, empresa_a):
    api = api_de(empresa_a)
    arquivo = png()

    resposta = _enviar(api, "claro", arquivo)
    baixado = api.get(LOGO.format(tema="claro"))

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["tipo_conteudo"] == "image/png"
    assert resposta.json()["sha256"] == hashlib.sha256(arquivo).hexdigest()
    assert baixado.status_code == 200 and baixado.content == arquivo
    assert baixado["Content-Type"] == "image/png"


@pytest.mark.parametrize(
    ("arquivo", "trecho"),
    [
        (b"", "vazio"),
        (b"MZ\x90\x00 isto e um executavel", "PNG ou SVG"),
        (b"GIF89a....", "PNG ou SVG"),
        (logos.ASSINATURA_PNG + b"curto", "PNG válido"),
        (png(largura=3000, altura=10), "pixels"),
        (png(largura=10, altura=3000), "pixels"),
        (png()[:-12], "incompleto"),  # sem o bloco IEND
        (png() + b"\x00" * (600 * 1024), "KB"),
    ],
)
def test_png_invalido_e_recusado(api_de, empresa_a, arquivo, trecho):
    resposta = _enviar(api_de(empresa_a), "claro", arquivo)

    assert resposta.status_code == 400
    assert trecho in resposta.json()["arquivo"][0]
    with schema_context(empresa_a.schema_name):
        assert LogoEmpresa.objects.count() == 0


def test_png_com_cabecalho_adulterado_e_recusado(api_de, empresa_a):
    adulterado = bytearray(png())
    adulterado[16] ^= 0xFF  # muda a largura sem refazer o CRC do IHDR

    resposta = _enviar(api_de(empresa_a), "claro", bytes(adulterado))

    assert resposta.status_code == 400


def test_o_formato_vem_do_conteudo_e_nao_do_nome(api_de, empresa_a):
    api = api_de(empresa_a)

    resposta = api.put_arquivo(LOGO.format(tema="claro"), png(), nome="logo.svg")
    falso = api.put_arquivo(LOGO.format(tema="escuro"), b"<?php evil(); ?>", nome="logo.png")

    assert resposta.json()["tipo_conteudo"] == "image/png"
    assert falso.status_code == 400


# --- SVG ----------------------------------------------------------------------------------


def test_svg_inofensivo_passa_sem_perder_o_desenho(api_de, empresa_a):
    api = api_de(empresa_a)

    resposta = _enviar(api, "claro", SVG_BOM)
    entregue = api.get(LOGO.format(tema="claro"))

    assert resposta.status_code == 201 and resposta.json()["removidos"] == []
    assert resposta.json()["tipo_conteudo"] == "image/svg+xml"
    corpo = entregue.content.decode()
    for esperado in ("<rect", "<circle", "linearGradient", 'fill="url(#g)"', "style=", "<title>"):
        assert esperado in corpo


MALICIOSOS = {
    "script": svg('<script>alert(1)</script><rect width="5" height="5"/>'),
    "onload na raiz": svg('<rect width="5" height="5"/>', 'onload="alert(1)"'),
    "onclick": svg('<rect width="5" height="5" onclick="alert(1)"/>'),
    "onmouseover": svg('<circle r="2" onmouseover="alert(1)"/>'),
    "link javascript": svg('<a href="javascript:alert(1)"><rect width="5" height="5"/></a>'),
    "use externo": svg('<use href="https://evil.example/x.svg#a"/>'),
    "use externo xlink": svg('<use xlink:href="https://evil.example/x.svg#a"/>'),
    "imagem externa": svg('<image href="https://evil.example/pixel.png" width="5" height="5"/>'),
    "imagem externa xlink": svg('<image xlink:href="http://evil.example/p.png" width="5"/>'),
    "imagem html": svg('<image href="data:text/html;base64,PHNjcmlwdD4=" width="5"/>'),
    "imagem svg embutida": svg(
        '<image href="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=" width="5"/>'
    ),
    "foreignObject": svg(
        '<foreignObject><body xmlns="http://www.w3.org/1999/xhtml" onload="x()"/></foreignObject>'
    ),
    "iframe html": svg('<iframe xmlns="http://www.w3.org/1999/xhtml" src="https://evil.example"/>'),
    "animate de href": svg('<a><animate attributeName="href" values="javascript:alert(1)"/></a>'),
    "set": svg('<rect width="5" height="5"><set attributeName="onload" to="alert(1)"/></rect>'),
    "estilo com import": svg(
        '<style>@import url(https://evil.example/x.css);</style><rect width="5"/>'
    ),
    "estilo com url externa": svg(
        '<style>rect{fill:url(https://evil.example/p)}</style><rect width="5"/>'
    ),
    "estilo com escape css": svg(r"<style>rect{background:\75rl(https://evil.example/p)}</style>"),
    "atributo style com url": svg('<rect width="5" style="fill:url(https://evil.example/p)"/>'),
    "fill com url externa": svg('<rect width="5" fill="url(https://evil.example/p)"/>'),
    "expression": svg('<rect width="5" style="width:expression(alert(1))"/>'),
    "filtro": svg(
        '<filter id="f"><feImage href="https://evil.example/x"/></filter><rect filter="url(#f)"/>'
    ),
    "elemento de outro namespace": svg('<x:script xmlns:x="http://evil.example/ns">1</x:script>'),
}


# Trechos que não podem sobrar no SVG entregue, em minúsculas.
PERIGOSOS = (
    "<script", "onload", "onclick", "onmouseover", "javascript:", "evil.example",
    "foreignobject", "<iframe", "<animate", "<set", "@import", "expression", "<filter",
    "<feimage", "data:text/html", "data:image/svg", "\\75",
)  # fmt: skip


@pytest.mark.parametrize("nome", MALICIOSOS)
def test_svg_malicioso_e_neutralizado(api_de, empresa_a, nome):
    api = api_de(empresa_a)

    resposta = _enviar(api, "claro", MALICIOSOS[nome])
    entregue = api.get(LOGO.format(tema="claro")).content.decode().lower()

    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["removidos"], "deveria ter removido algo"
    for perigoso in PERIGOSOS:
        assert perigoso not in entregue, f"{perigoso!r} sobrou em {nome}"


def test_o_desenho_inofensivo_sobrevive_ao_saneamento(api_de, empresa_a):
    api = api_de(empresa_a)

    _enviar(
        api,
        "claro",
        svg('<script>x()</script><rect width="5" height="5" fill="#ff5900" onclick="x()"/>'),
    )
    entregue = api.get(LOGO.format(tema="claro")).content.decode()

    assert '<rect width="5" height="5" fill="#ff5900"' in entregue


def test_imagem_png_embutida_em_base64_e_permitida(api_de, empresa_a):
    dados = base64.b64encode(png()).decode()
    arquivo = svg(f'<image href="data:image/png;base64,{dados}" width="5" height="5"/>')

    resposta = _enviar(api_de(empresa_a), "claro", arquivo)

    assert resposta.status_code == 201 and resposta.json()["removidos"] == []


def test_referencia_interna_por_id_e_permitida(api_de, empresa_a):
    arquivo = svg('<defs><path id="a" d="M0 0h5v5z"/></defs><use href="#a"/><use xlink:href="#a"/>')

    resposta = _enviar(api_de(empresa_a), "claro", arquivo)

    assert resposta.status_code == 201 and resposta.json()["removidos"] == []


@pytest.mark.parametrize(
    ("arquivo", "trecho"),
    [
        (b'<svg xmlns="http://www.w3.org/2000/svg"><rect', "malformado"),
        (b"<html><body>nao e svg</body></html>", "não é um SVG"),
        (b'<svg xmlns="http://evil.example/ns"/>', "não é um SVG"),
        (
            b'<!DOCTYPE svg [<!ENTITY a "AAAA"><!ENTITY b "&a;&a;&a;&a;">]>'
            b'<svg xmlns="http://www.w3.org/2000/svg"><text>&b;</text></svg>',
            "entidades",
        ),
        (
            b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
            "entidades",
        ),
        (b"<svg xmlns='http://www.w3.org/2000/svg'>" + b"<g>" * 10 + b"x" * (210 * 1024), "KB"),
    ],
)
def test_svg_invalido_e_recusado(api_de, empresa_a, arquivo, trecho):
    resposta = _enviar(api_de(empresa_a), "claro", arquivo)

    assert resposta.status_code == 400
    assert trecho in resposta.json()["arquivo"][0]


def test_o_que_foi_removido_vai_para_a_auditoria(api_de, empresa_a, usuario):
    _enviar(api_de(empresa_a), "claro", MALICIOSOS["script"])

    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.LOGO_ALTERADO)
    assert registro.usuario == usuario and registro.empresa == empresa_a
    assert "elemento <script>" in registro.detalhes["removidos"]


# --- Entrega, tema, permissões e isolamento ------------------------------------------------


def test_svg_e_entregue_com_cabecalhos_que_impedem_script(api_de, empresa_a):
    api = api_de(empresa_a)
    _enviar(api, "claro", SVG_BOM)

    resposta = api.get(LOGO.format(tema="claro"))

    assert resposta["Content-Type"] == "image/svg+xml"
    assert "sandbox" in resposta["Content-Security-Policy"]
    assert "default-src 'none'" in resposta["Content-Security-Policy"]
    assert resposta["X-Content-Type-Options"] == "nosniff"
    assert resposta["Cache-Control"] == "private, no-cache"


def test_sem_logo_escuro_usa_o_claro(api_de, empresa_a):
    api = api_de(empresa_a)
    _enviar(api, "claro", png(10, 10))

    assert api.get(LOGO.format(tema="escuro")).content == png(10, 10)
    _enviar(api, "escuro", png(20, 20))
    assert api.get(LOGO.format(tema="escuro")).content == png(20, 20)
    assert api.get(LOGO.format(tema="claro")).content == png(10, 10)


def test_sem_nenhum_logo_responde_404(api_de, empresa_a):
    api = api_de(empresa_a)

    assert api.get(LOGO.format(tema="claro")).status_code == 404
    assert api.get(LOGO.format(tema="escuro")).status_code == 404


def test_cache_condicional_por_etag(api_de, empresa_a):
    api = api_de(empresa_a)
    enviado = _enviar(api, "claro", png()).json()

    resposta = api.cliente.get(
        LOGO.format(tema="claro"),
        HTTP_X_EMPRESA=str(empresa_a.pk),
        HTTP_IF_NONE_MATCH=f'"{enviado["sha256"]}"',
    )

    assert resposta.status_code == 304 and resposta.content == b""


def test_tema_invalido_e_recusado(api_de, empresa_a):
    api = api_de(empresa_a)

    assert api.get(LOGO.format(tema="roxo")).status_code == 400
    assert _enviar(api, "roxo", png()).status_code == 400


def test_substituir_e_remover(api_de, empresa_a):
    api = api_de(empresa_a)
    _enviar(api, "claro", png(10, 10))
    _enviar(api, "claro", png(20, 20))

    assert api.get(LOGO.format(tema="claro")).content == png(20, 20)
    assert api.delete(LOGO.format(tema="claro")).status_code == 204
    assert api.get(LOGO.format(tema="claro")).status_code == 404
    with schema_context(empresa_a.schema_name):
        assert LogoEmpresa.objects.count() == 0


def test_sem_arquivo_e_recusado(api_de, empresa_a):
    resposta = api_de(empresa_a).cliente.put(
        LOGO.format(tema="claro"), {}, format="multipart", HTTP_X_EMPRESA=str(empresa_a.pk)
    )

    assert resposta.status_code == 400


@pytest.mark.parametrize("perfil", [Perfil.CONSULTA, Perfil.FINANCEIRO, Perfil.EMISSOR])
def test_todos_os_vinculados_veem_o_logo_mas_so_config_editar_altera(
    api_de, api_do_master, empresa_a, perfil
):
    _enviar(api_do_master(empresa_a), "claro", png())
    api = api_de(empresa_a, perfil)

    assert api.get(LOGO.format(tema="claro")).status_code == 200
    assert _enviar(api, "claro", png()).status_code == 403
    assert api.delete(LOGO.format(tema="claro")).status_code == 403


def test_sem_vinculo_nao_ve_o_logo(cliente_de, usuario, api_do_master, empresa_a):
    _enviar(api_do_master(empresa_a), "claro", png())

    resposta = cliente_de(usuario).get(LOGO.format(tema="claro"), HTTP_X_EMPRESA=str(empresa_a.pk))

    assert resposta.status_code == 403


def test_logo_da_empresa_a_nao_aparece_na_b(api_do_master, empresa_a, empresa_b):
    _enviar(api_do_master(empresa_a), "claro", png(10, 10))
    _enviar(api_do_master(empresa_b), "claro", png(20, 20))

    assert api_do_master(empresa_a).get(LOGO.format(tema="claro")).content == png(10, 10)
    assert api_do_master(empresa_b).get(LOGO.format(tema="claro")).content == png(20, 20)
    assert api_do_master(empresa_b).get(IDENTIDADE).json()["logo"] == {
        "claro": hashlib.sha256(png(20, 20)).hexdigest()
    }


# --- Identidade da empresa (ambiente, logo, certificado) ----------------------------------


@pytest.mark.parametrize(
    "perfil", [Perfil.CONSULTA, Perfil.FINANCEIRO, Perfil.EMISSOR, Perfil.ADMINISTRADOR]
)
def test_identidade_e_visivel_para_todos_os_vinculados(api_de, empresa_a, perfil):
    corpo = api_de(empresa_a, perfil).get(IDENTIDADE).json()

    assert corpo["ambiente"] == "producao_restrita"
    assert corpo["ambiente_rotulo"] == "Produção restrita (testes)"
    assert corpo["logo"] == {}
    assert corpo["certificado"] == {
        "existe": False, "vencido": False, "dias_para_vencer": None, "faixa_alerta": None,
    }  # fmt: skip


def test_identidade_acompanha_o_ambiente_e_os_logos(api_de, empresa_a):
    api = api_de(empresa_a)
    api.patch("/api/fiscal/parametros/", {"ambiente": "producao", "confirmar_producao": True})
    sha = _enviar(api, "claro", png()).json()["sha256"]

    corpo = api.get(IDENTIDADE).json()

    assert corpo["ambiente"] == "producao" and corpo["logo"] == {"claro": sha}


def test_identidade_sem_vinculo_e_negada(cliente_de, usuario, empresa_a):
    resposta = cliente_de(usuario).get(IDENTIDADE, HTTP_X_EMPRESA=str(empresa_a.pk))

    assert resposta.status_code == 403
