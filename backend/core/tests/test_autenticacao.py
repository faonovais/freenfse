"""Autenticação (allauth headless): login, bloqueio, sessão, 2FA, login social e provedores."""

import runpy
import time
from datetime import timedelta
from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.mfa.models import Authenticator
from allauth.mfa.signals import authenticator_removed
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, hotp_value
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings as django_settings
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from conftest import SENHA_DE_TESTE, criar_usuario_de_teste
from core.auth.adapters import AccountAdapter, SocialAccountAdapter
from core.models import LogAuditoria, Usuario

BASE = "/_allauth/browser/v1"
LOGIN = f"{BASE}/auth/login"
SESSAO = f"{BASE}/auth/session"
TOTP_API = f"{BASE}/account/authenticators/totp"
MFA_AUTENTICAR = f"{BASE}/auth/2fa/authenticate"
REAUTENTICAR = f"{BASE}/auth/reauthenticate"
Acao = LogAuditoria.Acao


def entrar(cliente, usuario, senha=SENHA_DE_TESTE):
    return cliente.post(LOGIN, {"email": usuario.email, "password": senha}, format="json")


@pytest.fixture
def google_configurado(settings):
    """Credenciais fictícias do Google, como estarão em produção (vêm do ambiente)."""
    settings.SOCIALACCOUNT_PROVIDERS = {
        "google": {"APPS": [{"client_id": "id-ficticio", "secret": "segredo-ficticio", "key": ""}]}
    }


def codigo_totp(segredo):
    """Código TOTP válido agora para o segredo (janela atual)."""
    contador = int(time.time()) // 30
    return format_hotp_value(hotp_value(segredo, contador))


# --- Login por e-mail e senha --------------------------------------------------------


def test_login_por_email_e_senha_abre_a_sessao(usuario):
    cliente = APIClient()

    resposta = entrar(cliente, usuario)

    assert resposta.status_code == 200
    assert resposta.json()["meta"]["is_authenticated"] is True
    assert cliente.get("/api/eu/").json()["email"] == usuario.email


def test_login_nao_diferencia_maiusculas_no_email(usuario):
    resposta = APIClient().post(
        LOGIN, {"email": usuario.email.upper(), "password": SENHA_DE_TESTE}, format="json"
    )

    assert resposta.status_code == 200


def test_senha_errada_e_email_inexistente_dao_a_mesma_resposta(usuario):
    senha_errada = APIClient().post(
        LOGIN, {"email": usuario.email, "password": "errada"}, format="json"
    )
    inexistente = APIClient().post(
        LOGIN, {"email": "ninguem@exemplo.test", "password": SENHA_DE_TESTE}, format="json"
    )

    assert senha_errada.status_code == inexistente.status_code == 400
    assert senha_errada.json() == inexistente.json()  # sem enumeração de usuários


def test_usuario_inativo_nao_entra(usuario):
    usuario.is_active = False
    usuario.save()

    assert entrar(APIClient(), usuario).status_code != 200


def test_login_exige_token_csrf(usuario):
    cliente = APIClient(enforce_csrf_checks=True)

    resposta = cliente.post(
        LOGIN, {"email": usuario.email, "password": SENHA_DE_TESTE}, format="json"
    )

    assert resposta.status_code == 403


def test_nao_ha_autocadastro(db):
    cliente = APIClient()

    cadastro = cliente.post(
        f"{BASE}/auth/signup",
        {"email": "intruso@exemplo.test", "password": SENHA_DE_TESTE},
        format="json",
    )

    assert cadastro.status_code == 403
    assert not Usuario.objects.filter(email="intruso@exemplo.test").exists()
    assert cliente.get(f"{BASE}/config").json()["data"]["account"]["is_open_for_signup"] is False


# --- Bloqueio por tentativas ---------------------------------------------------------


def test_bloqueio_apos_n_tentativas_falhas(settings, usuario):
    settings.ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip,3/900s/key"}
    cliente = APIClient()

    for _ in range(3):
        assert entrar(cliente, usuario, "errada").status_code == 400
    # Mesmo com a senha certa, a conta fica bloqueada até a janela expirar.
    bloqueado = entrar(cliente, usuario)

    assert bloqueado.status_code == 400
    assert bloqueado.json()["errors"][0]["code"] == "too_many_login_attempts"
    assert cliente.get("/api/eu/").status_code == 403


