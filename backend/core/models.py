"""Modelos do schema público."""

from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Empresa(TenantMixin):
    """Empresa (tenant): cada uma tem um schema próprio no PostgreSQL (D16).

    Modelo mínimo exigido pelo django-tenants. A Fase 1 acrescenta CNPJ,
    ambiente fiscal, vínculos de usuários e demais dados.
    """

    nome = models.CharField(max_length=200)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    auto_create_schema = True

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self):
        return self.nome


class Dominio(DomainMixin):
    """Domínio associado a uma empresa (exigido pelo django-tenants).

    A empresa ativa é resolvida pelo cabeçalho X-Empresa (D10), não pelo domínio.
    """

    class Meta:
        verbose_name = "domínio"
        verbose_name_plural = "domínios"
