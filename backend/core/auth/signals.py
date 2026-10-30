"""Registro dos eventos de acesso na trilha de auditoria."""

from allauth.mfa.models import Authenticator
from allauth.mfa.signals import authenticator_added, authenticator_removed
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from core.models import LogAuditoria
from core.services import auditoria

Acao = LogAuditoria.Acao


@receiver(user_logged_in)
def registrar_login(sender, request, user, **kwargs):
    """Login concluído (inclusive a etapa de 2FA, quando houver)."""
    auditoria.registrar(Acao.LOGIN, request=request, usuario=user, alvo=f"Usuario:{user.pk}")


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    """Logout explícito."""
    if user is not None:
        auditoria.registrar(Acao.LOGOUT, request=request, usuario=user, alvo=f"Usuario:{user.pk}")


@receiver(user_login_failed)
def registrar_login_falho(sender, credentials, request=None, **kwargs):
    """Tentativa recusada. Só o e-mail é guardado: a senha nunca chega à auditoria."""
    email = (credentials.get("email") or credentials.get("username") or "").strip().lower()
    auditoria.registrar(Acao.LOGIN_FALHOU, request=request, alvo="login", detalhes={"email": email})


@receiver(authenticator_added)
def registrar_mfa_ativado(sender, request, user, authenticator, **kwargs):
    """2FA por aplicativo configurado."""
    if authenticator.type == Authenticator.Type.TOTP:
        auditoria.registrar(
            Acao.MFA_ATIVADO, request=request, usuario=user, alvo=f"Usuario:{user.pk}"
        )


@receiver(authenticator_removed)
def registrar_mfa_desativado(sender, request, user, authenticator, **kwargs):
    """2FA por aplicativo removido."""
    if authenticator.type == Authenticator.Type.TOTP:
        auditoria.registrar(
            Acao.MFA_DESATIVADO, request=request, usuario=user, alvo=f"Usuario:{user.pk}"
        )
