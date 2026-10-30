"""Certificado A1: validação (senha, CNPJ, validade), guarda cifrada e sigilo do .pfx e da senha."""

import base64
import datetime as dt
import logging

import pytest
from django.db import connection
from django_tenants.utils import schema_context

from conftest import CNPJ_A, CNPJ_B, cnpj_de_teste
from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal.models import Certificado
from fiscal.tests.apoio import SENHA_DO_PFX, gerar_pfx

URL = "/api/fiscal/certificado/"
pytestmark = pytest.mark.django_db


def _enviar(api, pfx, senha=SENHA_DO_PFX, **campos):
    return api.post_arquivo(URL, pfx, nome="certificado.pfx", senha=senha, **campos)


def _coluna_bruta(empresa, coluna):
    with schema_context(empresa.schema_name), connection.cursor() as cursor:
        cursor.execute(f"SELECT {coluna} FROM fiscal_certificado")  # noqa: S608 - nome fixo
        valor = cursor.fetchone()[0]
    return bytes(valor) if isinstance(valor, memoryview) else valor


def _vazamentos(texto, pfx, senha=SENHA_DO_PFX):
    """Pedaços do segredo encontrados em `texto` (JSON, log…): lista vazia = nada vazou."""
    candidatos = {
        "senha": senha,
        "pfx em base64": base64.b64encode(pfx).decode()[:60],
        "pfx em hex": pfx.hex()[:60],
        "pfx em base64 url-safe": base64.urlsafe_b64encode(pfx).decode()[:60],
    }
    return [nome for nome, valor in candidatos.items() if valor in texto]


# --- Envio válido -----------------------------------------------------------------------


def test_envio_valido_guarda_e_mostra_so_os_metadados(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_A)

    resposta = _enviar(api_de(empresa_a), pfx)

    assert resposta.status_code == 201, resposta.json()
    corpo = resposta.json()
    assert corpo["existe"] is True
    assert corpo["cnpj_titular"] == CNPJ_A and corpo["cnpj_formatado"] == "11.222.333/0001-81"
    assert CNPJ_A in corpo["titular"]
    assert corpo["vencido"] is False and corpo["faixa_alerta"] is None
    assert 360 <= corpo["dias_para_vencer"] <= 365
    assert corpo["mesma_raiz_autorizada"] is False
    assert len(corpo["impressao_digital"]) == 64
    assert set(corpo) == {
        "existe", "titular", "cnpj_titular", "cnpj_formatado", "valido_de", "valido_ate",
        "dias_para_vencer", "vencido", "faixa_alerta", "impressao_digital",
        "mesma_raiz_autorizada", "enviado_por", "enviado_em",
    }  # fmt: skip


def test_nunca_devolve_o_pfx_nem_a_senha(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_A)
    api = api_de(empresa_a)

    enviado = _enviar(api, pfx)
    consultado = api.get(URL)

    for resposta in (enviado, consultado):
        assert _vazamentos(resposta.content.decode(), pfx) == []
        assert "arquivo_pfx" not in resposta.json() and "senha" not in resposta.json()


def test_pfx_e_senha_ficam_cifrados_no_banco(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_A)
    _enviar(api_de(empresa_a), pfx)

    bruto_pfx = _coluna_bruta(empresa_a, "arquivo_pfx")
    bruto_senha = _coluna_bruta(empresa_a, "senha")

    assert bruto_pfx.startswith(b"v1:") and bruto_senha.startswith("v1:")
    assert pfx not in bruto_pfx and pfx[:40] not in bruto_pfx
    assert SENHA_DO_PFX not in bruto_senha and SENHA_DO_PFX.encode() not in bruto_pfx
    with schema_context(empresa_a.schema_name):  # e o ORM decifra de volta
        certificado = Certificado.objects.get()
        assert bytes(certificado.arquivo_pfx) == pfx and certificado.senha == SENHA_DO_PFX


def test_pfx_e_senha_nao_vao_para_os_logs(api_de, empresa_a, caplog):
    pfx = gerar_pfx(CNPJ_A)
    caplog.set_level(logging.DEBUG)
    api = api_de(empresa_a)

    _enviar(api, pfx)  # sucesso
    _enviar(api, pfx, senha="senha-errada-123")  # falha
    api.get(URL)
    api.delete(URL)

    assert _vazamentos(caplog.text, pfx) == []
    assert "senha-errada-123" not in caplog.text


