"""Retenção (ADR 0008): registros de envio de e-mail somem após 5 anos; documentos fiscais nunca.

O relógio é sempre explícito (`agora=` ou `contexto.agora`), nunca o do computador.
"""

import datetime as dt

import pytest
from django_tenants.utils import schema_context

from core.models import LogAuditoria
from documentos.models import EnvioEmail
from documentos.services import contexto, retencao
from documentos.tasks import expurgar_envios_email, expurgar_exportacoes
from documentos.tests.apoio import emitir
from fiscal.models import EventoNfse, Nfse, TransicaoNfse
from fiscal.persistencia.modelos import DocumentoFiscal, EventoFiscal, EvidenciaFiscal
from fiscal.services import emissao

pytestmark = pytest.mark.django_db
AGORA = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.UTC)


def _envio(criado_em, **extra):
    envio = EnvioEmail.objects.create(
        tipo=EnvioEmail.Tipo.MANUAL, destinatarios=["cliente@tomador.test"], **extra
    )
    EnvioEmail.objects.filter(pk=envio.pk).update(criado_em=criado_em)  # `auto_now_add`
    return envio.pk


def test_so_o_que_passou_de_5_anos_e_apagado(empresa_a):
    with schema_context(empresa_a.schema_name):
        velho = _envio(AGORA.replace(year=2021) - dt.timedelta(days=1))
        no_limite = _envio(AGORA.replace(year=2021))  # exatamente 5 anos: ainda é guardado
        quase = _envio(AGORA.replace(year=2021) + dt.timedelta(days=1))
        recente = _envio(AGORA - dt.timedelta(days=3))

        apagados = retencao.expurgar_envios_de_email(agora=AGORA)

        assert apagados == 1
        assert set(EnvioEmail.objects.values_list("pk", flat=True)) == {no_limite, quase, recente}
        assert not EnvioEmail.objects.filter(pk=velho).exists()


def test_o_29_de_fevereiro_nao_quebra_o_calculo_do_limite():
    assert retencao.limite_de_retencao(dt.datetime(2028, 2, 29, 8, 0, tzinfo=dt.UTC), 5) == (
        dt.datetime(2023, 2, 28, 8, 0, tzinfo=dt.UTC)
    )
    assert retencao.limite_de_retencao(AGORA, 5) == AGORA.replace(year=2021)


def test_os_anos_de_retencao_sao_configuraveis_e_nunca_zero(settings):
    settings.FREENFSE_RETENCAO_ENVIOS_ANOS = 7
    assert retencao.anos_de_retencao() == 7
    settings.FREENFSE_RETENCAO_ENVIOS_ANOS = 0
    assert retencao.anos_de_retencao() == 1


def test_a_tarefa_percorre_todas_as_empresas_inclusive_as_inativas(
    empresa_a, empresa_b, monkeypatch
):
    monkeypatch.setattr(contexto, "agora", lambda: AGORA)
    empresa_b.ativo = False
    empresa_b.save()
    antigo = AGORA.replace(year=2019)
    for empresa in (empresa_a, empresa_b):
        with schema_context(empresa.schema_name):
            _envio(antigo)
            _envio(AGORA)

    assert expurgar_envios_email() == 2

    for empresa in (empresa_a, empresa_b):
        with schema_context(empresa.schema_name):
            assert EnvioEmail.objects.count() == 1


def test_o_expurgo_diario_esta_no_beat(settings):
    entrada = settings.CELERY_BEAT_SCHEDULE["expurgar-envios-de-email"]
    assert entrada["task"] == "documentos.tasks.expurgar_envios_email"


# -- nenhum documento fiscal é apagado por expurgo ------------------------------------------------


def test_dez_anos_depois_nenhum_documento_fiscal_foi_apagado(
    empresa_pronta, nova_nota, sefin, monkeypatch
):
    """Guarda do XML ≥ 5 anos: com o relógio 10 anos à frente, todos os expurgos automáticos
    rodam e a nota, os XMLs, as evidências, os eventos e a auditoria continuam lá."""
    nota = emitir(empresa_pronta, nova_nota)
    emissao.cancelar(
        empresa_pronta,
        nota,
        codigo_motivo=1,
        justificativa="Nota emitida com o valor errado.",
        usuario=None,
    )
    envio = _envio(AGORA)
    contagens = {
        modelo: modelo.objects.count()
        for modelo in (
            Nfse,
            EventoNfse,
            TransicaoNfse,
            EvidenciaFiscal,
            DocumentoFiscal,
            EventoFiscal,
            LogAuditoria,
        )
    }
    assert all(n > 0 for modelo, n in contagens.items() if modelo is not EventoFiscal)
    xml = bytes(Nfse.objects.get(pk=nota.pk).xml_nfse)
    em_dez_anos = dt.datetime.now(dt.UTC).replace(year=dt.datetime.now(dt.UTC).year + 10)
    monkeypatch.setattr(contexto, "agora", lambda: em_dez_anos)

    apagados_envios = expurgar_envios_email()
    expurgar_exportacoes()

    assert apagados_envios == 1  # o registro de envio venceu...
    assert not EnvioEmail.objects.filter(pk=envio).exists()
    for modelo, antes in contagens.items():  # ...mas nenhum documento fiscal saiu
        assert modelo.objects.count() == antes, modelo.__name__
    assert bytes(Nfse.objects.get(pk=nota.pk).xml_nfse) == xml
