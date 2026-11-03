"""`RepositorioDocumentosPostgres`: XML íntegro, hash conferido, eventos e isolamento."""

import hashlib

import pytest
from django.db import connection
from django_tenants.utils import schema_context
from freedfe.distribuicao.retorno import DocumentoRecebido
from freedfe.excecoes import FreeDFeErro
from freedfe.tipos import ModeloDocumento, SituacaoDocumento

from fiscal.persistencia.modelos import DocumentoFiscal, EventoFiscal, XmlNaoReconhecido
from fiscal.persistencia.repositorio import DocumentoAdulteradoErro, RepositorioDocumentosPostgres
from fiscal.tests.persistencia.contrato_estado_emissao import montar_id
from fiscal.tests.xml_ficticio import evento_ficticio, nfse_ficticia

pytestmark = pytest.mark.django_db


@pytest.fixture
def repositorio(empresa_ativa):
    return RepositorioDocumentosPostgres(empresa_ativa.cnpj)


@pytest.fixture
def nota():
    chave, xml = nfse_ficticia(montar_id(1))
    return chave, xml


def test_guarda_o_xml_exatamente_como_chegou_com_o_hash(repositorio, nota):
    chave, xml = nota

    resultado = repositorio.armazenar([DocumentoRecebido(xml=xml)])

    assert resultado.documentos == 1
    resumo = repositorio.obter(ModeloDocumento.NFSE, chave)
    assert repositorio.ler_xml(resumo) == xml
    assert (
        repositorio.hash_do_documento(ModeloDocumento.NFSE, chave)
        == hashlib.sha256(xml).hexdigest()
    )


def test_o_resumo_traz_numero_valor_e_tomador(repositorio, nota):
    chave, xml = nota
    repositorio.armazenar([DocumentoRecebido(xml=xml)])

    resumo = repositorio.obter(ModeloDocumento.NFSE, chave)

    assert resumo.chave == chave
    assert resumo.numero == "1"
    assert str(resumo.valor_total) == "100.00"
    assert resumo.destinatario_documento == "11444777000161"
    assert resumo.situacao is SituacaoDocumento.AUTORIZADO


def test_xml_adulterado_no_banco_e_detectado_na_leitura(repositorio, nota):
    chave, xml = nota
    repositorio.armazenar([DocumentoRecebido(xml=xml)])
    DocumentoFiscal.objects.filter(chave=chave).update(xml=xml.replace(b"100.00", b"999.00"))

    with pytest.raises(DocumentoAdulteradoErro, match="não confere com o hash"):
        repositorio.ler_xml(repositorio.obter(ModeloDocumento.NFSE, chave))


def test_gravar_a_mesma_nota_de_novo_nao_duplica(repositorio, nota):
    _, xml = nota
    repositorio.armazenar([DocumentoRecebido(xml=xml)])
    repositorio.armazenar([DocumentoRecebido(xml=xml)])

    assert DocumentoFiscal.objects.count() == 1


def test_cancelamento_muda_a_situacao_e_tem_precedencia(repositorio, nota):
    chave, xml = nota
    repositorio.armazenar([DocumentoRecebido(xml=xml)])

    repositorio.armazenar([DocumentoRecebido(xml=evento_ficticio(chave, "105102"))])
    assert (
        repositorio.obter_atual(ModeloDocumento.NFSE, chave).situacao
        is SituacaoDocumento.SUBSTITUIDO
    )

    repositorio.armazenar([DocumentoRecebido(xml=evento_ficticio(chave, "101101"))])
    assert (
        repositorio.obter_atual(ModeloDocumento.NFSE, chave).situacao is SituacaoDocumento.CANCELADO
    )
    assert [e.tipo_evento for e in repositorio.eventos(ModeloDocumento.NFSE, chave)] == [
        "105102",
        "101101",
    ]


def test_o_mesmo_evento_chegando_duas_vezes_e_gravado_uma_vez(repositorio, nota):
    chave, xml = nota
    repositorio.armazenar([DocumentoRecebido(xml=xml)])
    evento = evento_ficticio(chave)

    repositorio.armazenar([DocumentoRecebido(xml=evento)])
    repositorio.armazenar([DocumentoRecebido(xml=evento)])

    assert EventoFiscal.objects.count() == 1


def test_xml_desconhecido_e_preservado(repositorio):
    resultado = repositorio.armazenar([DocumentoRecebido(xml=b"<outra-coisa/>")])

    assert resultado.nao_reconhecidos == 1
    assert XmlNaoReconhecido.objects.count() == 1


def test_o_lote_e_tudo_ou_nada(repositorio, nota, monkeypatch):
    chave, xml = nota
    _, outro = nfse_ficticia(montar_id(2))
    gravar = repositorio._gravar_documento
    chamadas = []

    def falha_no_segundo(resumo, conteudo):
        chamadas.append(resumo.chave)
        if len(chamadas) == 2:
            raise FreeDFeErro("falha simulada no meio do lote")
        gravar(resumo, conteudo)

    monkeypatch.setattr(repositorio, "_gravar_documento", falha_no_segundo)

    with pytest.raises(FreeDFeErro):
        repositorio.armazenar([DocumentoRecebido(xml=xml), DocumentoRecebido(xml=outro)])

    assert DocumentoFiscal.objects.count() == 0


def test_cada_empresa_so_enxerga_as_proprias_notas(empresa_a, empresa_b, nota):
    chave, xml = nota
    with schema_context(empresa_a.schema_name):
        RepositorioDocumentosPostgres(empresa_a.cnpj).armazenar([DocumentoRecebido(xml=xml)])
        assert DocumentoFiscal.objects.filter(chave=chave).count() == 1
    with schema_context(empresa_b.schema_name):
        repositorio_b = RepositorioDocumentosPostgres(empresa_b.cnpj)
        assert repositorio_b.obter(ModeloDocumento.NFSE, chave) is None
        assert repositorio_b.listar() == []
        assert DocumentoFiscal.objects.count() == 0


def test_a_tabela_fica_no_schema_da_empresa_e_nao_no_publico(empresa_a):
    with schema_context(empresa_a.schema_name), connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = 'fiscal_documentofiscal'"
        )
        assert {linha[0] for linha in cursor.fetchall()} == {empresa_a.schema_name}


def test_listar_devolve_todas_as_notas_do_modelo(repositorio):
    for numero in (3, 1, 2):
        repositorio.armazenar([DocumentoRecebido(xml=nfse_ficticia(montar_id(numero))[1])])

    assert sorted(r.numero for r in repositorio.listar()) == ["1", "2", "3"]
