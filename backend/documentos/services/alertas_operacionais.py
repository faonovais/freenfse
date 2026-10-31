"""Alertas operacionais por empresa, pelo e-mail configurado da empresa (Fase 4 reaproveitada).

Os destinatários são os da configuração (`emails_alerta`) ou os Administradores ativos, como no
alerta de certificado. Cada alerta tem chave de idempotência: o mesmo problema não vira vários
e-mails. Se a empresa não tem e-mail configurado, nada é enviado — o problema continua visível
nas telas e no log estruturado. Os textos não trazem dado pessoal do tomador, só o número interno.

Já existem (Fases 2 e 5) e não se repetem aqui: certificado a vencer e agendamento com erro,
suspenso ou perdido.
"""

import datetime as dt
import logging

from django.conf import settings

from documentos.models import ArquivoDrive, ConfiguracaoEmail, EnvioEmail
from documentos.services import contexto, envio_email
from fiscal.models import Nfse

logger = logging.getLogger(__name__)
T = EnvioEmail.Tipo
TIPOS_DE_ALERTA = {T.ALERTA_CERTIFICADO, T.ALERTA_OPERACIONAL, T.AVISO_AGENDAMENTO}
JANELA_DAS_FALHAS = dt.timedelta(hours=48)


def _avisar(*, empresa, assunto, texto, chave, agora):
    configuracao = ConfiguracaoEmail.obter()
    para = envio_email.destinatarios_do_alerta(configuracao, empresa)
    return envio_email.registrar_aviso_avulso(
        tipo=T.ALERTA_OPERACIONAL,
        destinatarios=para,
        assunto=assunto,
        texto=texto,
        chave_idempotencia=chave,
        agora=agora,
    )


def alertar_emissoes_prolongadas(*, empresa, agora=None):
    """Avisa (uma vez por nota) das notas sem resposta definitiva há mais que o limite de horas.

    Vale para "enviando" e "incerta". O texto manda **não emitir de novo**: o sistema continua
    conferindo na Sefin e uma segunda emissão poderia duplicar a nota.
    """
    agora = agora or contexto.agora()
    limite = agora - dt.timedelta(hours=settings.FREENFSE_ALERTA_EMISSAO_HORAS)
    notas = Nfse.objects.filter(
        situacao__in=[Nfse.Situacao.ENVIANDO, Nfse.Situacao.INCERTA], atualizado_em__lte=limite
    )
    envios = []
    for nota in notas:
        logger.warning(
            "Emissão sem resposta definitiva há mais de %s h.",
            settings.FREENFSE_ALERTA_EMISSAO_HORAS,
            extra={"empresa": empresa.schema_name, "nota": nota.pk},
        )
        envio = _avisar(
            empresa=empresa,
            assunto=f"Nota #{nota.pk} de {empresa.razao_social} sem resposta da Sefin",
            texto=(
                f"A nota interna #{nota.pk} está há mais de "
                f"{settings.FREENFSE_ALERTA_EMISSAO_HORAS} horas sem resposta definitiva da Sefin "
                f"(situação: {nota.get_situacao_display()}). O sistema continua conferindo. "
                "Não emita a mesma nota de novo: isso poderia duplicá-la. Se não resolver, "
                "procure o suporte com este número."
            ),
            chave=f"op:incerta:{nota.pk}",
            agora=agora,
        )
        if envio is not None:
            envios.append(envio)
    return envios


def alertar_falhas_permanentes(*, empresa, agora=None):
    """Um resumo por dia dos e-mails e cópias ao Drive que falharam de forma definitiva.

    Os próprios alertas não entram na conta (evita um alerta falho gerar outro). Devolve o
    e-mail do resumo, ou `None` se não há falha ou o e-mail da empresa está desligado.
    """
    agora = agora or contexto.agora()
    desde = agora - JANELA_DAS_FALHAS
    emails = (
        EnvioEmail.objects.filter(situacao=EnvioEmail.Situacao.FALHOU, criado_em__gte=desde)
        .exclude(tipo__in=TIPOS_DE_ALERTA)
        .count()
    )
    arquivos = ArquivoDrive.objects.filter(
        situacao=ArquivoDrive.Situacao.FALHOU,
        proxima_tentativa__isnull=True,
        atualizado_em__gte=desde,
    ).count()
    if not emails and not arquivos:
        return None
    logger.warning(
        "Envios com falha definitiva: %s e-mail(s), %s cópia(s) ao Drive.",
        emails,
        arquivos,
        extra={"empresa": empresa.schema_name},
    )
    partes = []
    if emails:
        partes.append(f"{emails} e-mail(s)")
    if arquivos:
        partes.append(f"{arquivos} cópia(s) ao Google Drive")
    return _avisar(
        empresa=empresa,
        assunto=f"Envios com falha em {empresa.razao_social}",
        texto=(
            f"Nos últimos 2 dias, {' e '.join(partes)} falharam de forma definitiva (o sistema "
            "já tentou de novo e desistiu). Veja o motivo no histórico de envios da nota e confira "
            "a configuração em Configuração › E-mail e Configuração › Google Drive."
        ),
        chave=f"op:falhas:{agora.astimezone(dt.UTC):%Y-%m-%d}",
        agora=agora,
    )
