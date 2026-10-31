"""Middleware de empresa por requisição, isolamento por schema e permissões por operação."""

from django.db import connection
from django_tenants.utils import schema_context

from apoio_testes.models import Anotacao
from core.models import LogAuditoria
from core.permissoes import PERFIL_MASTER, Perfil

ROTA_EMPRESA = "/api/empresa-ativa/"
ROTA_ANOTACOES = "/api/teste/anotacoes/"


def cab(empresa):
    """Cabeçalho X-Empresa de uma empresa."""
    return {"X-Empresa": str(empresa.pk)}


# --- Resolução da empresa --------------------------------------------------------


def test_rota_de_empresa_sem_cabecalho_e_recusada(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.EMISSOR)

    resposta = cliente_de(usuario).get(ROTA_EMPRESA)

    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "empresa_nao_informada"


def test_cabecalho_nao_numerico_e_recusado(cliente_de, usuario):
    resposta = cliente_de(usuario).get(ROTA_EMPRESA, headers={"X-Empresa": "abc"})

    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "empresa_invalida"


def test_sem_login_a_rota_de_empresa_responde_401(cliente_de, empresa_a):
    resposta = cliente_de().get(ROTA_EMPRESA, headers=cab(empresa_a))

    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "nao_autenticado"


def test_usuario_sem_vinculo_recebe_403(cliente_de, usuario, empresa_a):
    resposta = cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_a))

    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "sem_acesso_a_empresa"


def test_x_empresa_de_outra_empresa_recebe_403(cliente_de, usuario, empresa_a, empresa_b, vincular):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)

    resposta = cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_b))

    assert resposta.status_code == 403


def test_empresa_inexistente_responde_igual_a_sem_vinculo(cliente_de, usuario, empresa_a):
    inexistente = cliente_de(usuario).get(ROTA_EMPRESA, headers={"X-Empresa": "999999"})
    sem_vinculo = cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_a))

    # Não revela quais empresas existem.
    assert inexistente.status_code == sem_vinculo.status_code == 403
    assert inexistente.json() == sem_vinculo.json()


def test_vinculo_inativo_recebe_403(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR, ativo=False)

    assert cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_a)).status_code == 403


def test_empresa_inativa_recebe_403_ate_para_o_master(
    cliente_de, master, usuario, empresa_a, vincular
):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    empresa_a.ativo = False
    empresa_a.save()

    assert cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_a)).status_code == 403
    assert cliente_de(master).get(ROTA_EMPRESA, headers=cab(empresa_a)).status_code == 403


def test_usuario_inativo_nao_acessa(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    cliente = cliente_de(usuario)
    usuario.is_active = False
    usuario.save()

    assert cliente.get(ROTA_EMPRESA, headers=cab(empresa_a)).status_code == 401


def test_vinculo_ativo_acessa_com_perfil_e_permissoes(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.CONSULTA)

    resposta = cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_a))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["id"] == empresa_a.pk
    assert corpo["perfil"] == "consulta"
    assert "nfse.consultar" in corpo["permissoes"]
    assert "nfse.emitir" not in corpo["permissoes"]


def test_master_acessa_qualquer_empresa_sem_vinculo(cliente_de, master, empresa_a, empresa_b):
    cliente = cliente_de(master)

    for empresa in (empresa_a, empresa_b):
        corpo = cliente.get(ROTA_EMPRESA, headers=cab(empresa)).json()
        assert corpo["id"] == empresa.pk
        assert corpo["perfil"] == PERFIL_MASTER
        assert "nfse.cancelar" in corpo["permissoes"]


def test_rotas_publicas_e_de_administracao_dispensam_empresa(cliente_de, master, usuario):
    assert cliente_de().get("/api/versao/").status_code == 200
    assert cliente_de(usuario).get("/api/eu/").status_code == 200
    assert cliente_de(master).get("/api/admin-global/empresas/").status_code == 200


