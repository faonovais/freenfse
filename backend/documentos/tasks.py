"""Tarefas Celery dos documentos (cada uma roda no schema da empresa informada)."""

import logging

from celery import shared_task
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


@shared_task
def processar_envio_email(schema_name, envio_id):
    """Tenta enviar um e-mail da fila; falha temporária fica reagendada no próprio registro."""
    from documentos.services import envio_email

    with schema_context(schema_name):
        return envio_email.processar(envio_id)


@shared_task
def enviar_nota_ao_drive(schema_name, nfse_id, forcar=False):
    """Copia o XML e o PDF da nota (e os eventos conhecidos) ao Google Drive da empresa."""
    from documentos.services.drive import envio
    from fiscal.models import Nfse

    with schema_context(schema_name):
        return envio.enviar_nota(Nfse.objects.get(pk=nfse_id), forcar=forcar)


@shared_task
def enviar_evento_ao_drive(schema_name, nfse_id, evento_id):
    """Copia o XML do evento ao Drive e troca o PDF pelo da nota com marca d'água."""
    from documentos.services.drive import envio
    from fiscal.models import EventoNfse, Nfse

    with schema_context(schema_name):
        return envio.enviar_evento(
            Nfse.objects.get(pk=nfse_id), EventoNfse.objects.get(pk=evento_id)
        )


@shared_task
def gerar_exportacao(schema_name, exportacao_id):
    """Gera o ZIP do download em lote."""
    from documentos.services import exportacao

    with schema_context(schema_name):
        return exportacao.gerar(exportacao_id)


@shared_task
def despachar_pendentes():
    """Enfileire os e-mails e as cópias ao Drive cuja hora de tentar de novo chegou.

    As retentativas ficam gravadas nos próprios registros; esta rotina (a cada minuto) é o que as
    retoma, inclusive depois de uma queda do worker.
    """
    from core.models import Empresa
    from documentos.services import envio_email
    from documentos.services.drive import envio

    totais = {"emails": 0, "notas_drive": 0}
    for empresa in Empresa.objects.filter(ativo=True):
        with schema_context(empresa.schema_name):
            for envio_id in envio_email.pendentes_vencidos():
                processar_envio_email.delay(empresa.schema_name, envio_id)
                totais["emails"] += 1
            for nfse_id in envio.pendentes_vencidos():
                enviar_nota_ao_drive.delay(empresa.schema_name, nfse_id)
                totais["notas_drive"] += 1
    return totais


@shared_task
def expurgar_exportacoes():
    """Apaga os ZIPs do download em lote que passaram da retenção (todas as empresas)."""
    from core.models import Empresa
    from documentos.services import exportacao

    apagados = 0
    for empresa in Empresa.objects.filter(ativo=True):
        with schema_context(empresa.schema_name):
            apagados += exportacao.expurgar()
    return apagados
