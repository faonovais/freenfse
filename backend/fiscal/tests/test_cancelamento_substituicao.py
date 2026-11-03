"""Cancelamento, substituição e DANFSe: a nota só muda depois de a Sefin confirmar o evento."""

import datetime as dt

import pytest
from freedfe.pdf.danfse import GeradorDanfse
from lxml import etree

from core.models import LogAuditoria
from fiscal.models import EventoNfse, Nfse
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse

pytestmark = pytest.mark.django_db
S = Nfse.Situacao
NS = "{http://www.sped.fazenda.gov.br/nfse}"
JUSTIFICATIVA = "Nota emitida com o valor errado."


@pytest.fixture
def autorizada(empresa_pronta, nova_nota, sefin):
    nota = nova_nota()
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    emissao.executar_emissao(empresa_pronta, nota.pk)
    nota.refresh_from_db()
    assert nota.situacao == S.AUTORIZADA
    return nota


def _cancelar(empresa, nota, **extra):
    dados = {"codigo_motivo": 1, "justificativa": JUSTIFICATIVA, "usuario": None}
    dados.update(extra)
    return emissao.cancelar(empresa, nota, **dados)


def _posts_de_evento(sefin):
    return [c for c in sefin.chamadas if c[0] == "POST" and c[1].endswith("/eventos")]


# -- cancelamento ------------------------------------------------------------------------


def test_cancelamento_confirmado_muda_a_nota_e_guarda_o_evento(empresa_pronta, autorizada, sefin):
    nota = _cancelar(empresa_pronta, autorizada)

    assert nota.situacao == S.CANCELADA
    evento = EventoNfse.objects.get(nfse=nota)
    assert evento.tipo_evento == "101101" and evento.rotulo == "Cancelamento"
    assert evento.hash_xml and bytes(evento.xml).startswith(b"<?xml")
    assert len(_posts_de_evento(sefin)) == 1
    assert [t.para for t in nota.transicoes.all()][-1] == "cancelada"
    assert "nfse_cancelada" in set(LogAuditoria.objects.values_list("acao", flat=True))


def test_cancelamento_recusado_por_prazo_mantem_a_nota_e_explica(empresa_pronta, autorizada, sefin):
    sefin.cancelamento_recusado = ("E0824", "Prazo de cancelamento expirado pelo município.")

    with pytest.raises(emissao.CancelamentoRecusado) as erro:
        _cancelar(empresa_pronta, autorizada)

    autorizada.refresh_from_db()
    assert autorizada.situacao == S.AUTORIZADA  # nada mudou: a Sefin não confirmou
    assert not EventoNfse.objects.exists()
    primeiro = erro.value.erros[0]
    assert primeiro["codigo"] == "E0824"
    assert "prazo" in primeiro["explicacao"] and "prefeitura" in primeiro["orientacao"]
    assert "análise fiscal" in primeiro["orientacao"]
    assert "nfse_cancelamento_recusado" in set(LogAuditoria.objects.values_list("acao", flat=True))


def test_cancelamento_sem_resposta_da_sefin_nao_cancela(empresa_pronta, autorizada, sefin):
    sefin.fora_do_ar = True

    with pytest.raises(emissao.CancelamentoIncerto, match="continua autorizada"):
        _cancelar(empresa_pronta, autorizada)

    autorizada.refresh_from_db()
    assert autorizada.situacao == S.AUTORIZADA


def test_nota_ja_cancelada_na_sefin_e_atualizada_ao_tentar_cancelar(
    empresa_pronta, autorizada, sefin
):
    sefin.eventos[autorizada.chave] = [sefin._evento(autorizada.chave, "101101", "Por outro meio")]

    with pytest.raises(emissao.CancelamentoRecusado) as erro:
        _cancelar(empresa_pronta, autorizada)

    assert erro.value.erros[0]["codigo"] == "E0840"
    autorizada.refresh_from_db()
    assert autorizada.situacao == S.CANCELADA  # o evento existe na Sefin: a nota acompanha


