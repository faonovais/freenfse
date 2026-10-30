"""Municípios do IBGE (schema público, dado de referência igual para todas as empresas)."""

from django.db import models

from core.municipios import normalizar_nome


class Municipio(models.Model):
    """Município brasileiro identificado pelo código IBGE de 7 dígitos.

    Fica no schema público porque é dado público, idêntico para todas as empresas: copiá-lo
    para cada schema multiplicaria 5,5 mil linhas por empresa. Os modelos de empresa guardam o
    código como texto (`codigo_municipio`), sem chave estrangeira entre schemas, e validam a
    existência por `core.services.municipios`.
    """

    codigo = models.CharField("código IBGE", max_length=7, primary_key=True)
    nome = models.CharField(max_length=120)
    uf = models.CharField("UF", max_length=2)
    nome_busca = models.CharField(max_length=120, db_index=True, editable=False, default="")

    class Meta:
        verbose_name = "município"
        verbose_name_plural = "municípios"
        ordering = ["uf", "nome"]
        indexes = [models.Index(fields=["uf", "nome"])]

    def __str__(self):
        return f"{self.nome}/{self.uf} ({self.codigo})"

    def save(self, *args, **kwargs):
        """Mantém o nome sem acento (usado na busca) em dia."""
        self.nome_busca = normalizar_nome(self.nome)
        super().save(*args, **kwargs)
