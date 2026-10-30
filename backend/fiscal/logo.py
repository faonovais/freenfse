"""Validação e saneamento dos logos enviados pelas empresas (PNG ou SVG).

O logo é exibido no cabeçalho de todas as telas e viaja em e-mails, então um arquivo malicioso
atingiria todos os usuários da empresa. O SVG é **reescrito por lista de permissões**: só
sobram elementos e atributos conhecidos e inofensivos; scripts, eventos (`on*`), referências
externas, `foreignObject`, animações e estilos com `url()` externo são removidos. O PNG é
validado pela assinatura e pelo cabeçalho (dimensões), sem depender do nome nem do tipo
informado pelo cliente.
"""

import re
import struct
import zlib
from dataclasses import dataclass, field

from lxml import etree

LIMITE_PNG_BYTES = 512 * 1024
LIMITE_SVG_BYTES = 200 * 1024
LIMITE_LADO_PNG = 2000  # pixels
ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"
NS_SVG = "http://www.w3.org/2000/svg"
NS_XLINK = "http://www.w3.org/1999/xlink"

ELEMENTOS_PERMITIDOS = frozenset(
    {
        "svg", "g", "defs", "symbol", "use", "path", "rect", "circle", "ellipse", "line",
        "polyline", "polygon", "text", "tspan", "title", "desc", "linearGradient",
        "radialGradient", "stop", "clipPath", "mask", "pattern", "image", "style",
    }
)  # fmt: skip

ATRIBUTOS_PERMITIDOS = frozenset(
    {
        "id", "class", "viewBox", "width", "height", "x", "y", "cx", "cy", "r", "rx", "ry",
        "x1", "y1", "x2", "y2", "points", "d", "transform", "fill", "fill-opacity",
        "fill-rule", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
        "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "stroke-opacity",
        "opacity", "offset", "stop-color", "stop-opacity", "gradientUnits",
        "gradientTransform", "spreadMethod", "fx", "fy", "clip-path", "clip-rule", "mask",
        "maskUnits", "maskContentUnits", "clipPathUnits", "patternUnits", "patternTransform",
        "patternContentUnits", "style", "font-family", "font-size", "font-weight",
        "font-style", "text-anchor", "dominant-baseline", "letter-spacing", "word-spacing",
        "text-decoration", "preserveAspectRatio", "version", "display", "visibility",
        "dx", "dy", "rotate", "textLength", "lengthAdjust", "href",
    }
)  # fmt: skip

# Atributos de apresentação que aceitam `url(...)`: só referência interna (`url(#id)`).
ATRIBUTOS_COM_URL = frozenset({"fill", "stroke", "clip-path", "mask", "style"})
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_PERIGOSO_NO_CSS = re.compile(
    r"@import|expression\s*\(|javascript:|vbscript:|behavior\s*:|-moz-binding|@charset",
    re.IGNORECASE,
)
_IMAGEM_EMBUTIDA = re.compile(r"data:image/(png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=\s]+")


class ErroDeLogo(ValueError):
    """O arquivo enviado não é um logo aceito (a mensagem é exibida ao usuário)."""


@dataclass
class LogoValidado:
    """Resultado da validação: o conteúdo a guardar e o que foi retirado do arquivo."""

    tipo_conteudo: str
    conteudo: bytes
    removidos: list[str] = field(default_factory=list)


def validar_logo(conteudo):
    """Identifica o formato pelo conteúdo, valida e devolve o logo seguro para guardar."""
    if not conteudo:
        raise ErroDeLogo("O arquivo está vazio.")
    if conteudo.startswith(ASSINATURA_PNG):
        return _validar_png(conteudo)
    if conteudo.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        return _sanear_svg(conteudo)
    raise ErroDeLogo("Envie o logo em PNG ou SVG.")


def _validar_png(conteudo):
    if len(conteudo) > LIMITE_PNG_BYTES:
        raise ErroDeLogo(f"O PNG tem mais de {LIMITE_PNG_BYTES // 1024} KB.")
    cabecalho = conteudo[8:33]  # tamanho(4) + "IHDR"(4) + dados(13) + CRC(4)
    if (
        len(cabecalho) < 25
        or cabecalho[4:8] != b"IHDR"
        or struct.unpack(">I", cabecalho[:4])[0] != 13
    ):
        raise ErroDeLogo("O arquivo não é um PNG válido.")
    if zlib.crc32(cabecalho[4:21]) != struct.unpack(">I", cabecalho[21:25])[0]:
        raise ErroDeLogo("O arquivo não é um PNG válido.")
    largura, altura = struct.unpack(">II", cabecalho[8:16])
    if not (0 < largura <= LIMITE_LADO_PNG and 0 < altura <= LIMITE_LADO_PNG):
        raise ErroDeLogo(f"O PNG deve ter no máximo {LIMITE_LADO_PNG}×{LIMITE_LADO_PNG} pixels.")
    if not conteudo.rstrip(b"\x00").endswith(b"IEND\xaeB`\x82"):
        raise ErroDeLogo("O PNG está incompleto.")
    return LogoValidado("image/png", conteudo)