def test_bloqueio_vale_por_e_mail_e_nao_afeta_outro_usuario(settings, usuario):
    settings.ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip,3/900s/key"}
    outro = criar_usuario_de_teste("outro@exemplo.test")
    cliente = APIClient()
    for _ in range(3):
        entrar(cliente, usuario, "errada")

    assert entrar(APIClient(), outro).status_code == 200


def test_bloqueio_e_liberado_depois_da_janela(settings, usuario):
    settings.ACCOUNT_RATE_LIMITS = {"login_failed": "10/m/ip,2/900s/key"}
    cliente = APIClient()
    for _ in range(2):
        entrar(cliente, usuario, "errada")
    assert entrar(cliente, usuario).json()["errors"][0]["code"] == "too_many_login_attempts"

    cache.clear()  # equivale a expirar a janela de bloqueio

    assert entrar(cliente, usuario).status_code == 200


def test_limites_padrao_vem_da_configuracao_do_ambiente():
    arquivo = Path(django_settings.BASE_DIR) / "config" / "settings.py"

    carregado = runpy.run_path(str(arquivo))

    assert carregado["ACCOUNT_RATE_LIMITS"]["login_failed"] == "10/m/ip,5/900s/key"


# --- Sessão ----------------------------------------------------------------------------


def test_sessao_expira_por_inatividade_e_renova_a_cada_uso(usuario):
    assert django_settings.SESSION_COOKIE_AGE == 30 * 60
    assert django_settings.SESSION_SAVE_EVERY_REQUEST is True
    cliente = APIClient()
    entrar(cliente, usuario)
    chave = cliente.session.session_key

    # Em uso, a validade é renovada.
    Session.objects.filter(session_key=chave).update(
        expire_date=timezone.now() + timedelta(seconds=60)
    )
    assert cliente.get("/api/eu/").status_code == 200
    renovada = Session.objects.get(session_key=chave).expire_date
    assert renovada > timezone.now() + timedelta(minutes=25)

    # Parada além do limite, a sessão deixa de valer.
    Session.objects.filter(session_key=chave).update(
        expire_date=timezone.now() - timedelta(seconds=1)
    )
    assert cliente.get("/api/eu/").status_code == 403


def test_cookies_da_sessao_nao_sao_acessiveis_por_javascript(usuario):
    cliente = APIClient()

    entrar(cliente, usuario)

    cookie = cliente.cookies[django_settings.SESSION_COOKIE_NAME]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"


# --- 2FA ---------------------------------------------------------------------------------


def test_2fa_do_master_e_exigido_por_padrao_e_libera_os_caminhos_de_configuracao(
    settings, cliente_de, master
):
    settings.AUTH_EXIGIR_2FA_MASTER = True
    cliente = cliente_de(master)

    bloqueado = cliente.get("/api/admin-global/empresas/")
    eu = cliente.get("/api/eu/")

    assert bloqueado.status_code == 403
    assert bloqueado.json()["codigo"] == "2fa_obrigatorio"
    assert eu.status_code == 200 and eu.json()["mfa"] == {"ativo": False, "obrigatorio": True}
    assert cliente.get(TOTP_API).status_code == 404  # o caminho para configurar segue livre
    assert cliente.get("/api/versao/").status_code == 200


def test_2fa_exigido_tambem_para_rotas_de_empresa(settings, cliente_de, master, empresa_a):
    settings.AUTH_EXIGIR_2FA_MASTER = True

    resposta = cliente_de(master).get(
        "/api/empresa-ativa/", headers={"X-Empresa": str(empresa_a.pk)}
    )

    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "2fa_obrigatorio"


def test_master_com_2fa_configurado_acessa(settings, cliente_de, master):
    settings.AUTH_EXIGIR_2FA_MASTER = True
    TOTP.activate(master, "JBSWY3DPEHPK3PXP")

    resposta = cliente_de(master).get("/api/admin-global/empresas/")

    assert resposta.status_code == 200