@pytest.mark.parametrize("justificativa", ["", "curta demais", "x" * 256])
def test_justificativa_fora_de_15_a_255_caracteres_nao_chega_a_sefin(
    empresa_pronta, autorizada, sefin, justificativa
):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _cancelar(empresa_pronta, autorizada, justificativa=justificativa)

    assert "justificativa" in erro.value.erros
    assert not _posts_de_evento(sefin)


def test_motivo_de_cancelamento_invalido_e_recusado(empresa_pronta, autorizada, sefin):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        _cancelar(empresa_pronta, autorizada, codigo_motivo=7)

    assert "codigo_motivo" in erro.value.erros


def test_so_nota_autorizada_pode_ser_cancelada(empresa_pronta, autorizada, sefin):
    nota = _cancelar(empresa_pronta, autorizada)

    with pytest.raises(emissao.ErroDeEmissao, match="Só é possível cancelar uma nota autorizada"):
        _cancelar(empresa_pronta, nota)
    assert len(_posts_de_evento(sefin)) == 1


def test_consultar_traz_o_cancelamento_feito_por_fora(empresa_pronta, autorizada, sefin):
    sefin.eventos[autorizada.chave] = [sefin._evento(autorizada.chave, "101101", "Pela prefeitura")]

    nota = emissao.consultar(empresa_pronta, autorizada)

    assert nota.situacao == S.CANCELADA
    assert EventoNfse.objects.filter(nfse=nota, tipo_evento="101101").exists()


def test_consultar_nota_sem_chave_explica(empresa_pronta, nova_nota, sefin):
    with pytest.raises(emissao.ErroDeEmissao, match="ainda não foi autorizada"):
        emissao.consultar(empresa_pronta, nova_nota())


# -- substituição ------------------------------------------------------------------------


def _substituir(empresa, original, **extra):
    dados = {"codigo_motivo": "01", "motivo": "", "usuario": None}
    dados.update(extra)
    substituta = servico_nfse.criar_substituta(original, **dados)
    emissao.solicitar_emissao(substituta, usuario=None, empresa=empresa)
    emissao.executar_emissao(empresa, substituta.pk)
    substituta.refresh_from_db()
    return substituta


def test_substituta_referencia_a_original_que_vira_substituida(empresa_pronta, autorizada, sefin):
    substituta = _substituir(empresa_pronta, autorizada, codigo_motivo="02")

    assert substituta.situacao == S.AUTORIZADA
    assert substituta.substitui_id == autorizada.pk
    autorizada.refresh_from_db()
    assert autorizada.situacao == S.SUBSTITUIDA
    assert EventoNfse.objects.filter(nfse=autorizada, tipo_evento="105102").exists()
    dps = etree.fromstring(bytes(substituta.xml_dps))
    assert dps.findtext(f".//{NS}subst/{NS}chSubstda") == autorizada.chave
    assert dps.findtext(f".//{NS}subst/{NS}cMotivo") == "02"
    assert substituta.numero_dps == autorizada.numero_dps + 1  # nota nova, número novo
    assert "nfse_substituida" in set(LogAuditoria.objects.values_list("acao", flat=True))


def test_original_so_vira_substituida_quando_a_sefin_confirma(empresa_pronta, autorizada, sefin):
    sefin.registrar_substituicao = False  # a Sefin autoriza a nova, mas não registra o evento

    substituta = _substituir(empresa_pronta, autorizada)

    autorizada.refresh_from_db()
    assert substituta.situacao == S.AUTORIZADA
    assert autorizada.situacao == S.AUTORIZADA  # sem evento, nada muda

    sefin._registrar_substituicao(autorizada.chave, substituta.chave)  # a Sefin registra depois
    resumo = emissao.reconciliar_pendentes()

    autorizada.refresh_from_db()
    assert autorizada.situacao == S.SUBSTITUIDA
    assert resumo.substituicoes_confirmadas == 1


