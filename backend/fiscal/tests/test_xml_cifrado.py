"""XMLs e evidências cifrados em repouso (ADR 0008, issue #9).

Todos os testes de gravação leem a coluna **bruta** por SQL, sem passar pelo campo do modelo
(que decifraria e esconderia um XML gravado em claro). O que chega ao usuário — download do XML,
DANFSe — continua igual: o modelo devolve o XML em claro.
"""

import hashlib
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django_tenants.utils import schema_context

from core import crypto
from core.permissoes import Perfil
from fiscal.models import EventoNfse, Nfse
from fiscal.persistencia.modelos import (
    DocumentoFiscal,
    EventoFiscal,
    EvidenciaFiscal,
    XmlNaoReconhecido,
)
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
NOTAS = "/api/fiscal/notas/"
S = Nfse.Situacao

# (modelo, coluna) de tudo o que guarda XML ou evidência bruta.
COLUNAS_DE_XML = [
    (Nfse, "xml_dps"),
    (Nfse, "xml_nfse"),
    (EventoNfse, "xml"),
    (EvidenciaFiscal, "conteudo"),
    (DocumentoFiscal, "xml"),
    (EventoFiscal, "xml"),
    (XmlNaoReconhecido, "xml"),
]


def _bruto(modelo, coluna, pk):
    """Bytes que estão de fato no banco (SQL puro, sem decifrar)."""
    tabela = connection.ops.quote_name(modelo._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {coluna} FROM {tabela} WHERE id = %s", [pk])  # noqa: S608
        return bytes(cursor.fetchone()[0])


def _brutos(modelo, coluna):
    tabela = connection.ops.quote_name(modelo._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {coluna} FROM {tabela} WHERE {coluna} IS NOT NULL")  # noqa: S608
        return [bytes(linha[0]) for linha in cursor.fetchall()]


def _emitir(empresa, nota):
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    assert nota.situacao == S.AUTORIZADA
    return nota


def _cancelar(empresa, nota):
    return emissao.cancelar(
        empresa,
        nota,
        codigo_motivo=1,
        justificativa="Nota emitida com o valor errado.",
        usuario=None,
    )


def _sem_o_conteudo_em_claro(bruto, *trechos):
    """O valor gravado é um token e não deixa à mostra nenhum trecho do documento."""
    assert bruto.startswith(b"v1:")
    for trecho in trechos:
        assert trecho not in bruto


# -- a coluna bruta ---------------------------------------------------------------------------


def test_o_xml_da_nfse_e_da_dps_ficam_cifrados_na_coluna_bruta(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())
    xml = sefin.nfses[nota.chave]
    dps = bytes(nota.xml_dps)

    for coluna, claro in (("xml_nfse", xml), ("xml_dps", dps)):
        bruto = _bruto(Nfse, coluna, nota.pk)
        _sem_o_conteudo_em_claro(
            bruto, b"<?xml", nota.chave.encode(), nota.tomador_documento.encode(), claro
        )
    # O modelo devolve o XML em claro, igual ao que a Sefin devolveu.
    assert bytes(Nfse.objects.get(pk=nota.pk).xml_nfse) == xml


def test_o_hash_continua_sendo_o_do_xml_em_claro(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())
    xml = sefin.nfses[nota.chave]
    bruto = _bruto(Nfse, "xml_nfse", nota.pk)

    assert nota.hash_xml_nfse == hashlib.sha256(xml).hexdigest()
    assert nota.hash_xml_nfse != hashlib.sha256(bruto).hexdigest()
    documento = DocumentoFiscal.objects.get(chave=nota.chave)
    assert documento.sha256 == nota.hash_xml_nfse


def test_todas_as_colunas_de_xml_estao_cifradas_depois_de_emitir_e_cancelar(
    empresa_pronta, nova_nota, sefin
):
    nota = _emitir(empresa_pronta, nova_nota())
    _cancelar(empresa_pronta, nota)

    for modelo, coluna in COLUNAS_DE_XML:
        for bruto in _brutos(modelo, coluna):
            _sem_o_conteudo_em_claro(bruto, b"<?xml", nota.chave.encode())
    # Há mesmo o que conferir nas colunas principais (o teste não passa por estarem vazias).
    for modelo, coluna in COLUNAS_DE_XML[:5]:
        assert _brutos(modelo, coluna), f"{modelo.__name__}.{coluna} ficou vazia"
    saida = io.StringIO()
    call_command("verificar_cifragem", stdout=saida)
    assert "estão cifrados" in saida.getvalue()


def test_o_mesmo_xml_gravado_duas_vezes_nao_gera_o_mesmo_valor(empresa_pronta, nova_nota, sefin):
    primeira = _emitir(empresa_pronta, nova_nota())
    segunda = _emitir(empresa_pronta, nova_nota())
    xml = bytes(primeira.xml_nfse)
    Nfse.objects.filter(pk=segunda.pk).update(xml_nfse=xml)
    Nfse.objects.filter(pk=primeira.pk).update(xml_nfse=xml)

    assert _bruto(Nfse, "xml_nfse", primeira.pk) != _bruto(Nfse, "xml_nfse", segunda.pk)


# -- o que o usuário recebe segue igual --------------------------------------------------------


def _baixar(api, nota_id, destino):
    return api.get(f"{NOTAS}{nota_id}/{destino}/")


def test_download_do_xml_e_danfse_partem_da_coluna_cifrada(
    empresa_pronta, empresa_a, nova_nota, sefin, api_de
):
    nota = _emitir(empresa_pronta, nova_nota())
    xml = sefin.nfses[nota.chave]
    assert xml not in _bruto(Nfse, "xml_nfse", nota.pk)
    emissor = api_de(empresa_a, Perfil.EMISSOR)

    resposta_xml = _baixar(emissor, nota.pk, "xml")
    resposta_pdf = _baixar(emissor, nota.pk, "danfse")

    assert resposta_xml.status_code == 200 and resposta_xml.content == xml
    assert resposta_xml["Content-Type"] == "application/xml"
    assert resposta_pdf.status_code == 200 and resposta_pdf.content.startswith(b"%PDF")


# -- adulteração -------------------------------------------------------------------------------


def test_valor_cifrado_adulterado_nao_e_lido_como_xml(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())
    tabela = connection.ops.quote_name(Nfse._meta.db_table)
    with connection.cursor() as cursor:
        # Troca um byte do meio do texto cifrado.
        cursor.execute(
            f"UPDATE {tabela} "  # noqa: S608
            "SET xml_nfse = overlay(xml_nfse placing '\\x00'::bytea from 40 for 1) WHERE id = %s",
            [nota.pk],
        )

    with pytest.raises(crypto.ErroDeCriptografia):
        Nfse.objects.get(pk=nota.pk).xml_nfse  # noqa: B018


def test_xml_trocado_por_outro_cifrado_valido_e_barrado_pelo_hash(
    empresa_pronta, empresa_a, nova_nota, sefin, api_de
):
    """Quem escreve no banco copia o valor cifrado de uma nota para outra: o GCM aceita (o valor
    é autêntico), mas o hash gravado na nota não confere e o XML trocado não é entregue."""
    uma = _emitir(empresa_pronta, nova_nota())
    outra = _emitir(empresa_pronta, nova_nota())
    emissor = api_de(empresa_a, Perfil.EMISSOR)
    xml_da_outra = sefin.nfses[outra.chave]
    assert sefin.nfses[uma.chave] != xml_da_outra
    with schema_context(empresa_a.schema_name):
        tabela = connection.ops.quote_name(Nfse._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {tabela} SET xml_nfse = (SELECT xml_nfse FROM {tabela} WHERE id = %s) "  # noqa: S608
                "WHERE id = %s",
                [outra.pk, uma.pk],
            )

    resposta = _baixar(emissor, uma.pk, "xml")

    assert resposta.status_code == 500
    assert resposta.json()["codigo"] == "xml_nao_confere"
    assert xml_da_outra not in resposta.content
    # A nota que não foi mexida continua sendo entregue normalmente.
    assert _baixar(emissor, outra.pk, "xml").content == xml_da_outra


# -- rotação de chave --------------------------------------------------------------------------


def test_a_rotacao_de_chave_recriptografa_tambem_os_xmls(
    settings, empresa_pronta, nova_nota, sefin
):
    nota = _emitir(empresa_pronta, nova_nota())
    xml = sefin.nfses[nota.chave]
    chave_antiga = settings.FREENFSE_CHAVES[0].split(":", 1)[1]
    settings.FREENFSE_CHAVES = [f"2:{crypto.gerar_chave()}", f"1:{chave_antiga}"]

    call_command("recriptografar", stdout=io.StringIO())

    for modelo, coluna in COLUNAS_DE_XML:
        for bruto in _brutos(modelo, coluna):
            assert bruto.startswith(b"v2:")
    assert bytes(Nfse.objects.get(pk=nota.pk).xml_nfse) == xml
    # Sem a chave antiga na configuração, tudo continua legível.
    settings.FREENFSE_CHAVES = settings.FREENFSE_CHAVES[:1]
    assert bytes(Nfse.objects.get(pk=nota.pk).xml_nfse) == xml


# -- verificação da cifragem -------------------------------------------------------------------


def test_verificar_cifragem_acusa_xml_em_claro_sem_mostrar_o_conteudo(
    empresa_pronta, nova_nota, sefin
):
    nota = _emitir(empresa_pronta, nova_nota())
    tabela = connection.ops.quote_name(Nfse._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {tabela} SET xml_nfse = %s WHERE id = %s",  # noqa: S608
            [b"<NFSe>conteudo-em-claro-do-teste</NFSe>", nota.pk],
        )
    erro, saida = io.StringIO(), io.StringIO()

    with pytest.raises(CommandError, match="em claro"):
        call_command("verificar_cifragem", stdout=saida, stderr=erro)

    assert "fiscal.Nfse.xml_nfse" in erro.getvalue()
    assert "conteudo-em-claro-do-teste" not in erro.getvalue() + saida.getvalue()


def test_verificar_cifragem_passa_quando_nao_ha_nada_em_claro(empresa_a):
    with schema_context(empresa_a.schema_name):
        saida = io.StringIO()
        call_command("verificar_cifragem", stdout=saida)
    assert "estão cifrados" in saida.getvalue()


def test_o_schema_de_cada_empresa_e_conferido(empresa_a, empresa_b):
    with schema_context(empresa_b.schema_name):
        tabela = connection.ops.quote_name(XmlNaoReconhecido._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {tabela} (nsu, esquema, xml, sha256, criado_em) "  # noqa: S608
                "VALUES ('1', 'x', %s, 'h', now())",
                [b"<x/>"],
            )
    erro = io.StringIO()

    with pytest.raises(CommandError, match="em claro"):
        call_command("verificar_cifragem", stdout=io.StringIO(), stderr=erro)

    assert f"[{empresa_b.schema_name}]" in erro.getvalue()
    assert f"[{empresa_a.schema_name}]" not in erro.getvalue()