def test_2fa_pode_ser_exigido_de_todos_e_nao_do_usuario_comum_por_padrao(
    settings, cliente_de, usuario
):
    assert cliente_de(usuario).get("/api/eu/").json()["mfa"]["obrigatorio"] is False

    settings.AUTH_EXIGIR_2FA_TODOS = True

    assert cliente_de(usuario).get("/api/eu/").json()["mfa"]["obrigatorio"] is True
    # O 2FA do usuário comum não afeta o Master quando a política do Master está desligada.
    settings.AUTH_EXIGIR_2FA_TODOS = False
    settings.AUTH_EXIGIR_2FA_MASTER = False
    assert cliente_de(usuario).get("/api/eu/").json()["mfa"]["obrigatorio"] is False


def test_2fa_desligado_para_o_master_quando_a_politica_permite(settings, cliente_de, master):
    settings.AUTH_EXIGIR_2FA_MASTER = False

    assert cliente_de(master).get("/api/admin-global/empresas/").status_code == 200


def test_ativar_o_2fa_exige_reautenticar_com_a_senha(usuario):
    cliente = APIClient()
    entrar(cliente, usuario)
    segredo = cliente.get(TOTP_API).json()["meta"]["secret"]

    sem_reautenticar = cliente.post(TOTP_API, {"code": codigo_totp(segredo)}, format="json")

    assert sem_reautenticar.status_code == 401
    assert {"id": "reauthenticate"} in sem_reautenticar.json()["data"]["flows"]
    assert not Authenticator.objects.filter(user=usuario).exists()


def test_usuario_configura_o_2fa_pela_api_e_a_ativacao_e_auditada(
    usuario, django_capture_on_commit_callbacks
):
    cliente = APIClient()
    entrar(cliente, usuario)
    segredo = cliente.get(TOTP_API).json()["meta"]["secret"]
    assert (
        cliente.post(REAUTENTICAR, {"password": SENHA_DE_TESTE}, format="json").status_code == 200
    )

    # O allauth avisa a ativação em on_commit; o teste executa esses callbacks.
    with django_capture_on_commit_callbacks(execute=True):
        ativado = cliente.post(TOTP_API, {"code": codigo_totp(segredo)}, format="json")

    assert ativado.status_code == 200
    assert Authenticator.objects.filter(user=usuario, type=Authenticator.Type.TOTP).exists()
    assert cliente.get("/api/eu/").json()["mfa"]["ativo"] is True
    assert LogAuditoria.objects.filter(acao=Acao.MFA_ATIVADO, usuario=usuario).exists()


def test_com_2fa_ativo_o_login_so_conclui_com_o_codigo(usuario):
    segredo = "JBSWY3DPEHPK3PXP"
    TOTP.activate(usuario, segredo)
    cliente = APIClient()

    primeira_etapa = entrar(cliente, usuario)

    assert primeira_etapa.status_code == 401
    fluxos = {f["id"] for f in primeira_etapa.json()["data"]["flows"]}
    assert "mfa_authenticate" in fluxos
    assert cliente.get("/api/eu/").status_code == 403  # ainda sem sessão válida

    errado = cliente.post(MFA_AUTENTICAR, {"code": "000000"}, format="json")
    assert errado.status_code == 400
    assert cliente.get("/api/eu/").status_code == 403

    certo = cliente.post(MFA_AUTENTICAR, {"code": codigo_totp(segredo)}, format="json")
    assert certo.status_code == 200
    assert cliente.get("/api/eu/").status_code == 200


def test_desativar_o_2fa_e_auditado(usuario):
    TOTP.activate(usuario, "JBSWY3DPEHPK3PXP")
    authenticator = Authenticator.objects.get(user=usuario, type=Authenticator.Type.TOTP)

    authenticator_removed.send(
        sender=Authenticator, request=None, user=usuario, authenticator=authenticator
    )

    assert LogAuditoria.objects.filter(acao=Acao.MFA_DESATIVADO, usuario=usuario).exists()


