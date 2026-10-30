"""Adaptadores do allauth: sem autocadastro, restrição de domínio e ligação ao usuário cadastrado.

Regras (D8, D23): quem cria usuários é o administrador. O login social só entra
se o e-mail verificado pelo provedor já for de um usuário ativo; o provedor
nunca cria conta.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpResponseRedirect

from core.models import LogAuditoria, Usuario
from core.services import auditoria


class AccountAdapter(DefaultAccountAdapter):
    """Fecha o cadastro: o allauth nunca cria usuário por conta própria."""

    def is_open_for_signup(self, request):
        """Não há autocadastro."""
        return False


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Aceita login social apenas de e-mails já cadastrados (e de domínios permitidos)."""

    def is_open_for_signup(self, request, sociallogin):
        """O provedor social não cria conta."""
        return False

    def pre_social_login(self, request, sociallogin):
        """Valida o e-mail do provedor e liga a conta social ao usuário cadastrado."""
        provedor = sociallogin.account.provider
        email = self._email_verificado(sociallogin)
        if not email:
            self._recusar(request, provedor, "email_nao_verificado", "")

        dominios = [
            d.strip().lower().lstrip("@") for d in settings.AUTH_DOMINIOS_PERMITIDOS if d.strip()
        ]
        if dominios and email.rpartition("@")[2].lower() not in dominios:
            self._recusar(request, provedor, "dominio_nao_permitido", email)

        if sociallogin.is_existing:
            if not sociallogin.user.is_active:
                self._recusar(request, provedor, "usuario_inativo", email)
            return

        usuario = Usuario.objects.filter(email__iexact=email, is_active=True).first()
        if usuario is None:
            self._recusar(request, provedor, "nao_cadastrado", email)
        sociallogin.connect(request, usuario)

    @staticmethod
    def _email_verificado(sociallogin):
        for endereco in sociallogin.email_addresses:
            if endereco.verified and endereco.email:
                return endereco.email.strip().lower()
        return ""

    @staticmethod
    def _recusar(request, provedor, motivo, email):
        """Registra a recusa e devolve o usuário à tela de login com o motivo."""
        auditoria.registrar(
            LogAuditoria.Acao.LOGIN_SOCIAL_RECUSADO,
            request=request,
            alvo=f"social:{provedor}",
            detalhes={"motivo": motivo, "email": email, "provedor": provedor},
        )
        raise ImmediateHttpResponse(
            HttpResponseRedirect(f"{settings.AUTH_URL_LOGIN}?erro={motivo}")
        )
