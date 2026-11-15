"""Cadastro de empresas (operação do Master)."""

from django.db import transaction

from core.models import Empresa, LogAuditoria
from core.services import auditoria

Acao = LogAuditoria.Acao


def criar_empresa(
    *,
    razao_social,
    cnpj,
    nome_exibicao="",
    ativo=True,
    servicos_oficiais=None,
    request=None,
):
    """Cria a empresa e o schema dedicado dela no PostgreSQL, e registra na auditoria."""
    # O schema é criado pelo django-tenants ao salvar; fica fora da transação do
    # registro de auditoria para um erro de DDL não deixar auditoria órfã.
    nome_exibicao = (nome_exibicao or "").strip()
    empresa = Empresa.objects.create(
        razao_social=razao_social,
        nome_exibicao=nome_exibicao,
        cnpj=cnpj,
        ativo=ativo,
    )
    if servicos_oficiais is not None:
        empresa.servicos_oficiais.set(servicos_oficiais)
    detalhes = {"cnpj": empresa.cnpj, "razao_social": empresa.razao_social}
    if empresa.nome_exibicao:
        detalhes["nome_exibicao"] = empresa.nome_exibicao
    if servicos_oficiais:
        detalhes["servicos_oficiais"] = sorted(s.id for s in servicos_oficiais)
    auditoria.registrar(
        Acao.EMPRESA_CRIADA,
        request=request,
        empresa=empresa,
        alvo=f"Empresa:{empresa.pk}",
        detalhes=detalhes,
    )
    return empresa


@transaction.atomic
def atualizar_empresa(empresa, *, request=None, **campos):
    """Altera razão social, nome para exibição, CNPJ e situação; preserva o schema."""
    servicos_oficiais = campos.pop("servicos_oficiais", None)
    if "nome_exibicao" in campos and campos["nome_exibicao"] is not None:
        campos["nome_exibicao"] = campos["nome_exibicao"].strip()
    antes = {c: getattr(empresa, c) for c in ("razao_social", "nome_exibicao", "cnpj", "ativo")}
    ids_antes = (
        sorted(empresa.servicos_oficiais.values_list("id", flat=True))
        if servicos_oficiais is not None
        else None
    )
    for campo in antes:
        if campo in campos:
            setattr(empresa, campo, campos[campo])
    empresa.save()
    mudancas = {
        campo: {"de": antes[campo], "para": getattr(empresa, campo)}
        for campo in antes
        if antes[campo] != getattr(empresa, campo)
    }
    if servicos_oficiais is not None:
        empresa.servicos_oficiais.set(servicos_oficiais)
        ids_depois = sorted(s.id for s in servicos_oficiais)
        if ids_antes != ids_depois:
            mudancas["servicos_oficiais"] = {"de": ids_antes, "para": ids_depois}
    auditoria.registrar(
        Acao.EMPRESA_ALTERADA,
        request=request,
        empresa=empresa,
        alvo=f"Empresa:{empresa.pk}",
        detalhes={"mudancas": mudancas},
    )
    return empresa
