"""Bloqueios de emissão: o que impede a empresa de emitir e como o usuário resolve."""

import datetime as dt

import pytest
from django.utils import timezone

from fiscal.models import Certificado, ParametrosFiscais
from fiscal.services.bloqueios import verificar_prontidao

pytestmark = pytest.mark.django_db


def _codigos():
    return [b.codigo for b in verificar_prontidao()]


def test_empresa_pronta_nao_tem_bloqueios(empresa_pronta):
    assert _codigos() == []


def test_certificado_vencido_bloqueia(empresa_pronta):
    Certificado.objects.update(valido_ate=timezone.now() - dt.timedelta(days=1))

    assert _codigos() == ["certificado_vencido"]


def test_convenio_de_outro_ambiente_ou_municipio_nao_vale(empresa_pronta):
    parametros = ParametrosFiscais.obter()
    parametros.ambiente = ParametrosFiscais.Ambiente.PRODUCAO  # a verificação foi na restrita
    parametros.save()

    assert _codigos() == ["convenio_nao_verificado"]


def test_resposta_de_convenio_indefinida_tambem_bloqueia(empresa_pronta):
    parametros = ParametrosFiscais.obter()
    parametros.convenio_resultado = {"aderente": None}
    parametros.save()

    assert _codigos() == ["convenio_nao_aderente"]


def test_simples_sem_regime_de_apuracao_bloqueia(empresa_pronta):
    parametros = ParametrosFiscais.obter()
    parametros.regime_tributario = ParametrosFiscais.RegimeTributario.SIMPLES_NACIONAL
    parametros.save()

    assert _codigos() == ["regime_incompleto"]


def test_cada_bloqueio_diz_a_tela_para_resolver(empresa_a):
    from django_tenants.utils import schema_context

    with schema_context(empresa_a.schema_name):
        bloqueios = verificar_prontidao()

    assert {b.tela for b in bloqueios} == {"/fiscal/certificado", "/fiscal/parametros"}
    assert all(b.mensagem.endswith(".") for b in bloqueios)