def _sanear_svg(conteudo):
    if len(conteudo) > LIMITE_SVG_BYTES:
        raise ErroDeLogo(f"O SVG tem mais de {LIMITE_SVG_BYTES // 1024} KB.")
    if re.search(rb"<!ENTITY", conteudo, re.IGNORECASE):
        raise ErroDeLogo("O SVG usa entidades XML, que não são aceitas.")
    analisador = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )
    try:
        raiz = etree.fromstring(conteudo, analisador)  # noqa: S320 - parser endurecido acima
    except etree.XMLSyntaxError:
        raise ErroDeLogo("O arquivo SVG está malformado.") from None
    if raiz.tag != f"{{{NS_SVG}}}svg":
        raise ErroDeLogo("O arquivo não é um SVG.")
    removidos = []
    _sanear_elemento(raiz, removidos)
    saida = etree.tostring(raiz, encoding="utf-8", xml_declaration=False)
    return LogoValidado("image/svg+xml", saida, sorted(set(removidos)))


def _nome_local(etiqueta):
    """(namespace, nome) de uma etiqueta lxml; elementos sem nome (comentários) viram vazio."""
    if not isinstance(etiqueta, str):
        return "", ""
    if etiqueta.startswith("{"):
        namespace, _, nome = etiqueta[1:].partition("}")
        return namespace, nome
    return "", etiqueta


def _sanear_elemento(elemento, removidos):
    for filho in list(elemento):
        namespace, nome = _nome_local(filho.tag)
        if namespace != NS_SVG or nome not in ELEMENTOS_PERMITIDOS:
            removidos.append(f"elemento <{nome or 'desconhecido'}>")
            elemento.remove(filho)
            continue
        if nome == "style" and not _css_seguro(filho.text or ""):
            removidos.append("elemento <style> com conteúdo perigoso")
            elemento.remove(filho)
            continue
        if nome == "image" and not _referencia_segura(filho, imagem=True):
            removidos.append("imagem externa")
            elemento.remove(filho)
            continue
        if nome == "use" and not _referencia_segura(filho, imagem=False):
            removidos.append("referência externa em <use>")
            elemento.remove(filho)
            continue
        _sanear_atributos(filho, removidos)
        _sanear_elemento(filho, removidos)
    _sanear_atributos(elemento, removidos)


def _referencia_segura(elemento, *, imagem):
    """`href` interno (`#id`) ou, em imagens, imagem embutida em base64."""
    valor = (elemento.get("href") or elemento.get(f"{{{NS_XLINK}}}href") or "").strip()
    if valor.startswith("#"):
        return True
    return imagem and _IMAGEM_EMBUTIDA.fullmatch(valor) is not None


def _sanear_atributos(elemento, removidos):
    for atributo in list(elemento.attrib):
        namespace, nome = _nome_local(atributo)
        valor = elemento.attrib[atributo]
        if namespace == NS_XLINK and nome == "href":
            nome, namespace = "href", ""
        elif namespace:
            removidos.append(f"atributo {nome}")
            del elemento.attrib[atributo]
            continue
        if nome not in ATRIBUTOS_PERMITIDOS:
            removidos.append(f"atributo {nome}")
            del elemento.attrib[atributo]
        elif nome == "href":
            if not _referencia_segura(elemento, imagem=elemento.tag.endswith("}image")):
                removidos.append("href externo")
                del elemento.attrib[atributo]
        elif nome in ATRIBUTOS_COM_URL and not _css_seguro(valor):
            removidos.append(f"valor perigoso em {nome}")
            del elemento.attrib[atributo]


def _css_seguro(texto):
    r"""CSS sem importação, script nem `url()` que não aponte para `#id` do próprio arquivo.

    Barra também a barra invertida: no CSS ela escreve caracteres (`\75rl(` vira `url(`) e
    permitiria esconder uma referência externa dos testes abaixo.
    """
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.DOTALL)
    if "\\" in texto or _PERIGOSO_NO_CSS.search(texto):
        return False
    return all(url.strip().startswith("#") for _, url in _URL.findall(texto))