def test_negacao_de_acesso_e_auditada(cliente_de, usuario, empresa_a):
    cliente_de(usuario).get(ROTA_EMPRESA, headers=cab(empresa_a))

    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.ACESSO_NEGADO)
    assert registro.usuario == usuario
    assert registro.alvo == f"Empresa:{empresa_a.pk}"


def test_schema_volta_ao_publico_apos_cada_requisicao(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    cliente = cliente_de(usuario)

    cliente.get(ROTA_EMPRESA, headers=cab(empresa_a))
    assert connection.schema_name == "public"
    cliente.get(ROTA_EMPRESA, headers={"X-Empresa": "999999"})
    assert connection.schema_name == "public"


def test_a_empresa_nao_vem_da_sessao(cliente_de, usuario, empresa_a, empresa_b, vincular):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    vincular(usuario, empresa_b, Perfil.ADMINISTRADOR)
    cliente = cliente_de(usuario)
    cliente.get(ROTA_EMPRESA, headers=cab(empresa_a))

    # A requisição seguinte, sem cabeçalho, não "herda" a empresa da anterior.
    assert cliente.get(ROTA_EMPRESA).status_code == 400
    assert "empresa" not in cliente.session.keys()


# --- Isolamento de dados por schema ------------------------------------------------


def test_dados_de_uma_empresa_nunca_aparecem_na_outra(
    cliente_de, usuario, empresa_a, empresa_b, vincular
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    cliente = cliente_de(usuario)

    cliente.post(ROTA_ANOTACOES, {"texto": "só da A"}, format="json", headers=cab(empresa_a))
    cliente.post(ROTA_ANOTACOES, {"texto": "só da B"}, format="json", headers=cab(empresa_b))

    textos_a = [n["texto"] for n in cliente.get(ROTA_ANOTACOES, headers=cab(empresa_a)).json()]
    textos_b = [n["texto"] for n in cliente.get(ROTA_ANOTACOES, headers=cab(empresa_b)).json()]
    assert textos_a == ["só da A"]
    assert textos_b == ["só da B"]
    # E no banco: cada registro está fisicamente no schema da própria empresa.
    with schema_context(empresa_a.schema_name):
        assert list(Anotacao.objects.values_list("texto", flat=True)) == ["só da A"]
    with schema_context(empresa_b.schema_name):
        assert list(Anotacao.objects.values_list("texto", flat=True)) == ["só da B"]


def test_duas_abas_na_mesma_sessao_alternando_empresas_nao_vazam(
    cliente_de, usuario, empresa_a, empresa_b, vincular
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.EMISSOR)
    cliente = cliente_de(usuario)  # uma sessão só, como duas abas do mesmo navegador

    for rodada in range(3):
        cliente.post(ROTA_ANOTACOES, {"texto": f"A{rodada}"}, format="json", headers=cab(empresa_a))
        cliente.post(ROTA_ANOTACOES, {"texto": f"B{rodada}"}, format="json", headers=cab(empresa_b))
        visto_na_a = {
            n["texto"] for n in cliente.get(ROTA_ANOTACOES, headers=cab(empresa_a)).json()
        }
        visto_na_b = {
            n["texto"] for n in cliente.get(ROTA_ANOTACOES, headers=cab(empresa_b)).json()
        }

        assert visto_na_a == {f"A{i}" for i in range(rodada + 1)}
        assert visto_na_b == {f"B{i}" for i in range(rodada + 1)}
        assert cliente.get(ROTA_EMPRESA, headers=cab(empresa_a)).json()["id"] == empresa_a.pk
        assert cliente.get(ROTA_EMPRESA, headers=cab(empresa_b)).json()["id"] == empresa_b.pk


def test_usuario_nao_le_nem_grava_na_empresa_sem_vinculo(
    cliente_de, usuario, empresa_a, empresa_b, vincular
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    cliente = cliente_de(usuario)

    assert cliente.get(ROTA_ANOTACOES, headers=cab(empresa_b)).status_code == 403
    assert (
        cliente.post(
            ROTA_ANOTACOES, {"texto": "invasão"}, format="json", headers=cab(empresa_b)
        ).status_code
        == 403
    )
    with schema_context(empresa_b.schema_name):
        assert Anotacao.objects.count() == 0


# --- Permissões por operação ---------------------------------------------------------


def test_perfil_consulta_le_mas_nao_escreve(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.CONSULTA)
    cliente = cliente_de(usuario)

    assert cliente.get(ROTA_ANOTACOES, headers=cab(empresa_a)).status_code == 200
    assert (
        cliente.post(
            ROTA_ANOTACOES, {"texto": "x"}, format="json", headers=cab(empresa_a)
        ).status_code
        == 403
    )


def test_emissor_cancela_ate_a_permissao_ser_removida(cliente_de, usuario, empresa_a, vincular):
    vinculo = vincular(usuario, empresa_a, Perfil.EMISSOR)
    cliente = cliente_de(usuario)
    nota = cliente.post(
        ROTA_ANOTACOES, {"texto": "x"}, format="json", headers=cab(empresa_a)
    ).json()
    rota = f"{ROTA_ANOTACOES}{nota['id']}/cancelar/"

    assert cliente.post(rota, headers=cab(empresa_a)).status_code == 200

    vinculo.permissoes_removidas = ["nfse.cancelar"]
    vinculo.save()

    assert cliente.post(rota, headers=cab(empresa_a)).status_code == 403
    # As demais permissões do perfil seguem valendo.
    assert cliente.get(ROTA_ANOTACOES, headers=cab(empresa_a)).status_code == 200
    assert (
        cliente.post(
            ROTA_ANOTACOES, {"texto": "y"}, format="json", headers=cab(empresa_a)
        ).status_code
        == 201
    )


def test_permissao_extra_libera_operacao_alem_do_perfil(cliente_de, usuario, empresa_a, vincular):
    vincular(usuario, empresa_a, Perfil.CONSULTA, permissoes_extras=["nfse.emitir"])

    resposta = cliente_de(usuario).post(
        ROTA_ANOTACOES, {"texto": "x"}, format="json", headers=cab(empresa_a)
    )

    assert resposta.status_code == 201


def test_perfil_diferente_em_cada_empresa(cliente_de, usuario, empresa_a, empresa_b, vincular):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)
    vincular(usuario, empresa_b, Perfil.CONSULTA)
    cliente = cliente_de(usuario)
    escrever = {"texto": "x"}

    assert (
        cliente.post(ROTA_ANOTACOES, escrever, format="json", headers=cab(empresa_a)).status_code
        == 201
    )
    assert (
        cliente.post(ROTA_ANOTACOES, escrever, format="json", headers=cab(empresa_b)).status_code
        == 403
    )
    assert cliente.get(ROTA_EMPRESA, headers=cab(empresa_a)).json()["perfil"] == "administrador"
    assert cliente.get(ROTA_EMPRESA, headers=cab(empresa_b)).json()["perfil"] == "consulta"


def test_operacao_sem_permissao_declarada_falha_fechada_ate_para_o_master(
    cliente_de, master, usuario, empresa_a, vincular
):
    vincular(usuario, empresa_a, Perfil.ADMINISTRADOR)

    for quem in (usuario, master):
        resposta = cliente_de(quem).get(f"{ROTA_ANOTACOES}sem_declaracao/", headers=cab(empresa_a))
        assert resposta.status_code == 403


def test_master_tem_todas_as_permissoes_na_empresa_escolhida(cliente_de, master, empresa_a):
    cliente = cliente_de(master)
    nota = cliente.post(
        ROTA_ANOTACOES, {"texto": "x"}, format="json", headers=cab(empresa_a)
    ).json()

    resposta = cliente.post(f"{ROTA_ANOTACOES}{nota['id']}/cancelar/", headers=cab(empresa_a))

    assert resposta.status_code == 200
