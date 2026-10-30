"""Vínculo entre usuário e empresa (schema público)."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.permissoes import Perfil, permissoes_desconhecidas, permissoes_do_perfil


class VinculoUsuarioEmpresa(models.Model):
    """Acesso de um usuário a uma empresa, com perfil próprio nela (D10).

    Um usuário pode ser Administrador na empresa A e só Consulta na B. As
    permissões efetivas são as do perfil, mais as extras, menos as removidas.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vinculos"
    )
    empresa = models.ForeignKey("core.Empresa", on_delete=models.CASCADE, related_name="vinculos")
    perfil = models.CharField(max_length=20, choices=Perfil, default=Perfil.CONSULTA)
    permissoes_extras = models.JSONField("permissões extras", default=list, blank=True)
    permissoes_removidas = models.JSONField("permissões removidas", default=list, blank=True)
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "vínculo usuário × empresa"
        verbose_name_plural = "vínculos usuário × empresa"
        ordering = ["empresa__razao_social", "usuario__email"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "empresa"], name="vinculo_unico_por_par"),
        ]

    def __str__(self):
        return f"{self.usuario_id} → {self.empresa_id} ({self.perfil})"

    def clean(self):
        """Recusa nomes de permissão fora do catálogo e extras que também são removidas."""
        super().clean()
        for campo in ("permissoes_extras", "permissoes_removidas"):
            valor = getattr(self, campo)
            if not isinstance(valor, list) or not all(isinstance(item, str) for item in valor):
                raise ValidationError({campo: "Informe uma lista de nomes de permissão."})
            desconhecidas = permissoes_desconhecidas(valor)
            if desconhecidas:
                raise ValidationError({campo: f"Permissões desconhecidas: {desconhecidas}"})
        em_conflito = set(self.permissoes_extras) & set(self.permissoes_removidas)
        if em_conflito:
            mensagem = f"Permissão extra e removida ao mesmo tempo: {sorted(em_conflito)}"
            raise ValidationError({"permissoes_removidas": mensagem})

    def permissoes_efetivas(self):
        """Permissões do perfil, mais as extras, menos as removidas."""
        return frozenset(
            (permissoes_do_perfil(self.perfil) | set(self.permissoes_extras))
            - set(self.permissoes_removidas)
        )