def test_pfx_e_senha_nao_vao_para_a_auditoria(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_A)
    api = api_de(empresa_a)
    _enviar(api, pfx)
    api.delete(URL)

    registros = list(
        LogAuditoria.objects.filter(
            acao__in=[LogAuditoria.Acao.CERTIFICADO_ENVIADO, LogAuditoria.Acao.CERTIFICADO_REMOVIDO]
        )
    )
    assert [r.acao for r in sorted(registros, key=lambda r: r.id)] == [
        "certificado_enviado",
        "certificado_removido",
    ]
    texto = " ".join(f"{r.alvo} {r.detalhes}" for r in registros)
    assert _vazamentos(texto, pfx) == []
    enviado = next(r for r in registros if r.acao == "certificado_enviado")
    assert enviado.detalhes["cnpj_titular"] == CNPJ_A and "valido_ate" in enviado.detalhes


def test_repr_do_certificado_nao_expoe_segredos(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_A)
    _enviar(api_de(empresa_a), pfx)

    with schema_context(empresa_a.schema_name):
        certificado = Certificado.objects.get()
        texto = f"{certificado!r} {certificado} {certificado.__dict__.get('titular')}"

    assert _vazamentos(texto, pfx) == []


# --- Recusas ---------------------------------------------------------------------------------


def test_senha_errada_e_recusada_sem_guardar_nada(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_A)

    resposta = _enviar(api_de(empresa_a), pfx, senha="outra-senha-qualquer")

    assert resposta.status_code == 400
    assert "senha" in resposta.json()["detalhe"].lower()
    assert resposta.json()["codigo"] == "certificado_recusado"
    assert "outra-senha-qualquer" not in resposta.content.decode()
    with schema_context(empresa_a.schema_name):
        assert Certificado.objects.count() == 0


def test_cnpj_diferente_do_da_empresa_e_recusado(api_de, empresa_a):
    pfx = gerar_pfx(CNPJ_B)  # certificado de outra empresa

    resposta = _enviar(api_de(empresa_a), pfx)

    assert resposta.status_code == 400
    detalhe = resposta.json()["detalhe"]
    assert CNPJ_B in detalhe and CNPJ_A in detalhe and "diferente" in detalhe


def test_mesma_raiz_exige_autorizacao_explicita(api_de, empresa_a):
    filial = cnpj_de_teste("112223330002")  # mesma raiz (11222333), outro estabelecimento
    pfx = gerar_pfx(filial)
    api = api_de(empresa_a)

    sem_autorizacao = _enviar(api, pfx)
    com_autorizacao = _enviar(api, pfx, mesma_raiz="true")

    assert sem_autorizacao.status_code == 400
    assert "mesma raiz" in sem_autorizacao.json()["detalhe"]
    assert com_autorizacao.status_code == 201, com_autorizacao.json()
    assert com_autorizacao.json()["cnpj_titular"] == filial
    assert com_autorizacao.json()["mesma_raiz_autorizada"] is True


def test_raiz_diferente_nao_passa_nem_com_autorizacao(api_de, empresa_a):
    resposta = _enviar(api_de(empresa_a), gerar_pfx(CNPJ_B), mesma_raiz="true")

    assert resposta.status_code == 400


def test_autorizacao_de_mesma_raiz_nao_marca_quando_o_cnpj_e_igual(api_de, empresa_a):
    resposta = _enviar(api_de(empresa_a), gerar_pfx(CNPJ_A), mesma_raiz="true")

    assert resposta.status_code == 201
    assert resposta.json()["mesma_raiz_autorizada"] is False


def test_certificado_vencido_e_recusado(api_de, empresa_a):
    agora = dt.datetime.now(dt.UTC)
    pfx = gerar_pfx(
        CNPJ_A, valido_de=agora - dt.timedelta(days=400), valido_ate=agora - dt.timedelta(days=2)
    )

    resposta = _enviar(api_de(empresa_a), pfx)

    assert resposta.status_code == 400
    assert "venceu em" in resposta.json()["detalhe"]


def test_certificado_que_ainda_nao_vale_e_recusado(api_de, empresa_a):
    agora = dt.datetime.now(dt.UTC)
    pfx = gerar_pfx(
        CNPJ_A, valido_de=agora + dt.timedelta(days=5), valido_ate=agora + dt.timedelta(days=400)
    )

    resposta = _enviar(api_de(empresa_a), pfx)

    assert resposta.status_code == 400
    assert "só passa a valer" in resposta.json()["detalhe"]


