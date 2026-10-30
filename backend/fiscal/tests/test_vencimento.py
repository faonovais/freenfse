"""Alertas de vencimento do certificado: faixas de 30, 15 e 7 dias e vencido, uma vez cada."""

import datetime as dt

import pytest
from django.conf import settings
from django_tenants.utils import schema_context

from config.celery import app as app_celery
from core.models import LogAuditoria
from fiscal.models import AlertaCertificado, Certificado
from fiscal.services import certificado as servico_certificado
from fiscal.services import vencimento
from fiscal.tasks import verificar_vencimento_certificados

pytestmark = pytest.mark.django_db
AGORA = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.UTC)


def _certificado(empresa, dias, *, impressao="a" * 64, horas=1):
    """Grava um certificado que vence daqui a `dias` dias (mais `horas`) em relação a AGORA."""
    with schema_context(empresa.schema_name):
        Certificado.objects.all().delete()
        return Certificado.objects.create(
            arquivo_pfx=b"conteudo-ficticio",
            senha="senha-ficticia",
            titular="TESTE",
            cnpj_titular=empresa.cnpj,
            valido_de=AGORA - dt.timedelta(days=300),
            valido_ate=AGORA + dt.timedelta(days=dias, hours=horas),
            impressao_digital=impressao,
        )


def _alertas(empresa):
    with schema_context(empresa.schema_name):
        return sorted(AlertaCertificado.objects.values_list("faixa", flat=True))


@pytest.mark.parametrize(
    ("dias", "faixa"),
    [
        (31, None),
        (30, 30),
        (16, 30),
        (15, 15),
        (8, 15),
        (7, 7),
        (1, 7),
        (0, 7),  # vence hoje, mais tarde
    ],
)
def test_faixas_de_alerta(empresa_a, dias, faixa):
    _certificado(empresa_a, dias)

    criados = vencimento.verificar_certificados(AGORA)

    assert [int(a.faixa) for a in criados] == ([] if faixa is None else [faixa])
    assert _alertas(empresa_a) == ([] if faixa is None else [faixa])


def test_certificado_vencido_gera_o_alerta_de_vencido(empresa_a):
    with schema_context(empresa_a.schema_name):
        Certificado.objects.create(
            arquivo_pfx=b"x", senha="y", titular="T", cnpj_titular=empresa_a.cnpj,
            valido_de=AGORA - dt.timedelta(days=400), valido_ate=AGORA - dt.timedelta(hours=1),
            impressao_digital="b" * 64,
        )  # fmt: skip

    criados = vencimento.verificar_certificados(AGORA)

    assert [int(a.faixa) for a in criados] == [0]
    assert criados[0].dias_restantes < 0


def test_rodar_de_novo_no_mesmo_dia_nao_repete(empresa_a):
    _certificado(empresa_a, 10)

    primeira = vencimento.verificar_certificados(AGORA)
    segunda = vencimento.verificar_certificados(AGORA + dt.timedelta(hours=6))

    assert len(primeira) == 1 and segunda == []
    assert _alertas(empresa_a) == [15]


def test_ao_longo_dos_dias_gera_um_alerta_por_faixa(empresa_a):
    certificado = _certificado(empresa_a, 40)
    vencimento_em = certificado.valido_ate

    historico = []
    for dia in range(0, 40):  # um passo por dia, até a véspera do vencimento
        agora = vencimento_em - dt.timedelta(days=40 - dia, hours=1)
        historico += [(dia, int(a.faixa)) for a in vencimento.verificar_certificados(agora)]
    depois = vencimento.verificar_certificados(vencimento_em + dt.timedelta(days=1))

    assert [faixa for _, faixa in historico] == [30, 15, 7]
    assert [int(a.faixa) for a in depois] == [0]
    assert _alertas(empresa_a) == [0, 7, 15, 30]


