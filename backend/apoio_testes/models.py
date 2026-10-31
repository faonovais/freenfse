"""Modelo de empresa usado nos testes de isolamento e de criptografia."""

from django.db import models

from core.fields import CampoBinarioCriptografado, CampoTextoCriptografado


class Anotacao(models.Model):
    """Registro por empresa, com campos criptografados de texto e binário."""

    texto = models.CharField(max_length=200)
    segredo = CampoTextoCriptografado(blank=True, null=True)
    arquivo = CampoBinarioCriptografado(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.texto
