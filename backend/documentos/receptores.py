"""Receptores dos sinais fiscais: o que acontece nos documentos quando a nota muda.

Tudo aqui só **enfileira** trabalho (Celery); nada de rede acontece na hora da emissão. Falha em
qualquer receptor é registrada e nunca interfere no resultado fiscal (ver `fiscal.signals`).
"""

import logging

from django.db import connection
from django.dispatch import receiver
from django_tenants.utils import schema_context

from documentos.models import ConfiguracaoDrive, ConfiguracaoEmail, EnvioEmail
from documentos.services import contexto, envio_email
from fiscal.models import EventoNfse
from fiscal.services.vencimento import certificado_a_vencer
from fiscal.signals import nfse_autorizada, nfse_evento_confirmado

logger = logging.getLogger(__name__)

EVENTOS_DE_CANCELAMENTO = {
    EventoNfse.Tipo.CANCELAMENTO,
    EventoNfse.Tipo.CANCELAMENTO_POR_ANALISE,
    EventoNfse.Tipo.CANCELAMENTO_DE_OFICIO,
}


def _tarefas():
    from documentos import tasks

    return tasks


@receiver(nfse_autorizada, dispatch_uid="documentos.ao_autorizar")
def ao_autorizar(sender, nfse, **_):
    """Nota autorizada: e-mail automático (se ligado) e cópia ao Drive (se ativo)."""
    schema = connection.schema_name
    configuracao = ConfiguracaoEmail.obter()
    efetiva = envio_email.configuracao_efetiva(configuracao, nfse)
    if efetiva["envio_automatico"] and configuracao.provedor != ConfiguracaoEmail.Provedor.NENHUM:
        envio = envio_email.solicitar(
            nfse, EnvioEmail.Tipo.AUTORIZACAO, chave_idempotencia=f"auto:{nfse.pk}:autorizacao"
        )
        if envio.situacao == EnvioEmail.Situacao.PENDENTE:
            _tarefas().processar_envio_email.delay(schema, envio.pk)
    drive = ConfiguracaoDrive.obter()
    if drive.ativo and drive.enviar_automaticamente:
        _tarefas().enviar_nota_ao_drive.delay(schema, nfse.pk)


@receiver(nfse_evento_confirmado, dispatch_uid="documentos.ao_registrar_evento")
def ao_registrar_evento(sender, nfse, evento, **_):
    """Evento confirmado: aviso de cancelamento por e-mail (se ligado) e XML do evento no Drive."""
    schema = connection.schema_name
    configuracao = ConfiguracaoEmail.obter()
    efetiva = envio_email.configuracao_efetiva(configuracao, nfse)
    cancelamento = evento.tipo_evento in {str(t) for t in EVENTOS_DE_CANCELAMENTO}
    if (
        cancelamento
        and efetiva["avisar_cancelamento"]
        and configuracao.provedor != ConfiguracaoEmail.Provedor.NENHUM
    ):
        envio = envio_email.solicitar(
            nfse, EnvioEmail.Tipo.CANCELAMENTO, chave_idempotencia=f"auto:{nfse.pk}:cancelamento"
        )
        if envio.situacao == EnvioEmail.Situacao.PENDENTE:
            _tarefas().processar_envio_email.delay(schema, envio.pk)
    drive = ConfiguracaoDrive.obter()
    if drive.ativo and drive.enviar_automaticamente:
        _tarefas().enviar_evento_ao_drive.delay(schema, nfse.pk, evento.pk)


@receiver(certificado_a_vencer, dispatch_uid="documentos.ao_certificado_a_vencer")
def ao_certificado_a_vencer(sender, empresa, certificado, faixa, dias_restantes, **_):
    """Alerta de vencimento do certificado (Fase 2): vira e-mail para os responsáveis."""
    try:
        with schema_context(empresa.schema_name):
            envio = envio_email.registrar_alerta_de_certificado(
                empresa=empresa,
                faixa=int(faixa),
                dias_restantes=dias_restantes,
                impressao=certificado.impressao_digital,
                agora=contexto.agora(),
            )
            if envio is not None and envio.situacao == EnvioEmail.Situacao.PENDENTE:
                _tarefas().processar_envio_email.delay(empresa.schema_name, envio.pk)
    except Exception:
        logger.exception("Não foi possível registrar o e-mail de alerta do certificado.")