def test_se_a_verificacao_ficar_dias_parada_so_gera_a_faixa_atual(empresa_a):
    _certificado(empresa_a, 5)

    criados = vencimento.verificar_certificados(AGORA)

    assert [int(a.faixa) for a in criados] == [7]  # não gera 30 nem 15 atrasados


def test_certificado_novo_volta_a_alertar(empresa_a):
    _certificado(empresa_a, 10, impressao="c" * 64)
    vencimento.verificar_certificados(AGORA)

    _certificado(empresa_a, 10, impressao="d" * 64)  # substituído por outro que também vence logo
    criados = vencimento.verificar_certificados(AGORA)

    assert len(criados) == 1 and criados[0].impressao_digital == "d" * 64


def test_empresas_sem_certificado_ou_inativas_sao_ignoradas(empresa_a, empresa_b):
    _certificado(empresa_a, 3)
    _certificado(empresa_b, 3)
    empresa_b.ativo = False
    empresa_b.save()

    criados = vencimento.verificar_certificados(AGORA)

    assert len(criados) == 1
    assert _alertas(empresa_b) == []


def test_cada_empresa_recebe_o_seu_alerta(empresa_a, empresa_b):
    _certificado(empresa_a, 3)
    _certificado(empresa_b, 20)

    vencimento.verificar_certificados(AGORA)

    assert _alertas(empresa_a) == [7]
    assert _alertas(empresa_b) == [30]


def test_alerta_e_auditado_e_emite_o_sinal_para_a_fase_4(empresa_a):
    _certificado(empresa_a, 10)
    recebidos = []

    def ouvinte(sender, **dados):
        recebidos.append(dados)

    vencimento.certificado_a_vencer.connect(ouvinte)
    try:
        vencimento.verificar_certificados(AGORA)
    finally:
        vencimento.certificado_a_vencer.disconnect(ouvinte)

    assert len(recebidos) == 1
    dados = recebidos[0]
    assert dados["empresa"] == empresa_a and int(dados["faixa"]) == 15
    assert dados["dias_restantes"] == 10 and dados["certificado"].cnpj_titular == empresa_a.cnpj
    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.CERTIFICADO_A_VENCER)
    assert registro.empresa == empresa_a and registro.usuario is None
    assert registro.detalhes == {"faixa": 15, "dias_restantes": 10}


def test_remover_o_certificado_apaga_os_alertas(empresa_a, rf, master):
    certificado = _certificado(empresa_a, 3)
    vencimento.verificar_certificados(AGORA)
    requisicao = rf.delete("/")
    requisicao.user, requisicao.empresa = master, empresa_a

    with schema_context(empresa_a.schema_name):
        assert servico_certificado.remover_certificado(request=requisicao) is True
        assert (
            AlertaCertificado.objects.filter(
                impressao_digital=certificado.impressao_digital
            ).count()
            == 0
        )


def test_tarefa_do_celery_roda_a_verificacao_e_devolve_quantos_alertas_criou(empresa_a):
    with schema_context(empresa_a.schema_name):
        Certificado.objects.create(
            arquivo_pfx=b"x", senha="y", titular="T", cnpj_titular=empresa_a.cnpj,
            valido_de=dt.datetime.now(dt.UTC) - dt.timedelta(days=300),
            valido_ate=dt.datetime.now(dt.UTC) + dt.timedelta(days=5),
            impressao_digital="e" * 64,
        )  # fmt: skip

    primeira = verificar_vencimento_certificados.apply().get()
    segunda = verificar_vencimento_certificados.apply().get()

    assert (primeira, segunda) == (1, 0)


def test_tarefa_esta_registrada_e_agendada_todo_dia():
    agendamento = settings.CELERY_BEAT_SCHEDULE["verificar-vencimento-de-certificados"]

    assert agendamento["task"] == "fiscal.tasks.verificar_vencimento_certificados"
    assert agendamento["task"] in app_celery.tasks
    assert (agendamento["schedule"].hour, agendamento["schedule"].minute) == ({6}, {40})