def test_nao_ha_duas_substitutas_para_a_mesma_nota(empresa_pronta, autorizada, sefin):
    servico_nfse.criar_substituta(autorizada, codigo_motivo="01", motivo="", usuario=None)

    with pytest.raises(servico_nfse.ErroDeNota, match="substituta em andamento"):
        servico_nfse.criar_substituta(autorizada, codigo_motivo="01", motivo="", usuario=None)


def test_so_nota_autorizada_pode_ser_substituida(empresa_pronta, nova_nota, sefin):
    with pytest.raises(servico_nfse.ErroDeNota, match="Só uma nota autorizada"):
        servico_nfse.criar_substituta(nova_nota(), codigo_motivo="01", motivo="", usuario=None)


@pytest.mark.parametrize(
    ("codigo", "motivo", "campo"),
    [("77", "", "codigo_motivo"), ("99", "curto", "motivo"), ("99", "", "motivo")],
)
def test_motivos_de_substituicao_invalidos(empresa_pronta, autorizada, codigo, motivo, campo):
    with pytest.raises(servico_nfse.ErroDeNota) as erro:
        servico_nfse.criar_substituta(autorizada, codigo_motivo=codigo, motivo=motivo, usuario=None)

    assert campo in erro.value.erros


# -- DANFSe ------------------------------------------------------------------------------


@pytest.fixture
def situacoes_do_danfse(monkeypatch):
    """Espia a situação que chega ao gerador do DANFSe (é ela que decide a marca d'água)."""
    recebidas = []
    original = GeradorDanfse.gerar_bytes

    def espiao(self, xml, modelo, situacao=None):
        recebidas.append(situacao.value if situacao else None)
        return original(self, xml, modelo, situacao)

    monkeypatch.setattr(GeradorDanfse, "gerar_bytes", espiao)
    return recebidas


def test_danfse_da_nota_autorizada_nao_leva_marca_dagua(
    empresa_pronta, autorizada, sefin, situacoes_do_danfse
):
    pdf = emissao.gerar_danfse(empresa_pronta, autorizada)

    assert pdf.startswith(b"%PDF")
    assert situacoes_do_danfse == ["autorizado"]


def test_danfse_da_nota_cancelada_leva_marca_dagua(
    empresa_pronta, autorizada, sefin, situacoes_do_danfse
):
    pdf_autorizada = emissao.gerar_danfse(empresa_pronta, autorizada)
    nota = _cancelar(empresa_pronta, autorizada)

    pdf_cancelada = emissao.gerar_danfse(empresa_pronta, nota)

    assert situacoes_do_danfse == ["autorizado", "cancelado"]
    assert pdf_cancelada.startswith(b"%PDF") and pdf_cancelada != pdf_autorizada


def test_danfse_da_nota_substituida_leva_marca_dagua(
    empresa_pronta, autorizada, sefin, situacoes_do_danfse
):
    _substituir(empresa_pronta, autorizada)
    autorizada.refresh_from_db()

    emissao.gerar_danfse(empresa_pronta, autorizada)

    assert situacoes_do_danfse == ["substituido"]


def test_danfse_nao_e_guardado_e_so_existe_para_nota_emitida(
    empresa_pronta, autorizada, nova_nota, sefin
):
    antes = [campo.name for campo in Nfse._meta.get_fields()]
    emissao.gerar_danfse(empresa_pronta, autorizada)
    assert [campo.name for campo in Nfse._meta.get_fields()] == antes  # nada de PDF no modelo

    with pytest.raises(emissao.ErroDeEmissao, match="só existe para nota autorizada"):
        emissao.gerar_danfse(empresa_pronta, nova_nota())


def test_competencia_e_data_do_relogio_nao_misturam(autorizada):
    assert autorizada.competencia == dt.date(2026, 10, 1)
