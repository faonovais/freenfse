"""Vínculos entre usuários e empresas (operação do Master)."""

from django.db import transaction

from core.models import LogAuditoria, VinculoUsuarioEmpresa
from core.services import auditoria

Acao = LogAuditoria.Acao
_CAMPOS = ("perfil", "permissoes_extras", "permissoes_removidas", "ativo")


@transaction.atomic
def criar_vinculo(
    *,
    usuario,
    empresa,
    perfil,
    permissoes_extras=(),
    permissoes_removidas=(),
    ativo=True,
    request=None,
):
    """Concede ao usuário acesso à empresa com o perfil informado."""
    vinculo = VinculoUsuarioEmpresa(
        usuario=usuario,
        empresa=empresa,
        perfil=perfil,
        permissoes_extras=list(permissoes_extras),
        permissoes_removidas=list(permissoes_removidas),
        ativo=ativo,
        criado_por=getattr(request, "user", None) if request is not None else None,
    )
    vinculo.full_clean(exclude=["criado_por"])
    vinculo.save()
    auditoria.registrar(
        Acao.VINCULO_CRIADO,
        request=request,
        empresa=empresa,
        alvo=f"Vinculo:{vinculo.pk}",
        detalhes={"usuario": usuario.email, "perfil": perfil, "ativo": ativo},
    )
    return vinculo


@transaction.atomic
def atualizar_vinculo(vinculo, *, request=None, **campos):
    """Altera perfil, permissões ajustadas e situação (usuário e empresa não mudam)."""
    antes = {campo: getattr(vinculo, campo) for campo in _CAMPOS}
    for campo in _CAMPOS:
        if campo in campos:
            setattr(vinculo, campo, campos[campo])
    vinculo.full_clean(exclude=["criado_por"])
    vinculo.save()
    mudancas = {
        campo: {"de": antes[campo], "para": getattr(vinculo, campo)}
        for campo in _CAMPOS
        if antes[campo] != getattr(vinculo, campo)
    }
    auditoria.registrar(
        Acao.VINCULO_ALTERADO,
        request=request,
        empresa=vinculo.empresa,
        alvo=f"Vinculo:{vinculo.pk}",
        detalhes={"usuario": vinculo.usuario.email, "mudancas": mudancas},
    )
    return vinculo