# --- Login social --------------------------------------------------------------------------


def _login_social(email, *, verificado=True, provedor="google"):
    conta = SocialAccount(provider=provedor, uid="uid-ficticio-1", extra_data={})
    enderecos = [EmailAddress(email=email, verified=verificado, primary=True)] if email else []
    return SocialLogin(user=Usuario(), account=conta, email_addresses=enderecos)


def _pedido():
    return RequestFactory().get("/accounts/google/login/callback/")


def _recusado(login):
    with pytest.raises(ImmediateHttpResponse) as excecao:
        SocialAccountAdapter().pre_social_login(_pedido(), login)
    resposta = excecao.value.response
    assert resposta.status_code == 302
    return resposta["Location"]


def test_login_social_com_email_nao_cadastrado_e_recusado(db):
    destino = _recusado(_login_social("desconhecido@exemplo.test"))

    assert destino == "/login?erro=nao_cadastrado"
    assert not Usuario.objects.filter(email="desconhecido@exemplo.test").exists()
    assert not SocialAccount.objects.exists()
    registro = LogAuditoria.objects.get(acao=Acao.LOGIN_SOCIAL_RECUSADO)
    assert registro.detalhes["motivo"] == "nao_cadastrado"
    assert registro.detalhes["email"] == "desconhecido@exemplo.test"


def test_login_social_com_email_nao_verificado_pelo_provedor_e_recusado(usuario):
    destino = _recusado(_login_social(usuario.email, verificado=False))

    assert destino == "/login?erro=email_nao_verificado"
    assert not SocialAccount.objects.exists()


def test_login_social_sem_email_e_recusado(db):
    assert _recusado(_login_social("")) == "/login?erro=email_nao_verificado"


def test_login_social_de_usuario_inativo_e_recusado(usuario):
    usuario.is_active = False
    usuario.save()

    assert _recusado(_login_social(usuario.email)) == "/login?erro=nao_cadastrado"


def test_login_social_de_email_cadastrado_liga_a_conta_ao_usuario(usuario, google_configurado):
    login = _login_social(usuario.email.upper())

    SocialAccountAdapter().pre_social_login(_pedido(), login)

    assert login.is_existing
    conta = SocialAccount.objects.get(provider="google", uid="uid-ficticio-1")
    assert conta.user == usuario
    assert Usuario.objects.count() == 1  # nenhum usuário foi criado


def test_login_social_respeita_a_restricao_de_dominio(settings, usuario):
    settings.AUTH_DOMINIOS_PERMITIDOS = ["topo.test", "@outro.test"]

    destino = _recusado(_login_social(usuario.email))  # exemplo.test não está na lista

    assert destino == "/login?erro=dominio_nao_permitido"
    assert not SocialAccount.objects.exists()


def test_login_social_de_dominio_permitido_entra(settings, usuario, google_configurado):
    settings.AUTH_DOMINIOS_PERMITIDOS = ["EXEMPLO.test"]
    login = _login_social(usuario.email)

    SocialAccountAdapter().pre_social_login(_pedido(), login)

    assert SocialAccount.objects.filter(user=usuario).exists()


def test_conta_social_ja_ligada_ainda_passa_pela_restricao_de_dominio(settings, usuario):
    conta = SocialAccount.objects.create(user=usuario, provider="google", uid="uid-ficticio-1")
    login = SocialLogin(
        user=usuario,
        account=conta,
        email_addresses=[EmailAddress(email=usuario.email, verified=True, primary=True)],
    )
    SocialAccountAdapter().pre_social_login(_pedido(), login)  # sem restrição: passa

    settings.AUTH_DOMINIOS_PERMITIDOS = ["topo.test"]

    assert _recusado(login) == "/login?erro=dominio_nao_permitido"


def test_os_adaptadores_nao_abrem_cadastro(db):
    pedido = _pedido()

    assert AccountAdapter().is_open_for_signup(pedido) is False
    assert (
        SocialAccountAdapter().is_open_for_signup(pedido, _login_social("x@exemplo.test")) is False
    )


# --- Provedores: ligados só por configuração ------------------------------------------------


