"""API de agendamentos: permissões por perfil, modelos, agendamentos, rascunhos e isolamento.

A API usa o relógio real (`timezone.now`); por isso as datas dos testes são sempre relativas a
"hoje". O cálculo exato das datas está em `test_recorrencia.py` e `test_dispatcher.py`.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

from agendamentos.models import Agendamento, ExecucaoAgendamento, ModeloNfse, OrigemNfse
from agendamentos.services import modelos as servico_modelos
from cadastros.tests.conftest import Api
from core.models import LogAuditoria
from core.permissoes import Perfil
from fiscal.models import Nfse
from fiscal.services import emissao
from fiscal.tests.apoio import criar_cadastros_de_teste

pytestmark = pytest.mark.django_db
MODELOS = "/api/agendamentos/modelos/"
AGENDAMENTOS = "/api/agendamentos/agendamentos/"
RASCUNHOS = "/api/agendamentos/rascunhos/"
EXECUCOES = "/api/agendamentos/execucoes/"
OPCOES = "/api/agendamentos/opcoes/"


def amanha():
    return timezone.localdate() + dt.timedelta(days=1)


@pytest.fixture
def emissor(api_de, empresa_pronta):
    return api_de(empresa_pronta, Perfil.EMISSOR)


@pytest.fixture
def dados_do_modelo(empresa_pronta):
    with schema_context(empresa_pronta.schema_name):
        tomador, servico = criar_cadastros_de_teste()
    return {
        "nome": "Mensalidade",
        "ativo": True,
        "tomador": tomador.pk,
        "servico": servico.pk,
        "valores": {"servico": "1500.00"},
        "informacoes_complementares": "Referente a {competencia}.",
    }


@pytest.fixture
def modelo_criado(empresa_pronta, emissor, dados_do_modelo):
    resposta = emissor.post(MODELOS, dados_do_modelo)
    assert resposta.status_code == 201, resposta.json()
    return resposta.json()


def dados_do_agendamento(base, usuario, **extra):
    return {
        "nome": "Cobrança mensal",
        "modelo": base["id"],
        "responsavel": usuario.pk,
        "frequencia": "mensal",
        "dia_do_mes": 5,
        "hora": "08:00",
        "data_inicio": amanha().isoformat(),
        **extra,
    }


# -- permissões ----------------------------------------------------------------------------


def test_cada_perfil_so_faz_o_que_pode(api_de, empresa_pronta, dados_do_modelo):
    emissor = api_de(empresa_pronta, Perfil.EMISSOR)
    criado = emissor.post(MODELOS, dados_do_modelo)
    assert criado.status_code == 201
    modelo_id = criado.json()["id"]

    # Financeiro e Consulta leem, mas não criam nem alteram
    for perfil in (Perfil.FINANCEIRO, Perfil.CONSULTA):
        from core.models import VinculoUsuarioEmpresa

        VinculoUsuarioEmpresa.objects.filter(empresa=empresa_pronta).update(perfil=perfil)
        leitor = Api(emissor.cliente, empresa_pronta)
        assert leitor.get(MODELOS).status_code == 200
        assert leitor.get(AGENDAMENTOS).status_code == 200
        assert leitor.get(EXECUCOES).status_code == 200
        assert leitor.post(MODELOS, dados_do_modelo).status_code == 403
        assert leitor.patch(f"{MODELOS}{modelo_id}/", {"nome": "x"}).status_code == 403
        assert leitor.post(f"{MODELOS}{modelo_id}/gerar-rascunho/").status_code == 403
        assert leitor.post(AGENDAMENTOS, {}).status_code == 403
        assert leitor.post(f"{RASCUNHOS}aprovar/", {"ids": [1]}).status_code == 403
        assert leitor.post(f"{RASCUNHOS}1/descartar/", {"motivo": "xxxxxxx"}).status_code == 403


def test_sem_vinculo_na_empresa_nao_ha_acesso(api_de, empresa_a, empresa_b, usuario, cliente_de):
    api_de(empresa_a, Perfil.ADMINISTRADOR)

    outra = Api(cliente_de(usuario), empresa_b)  # o usuário não tem vínculo com a B

    for url in (MODELOS, AGENDAMENTOS, EXECUCOES, RASCUNHOS, OPCOES):
        assert outra.get(url).status_code == 403


def test_nao_autenticado_nao_entra(empresa_a, cliente_de):
    anonimo = Api(cliente_de(), empresa_a)

    assert anonimo.get(MODELOS).status_code in (401, 403)


# -- modelos -------------------------------------------------------------------------------


def test_criar_modelo_devolve_os_dados_e_registra_a_auditoria(
    emissor, empresa_pronta, modelo_criado
):
    assert modelo_criado["nome"] == "Mensalidade"
    assert modelo_criado["tomador_nome"] == "TOMADOR FICTICIO LTDA"
    assert modelo_criado["servico_nome"] == "Consultoria"
    assert modelo_criado["valores"] == {"servico": "1500.00"}
    assert modelo_criado["informacoes_complementares"] == "Referente a {competencia}."
    assert modelo_criado["problemas"] == {} and modelo_criado["agendamentos_em_uso"] == 0
    assert LogAuditoria.objects.filter(acao="modelo_nfse_salvo").exists()


@pytest.mark.parametrize(
    ("ajuste", "campo"),
    [
        ({"nome": ""}, "nome"),
        ({"tomador": None}, "tomador"),
        ({"tomador": 999999}, "tomador"),
        ({"servico": 999999}, "servico"),
        ({"valores": {"servico": "0"}}, "valores.servico"),
        ({"informacoes_complementares": "{xpto}"}, "informacoes_complementares"),
        ({"email_assunto_modelo": "{desconhecida}"}, "email_assunto_modelo"),
        ({"email_copias_fixas": ["nao-e-email"]}, "email_copias_fixas"),
    ],
)
def test_modelo_invalido_volta_400_apontando_o_campo(emissor, dados_do_modelo, ajuste, campo):
    resposta = emissor.post(MODELOS, {**dados_do_modelo, **ajuste})

    assert resposta.status_code == 400 and campo in resposta.json()


def test_nome_de_modelo_repetido_e_recusado_e_o_inativo_pode_ficar_incompleto(
    emissor, dados_do_modelo, modelo_criado
):
    repetido = emissor.post(MODELOS, {**dados_do_modelo, "nome": "MENSALIDADE"})
    incompleto = emissor.post(MODELOS, {"nome": "Rascunho de modelo", "ativo": False})

    assert repetido.status_code == 400 and "Já existe" in repetido.json()["nome"]
    assert incompleto.status_code == 201


def test_alterar_o_modelo_nao_muda_o_rascunho_ja_gerado(emissor, empresa_pronta, modelo_criado):
    gerado = emissor.post(f"{MODELOS}{modelo_criado['id']}/gerar-rascunho/")
    assert gerado.status_code == 201

    emissor.patch(f"{MODELOS}{modelo_criado['id']}/", {"valores": {"servico": "9000.00"}})

    with schema_context(empresa_pronta.schema_name):
        assert Nfse.objects.get(pk=gerado.json()["id"]).valor_servico == Decimal("1500.00")
    novo = emissor.post(f"{MODELOS}{modelo_criado['id']}/gerar-rascunho/")
    with schema_context(empresa_pronta.schema_name):
        assert Nfse.objects.get(pk=novo.json()["id"]).valor_servico == Decimal("9000.00")


def test_a_api_do_modelo_nao_aceita_nem_devolve_ibs_cbs(emissor, dados_do_modelo):
    corpo = {**dados_do_modelo, "ibs_cbs": {"codigo_indicador_operacao": "000001"}}

    criado = emissor.post(MODELOS, corpo)

    assert criado.status_code == 201
    assert "ibs_cbs" not in criado.json()
    assert "ibs_cbs" not in emissor.get(f"{MODELOS}{criado.json()['id']}/").json()


def test_a_lista_mostra_o_que_impede_o_modelo_de_gerar_rascunho(
    emissor, empresa_pronta, modelo_criado
):
    with schema_context(empresa_pronta.schema_name):
        ModeloNfse.objects.get().servico.__class__.objects.update(vigencia_fim=dt.date(2026, 1, 31))

    lista = emissor.get(MODELOS).json()

    assert "versão vigente" in lista[0]["problemas"]["servico"]


def test_alterar_so_o_email_de_um_modelo_com_servico_vencido_nao_e_bloqueado(
    emissor, empresa_pronta, modelo_criado
):
    with schema_context(empresa_pronta.schema_name):
        ModeloNfse.objects.get().servico.__class__.objects.update(vigencia_fim=dt.date(2026, 1, 31))

    so_email = emissor.patch(f"{MODELOS}{modelo_criado['id']}/", {"email_anexar_pdf": False})
    trocando_servico = emissor.patch(
        f"{MODELOS}{modelo_criado['id']}/", {"valores": {"servico": "10"}}
    )

    assert so_email.status_code == 200 and so_email.json()["email_anexar_pdf"] is False
    assert trocando_servico.status_code == 400 and "servico" in trocando_servico.json()


def test_previa_do_modelo_mostra_totais_e_texto_ou_os_erros(emissor, empresa_pronta, modelo_criado):
    boa = emissor.post(f"{MODELOS}{modelo_criado['id']}/previa/").json()

    assert boa["ok"] and boa["totais"]["valor_servico"] == "1500.00"
    assert boa["informacoes_complementares"].startswith("Referente a ")
    with schema_context(empresa_pronta.schema_name):
        ModeloNfse.objects.update(ativo=False)
    inativo = emissor.post(f"{MODELOS}{modelo_criado['id']}/previa/").json()
    assert inativo["ok"] is False and "inativo" in inativo["erros"]["modelo"]


def test_gerar_rascunho_a_partir_do_modelo_copia_e_nao_emite(
    emissor, empresa_pronta, modelo_criado
):
    resposta = emissor.post(f"{MODELOS}{modelo_criado['id']}/gerar-rascunho/")

    assert resposta.status_code == 201
    with schema_context(empresa_pronta.schema_name):
        nota = Nfse.objects.get(pk=resposta.json()["id"])
        assert (
            nota.situacao == Nfse.Situacao.RASCUNHO
            and nota.criado_por_email == "usuario@exemplo.test"
        )
        assert OrigemNfse.objects.get(nfse=nota).modelo_id == modelo_criado["id"]
        assert LogAuditoria.objects.filter(acao="nfse_rascunho_criado").exists()


def test_gerar_rascunho_de_modelo_invalido_explica(emissor, empresa_pronta, modelo_criado):
    with schema_context(empresa_pronta.schema_name):
        ModeloNfse.objects.update(ativo=False)

    resposta = emissor.post(f"{MODELOS}{modelo_criado['id']}/gerar-rascunho/")

    assert resposta.status_code == 400
    assert (
        resposta.json()["codigo"] == "modelo_invalido"
        and "inativo" in resposta.json()["erros"]["modelo"]
    )


# -- agendamentos --------------------------------------------------------------------------


def test_criar_agendamento_calcula_a_proxima_data_e_lista_as_seguintes(
    emissor, usuario, modelo_criado
):
    resposta = emissor.post(AGENDAMENTOS, dados_do_agendamento(modelo_criado, usuario))

    assert resposta.status_code == 201, resposta.json()
    dados = resposta.json()
    assert dados["situacao"] == "ativo" and dados["execucoes_realizadas"] == 0
    assert dados["proxima_execucao"] is not None and dados["modelo_nome"] == "Mensalidade"
    assert len(dados["proximas"]) == 5
    assert dados["proximas"][0]["instante"] == dados["proxima_execucao"]
    assert dados["proximas"][0]["hora"] == "08:00"
    assert LogAuditoria.objects.filter(acao="agendamento_salvo").exists()


@pytest.mark.parametrize(
    ("ajuste", "campo"),
    [
        ({"data_fim": "2099-01-01", "max_execucoes": 3}, "max_execucoes"),
        ({"dia_do_mes": 32}, "dia_do_mes"),
        ({"frequencia": "semanal", "dias_semana": []}, "dias_semana"),
        ({"data_inicio": "2020-01-01"}, "data_inicio"),
        ({"hora": "25:00"}, "hora"),
        ({"frequencia": "quinzenal"}, "frequencia"),
        ({"modelo": 999999}, "modelo"),
        ({"responsavel": 999999}, "responsavel"),
    ],
)
def test_agendamento_invalido_volta_400_apontando_o_campo(
    emissor, usuario, modelo_criado, ajuste, campo
):
    resposta = emissor.post(AGENDAMENTOS, dados_do_agendamento(modelo_criado, usuario, **ajuste))

    assert resposta.status_code == 400 and campo in resposta.json()


def test_campos_obrigatorios_do_agendamento(emissor):
    resposta = emissor.post(AGENDAMENTOS, {"nome": "Sem nada"})

    assert resposta.status_code == 400
    assert {"frequencia", "hora", "data_inicio", "modelo", "responsavel"} <= set(resposta.json())


def test_responsavel_precisa_poder_emitir_notas(
    emissor, empresa_pronta, modelo_criado, dados_do_modelo
):
    from conftest import criar_usuario_de_teste
    from core.models import VinculoUsuarioEmpresa

    consulta = criar_usuario_de_teste("consulta@exemplo.test")
    VinculoUsuarioEmpresa.objects.create(
        usuario=consulta, empresa=empresa_pronta, perfil=Perfil.CONSULTA
    )

    resposta = emissor.post(AGENDAMENTOS, dados_do_agendamento(modelo_criado, consulta))

    assert resposta.status_code == 400 and "permissão para emitir" in resposta.json()["responsavel"]


def test_alterar_a_regra_recalcula_e_suspender_e_reativar_seguem_o_ciclo(
    emissor, usuario, modelo_criado
):
    criado = emissor.post(AGENDAMENTOS, dados_do_agendamento(modelo_criado, usuario)).json()
    url = f"{AGENDAMENTOS}{criado['id']}/"

    alterado = emissor.patch(url, {"dia_do_mes": 20, "hora": "09:30"}).json()
    assert alterado["proxima_execucao"] != criado["proxima_execucao"]
    assert alterado["proximas"][0]["hora"] == "09:30"

    suspenso = emissor.post(f"{url}suspender/", {"motivo": "Contrato em renegociação"}).json()
    assert suspenso["situacao"] == "suspenso" and suspenso["proxima_execucao"] is None
    assert suspenso["motivo_situacao"] == "Contrato em renegociação" and suspenso["proximas"] == []
    assert emissor.post(f"{url}suspender/").status_code == 400  # já suspenso

    reativado = emissor.post(f"{url}reativar/").json()
    assert reativado["situacao"] == "ativo" and reativado["proxima_execucao"] is not None
    assert emissor.post(f"{url}reativar/").status_code == 400  # já ativo
    acoes = set(LogAuditoria.objects.values_list("acao", flat=True))
    assert {"agendamento_suspenso", "agendamento_reativado"} <= acoes


def test_previa_de_datas_antes_de_salvar(emissor, usuario, modelo_criado):
    corpo = {
        "frequencia": "mensal", "dia_do_mes": 31, "hora": "08:00",
        "data_inicio": "2099-01-01", "quantidade": 4,
    }  # fmt: skip

    resposta = emissor.post(f"{AGENDAMENTOS}previa-datas/", corpo).json()

    assert [d["data"] for d in resposta["datas"]] == [
        "2099-01-31", "2099-02-28", "2099-03-31", "2099-04-30",
    ]  # fmt: skip
    assert resposta["termina"] is False
    limitada = emissor.post(f"{AGENDAMENTOS}previa-datas/", {**corpo, "max_execucoes": 2}).json()
    assert len(limitada["datas"]) == 2 and limitada["termina"] is True


def test_previa_de_datas_com_regra_invalida_explica(emissor):
    resposta = emissor.post(
        f"{AGENDAMENTOS}previa-datas/",
        {"frequencia": "semanal", "hora": "08:00", "data_inicio": "2099-01-01"},
    )

    assert resposta.status_code == 400 and "dias_semana" in resposta.json()


def test_opcoes_so_listam_responsaveis_para_quem_edita(emissor, api_de, empresa_pronta, usuario):
    do_emissor = emissor.get(OPCOES).json()
    assert {"valor": "mensal", "rotulo": "Mensal"} in do_emissor["frequencias"]
    assert [r["email"] for r in do_emissor["responsaveis"]] == ["usuario@exemplo.test"]
    assert "competencia" in do_emissor["variaveis_do_texto"]

    from core.models import VinculoUsuarioEmpresa

    VinculoUsuarioEmpresa.objects.filter(empresa=empresa_pronta).update(perfil=Perfil.CONSULTA)
    assert emissor.get(OPCOES).json()["responsaveis"] == []


def test_historico_filtra_por_agendamento_e_situacao(
    emissor, usuario, empresa_pronta, modelo_criado
):
    um = emissor.post(AGENDAMENTOS, dados_do_agendamento(modelo_criado, usuario)).json()
    outro = emissor.post(
        AGENDAMENTOS, dados_do_agendamento(modelo_criado, usuario, nome="Outra cobrança")
    ).json()
    with schema_context(empresa_pronta.schema_name):
        for agendamento_id, situacao in ((um["id"], "gerada"), (outro["id"], "falhou")):
            ExecucaoAgendamento.objects.create(
                agendamento_id=agendamento_id, data_execucao=dt.date(2026, 11, 5),
                previsto_para=timezone.now(), situacao=situacao,
                erro="x" if situacao == "falhou" else "",
            )  # fmt: skip

    todas = emissor.get(EXECUCOES).json()
    do_um = emissor.get(EXECUCOES, agendamento=um["id"]).json()
    falhas = emissor.get(EXECUCOES, situacao="falhou").json()

    assert len(todas) == 2
    assert [e["agendamento_nome"] for e in do_um] == ["Cobrança mensal"]
    assert [e["agendamento_nome"] for e in falhas] == ["Outra cobrança"]
    assert falhas[0]["situacao_rotulo"] == "Falhou"


# -- rascunhos -----------------------------------------------------------------------------


def criar_rascunhos(empresa, modelo_id, quantidade=3):
    with schema_context(empresa.schema_name):
        modelo = ModeloNfse.objects.get(pk=modelo_id)
        return [
            servico_modelos.gerar_rascunho(
                modelo, usuario=None, data_execucao=dt.date(2026, 11, dia)
            ).pk
            for dia in range(3, 3 + quantidade)
        ]


def test_lista_de_rascunhos_mostra_a_origem(emissor, usuario, empresa_pronta, modelo_criado):
    ids = criar_rascunhos(empresa_pronta, modelo_criado["id"], 1)
    with schema_context(empresa_pronta.schema_name):
        manual = Nfse.objects.create(
            ambiente="producao_restrita", serie=900, competencia=dt.date(2026, 11, 1),
            valor_servico=Decimal("10"), tomador_nome="Avulso",
        )  # fmt: skip

    lista = emissor.get(RASCUNHOS).json()

    assert lista["total"] == 2
    origens = {i["id"]: i["origem"] for i in lista["itens"]}
    assert origens[ids[0]] == {"tipo": "modelo", "nome": "Mensalidade", "data_execucao": None}
    assert origens[manual.pk]["tipo"] == "manual"


def test_aprovacao_em_lote_pela_api_emite_pelo_fluxo_da_fase_3(
    emissor, empresa_pronta, modelo_criado, sefin, fila
):
    ids = criar_rascunhos(empresa_pronta, modelo_criado["id"])
    sefin.proximas("ok", ("rejeitar", [("E0188", "CNPJ inválido.")]), "ok")

    resposta = emissor.post(f"{RASCUNHOS}aprovar/", {"ids": [*ids, 999999]})

    assert resposta.status_code == 200
    dados = resposta.json()
    assert (dados["aceitas"], dados["recusadas"]) == (3, 1)
    assert [r["ok"] for r in dados["resultados"]] == [True, True, True, False]
    assert dados["resultados"][3]["codigo"] == "nao_encontrada"
    assert [i for _, i in fila.emissoes] == ids  # só os aceitos foram para a fila
    with schema_context(empresa_pronta.schema_name):
        for _schema, nfse_id in fila.emissoes:
            emissao.executar_emissao(empresa_pronta, nfse_id)
        situacoes = [Nfse.objects.get(pk=i).situacao for i in ids]
    assert situacoes == ["autorizada", "rejeitada", "autorizada"]
    acompanhamento = emissor.get(f"{RASCUNHOS}situacao/", ids=",".join(map(str, ids))).json()
    assert {n["id"]: n["situacao"] for n in acompanhamento} == dict(
        zip(ids, situacoes, strict=True)
    )
    assert all(n["numero_nfse"] for n in acompanhamento if n["situacao"] == "autorizada")


def test_aprovacao_exige_nfse_emitir_e_lote_invalido_volta_400(
    emissor, empresa_pronta, modelo_criado
):
    assert emissor.post(f"{RASCUNHOS}aprovar/", {"ids": []}).status_code == 400
    assert emissor.post(f"{RASCUNHOS}aprovar/", {"ids": list(range(101))}).status_code == 400
    assert emissor.post(f"{RASCUNHOS}aprovar/", {"ids": "abc"}).status_code == 400
    with schema_context(empresa_pronta.schema_name):
        from core.models import VinculoUsuarioEmpresa

        VinculoUsuarioEmpresa.objects.filter(empresa=empresa_pronta).update(
            permissoes_removidas=["nfse.emitir"]
        )
    assert emissor.post(f"{RASCUNHOS}aprovar/", {"ids": [1]}).status_code == 403


def test_descartar_com_motivo_tira_o_rascunho_da_lista_e_das_notas(
    emissor, empresa_pronta, modelo_criado
):
    (nfse_id,) = criar_rascunhos(empresa_pronta, modelo_criado["id"], 1)

    sem_motivo = emissor.post(f"{RASCUNHOS}{nfse_id}/descartar/", {"motivo": ""})
    descartado = emissor.post(f"{RASCUNHOS}{nfse_id}/descartar/", {"motivo": "Cliente cancelou"})
    de_novo = emissor.post(f"{RASCUNHOS}{nfse_id}/descartar/", {"motivo": "Cliente cancelou"})

    assert sem_motivo.status_code == 400 and "motivo" in sem_motivo.json()
    assert descartado.status_code == 200 and descartado.json()["situacao"] == "descartada"
    assert de_novo.status_code == 404  # já não é rascunho
    assert emissor.get(RASCUNHOS).json()["total"] == 0
    notas = emissor.get("/api/fiscal/notas/").json()["results"]
    assert nfse_id not in [n["id"] for n in notas]  # sai da lista padrão de notas
    descartadas = emissor.get("/api/fiscal/notas/", situacao="descartada").json()["results"]
    assert [n["id"] for n in descartadas] == [nfse_id]
    detalhe = emissor.get(f"/api/fiscal/notas/{nfse_id}/").json()
    assert detalhe["situacao"] == "descartada" and not any(detalhe["acoes"].values())


# -- isolamento entre empresas -------------------------------------------------------------


def test_modelos_agendamentos_e_rascunhos_de_uma_empresa_nao_aparecem_na_outra(
    empresa_b, api_de, empresa_pronta, vincular, usuario, cliente_de, dados_do_modelo
):
    na_a = api_de(empresa_pronta, Perfil.EMISSOR)
    modelo = na_a.post(MODELOS, dados_do_modelo).json()
    na_a.post(AGENDAMENTOS, dados_do_agendamento(modelo, usuario))
    (rascunho,) = criar_rascunhos(empresa_pronta, modelo["id"], 1)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    na_b = Api(cliente_de(usuario), empresa_b)

    assert na_b.get(MODELOS).json() == []
    assert na_b.get(AGENDAMENTOS).json() == []
    assert na_b.get(EXECUCOES).json() == []
    assert na_b.get(RASCUNHOS).json() == {"total": 0, "itens": []}
    assert na_b.get(f"{MODELOS}{modelo['id']}/").status_code == 404
    assert (
        na_b.post(f"{RASCUNHOS}{rascunho}/descartar/", {"motivo": "tentativa indevida"}).status_code
        == 404
    )
    with schema_context(empresa_pronta.schema_name):
        assert Nfse.objects.get(pk=rascunho).situacao == Nfse.Situacao.RASCUNHO
        assert Agendamento.objects.count() == 1


def test_o_modelo_so_aceita_tomador_e_servico_da_propria_empresa(
    empresa_b, api_de, empresa_pronta, vincular, usuario, cliente_de, dados_do_modelo
):
    api_de(empresa_pronta, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    na_b = Api(cliente_de(usuario), empresa_b)

    # ids do tomador/serviço da empresa A não existem no schema da B
    resposta = na_b.post(MODELOS, {**dados_do_modelo, "nome": "Cruzado"})

    assert resposta.status_code == 400
    assert {"tomador", "servico"} & set(resposta.json())
