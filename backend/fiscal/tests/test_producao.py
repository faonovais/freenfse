"""Troca para produção (issue #20): certificado válido, CNPJ conferido e convênio vigente.

Cada condição tem o seu teste. Em todas as recusas vale o mesmo: nada é gravado (o ambiente e o
convênio guardado ficam como estavam) e a mensagem lista, em linguagem simples, o que falta.
"""

import datetime as dt
from types import SimpleNamespace

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

from conftest import CNPJ_A, CNPJ_B
from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal import gateway
from fiscal.models import Certificado, ParametrosFiscais
from fiscal.services import producao as servico_producao
from fiscal.services.certificado import divergencia_de_cnpj
from fiscal.services.producao import (
    ProducaoNaoLiberada,
    avaliar_convenio,
    mensagem_das_pendencias,
    pendencias_locais,
)
from fiscal.tests.apoio import convenio_aderente, convenio_nao_aderente, falha_de_rede

URL = "/api/fiscal/parametros/"
VERIFICAR = f"{URL}verificar-convenio/"
TROCAR = {"ambiente": "producao", "confirmar_producao": True}
HOJE = dt.date(2026, 10, 31)
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _municipios(municipios_basicos):
    """O município emissor é validado e nomeado pela tabela de municípios."""


def _codigos(resposta):
    return [p["codigo"] for p in resposta.json()["pendencias"]]


def _no_banco(empresa):
    """Parâmetros e certificado como estão no banco (fora da API)."""
    with schema_context(empresa.schema_name):
        return ParametrosFiscais.obter(), Certificado.objects.first()


def _alterar_certificado(empresa, **campos):
    with schema_context(empresa.schema_name):
        Certificado.objects.update(**campos)


def _nada_mudou(empresa, antes):
    """A recusa não gravou nada: ambiente e convênio guardado são os de antes."""
    parametros, _ = _no_banco(empresa)
    assert parametros.ambiente == "producao_restrita"
    assert parametros.convenio_resultado == antes.convenio_resultado
    assert parametros.convenio_ambiente == antes.convenio_ambiente
    assert parametros.convenio_verificado_em == antes.convenio_verificado_em
    assert not LogAuditoria.objects.filter(acao=LogAuditoria.Acao.AMBIENTE_ALTERADO).exists()


@pytest.fixture
def apta(api_de, empresa_a, liberar_producao):
    """Empresa A apta (certificado, município, convênio aderente) e já verificada na restrita."""
    api = api_de(empresa_a)
    transporte = liberar_producao(api)
    assert api.post(VERIFICAR).status_code == 200  # o convênio guardado é o da restrita
    transporte.chamadas.clear()
    return SimpleNamespace(api=api, transporte=transporte, antes=_no_banco(empresa_a)[0])


# -- o caminho feliz ------------------------------------------------------------------------


def test_troca_consulta_o_convenio_de_producao_e_ja_o_deixa_valido(apta, empresa_a, usuario):
    resposta = apta.api.patch(URL, TROCAR)

    assert resposta.status_code == 200, resposta.json()
    corpo = resposta.json()
    assert corpo["ambiente"] == "producao"
    # O convênio guardado agora é o de PRODUÇÃO, do município atual: a emissão não fica bloqueada.
    assert corpo["convenio"]["atual"] is True and corpo["convenio"]["ambiente"] == "producao"
    assert corpo["convenio"]["aderente"] is True
    # A consulta foi ao host de produção, nunca ao da produção restrita.
    assert apta.transporte.chamadas
    assert all(u.startswith("https://adn.nfse.gov.br/") for _, u in apta.transporte.chamadas)
    # Duas verificações auditadas: a da restrita (preparo) e a da própria troca.
    verificacoes = list(
        LogAuditoria.objects.filter(acao=LogAuditoria.Acao.CONVENIO_VERIFICADO).order_by("id")
    )
    assert [v.detalhes["ambiente"] for v in verificacoes] == ["producao_restrita", "producao"]
    assert verificacoes[1].detalhes["na_troca_para_producao"] is True
    assert verificacoes[1].usuario == usuario
    assert LogAuditoria.objects.filter(acao=LogAuditoria.Acao.AMBIENTE_ALTERADO).count() == 1


def test_convenio_com_ativacao_hoje_ja_e_vigente(apta, transporte):
    transporte({"/convenio": convenio_aderente(dataAtivacao=timezone.localdate().isoformat())})

    assert apta.api.patch(URL, TROCAR).status_code == 200


def test_certificado_de_outro_estabelecimento_autorizado_serve(apta, empresa_a):
    _alterar_certificado(empresa_a, cnpj_titular=CNPJ_A[:8] + "000299", mesma_raiz_autorizada=True)

    assert apta.api.patch(URL, TROCAR).status_code == 200


