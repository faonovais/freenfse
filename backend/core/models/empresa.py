"""Empresa (tenant) e domínio (schema público)."""

from django.db import models
from django_tenants.models import DomainMixin, TenantMixin

from core.validators import formatar_cnpj, normalizar_cnpj, validar_cnpj


class Empresa(TenantMixin):
    """Empresa (tenant): cada uma tem um schema próprio no PostgreSQL (D16).

    Dados mínimos da Fase 1; parâmetros fiscais, certificado e logo entram na
    Fase 2, no schema da própria empresa.
    """

    razao_social = models.CharField("razão social", max_length=200)
    cnpj = models.CharField("CNPJ", max_length=14, unique=True, validators=[validar_cnpj])
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    # O schema é criado ao salvar e NUNCA removido automaticamente: apagar uma
    # empresa não pode destruir XML e dados fiscais (guarda legal).
    auto_create_schema = True
    auto_drop_schema = False

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["razao_social"]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj_formatado})"

    @property
    def cnpj_formatado(self):
        """CNPJ no formato 00.000.000/0000-00."""
        return formatar_cnpj(self.cnpj)

    def save(self, *args, **kwargs):
        """Normaliza o CNPJ e define o nome do schema a partir dele."""
        self.cnpj = normalizar_cnpj(self.cnpj)
        if not self.schema_name:
            self.schema_name = f"empresa_{self.cnpj.lower()}"
        super().save(*args, **kwargs)


class Dominio(DomainMixin):
    """Domínio associado a uma empresa (exigido pelo django-tenants).

    A empresa ativa é resolvida pelo cabeçalho X-Empresa (D10), não pelo
    domínio; por isso nenhum domínio é cadastrado.
    """

    class Meta:
        verbose_name = "domínio"
        verbose_name_plural = "domínios"
