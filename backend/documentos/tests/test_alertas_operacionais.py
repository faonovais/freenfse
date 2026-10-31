"""Alertas operacionais por empresa (Fase 6): emissão incerta prolongada e falhas permanentes.

Saem pelo e-mail configurado da empresa (Fase 4), uma vez por problema, sem dado do tomador.
"""

import datetime as dt

import pytest

from documentos.models import ArquivoDrive, ConfiguracaoEmail, EnvioEmail
from documentos.services import alertas_operacionais as alertas
from documentos.services import envio_email
from documentos.tests.apoio import configurar_email, nota_avulsa
from fiscal.models import Nfse

pytestmark = pytest.mark.django_db
AGORA = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.UTC)
S = Nfse.Situacao
T = EnvioEmail.Tipo


@pytest.fixture
def com_email(empresa_pronta):
    configurar_email("smtp", emails_alerta=["operacao@empresa-alfa.test"])
    return empresa_pronta


def _envelhecer(nota, horas):
    Nfse.objects.filter(pk=nota.pk).update(atualizado_em=AGORA - dt.timedelta(hours=horas))


def _nota(numero, situacao, horas):
    nota = nota_avulsa(numero, situacao=situacao)
    _envelhecer(nota, horas)
    return nota


# -- emissão incerta prolongada ------------------------------------------------------------------


@pytest.mark.parametrize("situacao", [S.ENVIANDO, S.INCERTA])
def test_nota_sem_resposta_da_sefin_ha_mais_de_2_horas_gera_um_alerta(com_email, situacao):
    nota = _nota(1, situacao, horas=3)

    envios = alertas.alertar_emissoes_prolongadas(empresa=com_email, agora=AGORA)

    assert len(envios) == 1
    envio = envios[0]
    assert envio.tipo == T.ALERTA_OPERACIONAL and envio.destinatarios == [
        "operacao@empresa-alfa.test"
    ]
    assert f"#{nota.pk}" in envio.assunto
    assert "Não emita a mesma nota de novo" in envio.corpo_avulso
    # Sem dado do tomador no e-mail.
    assert "TOMADOR AVULSO" not in envio.assunto + envio.corpo_avulso


def test_o_mesmo_problema_nao_vira_varios_emails(com_email):
    _nota(1, S.INCERTA, horas=3)

    primeira = alertas.alertar_emissoes_prolongadas(empresa=com_email, agora=AGORA)
    segunda = alertas.alertar_emissoes_prolongadas(
        empresa=com_email, agora=AGORA + dt.timedelta(hours=5)
    )

    assert [e.pk for e in primeira] == [e.pk for e in segunda]
    assert EnvioEmail.objects.filter(tipo=T.ALERTA_OPERACIONAL).count() == 1


def test_nota_recente_autorizada_ou_rascunho_nao_alerta(com_email):
    _nota(1, S.ENVIANDO, horas=1)  # ainda dentro do limite
    _nota(2, S.AUTORIZADA, horas=100)
    _nota(3, S.RASCUNHO, horas=100)
    _nota(4, S.REJEITADA, horas=100)

    assert alertas.alertar_emissoes_prolongadas(empresa=com_email, agora=AGORA) == []


def test_o_limite_de_horas_e_configuravel(com_email, settings):
    _nota(1, S.INCERTA, horas=3)
    settings.FREENFSE_ALERTA_EMISSAO_HORAS = 6

    assert alertas.alertar_emissoes_prolongadas(empresa=com_email, agora=AGORA) == []


def test_sem_email_configurado_nada_e_enviado(empresa_pronta):
    _nota(1, S.INCERTA, horas=3)
    assert ConfiguracaoEmail.obter().provedor == ConfiguracaoEmail.Provedor.NENHUM

    assert alertas.alertar_emissoes_prolongadas(empresa=empresa_pronta, agora=AGORA) == []
    assert EnvioEmail.objects.count() == 0


def test_o_alerta_e_entregue_pelo_provedor_da_empresa(com_email, provedores):
    _nota(1, S.INCERTA, horas=3)
    (envio,) = alertas.alertar_emissoes_prolongadas(empresa=com_email, agora=AGORA)

    assert envio_email.processar(envio.pk, agora=AGORA) == "enviado"

    mime = provedores.smtp.mensagens[0]["mime"]
    assert mime["To"] == "operacao@empresa-alfa.test"
    assert "sem resposta da Sefin" in mime["Subject"]


# -- falhas permanentes de e-mail e Drive --------------------------------------------------------


def _email_falho(criado_em, tipo=T.MANUAL):
    envio = EnvioEmail.objects.create(
        tipo=tipo, situacao=EnvioEmail.Situacao.FALHOU, destinatarios=["x@tomador.test"]
    )
    EnvioEmail.objects.filter(pk=envio.pk).update(criado_em=criado_em)
    return envio


def _arquivo_falho(nota, atualizado_em, proxima=None):
    arquivo = ArquivoDrive.objects.create(
        nfse=nota, papel="xml", situacao=ArquivoDrive.Situacao.FALHOU, proxima_tentativa=proxima
    )
    ArquivoDrive.objects.filter(pk=arquivo.pk).update(atualizado_em=atualizado_em)


def test_um_resumo_diario_conta_os_emails_e_as_copias_ao_drive_que_falharam(com_email):
    nota = nota_avulsa(1)
    _email_falho(AGORA - dt.timedelta(hours=5))
    _email_falho(AGORA - dt.timedelta(hours=30))
    _arquivo_falho(nota, AGORA - dt.timedelta(hours=2))

    envio = alertas.alertar_falhas_permanentes(empresa=com_email, agora=AGORA)

    assert envio.tipo == T.ALERTA_OPERACIONAL
    assert "2 e-mail(s) e 1 cópia(s) ao Google Drive" in envio.corpo_avulso
    # No mesmo dia, nada novo: é o mesmo registro.
    assert (
        alertas.alertar_falhas_permanentes(
            empresa=com_email, agora=AGORA + dt.timedelta(hours=3)
        ).pk
        == envio.pk
    )


def test_so_conta_falha_definitiva_recente_e_nao_os_proprios_alertas(com_email):
    nota = nota_avulsa(1)
    _email_falho(AGORA - dt.timedelta(days=5))  # antiga demais
    _email_falho(AGORA - dt.timedelta(hours=1), tipo=T.ALERTA_OPERACIONAL)  # um alerta falho
    _email_falho(AGORA - dt.timedelta(hours=1), tipo=T.ALERTA_CERTIFICADO)
    _arquivo_falho(nota, AGORA - dt.timedelta(hours=1), proxima=AGORA)  # ainda vai tentar de novo

    assert alertas.alertar_falhas_permanentes(empresa=com_email, agora=AGORA) is None


def test_sem_falhas_nao_ha_resumo(com_email):
    assert alertas.alertar_falhas_permanentes(empresa=com_email, agora=AGORA) is None