# -- certificado ----------------------------------------------------------------------------


def test_sem_certificado_nao_troca_e_nao_consulta_a_rede(
    api_de, empresa_a, municipios_basicos, transporte
):
    api = api_de(empresa_a)
    api.patch(URL, {"codigo_municipio_emissor": "2101400"})
    falso = transporte({"/convenio": convenio_aderente()})
    antes = _no_banco(empresa_a)[0]

    resposta = api.patch(URL, TROCAR)

    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["codigo"] == "producao_nao_liberada" and _codigos(resposta) == ["sem_certificado"]
    assert corpo["pendencias"][0]["tela"] == "/fiscal/certificado"
    assert "certificado digital A1" in corpo["detalhe"]
    assert falso.chamadas == []
    _nada_mudou(empresa_a, antes)


def test_sem_certificado_a_consulta_nao_sai_nem_se_a_conferencia_local_deixar_passar(
    api_de, empresa_a, municipios_basicos, transporte, monkeypatch
):
    """Segunda trava: se a conferência local falhasse, a consulta ainda recusaria (nunca um 500)."""
    monkeypatch.setattr(servico_producao, "pendencias_locais", lambda **_: [])
    api = api_de(empresa_a)
    api.patch(URL, {"codigo_municipio_emissor": "2101400"})
    falso = transporte({"/convenio": convenio_aderente()})
    antes = _no_banco(empresa_a)[0]

    resposta = api.patch(URL, TROCAR)

    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "producao_nao_liberada"
    assert _codigos(resposta) == ["convenio_nao_verificado"]
    assert "não tem certificado A1" in resposta.json()["detalhe"]
    assert falso.chamadas == []
    _nada_mudou(empresa_a, antes)


@pytest.mark.parametrize(
    ("campos", "codigo", "trecho"),
    [
        (
            {"valido_ate": timezone.now() - dt.timedelta(days=1)},
            "certificado_vencido",
            "venceu em",
        ),
        (
            {"valido_de": timezone.now() + dt.timedelta(days=2)},
            "certificado_ainda_nao_vale",
            "só passa a valer em",
        ),
        ({"cnpj_titular": CNPJ_B}, "certificado_cnpj", "diferente do CNPJ da empresa"),
        (
            {"cnpj_titular": CNPJ_A[:8] + "000299", "mesma_raiz_autorizada": False},
            "certificado_cnpj",
            "outro estabelecimento da mesma empresa",
        ),
    ],
    ids=["vencido", "ainda_nao_vale", "cnpj_de_outra_empresa", "mesma_raiz_nao_autorizada"],
)
def test_certificado_invalido_nao_libera_a_troca(apta, empresa_a, campos, codigo, trecho):
    _alterar_certificado(empresa_a, **campos)
    antes = _no_banco(empresa_a)[0]

    resposta = apta.api.patch(URL, TROCAR)

    assert resposta.status_code == 400 and resposta.json()["codigo"] == "producao_nao_liberada"
    assert _codigos(resposta) == [codigo]
    assert trecho in resposta.json()["detalhe"]
    assert apta.transporte.chamadas == []  # nem a consulta ao vivo é tentada
    _nada_mudou(empresa_a, antes)


def test_certificado_vencido_e_com_cnpj_errado_lista_os_dois_motivos(apta, empresa_a):
    _alterar_certificado(
        empresa_a, cnpj_titular=CNPJ_B, valido_ate=timezone.now() - dt.timedelta(days=1)
    )

    resposta = apta.api.patch(URL, TROCAR)

    assert _codigos(resposta) == ["certificado_cnpj", "certificado_vencido"]


# -- município e a lista do que falta -------------------------------------------------------


def test_sem_municipio_emissor_nao_libera(apta, empresa_a):
    with schema_context(empresa_a.schema_name):
        ParametrosFiscais.objects.update(codigo_municipio_emissor="")
    antes = _no_banco(empresa_a)[0]

    resposta = apta.api.patch(URL, TROCAR)

    assert _codigos(resposta) == ["sem_municipio"]
    assert resposta.json()["pendencias"][0]["tela"] == "/fiscal/parametros"
    _nada_mudou(empresa_a, antes)


