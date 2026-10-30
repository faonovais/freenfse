"""Cadastro de empresas (operação do Master)."""

from django.db import transaction

from core.models import Empresa, LogAuditoria
from core.services import auditoria

Acao = LogAuditoria.Acao


def criar_empresa(*, razao_social, cnpj, ativo=True, request=None):
    """Cria a empresa e o schema dedicado dela no PostgreSQL, e registra na auditoria."""
    # O schema é criado pelo django-tenants ao salvar; fica fora da transação do
    # registro de auditoria para um erro de DDL não deixar auditoria órfã.
    empresa = Empresa.objects.create(razao_social=razao_social, cnpj=cnpj, ativo=ativo)
    auditoria.registrar(
        Acao.EMPRESA_CRIADA,
        request=request,
        empresa=empresa,
        alvo=f"Empresa:{empresa.pk}",
        detalhes={"cnpj": empresa.cnpj, "razao_social": empresa.razao_social},
    )
    return empresa


@transaction.atomic
def atualizar_empresa(empresa, *, request=None, **campos):
    """Altera razão social, CNPJ e situação. O schema nunca é renomeado nem removido."""
    antes = {c: getattr(empresa, c) for c in ("razao_social", "cnpj", "ativo")}
    for campo in antes:
        if campo in campos:
            setattr(empresa, campo, campos[campo])
    empresa.save()
    mudancas = {
        campo: {"de": antes[campo], "para": getattr(empresa, campo)}
        for campo in antes
        if antes[campo] != getattr(empresa, campo)
    }
    auditoria.registrar(
        Acao.EMPRESA_ALTERADA,
        request=request,
        empresa=empresa,
        alvo=f"Empresa:{empresa.pk}",
        detalhes={"mudancas": mudancas},
    )
    return empresa
