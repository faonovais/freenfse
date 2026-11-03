"""Emissão contra a Sefin simulada: autorização, resultado incerto, rejeição e reconciliação.

A biblioteca roda inteira (montagem e assinatura da DPS, envio, consulta); só o transporte HTTP
é trocado. O que os testes conferem é o que **chegou** à Sefin (`sefin.posts_de_emissao`).
"""

import datetime as dt
import hashlib

import pytest
from lxml import etree

from core.models import LogAuditoria
from fiscal.models import Nfse
from fiscal.persistencia.modelos import DocumentoFiscal, EmissaoDps, EvidenciaFiscal
from fiscal.services import emissao
from fiscal.services.nfse_estados import transicionar

pytestmark = pytest.mark.django_db
S = Nfse.Situacao


def _emitir(empresa, nota, usuario=None):
    """Percorre o que a API e a fila fazem: solicitar e executar."""
    emissao.solicitar_emissao(nota, usuario=usuario, empresa=empresa)
    emissao.executar_emissao(empresa, nota.pk)
    nota.refresh_from_db()
    return nota


# -- autorização -------------------------------------------------------------------------


def test_emissao_autorizada_guarda_xml_hash_e_leiaute(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.AUTORIZADA
    assert nota.chave and len(nota.chave) == 50
    assert nota.numero_dps == 1 and nota.serie == 900
    assert nota.numero_nfse == "1"
    assert nota.leiaute == "nt009_v101"  # produção restrita usa sempre a NT 009
    assert nota.id_dps == sefin.posts_de_emissao[0]
    assert bytes(nota.xml_nfse) == sefin.nfses[nota.chave]
    assert nota.hash_xml_nfse == hashlib.sha256(bytes(nota.xml_nfse)).hexdigest()
    assert sefin.total_de_posts == 1


def test_o_xml_guardado_e_o_do_repositorio_com_o_mesmo_hash(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())

    documento = DocumentoFiscal.objects.get(chave=nota.chave)
    assert documento.sha256 == nota.hash_xml_nfse
    assert bytes(documento.xml) == bytes(nota.xml_nfse)


def test_a_dps_enviada_fica_guardada_como_evidencia_e_na_nota(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota(valor="1500.00"))

    dps = bytes(nota.xml_dps)
    raiz = etree.fromstring(dps)
    ns = "{http://www.sped.fazenda.gov.br/nfse}"
    assert raiz.find(f".//{ns}infDPS").get("Id") == nota.id_dps
    assert raiz.findtext(f".//{ns}vServ") == "1500.00"
    assert raiz.findtext(f".//{ns}toma/{ns}xNome") == "TOMADOR FICTICIO LTDA"
    assert raiz.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature") is not None
    evidencia = EvidenciaFiscal.objects.get(id_dps=nota.id_dps, sufixo="dps.xml")
    assert bytes(evidencia.conteudo) == dps


def test_cada_transicao_fica_no_historico(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())

    assert [(t.de, t.para) for t in nota.transicoes.all()] == [
        ("rascunho", "enviando"),
        ("enviando", "autorizada"),
    ]
    acoes = set(LogAuditoria.objects.values_list("acao", flat=True))
    assert {"nfse_emissao_solicitada", "nfse_autorizada"} <= acoes


def test_o_numero_segue_a_sequencia_da_empresa(empresa_pronta, nova_nota, sefin):
    primeira = _emitir(empresa_pronta, nova_nota())
    segunda = _emitir(empresa_pronta, nova_nota(valor="200.00"))

    assert (primeira.numero_dps, segunda.numero_dps) == (1, 2)
    assert (primeira.numero_nfse, segunda.numero_nfse) == ("1", "2")


def test_reentrega_da_tarefa_de_uma_nota_autorizada_nao_envia_de_novo(
    empresa_pronta, nova_nota, sefin
):
    nota = _emitir(empresa_pronta, nova_nota())

    assert emissao.executar_emissao(empresa_pronta, nota.pk) == S.AUTORIZADA
    assert emissao.executar_emissao(empresa_pronta, nota.pk) == S.AUTORIZADA
    assert sefin.total_de_posts == 1


# -- resultado incerto -------------------------------------------------------------------


def test_timeout_deixa_a_nota_incerta_sem_reenviar(empresa_pronta, nova_nota, sefin):
    sefin.proximas("timeout")

    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.INCERTA
    assert "não envia de novo" in nota.mensagem
    assert nota.id_dps and nota.numero_dps == 1
    assert sefin.total_de_posts == 1
    assert EmissaoDps.objects.get(id_dps=nota.id_dps).situacao in ("incerta", "enviada")


def test_erro_5xx_deixa_a_nota_incerta(empresa_pronta, nova_nota, sefin):
    sefin.proximas("5xx")

    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.INCERTA
    assert sefin.total_de_posts == 1


def test_a_reconciliacao_acha_a_nota_ja_autorizada_sem_enviar_de_novo(
    empresa_pronta, nova_nota, sefin
):
    """A resposta se perdeu, mas a Sefin processou: consultar basta; reenviar duplicaria."""
    sefin.proximas("cai_depois_de_processar")
    nota = _emitir(empresa_pronta, nova_nota())
    assert nota.situacao == S.INCERTA and sefin.total_de_posts == 1

    sefin.fora_do_ar = False
    resumo = emissao.reconciliar_pendentes()

    nota.refresh_from_db()
    assert nota.situacao == S.AUTORIZADA
    assert resumo.autorizadas == 1
    assert nota.chave in sefin.nfses
    assert sefin.total_de_posts == 1  # o POST de emissão NÃO foi repetido
    assert EmissaoDps.objects.get(id_dps=nota.id_dps).situacao == "autorizada"
    assert [t.para for t in nota.transicoes.all()] == [
        "enviando",
        "incerta",
        "enviando",
        "autorizada",
    ]


def test_reconciliar_com_a_sefin_fora_do_ar_mantem_a_nota_incerta(empresa_pronta, nova_nota, sefin):
    sefin.proximas("timeout")
    nota = _emitir(empresa_pronta, nova_nota())

    resumo = emissao.reconciliar_pendentes()  # a Sefin segue fora do ar

    nota.refresh_from_db()
    assert nota.situacao == S.INCERTA
    assert resumo.autorizadas == 0
    assert sefin.total_de_posts == 1


def test_nota_nao_localizada_segue_incerta_ate_o_usuario_pedir_novo_envio(
    empresa_pronta, nova_nota, sefin
):
    sefin.proximas("timeout")
    nota = _emitir(empresa_pronta, nova_nota())
    sefin.fora_do_ar = False

    emissao.reconciliar_pendentes()

    nota.refresh_from_db()
    assert nota.situacao == S.INCERTA  # a Sefin não conhece a DPS, mas nada é reenviado sozinho
    assert sefin.total_de_posts == 1


def test_novo_envio_manual_da_incerta_confere_antes_e_reaproveita_o_numero(
    empresa_pronta, nova_nota, sefin
):
    sefin.proximas("timeout")
    nota = _emitir(empresa_pronta, nova_nota())
    id_original = nota.id_dps
    sefin.fora_do_ar = False

    nota = _emitir(empresa_pronta, nota)  # "Tentar de novo"

    assert nota.situacao == S.AUTORIZADA
    assert nota.id_dps == id_original and nota.numero_dps == 1  # nenhum número novo foi gasto
    assert sefin.posts_de_emissao == [id_original, id_original]
    consultas = [c for c in sefin.chamadas if c[0] == "HEAD"]
    assert consultas  # antes de reenviar, a Sefin foi consultada


def test_nao_numera_outra_nota_da_serie_enquanto_ha_uma_incerta(empresa_pronta, nova_nota, sefin):
    sefin.proximas("timeout")
    _emitir(empresa_pronta, nova_nota())

    outra = nova_nota(valor="50.00")
    with pytest.raises(emissao.ErroDeEmissao, match="sem resultado confirmado"):
        emissao.solicitar_emissao(outra, usuario=None, empresa=empresa_pronta)

    outra.refresh_from_db()
    assert outra.situacao == S.RASCUNHO
    assert sefin.total_de_posts == 1


def test_processo_que_cai_depois_do_envio_e_recuperado_pelo_registro(
    empresa_pronta, nova_nota, sefin
):
    """Simula a queda: o registro diz `enviada`, mas a nota ficou presa em 'enviando'."""
    sefin.proximas("cai_depois_de_processar")
    nota = _emitir(empresa_pronta, nova_nota())
    transicionar(nota, S.ENVIANDO, motivo="simula a queda antes de gravar o desfecho")
    nota.refresh_from_db()
    Nfse.objects.filter(pk=nota.pk).update(atualizado_em=sefin.agora.replace(year=2020))
    sefin.fora_do_ar = False

    emissao.reconciliar_pendentes()

    nota.refresh_from_db()
    assert nota.situacao == S.AUTORIZADA
    assert sefin.total_de_posts == 1


# -- rejeição ----------------------------------------------------------------------------


def test_rejeicao_da_sefin_vira_mensagem_didatica(empresa_pronta, nova_nota, sefin):
    sefin.proximas(("rejeitar", [("E0160", "Situação no Simples diverge do cadastro.")]))

    nota = _emitir(empresa_pronta, nova_nota())

    assert nota.situacao == S.REJEITADA
    erro = nota.erros[0]
    assert erro["codigo"] == "E0160"
    assert "Simples Nacional" in erro["explicacao"]
    assert "Parâmetros fiscais" in erro["orientacao"]
    assert erro["descricao_original"] == "Situação no Simples diverge do cadastro."
    assert "Simples" in nota.mensagem
    assert nota.numero_dps == 1 and nota.id_dps


def test_codigo_desconhecido_recebe_orientacao_generica_e_preserva_o_texto(
    empresa_pronta, nova_nota, sefin
):
    sefin.proximas(("rejeitar", [("E7777", "Algo que ninguém previu.")]))

    nota = _emitir(empresa_pronta, nova_nota())

    erro = nota.erros[0]
    assert erro["codigo"] == "E7777" and erro["descricao_original"] == "Algo que ninguém previu."
    assert "recusou" in erro["explicacao"]


def test_reenvio_apos_rejeicao_reaproveita_o_numero_e_guarda_as_duas_tentativas(
    empresa_pronta, nova_nota, sefin
):
    sefin.proximas(("rejeitar", [("E0188", "CNPJ inválido.")]))
    nota = _emitir(empresa_pronta, nova_nota())
    assert nota.situacao == S.REJEITADA
    id_dps = nota.id_dps

    nota = _emitir(empresa_pronta, nota)  # corrigida (aqui: a Sefin passa a aceitar)

    assert nota.situacao == S.AUTORIZADA
    assert nota.id_dps == id_dps and nota.numero_dps == 1  # sem lacuna na numeração
    assert sefin.posts_de_emissao == [id_dps, id_dps]
    registro = EmissaoDps.objects.get(id_dps=id_dps)
    assert registro.tentativas == 2
    tentativas = EvidenciaFiscal.objects.filter(id_dps=id_dps, sufixo="dps.xml")
    assert sorted(tentativas.values_list("tentativa", flat=True)) == [1, 2]


def test_o_proximo_numero_depois_de_uma_rejeicao_nao_repete_o_rejeitado(
    empresa_pronta, nova_nota, sefin
):
    sefin.proximas(("rejeitar", [("E0188", "CNPJ inválido.")]))
    rejeitada = _emitir(empresa_pronta, nova_nota())

    seguinte = _emitir(empresa_pronta, nova_nota(valor="10.00"))

    assert rejeitada.numero_dps == 1 and seguinte.numero_dps == 2
    assert seguinte.situacao == S.AUTORIZADA


def test_dado_invalido_nao_chega_a_sefin_e_a_nota_volta_a_rascunho(
    empresa_pronta, nova_nota, sefin
):
    nota = nova_nota()
    Nfse.objects.filter(pk=nota.pk).update(
        tomador={**nota.tomador, "documento": "11111111111111"}  # CNPJ inválido
    )
    nota.refresh_from_db()

    nota = _emitir(empresa_pronta, nota)

    assert nota.situacao == S.RASCUNHO
    assert "CNPJ" in nota.mensagem
    assert sefin.total_de_posts == 0
    assert not EmissaoDps.objects.exists()  # a reserva de número foi devolvida


# -- bloqueios ---------------------------------------------------------------------------


def test_sem_certificado_a_emissao_e_bloqueada_com_o_motivo(empresa_pronta, nova_nota, sefin):
    from fiscal.models import Certificado

    nota = nova_nota()
    Certificado.objects.all().delete()

    with pytest.raises(emissao.BloqueioDeEmissao) as erro:
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)

    assert [b.codigo for b in erro.value.bloqueios] == ["sem_certificado"]
    assert sefin.total_de_posts == 0


