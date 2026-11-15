"""Testes do endpoint de resumo gerencial (dashboard) das NFS-e."""

import datetime as dt
from decimal import Decimal

from django.utils import timezone
from django_tenants.utils import schema_context

from core.permissoes import Perfil
from fiscal.models import Nfse
from fiscal.tests.apoio import criar_rascunho_de_teste, preparar_empresa_para_emitir

DASHBOARD = "/api/fiscal/notas/dashboard/"


def _criar_nota_dashboard(
    empresa,
    *,
    situacao=Nfse.Situacao.AUTORIZADA,
    servico_nome="Consultoria",
    valor="100.00",
    tomador="TOMADOR PADRAO LTDA",
    dias_atras=0,
    horas_atras=0,
    numero_nfse="100",
    com_emitida_em=True,
):
    with schema_context(empresa.schema_name):
        nota = criar_rascunho_de_teste(valor=valor)
        momento = timezone.now() - dt.timedelta(days=dias_atras, hours=horas_atras)
        Nfse.objects.filter(pk=nota.pk).update(
            situacao=situacao,
            servico={**nota.servico, "nome": servico_nome},
            tomador_nome=tomador,
            valor_servico=Decimal(valor),
            numero_nfse=numero_nfse if situacao == Nfse.Situacao.AUTORIZADA else "",
            emitida_em=momento if com_emitida_em else None,
            criado_em=momento,
        )
        return nota.pk


def test_dashboard_vazio(api_de, empresa_a):
    """Retorna contadores zerados e listas vazias quando não há notas autorizadas."""
    api = api_de(empresa_a, Perfil.CONSULTA)

    resposta = api.get(DASHBOARD)

    assert resposta.status_code == 200
    assert resposta.json() == {
        "quantidade_emitidas": 0,
        "valor_total_servicos": "0.00",
        "servicos_mais_utilizados": [],
        "ultimas_notas": [],
    }


def test_dashboard_filtra_janela_30_dias_e_situacao(api_de, empresa_a):
    """Considera apenas NFS-e autorizadas nos últimos 30 dias (com fallback para criado_em)."""
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)

    id_recente = _criar_nota_dashboard(
        empresa_a,
        servico_nome="Consultoria Fiscal",
        valor="250.00",
        tomador="CLIENTE ALFA LTDA",
        dias_atras=1,
        numero_nfse="101",
    )
    id_fallback = _criar_nota_dashboard(
        empresa_a,
        servico_nome="Suporte Mensal",
        valor="150.00",
        tomador="CLIENTE BETA LTDA",
        dias_atras=29,
        numero_nfse="102",
        com_emitida_em=False,
    )
    _criar_nota_dashboard(
        empresa_a,
        servico_nome="Serviço Antigo",
        valor="999.00",
        dias_atras=31,
        numero_nfse="99",
    )
    for situacao in (
        Nfse.Situacao.RASCUNHO,
        Nfse.Situacao.CANCELADA,
        Nfse.Situacao.REJEITADA,
    ):
        _criar_nota_dashboard(
            empresa_a,
            situacao=situacao,
            servico_nome="Não Contabilizar",
            valor="500.00",
            dias_atras=2,
        )

    api = api_de(empresa_a, Perfil.CONSULTA)
    resposta = api.get(DASHBOARD)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["quantidade_emitidas"] == 2
    assert dados["valor_total_servicos"] == "400.00"
    assert [s["servico"] for s in dados["servicos_mais_utilizados"]] == [
        "Consultoria Fiscal",
        "Suporte Mensal",
    ]
    assert [n["id"] for n in dados["ultimas_notas"]] == [id_recente, id_fallback]
    assert dados["ultimas_notas"][0]["tomador_nome"] == "CLIENTE ALFA LTDA"
    assert dados["ultimas_notas"][0]["valor_servico"] == "250.00"


def test_dashboard_limita_top_6_servicos_e_10_ultimas_notas(api_de, empresa_a):
    """Agrupa os 6 serviços mais utilizados e ordena as 10 notas mais recentes."""
    with schema_context(empresa_a.schema_name):
        preparar_empresa_para_emitir(empresa_a)

    lotes = [
        ("Serviço A", "100.00"),
        ("Serviço A", "100.00"),
        ("Serviço A", "100.00"),
        ("Serviço B", "250.00"),
        ("Serviço B", "250.00"),
        ("Serviço C", "100.00"),
        ("Serviço C", "100.00"),
        ("Serviço D", "900.00"),
        ("Serviço E", "400.00"),
        ("Serviço F", "300.00"),
        ("Serviço G", "100.00"),
    ]
    ids_por_ordem_crescente_idade = []
    for idx, (nome, valor) in enumerate(lotes):
        nota_id = _criar_nota_dashboard(
            empresa_a,
            servico_nome=nome,
            valor=valor,
            tomador=f"TOMADOR {idx + 1}",
            horas_atras=idx + 1,
            numero_nfse=str(200 + idx),
        )
        ids_por_ordem_crescente_idade.append(nota_id)

    api = api_de(empresa_a, Perfil.CONSULTA)
    resposta = api.get(DASHBOARD)

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["quantidade_emitidas"] == 11
    assert dados["valor_total_servicos"] == "2700.00"

    assert dados["servicos_mais_utilizados"] == [
        {"servico": "Serviço A", "quantidade": 3, "valor_total": "300.00"},
        {"servico": "Serviço B", "quantidade": 2, "valor_total": "500.00"},
        {"servico": "Serviço C", "quantidade": 2, "valor_total": "200.00"},
        {"servico": "Serviço D", "quantidade": 1, "valor_total": "900.00"},
        {"servico": "Serviço E", "quantidade": 1, "valor_total": "400.00"},
        {"servico": "Serviço F", "quantidade": 1, "valor_total": "300.00"},
    ]

    assert [n["id"] for n in dados["ultimas_notas"]] == ids_por_ordem_crescente_idade[:10]
    assert set(dados["ultimas_notas"][0].keys()) == {
        "id",
        "serie",
        "numero_dps",
        "numero_nfse",
        "emitida_em",
        "tomador_nome",
        "valor_servico",
    }


def test_dashboard_exige_permissao_nfse_consultar(api_de, empresa_a):
    """Recusa acesso quando o vínculo não possui a permissão nfse.consultar."""
    api = api_de(empresa_a, Perfil.EMISSOR, permissoes_removidas=["nfse.consultar"])

    resposta = api.get(DASHBOARD)

    assert resposta.status_code == 403
