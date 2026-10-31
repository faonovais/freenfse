"""Evidências, cache, NSU, auditoria e a regra de transação da trava."""

import datetime as dt

import pytest
from django.db import transaction
from django.test import override_settings
from django_tenants.utils import schema_context
from freedfe.excecoes import ComunicacaoErro
from freedfe.excecoes import SincronizacaoEmAndamentoErro as TravaOcupada

from fiscal.persistencia.auditoria import AuditoriaPostgres
from fiscal.persistencia.cache import CacheParametrosPostgres
from fiscal.persistencia.evidencias import ArmazenamentoEvidenciasPostgres
from fiscal.persistencia.modelos import AuditoriaFiscal, EvidenciaFiscal
from fiscal.persistencia.nsu import EstadoSequenciaNsuPostgres
from fiscal.persistencia.trava import TravaPostgres, chave_da_trava
from fiscal.tests.persistencia.contrato_estado_emissao import montar_id

pytestmark = pytest.mark.django_db
DPS_XML = b'<DPS xmlns="http://www.sped.fazenda.gov.br/nfse"><infDPS Id="x"/></DPS>'


# -- evidências ------------------------------------------------------------------------


@pytest.fixture
def evidencias(empresa_ativa):
    return ArmazenamentoEvidenciasPostgres()


def test_grava_a_dps_e_devolve_uma_referencia_que_le_de_volta(evidencias):
    referencia = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML)

    assert referencia == f"dps/{montar_id(1)}/1/dps.xml"
    assert evidencias.ler(referencia) == DPS_XML


def test_regravar_a_mesma_tentativa_com_o_mesmo_conteudo_nao_duplica(evidencias):
    primeira = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML)
    segunda = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML)

    assert primeira == segunda
    assert EvidenciaFiscal.objects.count() == 1


def test_conteudo_diferente_na_mesma_tentativa_nunca_sobrescreve(evidencias):
    primeira = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML)
    segunda = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML + b"<!-- -->")

    assert primeira != segunda
    assert evidencias.ler(primeira) == DPS_XML
    assert evidencias.ler(segunda) == DPS_XML + b"<!-- -->"


def test_reenvio_apos_rejeicao_guarda_cada_tentativa(evidencias):
    um = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML)
    dois = evidencias.gravar_dps(montar_id(1), "2026-11", 2, "dps.xml", DPS_XML)

    assert um != dois and EvidenciaFiscal.objects.count() == 2


def test_eventos_repetidos_geram_entradas_novas(evidencias):
    chave = "1" * 50
    a = evidencias.gravar_evento(chave, "101101", "2026-11", "pedido.xml", b"<a/>")
    b = evidencias.gravar_evento(chave, "101101", "2026-11", "pedido.xml", b"<a/>")

    assert a != b and EvidenciaFiscal.objects.filter(chave=chave).count() == 2


def test_evidencia_adulterada_e_detectada(evidencias):
    referencia = evidencias.gravar_dps(montar_id(1), "2026-11", 1, "dps.xml", DPS_XML)
    EvidenciaFiscal.objects.filter(referencia=referencia).update(conteudo=b"<outro/>")

    with pytest.raises(ValueError, match="não confere com o hash"):
        evidencias.ler(referencia)


# -- cache -----------------------------------------------------------------------------


class RelogioDeCache:
    def __init__(self):
        self.agora = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.UTC)

    def __call__(self):
        return self.agora


@pytest.fixture
def cache(empresa_ativa):
    relogio = RelogioDeCache()
    return CacheParametrosPostgres(relogio), relogio


def test_o_cache_reaproveita_ate_o_prazo_e_busca_de_novo_depois(cache):
    cache_, relogio = cache
    buscas = []

    def buscar():
        buscas.append(1)
        return {"valor": len(buscas)}

    assert cache_.obter_ou_buscar("2927408", "convenio", buscar) == {"valor": 1}
    relogio.agora += dt.timedelta(hours=23)
    assert cache_.obter_ou_buscar("2927408", "convenio", buscar) == {"valor": 1}
    relogio.agora += dt.timedelta(hours=2)
    assert cache_.obter_ou_buscar("2927408", "convenio", buscar) == {"valor": 2}


def test_sem_internet_o_cache_vencido_ainda_serve(cache):
    cache_, relogio = cache
    cache_.obter_ou_buscar("2927408", "convenio", lambda: {"valor": "antigo"})
    relogio.agora += dt.timedelta(days=3)

    def sem_rede():
        raise ComunicacaoErro("sem internet")

    assert cache_.obter_ou_buscar("2927408", "convenio", sem_rede) == {"valor": "antigo"}