def test_certificado_de_pessoa_fisica_e_recusado(api_de, empresa_a):
    resposta = _enviar(api_de(empresa_a), gerar_pfx(None, cpf="52998224725"))

    assert resposta.status_code == 400
    assert "não traz CNPJ" in resposta.json()["detalhe"]


@pytest.mark.parametrize(
    ("conteudo", "trecho"),
    [
        (b"isto nao e um certificado", "abrir o certificado"),
        (b"", "Escolha o arquivo"),
        (b"\x00" * (256 * 1024 + 1), "grande demais"),
    ],
)
def test_arquivo_invalido_e_recusado(api_de, empresa_a, conteudo, trecho):
    resposta = _enviar(api_de(empresa_a), conteudo)

    assert resposta.status_code == 400
    assert trecho in resposta.json()["detalhe"]


def test_senha_em_branco_e_recusada(api_de, empresa_a):
    resposta = _enviar(api_de(empresa_a), gerar_pfx(CNPJ_A), senha="")

    assert resposta.status_code == 400
    assert "senha" in resposta.json()["detalhe"].lower()


def test_envio_sem_arquivo_e_recusado(api_de, empresa_a):
    resposta = api_de(empresa_a).cliente.post(
        URL, {"senha": SENHA_DO_PFX}, format="multipart", HTTP_X_EMPRESA=str(empresa_a.pk)
    )

    assert resposta.status_code == 400


# --- Substituição, remoção, permissões e isolamento ------------------------------------------


def test_novo_envio_substitui_o_anterior(api_de, empresa_a):
    api = api_de(empresa_a)
    primeiro = _enviar(api, gerar_pfx(CNPJ_A, nome="PRIMEIRO")).json()

    segundo = _enviar(
        api,
        gerar_pfx(CNPJ_A, nome="SEGUNDO", senha="outra-senha-valida-9"),
        senha="outra-senha-valida-9",
    ).json()

    assert segundo["impressao_digital"] != primeiro["impressao_digital"]
    with schema_context(empresa_a.schema_name):
        assert Certificado.objects.count() == 1
        assert Certificado.objects.get().senha == "outra-senha-valida-9"


def test_remover_apaga_o_certificado(api_de, empresa_a):
    api = api_de(empresa_a)
    _enviar(api, gerar_pfx(CNPJ_A))

    removido = api.delete(URL)

    assert removido.status_code == 204
    assert api.get(URL).json() == {"existe": False}
    with schema_context(empresa_a.schema_name):
        assert Certificado.objects.count() == 0


def test_sem_certificado_a_consulta_diz_que_nao_existe(api_de, empresa_a):
    assert api_de(empresa_a).get(URL).json() == {"existe": False}


@pytest.mark.parametrize("perfil", [Perfil.CONSULTA, Perfil.FINANCEIRO])
def test_quem_so_consulta_ve_os_metadados_mas_nao_altera(api_de, api_do_master, empresa_a, perfil):
    _enviar(api_do_master(empresa_a), gerar_pfx(CNPJ_A))
    api = api_de(empresa_a, perfil)

    assert api.get(URL).status_code == 200
    assert _enviar(api, gerar_pfx(CNPJ_A)).status_code == 403
    assert api.delete(URL).status_code == 403


def test_emissor_nao_tem_acesso_a_configuracao(api_de, api_do_master, empresa_a):
    _enviar(api_do_master(empresa_a), gerar_pfx(CNPJ_A))
    api = api_de(empresa_a, Perfil.EMISSOR)

    assert api.get(URL).status_code == 403
    assert _enviar(api, gerar_pfx(CNPJ_A)).status_code == 403


def test_administrador_sem_config_editar_nao_envia(api_de, empresa_a):
    api = api_de(empresa_a, Perfil.ADMINISTRADOR, permissoes_removidas=["config.editar"])

    assert _enviar(api, gerar_pfx(CNPJ_A)).status_code == 403


def test_certificado_da_empresa_a_nao_aparece_na_b(api_do_master, empresa_a, empresa_b):
    _enviar(api_do_master(empresa_a), gerar_pfx(CNPJ_A))

    assert api_do_master(empresa_b).get(URL).json() == {"existe": False}
    # O certificado da A não serve para a B: o CNPJ do titular é conferido por empresa.
    assert _enviar(api_do_master(empresa_b), gerar_pfx(CNPJ_A)).status_code == 400
    assert _enviar(api_do_master(empresa_b), gerar_pfx(CNPJ_B)).status_code == 201
    assert api_do_master(empresa_a).get(URL).json()["cnpj_titular"] == CNPJ_A
