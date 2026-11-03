"""Tarefas agendadas do app fiscal."""

from celery import shared_task

from fiscal.services import vencimento


@shared_task
def verificar_vencimento_certificados():
    """Gera os alertas de vencimento (30/15/7 dias e vencido) de todas as empresas.

    Roda uma vez por dia (ver `CELERY_BEAT_SCHEDULE`). Devolve quantos alertas novos criou.
    """
    return len(vencimento.verificar_certificados())


TEMPO_ENTRE_TENTATIVAS_DA_TRAVA = 10  # segundos
TENTATIVAS_DA_TRAVA = 30


@shared_task(bind=True, acks_late=True, max_retries=TENTATIVAS_DA_TRAVA)
def emitir_nfse(self, schema_name, nfse_id):
    """Envia uma nota à Sefin, uma de cada vez por empresa.

    Idempotente: se o Celery entregar a tarefa de novo (queda do worker), uma nota que já saiu de
    "enviando" é ignorada, e uma nota com DPS no registro é *conferida* na Sefin antes de
    qualquer novo envio. Se outra emissão da empresa está em andamento (trava ocupada), a
    tarefa se reagenda sem consumir a nota.
    """
    from django_tenants.utils import schema_context

    from core.models import Empresa
    from fiscal import gateway
    from fiscal.services import emissao

    empresa = Empresa.objects.get(schema_name=schema_name)
    with schema_context(schema_name):
        try:
            return emissao.executar_emissao(empresa, nfse_id)
        except gateway.TravaOcupadaErro as erro:
            raise self.retry(exc=erro, countdown=TEMPO_ENTRE_TENTATIVAS_DA_TRAVA) from erro


@shared_task
def reconciliar_notas_incertas():
    """Confere na Sefin as notas incertas (ou presas em "enviando") de todas as empresas.

    Só consulta: **nunca reenvia**. Roda a cada poucos minutos (ver `CELERY_BEAT_SCHEDULE`).
    """
    from dataclasses import asdict

    from fiscal.services import emissao

    return asdict(emissao.reconciliar_pendentes())
