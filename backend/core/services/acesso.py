"""Regras de acesso: quais empresas o usuário vê e o que pode fazer em cada uma."""

from allauth.mfa.models import Authenticator
from django.conf import settings

from core.models import Empresa, VinculoUsuarioEmpresa
from core.permissoes import PERFIL_MASTER, todas_as_permissoes


def empresas_acessiveis(usuario):
    """Empresas ativas que o usuário pode operar (todas, para o Master)."""
    if not usuario.is_active:
        return Empresa.objects.none()
    if usuario.is_master:
        return Empresa.objects.filter(ativo=True)
    return Empresa.objects.filter(
        ativo=True, vinculos__usuario=usuario, vinculos__ativo=True
    ).distinct()


def vinculo_ativo(usuario, empresa):
    """Vínculo ativo do usuário com a empresa, ou `None`."""
    return VinculoUsuarioEmpresa.objects.filter(
        usuario=usuario, empresa=empresa, ativo=True
    ).first()


def acesso_a_empresa(usuario, empresa):
    """Resolve o acesso: `(vinculo, perfil, permissoes)` ou `None` se não pode operar.

    O Master opera qualquer empresa ativa sem vínculo, com todas as permissões.
    """
    if not usuario.is_active or not empresa.ativo:
        return None
    if usuario.is_master:
        return None, PERFIL_MASTER, todas_as_permissoes()
    vinculo = vinculo_ativo(usuario, empresa)
    if vinculo is None:
        return None
    return vinculo, vinculo.perfil, vinculo.permissoes_efetivas()


def usuario_tem_2fa(usuario):
    """Indica se o usuário já configurou o 2FA por aplicativo (TOTP)."""
    return Authenticator.objects.filter(user=usuario, type=Authenticator.Type.TOTP).exists()


def exige_2fa(usuario):
    """Indica se a política configurada obriga este usuário a ter 2FA."""
    if settings.AUTH_EXIGIR_2FA_TODOS:
        return True
    return bool(usuario.is_master and settings.AUTH_EXIGIR_2FA_MASTER)