def test_convenio_nao_verificado_ou_municipio_nao_aderente_bloqueia(
    empresa_pronta, nova_nota, sefin
):
    from fiscal.models import ParametrosFiscais

    nota = nova_nota()
    parametros = ParametrosFiscais.obter()
    parametros.convenio_resultado = {"aderente": False}
    parametros.save()

    with pytest.raises(emissao.BloqueioDeEmissao) as erro:
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    assert [b.codigo for b in erro.value.bloqueios] == ["convenio_nao_aderente"]

    parametros.convenio_verificado_em = None
    parametros.save()
    with pytest.raises(emissao.BloqueioDeEmissao) as erro:
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    assert [b.codigo for b in erro.value.bloqueios] == ["convenio_nao_verificado"]


def test_nota_ja_enviada_nao_pode_ser_solicitada_de_novo(empresa_pronta, nova_nota, sefin):
    nota = _emitir(empresa_pronta, nova_nota())

    with pytest.raises(emissao.ErroDeEmissao, match="não pode ser enviada de novo"):
        emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)


def test_nota_enviando_sem_rastro_so_volta_a_rascunho_depois_de_muito_tempo(
    empresa_pronta, nova_nota, sefin
):
    """Esperar a vez na fila não é queda: a nota só é solta quando o prazo é bem longo."""
    nota = nova_nota()
    emissao.solicitar_emissao(nota, usuario=None, empresa=empresa_pronta)
    agora = nota.atualizado_em

    antes = emissao.reconciliar_pendentes(agora + dt.timedelta(minutes=15))
    nota.refresh_from_db()
    assert nota.situacao == S.ENVIANDO and antes.soltas == 0

    depois = emissao.reconciliar_pendentes(agora + dt.timedelta(minutes=31))
    nota.refresh_from_db()
    assert nota.situacao == S.RASCUNHO and depois.soltas == 1
    assert sefin.total_de_posts == 0


def test_excluir_o_usuario_nao_quebra_nem_perde_a_autoria_da_nota(empresa_pronta, nova_nota):
    """O usuário vive no schema público; a nota guarda o e-mail e não depende dele."""
    from core.models import Usuario

    usuario = Usuario.objects.create_user(
        email="autor@exemplo.test", password="x" * 14, nome="Autor"
    )
    nota = nova_nota(usuario=usuario)
    assert nota.criado_por == usuario and nota.criado_por_email == "autor@exemplo.test"

    usuario.delete()

    nota.refresh_from_db()
    assert nota.criado_por is None
    assert nota.criado_por_email == "autor@exemplo.test"
