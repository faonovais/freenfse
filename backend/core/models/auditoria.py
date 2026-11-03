"""Trilha de auditoria (schema público)."""

from django.conf import settings
from django.db import models


class _SoInsercao(models.QuerySet):
    """Impede alterar ou apagar registros em lote (a trilha só recebe inserções)."""

    def update(self, **kwargs):
        """Alteração em lote não é permitida."""
        raise PermissionError("Registros de auditoria são imutáveis.")

    def delete(self):
        """Exclusão em lote não é permitida."""
        raise PermissionError("Registros de auditoria são imutáveis.")

    def bulk_update(self, objs, fields, batch_size=None):
        """Alteração em lote não é permitida."""
        raise PermissionError("Registros de auditoria são imutáveis.")


class LogAuditoria(models.Model):
    """Registro imutável de uma operação: quem, onde, o quê, de qual IP.

    Guarda usuário **e** empresa (D10) e a marca `master` quando a ação foi do
    papel global (D22). Os campos `*_snapshot` preservam a identificação mesmo
    se o usuário ou a empresa forem removidos depois.
    """

    class Acao(models.TextChoices):
        """Ações registradas."""

        LOGIN = "login", "Login"
        LOGIN_FALHOU = "login_falhou", "Login recusado"
        LOGIN_SOCIAL_RECUSADO = "login_social_recusado", "Login social recusado"
        LOGOUT = "logout", "Logout"
        ACESSO_NEGADO = "acesso_negado", "Acesso negado a empresa"
        MFA_ATIVADO = "mfa_ativado", "2FA ativado"
        MFA_DESATIVADO = "mfa_desativado", "2FA desativado"
        EMPRESA_CRIADA = "empresa_criada", "Empresa criada"
        EMPRESA_ALTERADA = "empresa_alterada", "Empresa alterada"
        USUARIO_CRIADO = "usuario_criado", "Usuário criado"
        USUARIO_ALTERADO = "usuario_alterado", "Usuário alterado"
        VINCULO_CRIADO = "vinculo_criado", "Vínculo criado"
        VINCULO_ALTERADO = "vinculo_alterado", "Vínculo alterado"
        PARAMETROS_ALTERADOS = "parametros_alterados", "Parâmetros fiscais alterados"
        AMBIENTE_ALTERADO = "ambiente_alterado", "Ambiente de emissão alterado"
        CONVENIO_VERIFICADO = "convenio_verificado", "Convênio do município verificado"
        CERTIFICADO_ENVIADO = "certificado_enviado", "Certificado A1 enviado"
        CERTIFICADO_REMOVIDO = "certificado_removido", "Certificado A1 removido"
        CERTIFICADO_A_VENCER = "certificado_a_vencer", "Alerta de vencimento do certificado"
        LOGO_ALTERADO = "logo_alterado", "Logo da empresa alterado"
        PESSOAS_COPIADAS = "pessoas_copiadas", "Cadastros copiados de outra empresa"
        NFSE_RASCUNHO_CRIADO = "nfse_rascunho_criado", "Rascunho de NFS-e criado"
        NFSE_EMISSAO_SOLICITADA = "nfse_emissao_solicitada", "Emissão de NFS-e solicitada"
        NFSE_AUTORIZADA = "nfse_autorizada", "NFS-e autorizada"
        NFSE_REJEITADA = "nfse_rejeitada", "NFS-e rejeitada pela Sefin"
        NFSE_INCERTA = "nfse_incerta", "Emissão de NFS-e com resultado incerto"
        NFSE_CANCELADA = "nfse_cancelada", "NFS-e cancelada"
        NFSE_CANCELAMENTO_RECUSADO = "nfse_cancelamento_recusado", "Cancelamento de NFS-e recusado"
        NFSE_SUBSTITUICAO_CRIADA = "nfse_substituicao_criada", "Substituição de NFS-e iniciada"
        NFSE_SUBSTITUIDA = "nfse_substituida", "NFS-e substituída"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    usuario_snapshot = models.CharField(max_length=254, blank=True)
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    empresa_snapshot = models.CharField(max_length=60, blank=True)
    acao = models.CharField(max_length=40, choices=Acao)
    alvo = models.CharField(max_length=120, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    master = models.BooleanField(default=False)
    detalhes = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    objects = _SoInsercao.as_manager()

    class Meta:
        verbose_name = "log de auditoria"
        verbose_name_plural = "logs de auditoria"
        ordering = ["-criado_em", "-id"]
        indexes = [
            models.Index(fields=["empresa", "-criado_em"]),
            models.Index(fields=["usuario", "-criado_em"]),
            models.Index(fields=["acao", "-criado_em"]),
        ]

    def __str__(self):
        return f"{self.acao} · {self.usuario_snapshot or '-'} · {self.criado_em:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        """Só permite inserir: um registro existente nunca é alterado."""
        if not self._state.adding:
            raise PermissionError("Registros de auditoria são imutáveis.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Registros de auditoria não podem ser removidos pela aplicação."""
        raise PermissionError("Registros de auditoria são imutáveis.")