def test_tudo_o_que_falta_vem_junto_numerado_e_com_a_tela_para_resolver(api_de, empresa_a):
    resposta = api_de(empresa_a).patch(URL, TROCAR)  # empresa sem nada configurado

    corpo = resposta.json()
    assert resposta.status_code == 400
    assert _codigos(resposta) == ["sem_certificado", "sem_municipio"]
    assert corpo["detalhe"].startswith("Ainda não é possível trocar para o ambiente de produção.")
    assert "(1) Envie o certificado" in corpo["detalhe"]
    assert "(2) Informe o município emissor" in corpo["detalhe"]
    assert corpo["ambiente"] == [corpo["detalhe"]]  # a tela mostra no campo "ambiente"
    assert {p["tela"] for p in corpo["pendencias"]} == {"/fiscal/certificado", "/fiscal/parametros"}


# -- convênio -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rota", "codigo", "trecho"),
    [
        (convenio_nao_aderente(), "convenio_nao_aderente", "NÃO tem convênio"),
        (
            convenio_aderente(dataAtivacao="2999-01-01"),
            "convenio_ainda_nao_vigente",
            "só passa a valer em 01/01/2999",
        ),
        (falha_de_rede(), "convenio_nao_verificado", "Não foi possível confirmar agora"),
    ],
    ids=["nao_aderente", "ativacao_futura", "sem_rede"],
)
def test_convenio_sem_vigencia_em_producao_nao_libera(
    apta, empresa_a, transporte, rota, codigo, trecho
):
    transporte({"/convenio": rota, f"/{CNPJ_A}": (200, {})})

    resposta = apta.api.patch(URL, TROCAR)

    assert resposta.status_code == 400 and resposta.json()["codigo"] == "producao_nao_liberada"
    assert _codigos(resposta) == [codigo]
    assert trecho in resposta.json()["detalhe"]
    # O convênio guardado da produção restrita continua valendo para a emissão de testes.
    _nada_mudou(empresa_a, apta.antes)
    assert apta.api.get(URL).json()["convenio"]["atual"] is True


def test_convenio_aderente_so_na_restrita_nao_basta_para_producao(apta, empresa_a, transporte):
    """A verificação feita na restrita (aderente) não vale: a produção é consultada de novo."""
    falso = transporte({"/convenio": convenio_nao_aderente()})  # em produção não aderiu

    resposta = apta.api.patch(URL, TROCAR)

    assert _codigos(resposta) == ["convenio_nao_aderente"]
    assert falso.chamadas and all(
        u.startswith("https://adn.nfse.gov.br/") for _, u in falso.chamadas
    )
    _nada_mudou(empresa_a, apta.antes)


# -- ordem das etapas -----------------------------------------------------------------------


def test_sem_confirmacao_nada_vai_para_a_rede(apta, empresa_a):
    resposta = apta.api.patch(URL, {"ambiente": "producao"})

    assert resposta.status_code == 400 and resposta.json()["codigo"] == "confirmacao_necessaria"
    assert apta.transporte.chamadas == []
    _nada_mudou(empresa_a, apta.antes)


def test_pendencia_local_vem_antes_do_pedido_de_confirmacao(api_de, empresa_a):
    """Não adianta pedir que digite a confirmação se a troca nem é possível."""
    resposta = api_de(empresa_a).patch(URL, {"ambiente": "producao"})

    assert resposta.status_code == 400 and resposta.json()["codigo"] == "producao_nao_liberada"


def test_o_municipio_novo_enviado_na_troca_e_o_consultado(apta):
    resposta = apta.api.patch(URL, {**TROCAR, "codigo_municipio_emissor": "1721000"})

    assert resposta.status_code == 200, resposta.json()
    assert any("1721000" in url for _, url in apta.transporte.chamadas)
    assert not any("2101400" in url for _, url in apta.transporte.chamadas)
    assert resposta.json()["convenio"]["codigo_municipio"] == "1721000"
    assert resposta.json()["convenio"]["atual"] is True


def test_depois_de_em_producao_alterar_outro_campo_nao_consulta_nada(apta):
    apta.api.patch(URL, TROCAR)
    apta.transporte.chamadas.clear()

    serie = apta.api.patch(URL, {"serie_dps": 3})
    de_novo = apta.api.patch(URL, TROCAR)  # já está em produção: não é uma troca

    assert serie.status_code == 200 and de_novo.status_code == 200
    assert apta.transporte.chamadas == []


def test_voltar_para_a_restrita_nao_exige_nada(apta, empresa_a):
    apta.api.patch(URL, TROCAR)
    apta.api.delete("/api/fiscal/certificado/")

    resposta = apta.api.patch(URL, {"ambiente": "producao_restrita"})

    assert resposta.status_code == 200 and resposta.json()["ambiente"] == "producao_restrita"


