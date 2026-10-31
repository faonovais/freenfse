"""Cadastro de usuários (operação do Master)."""

from allauth.account.models import EmailAddress
from django.db import transaction

from core.models import LogAuditoria, Usuario
from core.services import auditoria

Acao = LogAuditoria.Acao


def _sincronizar_email(usuario):
    """Mantém o endereço verificado/primário do allauth igual ao e-mail do usuário.

    O administrador cadastra o e-mail (não há autocadastro), então ele nasce
    verificado; o allauth usa essa tabela para o login e a ligação social.
    """
    EmailAddress.objects.filter(user=usuario).exclude(email__iexact=usuario.email).delete()
    EmailAddress.objects.update_or_create(
        user=usuario,
        email=usuario.email,
        defaults={"verified": True, "primary": True},
    )


@transaction.atomic
def criar_usuario(*, email, nome="", senha=None, is_master=False, request=None):
    """Cria o usuário (sem senha utilizável se `senha` for omitida) e registra na auditoria."""
    fabrica = Usuario.objects.create_superuser if is_master else Usuario.objects.create_user
    usuario = fabrica(email=email, password=senha, nome=nome)
    _sincronizar_email(usuario)
    auditoria.registrar(
        Acao.USUARIO_CRIADO,
        request=request,
        alvo=f"Usuario:{usuario.pk}",
        detalhes={"email": usuario.email, "is_master": usuario.is_master},
    )
    return usuario


@transaction.atomic
def atualizar_usuario(usuario, *, request=None, senha=None, **campos):
    """Altera nome, e-mail, situação e papel Master; troca a senha se informada."""
    antes = {c: getattr(usuario, c) for c in ("email", "nome", "is_active", "is_master")}
    for campo in ("email", "nome", "is_active", "is_master"):
        if campo in campos:
            setattr(usuario, campo, campos[campo])
    if senha:
        usuario.set_password(senha)
    usuario.save()
    _sincronizar_email(usuario)
    mudancas = {
        campo: {"de": antes[campo], "para": getattr(usuario, campo)}
        for campo in antes
        if antes[campo] != getattr(usuario, campo)
    }
    if senha:
        mudancas["senha"] = "redefinida"  # nunca registra a senha
    auditoria.registrar(
        Acao.USUARIO_ALTERADO,
        request=request,
        alvo=f"Usuario:{usuario.pk}",
        detalhes={"mudancas": mudancas},
    )
    return usuario