def test_o_cache_e_por_municipio(cache):
    cache_, _ = cache
    cache_.obter_ou_buscar("2927408", "convenio", lambda: {"m": "salvador"})

    assert cache_.obter_ou_buscar("3550308", "convenio", lambda: {"m": "sao paulo"}) == {
        "m": "sao paulo"
    }


# -- NSU -------------------------------------------------------------------------------


def test_o_estado_do_nsu_sobrevive_entre_instancias(empresa_ativa):
    estado = EstadoSequenciaNsuPostgres("nsu_nfse")
    estado.atualizar_sequencia("000000000000010", "000000000000020")
    estado.bloquear()
    estado.salvar()

    outro = EstadoSequenciaNsuPostgres("nsu_nfse")

    assert outro.ult_nsu == "000000000000010" and outro.max_nsu == "000000000000020"
    assert outro.segundos_para_liberar() > 0


def test_o_nsu_e_independente_por_recurso_e_por_empresa(empresa_a, empresa_b):
    with schema_context(empresa_a.schema_name):
        a = EstadoSequenciaNsuPostgres("nsu_nfse")
        a.atualizar_sequencia("000000000000005", None)
        a.salvar()
        assert EstadoSequenciaNsuPostgres("nsu_nfse_x").ult_nsu == "0" * 15
    with schema_context(empresa_b.schema_name):
        assert EstadoSequenciaNsuPostgres("nsu_nfse").ult_nsu == "0" * 15


# -- auditoria -------------------------------------------------------------------------


def test_a_auditoria_grava_a_chamada_sem_xml(empresa_ativa):
    AuditoriaPostgres().registrar(
        servico="nfse",
        operacao="emitir",
        id_dps=montar_id(1),
        situacao="autorizada",
        chave="1" * 50,
        codigos=["E0014"],
        corpo=b"<xml/>",
        status=201,
    )

    linha = AuditoriaFiscal.objects.get()
    assert (linha.servico, linha.operacao, linha.situacao) == ("nfse", "emitir", "autorizada")
    assert linha.id_dps == montar_id(1) and linha.chave == "1" * 50
    assert linha.dados == {"codigos": ["E0014"], "status": 201}  # o conteúdo binário não entra


def test_a_auditoria_corta_texto_longo(empresa_ativa):
    AuditoriaPostgres().registrar(servico="nfse", detalhe="x" * 5000)

    assert len(AuditoriaFiscal.objects.get().dados["detalhe"]) == 500


# -- trava -----------------------------------------------------------------------------


def test_a_chave_da_trava_depende_do_schema_e_do_recurso():
    chaves = {
        chave_da_trava("empresa_a", "emissao_nfse"),
        chave_da_trava("empresa_b", "emissao_nfse"),
        chave_da_trava("empresa_a", "nsu_nfse"),
    }
    assert len(chaves) == 3
    assert chave_da_trava("empresa_a", "emissao_nfse") == chave_da_trava(
        "empresa_a", "emissao_nfse"
    )


def test_trava_recusa_transacao_aberta_fora_dos_testes(empresa_ativa):
    with override_settings(FREENFSE_EMISSAO_EM_TRANSACAO_PERMITIDA=False):
        with transaction.atomic(), pytest.raises(RuntimeError, match="dentro de uma transação"):
            with TravaPostgres("emissao_nfse"):
                pass


def test_a_trava_e_liberada_mesmo_com_excecao_no_bloco(empresa_ativa):
    with pytest.raises(ValueError):
        with TravaPostgres("emissao_nfse"):
            raise ValueError("falha dentro da trava")

    with TravaPostgres("emissao_nfse"):  # voltou a ficar livre
        pass


def test_segunda_aquisicao_sem_espera_falha_enquanto_a_primeira_segura(empresa_ativa):
    with TravaPostgres("emissao_nfse"):
        with pytest.raises(TravaOcupada):
            with TravaPostgres("emissao_nfse", espera_segundos=0):
                pass


def test_a_espera_faz_novas_tentativas_ate_o_prazo(empresa_ativa):
    pausas = []
    tempo = [0.0]

    def relogio():
        return tempo[0]

    def pausa(segundos):
        pausas.append(segundos)
        tempo[0] += segundos

    with TravaPostgres("emissao_nfse"):
        with pytest.raises(TravaOcupada):
            with TravaPostgres("emissao_nfse", espera_segundos=1.0, pausa=pausa, relogio=relogio):
                pass

    assert len(pausas) >= 5  # tentou várias vezes antes de desistir