@pytest.mark.parametrize("perfil", [Perfil.EMISSOR, Perfil.CONSULTA, Perfil.FINANCEIRO])
def test_so_quem_edita_a_configuracao_troca_de_ambiente(
    api_de, empresa_a, liberar_producao, perfil
):
    api = api_de(empresa_a, perfil)

    assert api.patch(URL, TROCAR).status_code == 403


# -- a verificação do convênio não desfaz o que outra pessoa fez no meio -------------------


def test_verificar_o_convenio_nao_desfaz_uma_troca_feita_durante_a_consulta(
    apta, empresa_a, monkeypatch
):
    instalado = gateway.verificar_convenio

    def com_outra_pessoa_mexendo(**kw):
        with schema_context(empresa_a.schema_name):
            ParametrosFiscais.objects.update(serie_dps=9, ambiente="producao")
        return instalado(**kw)

    monkeypatch.setattr(gateway, "verificar_convenio", com_outra_pessoa_mexendo)

    resposta = apta.api.post(VERIFICAR)

    assert resposta.status_code == 200
    parametros, _ = _no_banco(empresa_a)
    assert (parametros.ambiente, parametros.serie_dps) == ("producao", 9)
    # O resultado é da restrita (onde a consulta foi feita): não vale para a produção atual.
    assert parametros.convenio_ambiente == "producao_restrita"
    assert parametros.convenio_atual is False


# -- regras puras ---------------------------------------------------------------------------


def _convenio(aderente=True, data_ativacao=None):
    return SimpleNamespace(aderente=aderente, data_ativacao=data_ativacao)


@pytest.mark.parametrize(
    ("convenio", "esperado"),
    [
        (_convenio(True), None),
        (_convenio(True, "2024-05-02"), None),
        (_convenio(True, "2024-05-02T00:00:00"), None),
        (_convenio(True, HOJE.isoformat()), None),  # ativa hoje: já vale
        (_convenio(True, (HOJE + dt.timedelta(days=1)).isoformat()), "convenio_ainda_nao_vigente"),
        (_convenio(True, "amanhã"), "convenio_data_ilegivel"),
        (_convenio(False, "2024-05-02"), "convenio_nao_aderente"),
        (_convenio(None), "convenio_indefinido"),
    ],
)
def test_avaliar_convenio_em_producao(convenio, esperado):
    pendencia = avaliar_convenio(convenio, lugar="Balsas/MA", hoje=HOJE)

    assert (pendencia.codigo if pendencia else None) == esperado
    if pendencia:
        assert "Balsas/MA" in pendencia.mensagem and pendencia.mensagem.endswith(".")


def test_mensagem_das_pendencias_numera_e_exige_resolver_antes():
    pendencias = [
        avaliar_convenio(_convenio(False), lugar="Balsas/MA"),
        avaliar_convenio(_convenio(None), lugar="Balsas/MA"),
    ]

    texto = mensagem_das_pendencias(pendencias)

    assert texto.startswith(
        "Ainda não é possível trocar para o ambiente de produção. Resolva antes:"
    )
    assert "(1) O município Balsas/MA NÃO tem convênio" in texto and "(2) A consulta" in texto
    assert str(ProducaoNaoLiberada(pendencias)) == texto


@pytest.mark.parametrize(
    ("certificado", "empresa", "mesma_raiz", "serve"),
    [
        ("11222333000181", "11222333000181", False, True),
        ("11222333000181", "11222333000181", True, True),
        ("11222333000262", "11222333000181", True, True),  # filial, autorizada
        ("11222333000262", "11222333000181", False, False),  # filial, não autorizada
        ("99888777000155", "11222333000181", True, False),  # outra raiz nunca serve
        ("ab12cd34000195", "AB12CD34000195", False, True),  # CNPJ alfanumérico, caixa indiferente
    ],
)
def test_divergencia_de_cnpj(certificado, empresa, mesma_raiz, serve):
    divergencia = divergencia_de_cnpj(certificado, empresa, mesma_raiz=mesma_raiz)

    assert (divergencia is None) is serve


def test_pendencias_locais_de_empresa_completa_e_vazia(apta, empresa_a):
    parametros, certificado = _no_banco(empresa_a)

    assert (
        pendencias_locais(empresa=empresa_a, parametros=parametros, certificado=certificado) == []
    )
    # No limite da validade: vale até o último instante, vence depois.
    limite = certificado.valido_ate
    assert not pendencias_locais(
        empresa=empresa_a, parametros=parametros, certificado=certificado, agora=limite
    )
    depois = pendencias_locais(
        empresa=empresa_a,
        parametros=parametros,
        certificado=certificado,
        agora=limite + dt.timedelta(seconds=1),
    )
    assert [p.codigo for p in depois] == ["certificado_vencido"]
