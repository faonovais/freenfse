"""Alertas da plataforma e orquestração dos alertas operacionais (Fase 6).

O que pertence a uma empresa sai pelo e-mail dela (`documentos.services.alertas_operacionais`).
O backup, que é da instalação inteira, sai por um SMTP do sistema (`EMAIL_*`) para
`ALERTAS_EMAIL_PARA` (ou os Master ativos). Sem SMTP configurado o alerta fica no log (CRITICAL)
e no endpoint de saúde; nunca se perde em silêncio. Um alerta por problema por dia.
"""

import datetime as dt
import logging

from django.conf import settings
from django.core.cache import cache
from django_tenants.utils import schema_context

from core.models import Empresa, Usuario
from documentos.services.email.base import ErroDeEnvio, MensagemEmail
from documentos.services.email.smtp import ProvedorSmtp
from operacao import saude

logger = logging.getLogger(__name__)
UM_DIA = 24 * 3600


def destinatarios_da_plataforma():
    """E-mails de `ALERTAS_EMAIL_PARA` ou, se vazio, dos usuários Master ativos."""
    if settings.ALERTAS_EMAIL_PARA:
        return sorted(set(settings.ALERTAS_EMAIL_PARA))
    masters = Usuario.objects.filter(is_master=True, is_active=True)
    return sorted({u.email for u in masters if u.email})


def _provedor_smtp():
    """SMTP do sistema (`ALERTAS_SMTP_*`), ou `None` se não estiver configurado."""
    if not settings.ALERTAS_SMTP_HOST:
        return None
    return ProvedorSmtp(
        host=settings.ALERTAS_SMTP_HOST,
        porta=settings.ALERTAS_SMTP_PORTA,
        seguranca=settings.ALERTAS_SMTP_SEGURANCA,
        usuario=settings.ALERTAS_SMTP_USUARIO,
        senha=settings.ALERTAS_SMTP_SENHA,
    )


def alertar_plataforma(assunto, texto, *, chave):
    """Envia um e-mail da plataforma, no máximo um por `chave` por dia. Devolve se enviou."""
    if not cache.add(f"freenfse:alerta:{chave}", 1, UM_DIA):
        return False
    provedor = _provedor_smtp()
    para = destinatarios_da_plataforma()
    if provedor is None or not para:
        logger.critical(
            "Alerta da plataforma não enviado (sem SMTP do sistema ou sem destinatário): %s",
            assunto,
        )
        return False
    mensagem = MensagemEmail(
        remetente=settings.ALERTAS_EMAIL_DE,
        nome_remetente="freenfse",
        destinatarios=para,
        assunto=f"[freenfse] {assunto}",
        texto=texto,
    )
    try:
        provedor.enviar(mensagem)
    except ErroDeEnvio as erro:
        logger.error("Não foi possível enviar o alerta da plataforma: %s (%s)", assunto, erro)
        return False
    return True


def alertar_backup_falhou(erro):
    """Backup diário que não deu certo (a mensagem do `ErroDeBackup` não traz segredo)."""
    return alertar_plataforma(
        "O backup do banco falhou",
        f"O backup cifrado de hoje não foi feito.\n\nMotivo: {erro}\n\n"
        "Enquanto isso, o último backup bom continua guardado. Corrija a causa e rode "
        "`python manage.py fazer_backup`.",
        chave=f"backup-falhou:{dt.datetime.now(dt.UTC):%Y-%m-%d}",
    )


def verificar_backup_atrasado():
    """Avisa se há backup configurado mas o último bom tem mais de 30 horas (ou não existe)."""
    estado = saude.verificar_backup()
    if estado not in ("atrasado", "sem_backup"):
        return False
    motivo = (
        "não há nenhum backup" if estado == "sem_backup" else "o último backup tem mais de 30 horas"
    )
    return alertar_plataforma(
        "Backup atrasado",
        f"O backup está configurado, mas {motivo}. Veja o log do worker e rode "
        "`python manage.py fazer_backup`.",
        chave=f"backup-atrasado:{dt.datetime.now(dt.UTC):%Y-%m-%d}",
    )


def verificar_alertas(*, agora=None):
    """Roda os alertas de todas as empresas ativas e os da plataforma. Devolve um resumo."""
    from documentos.services import alertas_operacionais

    resumo = {"emissoes": 0, "falhas": 0}
    for empresa in Empresa.objects.filter(ativo=True):
        with schema_context(empresa.schema_name):
            resumo["emissoes"] += len(
                alertas_operacionais.alertar_emissoes_prolongadas(empresa=empresa, agora=agora)
            )
            if alertas_operacionais.alertar_falhas_permanentes(empresa=empresa, agora=agora):
                resumo["falhas"] += 1
    resumo["backup"] = verificar_backup_atrasado()
    return resumo
