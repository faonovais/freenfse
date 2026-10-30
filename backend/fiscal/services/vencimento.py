"""Alertas de vencimento do certificado A1 (30, 15 e 7 dias, e vencido).

A verificação roda todo dia (Celery beat). Para cada empresa ativa com certificado, grava no
máximo um alerta por faixa e por certificado. O envio por e-mail é da Fase 4: o ponto de
extensão é o sinal `certificado_a_vencer`, que a Fase 4 passa a ouvir.
"""

import logging

from django.dispatch import Signal
from django.utils import timezone
from django_tenants.utils import schema_context

from core.models import Empresa, LogAuditoria
from core.services import auditoria
from fiscal.models import AlertaCertificado, Certificado

logger = logging.getLogger(__name__)

# Enviado a cada alerta novo, com: empresa, certificado, faixa, dias_restantes, alerta.
certificado_a_vencer = Signal()

FAIXAS = (
    (AlertaCertificado.Faixa.SETE_DIAS, 7),
    (AlertaCertificado.Faixa.QUINZE_DIAS, 15),
    (AlertaCertificado.Faixa.TRINTA_DIAS, 30),
)


def faixa_de(dias_restantes, vencido):
    """Devolve a faixa de alerta, ou `None` se ainda falta mais de 30 dias."""
    if vencido:
        return AlertaCertificado.Faixa.VENCIDO
    for faixa, limite in FAIXAS:
        if dias_restantes <= limite:
            return faixa
    return None


def verificar_certificados(agora=None):
    """Gera os alertas pendentes de todas as empresas ativas; devolve os alertas criados.

    Idempotente: rodar de novo no mesmo dia não repete alertas. Se a verificação ficar dias
    sem rodar, gera só o alerta da faixa atual (a mais urgente), não os intermediários.
    """
    agora = agora or timezone.now()
    criados = []
    for empresa in Empresa.objects.filter(ativo=True):
        with schema_context(empresa.schema_name):
            certificado = Certificado.objects.first()
            if certificado is None:
                continue
            dias = certificado.dias_para_vencer(agora)
            faixa = faixa_de(dias, certificado.vencido(agora))
            if faixa is None:
                continue
            alerta, novo = AlertaCertificado.objects.get_or_create(
                impressao_digital=certificado.impressao_digital,
                faixa=faixa,
                defaults={"dias_restantes": dias, "valido_ate": certificado.valido_ate},
            )
            if not novo:
                continue
        auditoria.registrar(
            LogAuditoria.Acao.CERTIFICADO_A_VENCER,
            empresa=empresa,
            alvo=f"certificado:{alerta.impressao_digital[:16]}",
            detalhes={"faixa": int(faixa), "dias_restantes": dias},
        )
        certificado_a_vencer.send(
            sender=verificar_certificados,
            empresa=empresa,
            certificado=certificado,
            faixa=faixa,
            dias_restantes=dias,
            alerta=alerta,
        )
        logger.warning(
            "Certificado da empresa %s: %s (%s dia(s)).",
            empresa.cnpj,
            alerta.get_faixa_display(),
            dias,
        )
        criados.append(alerta)
    return criados