def _carregar_settings(monkeypatch, **ambiente):
    for nome in (
        "AUTH_GOOGLE_CLIENT_ID",
        "AUTH_MICROSOFT_ATIVO",
        "AUTH_OIDC_ATIVO",
    ):
        monkeypatch.delenv(nome, raising=False)
    for nome, valor in ambiente.items():
        monkeypatch.setenv(nome, valor)
    return runpy.run_path(str(Path(django_settings.BASE_DIR) / "config" / "settings.py"))


def test_provedores_estao_instalados_mas_desligados_por_padrao(monkeypatch):
    carregado = _carregar_settings(monkeypatch)

    assert "allauth.socialaccount.providers.google" in carregado["INSTALLED_APPS"]
    assert "allauth.socialaccount.providers.microsoft" in carregado["INSTALLED_APPS"]
    assert "allauth.socialaccount.providers.openid_connect" in carregado["INSTALLED_APPS"]
    assert carregado["SOCIALACCOUNT_PROVIDERS"] == {}


def test_google_liga_com_credenciais_do_ambiente(monkeypatch):
    carregado = _carregar_settings(
        monkeypatch,
        AUTH_GOOGLE_CLIENT_ID="id-ficticio",
        AUTH_GOOGLE_CLIENT_SECRET="segredo-ficticio",
    )

    assert set(carregado["SOCIALACCOUNT_PROVIDERS"]) == {"google"}
    app = carregado["SOCIALACCOUNT_PROVIDERS"]["google"]["APPS"][0]
    assert app["client_id"] == "id-ficticio" and app["secret"] == "segredo-ficticio"


def test_microsoft_e_openid_connect_so_ligam_com_a_flag(monkeypatch):
    carregado = _carregar_settings(
        monkeypatch,
        AUTH_MICROSOFT_ATIVO="true",
        AUTH_MICROSOFT_CLIENT_ID="id-ms",
        AUTH_OIDC_ATIVO="true",
        AUTH_OIDC_URL="https://idp.exemplo.test",
    )

    assert set(carregado["SOCIALACCOUNT_PROVIDERS"]) == {"microsoft", "openid_connect"}
    oidc = carregado["SOCIALACCOUNT_PROVIDERS"]["openid_connect"]["APPS"][0]
    assert oidc["settings"]["server_url"] == "https://idp.exemplo.test"


def test_a_api_nao_oferece_provedores_sem_configuracao(db):
    resposta = APIClient().get(f"{BASE}/config").json()

    assert resposta["data"]["socialaccount"]["providers"] == []


# --- Auditoria dos eventos de acesso ----------------------------------------------------------


def test_login_e_logout_sao_auditados_com_ip(usuario):
    cliente = APIClient()

    entrar(cliente, usuario)
    cliente.delete(SESSAO)

    login = LogAuditoria.objects.get(acao=Acao.LOGIN)
    assert login.usuario == usuario and login.ip == "127.0.0.1" and login.master is False
    assert LogAuditoria.objects.filter(acao=Acao.LOGOUT, usuario=usuario).exists()


def test_login_do_master_leva_a_marca_master(master):
    entrar(APIClient(), master)

    assert LogAuditoria.objects.get(acao=Acao.LOGIN).master is True


def test_login_recusado_e_auditado_sem_a_senha(usuario):
    entrar(APIClient(), usuario, "senha-errada-que-nao-pode-aparecer")

    registro = LogAuditoria.objects.get(acao=Acao.LOGIN_FALHOU)
    assert registro.detalhes == {"email": usuario.email}
    assert "senha-errada-que-nao-pode-aparecer" not in str(registro.detalhes)


def test_ip_vem_do_cabecalho_confiavel_quando_configurado(settings, usuario):
    settings.ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "X-Real-IP"

    APIClient().post(
        LOGIN,
        {"email": usuario.email, "password": SENHA_DE_TESTE},
        format="json",
        headers={"X-Real-IP": "203.0.113.7"},
    )

    assert LogAuditoria.objects.get(acao=Acao.LOGIN).ip == "203.0.113.7"
