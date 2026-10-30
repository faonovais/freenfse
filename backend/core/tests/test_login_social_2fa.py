"""O login social NÃO contorna o 2FA: com TOTP ativo, o Google sozinho não abre a sessão.

O fluxo é percorrido de verdade (rotas, sessão e etapas do allauth), com o provedor
simulado: só a conversa com o Google é trocada por dados fictícios. Há duas portas de
entrada social, e as duas precisam respeitar o segundo fator: o retorno OAuth
(`/accounts/google/login/callback/`) e o login por token do Google
(`/_allauth/browser/v1/auth/provider/token`).
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account import app_settings as account_settings
from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.totp.internal.auth import TOTP
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from rest_framework.test import APIClient

from core.models import LogAuditoria
from core.tests.test_autenticacao import codigo_totp

BASE = "/_allauth/browser/v1"
SESSAO = f"{BASE}/auth/session"
MFA_AUTENTICAR = f"{BASE}/auth/2fa/authenticate"
SEGREDO = "JBSWY3DPEHPK3PXP"
Acao = LogAuditoria.Acao


@pytest.fixture(autouse=True)
def google_configurado(settings):
    """Credenciais fictícias do Google, como estarão em produção (vêm do ambiente)."""
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {"APPS": [{"client_id": "id-ficticio", "secret": "segredo-ficticio", "key": ""}]}
    }


def _identidade(email):
    """Dados que o Google devolveria para este e-mail (verificado)."""
    return {
        "sub": f"uid-{email}",
        "id": f"uid-{email}",
        "email": email,
        "email_verified": True,
        "verified_email": True,
        "name": "Pessoa Ficticia",
    }


def entrar_pelo_retorno_oauth(cliente, email):
    """Percorre o login Google: redireciona ao provedor e volta pelo callback OAuth."""
    ida = cliente.post(
        f"{BASE}/auth/provider/redirect",
        {"provider": "google", "callback_url": "/", "process": "login"},
    )
    estado = parse_qs(urlparse(ida["Location"]).query)["state"][0]

    def completar_login(self, request, app, token, **kwargs):
        return self.get_provider().sociallogin_from_response(request, _identidade(email))

    with (
        patch.object(
            OAuth2Client, "get_access_token", lambda self, code, **kw: {"access_token": "t"}
        ),
        patch.object(GoogleOAuth2Adapter, "complete_login", completar_login),
    ):
        return cliente.get("/accounts/google/login/callback/", {"code": "c", "state": estado})


def entrar_pelo_token_do_google(cliente, email):
    """Login pelo token (id_token) do Google, a segunda porta social do allauth headless."""
    corpo = {
        "provider": "google",
        "process": "login",
        "token": {"client_id": "id-ficticio", "id_token": "token-ficticio"},
    }
    with patch(
        "allauth.socialaccount.providers.google.views._verify_and_decode",
        return_value=_identidade(email),
    ):
        return cliente.post(f"{BASE}/auth/provider/token", corpo, format="json")


PORTAS_SOCIAIS = [
    pytest.param(entrar_pelo_retorno_oauth, id="retorno-oauth"),
    pytest.param(entrar_pelo_token_do_google, id="token-do-google"),
]


def autenticado(cliente):
    """A sessão do cliente está autenticada?"""
    return cliente.get(SESSAO).json()["meta"]["is_authenticated"]


@pytest.mark.parametrize("entrar", PORTAS_SOCIAIS)
@pytest.mark.parametrize("quem", ["usuario", "master"])
def test_com_totp_ativo_o_google_sozinho_nao_abre_a_sessao(request, entrar, quem):
    pessoa = request.getfixturevalue(quem)
    TOTP.activate(pessoa, SEGREDO)
    cliente = APIClient()

    entrar(cliente, pessoa.email)

    # O Google já confirmou a identidade, mas a sessão continua anônima...
    sessao = cliente.get(SESSAO)
    assert sessao.status_code == 401
    assert sessao.json()["meta"]["is_authenticated"] is False
    pendentes = [f for f in sessao.json()["data"]["flows"] if f.get("is_pending")]
    assert [f["id"] for f in pendentes] == ["mfa_authenticate"]
    # ...e nada da aplicação responde antes do código.
    assert cliente.get("/api/eu/").status_code == 403
    assert not LogAuditoria.objects.filter(acao=Acao.LOGIN, usuario=pessoa).exists()


@pytest.mark.parametrize("entrar", PORTAS_SOCIAIS)
@pytest.mark.parametrize("quem", ["usuario", "master"])
def test_codigo_errado_nao_abre_a_sessao_e_o_certo_conclui_o_login(request, entrar, quem):
    pessoa = request.getfixturevalue(quem)
    TOTP.activate(pessoa, SEGREDO)
    cliente = APIClient()
    entrar(cliente, pessoa.email)

    errado = cliente.post(MFA_AUTENTICAR, {"code": "000000"}, format="json")

    assert errado.status_code == 400
    assert autenticado(cliente) is False
    assert cliente.get("/api/eu/").status_code == 403

    certo = cliente.post(MFA_AUTENTICAR, {"code": codigo_totp(SEGREDO)}, format="json")

    assert certo.status_code == 200
    assert autenticado(cliente) is True
    assert cliente.get("/api/eu/").json()["email"] == pessoa.email
    assert LogAuditoria.objects.filter(acao=Acao.LOGIN, usuario=pessoa).exists()


@pytest.mark.parametrize("entrar", PORTAS_SOCIAIS)
def test_sem_totp_o_login_social_abre_a_sessao_direto(usuario, entrar):
    """Controle: prova que os testes acima distinguem 'desafiado' de 'autenticado'."""
    cliente = APIClient()

    entrar(cliente, usuario.email)

    assert autenticado(cliente) is True
    assert cliente.get("/api/eu/").json()["email"] == usuario.email


@pytest.mark.parametrize("entrar", PORTAS_SOCIAIS)
def test_master_sem_totp_pelo_google_cai_na_exigencia_de_2fa(settings, master, entrar):
    """A política de 2FA do Master vale igual para o login social: só a tela de configuração."""
    settings.AUTH_EXIGIR_2FA_MASTER = True
    cliente = APIClient()

    entrar(cliente, master.email)

    eu = cliente.get("/api/eu/")
    assert eu.status_code == 200
    assert eu.json()["mfa"] == {"ativo": False, "obrigatorio": True}
    bloqueada = cliente.get("/api/admin-global/empresas/")
    assert bloqueada.status_code == 403
    assert bloqueada.json()["codigo"] == "2fa_obrigatorio"


def test_confiar_neste_navegador_esta_desligado():
    """Se ligado, um navegador 'confiável' dispensaria o código também no login social."""
    assert mfa_settings.TRUST_ENABLED is False
    assert account_settings.LOGIN_BY_CODE_TRUST_ENABLED is False
