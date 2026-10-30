"""API de administração (só Master): empresas, usuários e vínculos."""

from allauth.account.models import EmailAddress
from django_tenants.utils import schema_exists

from conftest import CNPJ_A, CNPJ_B, SENHA_DE_TESTE, criar_usuario_de_teste
from core.models import Empresa, LogAuditoria, Usuario, VinculoUsuarioEmpresa
from core.permissoes import Perfil

EMPRESAS = "/api/admin-global/empresas/"
USUARIOS = "/api/admin-global/usuarios/"
VINCULOS = "/api/admin-global/vinculos/"


def cab(empresa):
    return {"X-Empresa": str(empresa.pk)}


# --- Quem pode administrar ------------------------------------------------------------


def test_so_o_master_administra(cliente_de, master, usuario):
    for rota in (EMPRESAS, USUARIOS, VINCULOS, "/api/admin-global/permissoes/"):
        assert cliente_de(master).get(rota).status_code == 200
        assert cliente_de(usuario).get(rota).status_code == 403
        assert cliente_de().get(rota).status_code == 403


def test_usuario_comum_nao_cria_empresa_nem_se_promove(cliente_de, usuario):
    cliente = cliente_de(usuario)

    assert (
        cliente.post(EMPRESAS, {"razao_social": "X", "cnpj": CNPJ_A}, format="json").status_code
        == 403
    )
    assert (
        cliente.patch(f"{USUARIOS}{usuario.pk}/", {"is_master": True}, format="json").status_code
        == 403
    )
    usuario.refresh_from_db()
    assert not usuario.is_master


def test_administracao_nao_oferece_exclusao(cliente_de, master, empresa_a):
    assert cliente_de(master).delete(f"{EMPRESAS}{empresa_a.pk}/").status_code == 405


# --- Empresas ---------------------------------------------------------------------------


def test_master_cria_empresa_com_schema_e_auditoria(cliente_de, master):
    resposta = cliente_de(master).post(
        EMPRESAS,
        {"razao_social": "Empresa Nova Teste Ltda", "cnpj": "11.222.333/0001-81"},
        format="json",
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["cnpj"] == CNPJ_A
    assert corpo["cnpj_formatado"] == "11.222.333/0001-81"
    assert schema_exists(corpo["schema_name"])
    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.EMPRESA_CRIADA)
    assert registro.master is True
    assert registro.usuario == master
    assert registro.empresa_id == corpo["id"]


def test_cnpj_invalido_e_duplicado_sao_recusados(cliente_de, master, empresa_a):
    cliente = cliente_de(master)

    invalido = cliente.post(
        EMPRESAS, {"razao_social": "X", "cnpj": "11222333000182"}, format="json"
    )
    duplicado = cliente.post(
        EMPRESAS, {"razao_social": "Y", "cnpj": "11.222.333/0001-81"}, format="json"
    )

    assert invalido.status_code == 400 and "cnpj" in invalido.json()
    assert duplicado.status_code == 400 and "cnpj" in duplicado.json()


def test_master_altera_razao_social_e_desativa_mas_nao_troca_o_cnpj(cliente_de, master, empresa_a):
    cliente = cliente_de(master)
    rota = f"{EMPRESAS}{empresa_a.pk}/"

    ok = cliente.patch(rota, {"razao_social": "Alfa Renomeada Ltda", "ativo": False}, format="json")
    troca = cliente.patch(rota, {"cnpj": CNPJ_B}, format="json")

    assert ok.status_code == 200
    empresa_a.refresh_from_db()
    assert empresa_a.razao_social == "Alfa Renomeada Ltda" and empresa_a.ativo is False
    assert troca.status_code == 400
    assert LogAuditoria.objects.filter(acao=LogAuditoria.Acao.EMPRESA_ALTERADA).count() == 1


def test_listagem_de_empresas_filtra_por_busca_e_situacao(cliente_de, master, empresa_a, empresa_b):
    empresa_b.ativo = False
    empresa_b.save()
    cliente = cliente_de(master)

    por_nome = cliente.get(EMPRESAS, {"busca": "alfa"}).json()
    por_cnpj = cliente.get(EMPRESAS, {"busca": "11.444.777/0001-61"}).json()
    inativas = cliente.get(EMPRESAS, {"ativo": "false"}).json()

    assert [e["id"] for e in por_nome] == [empresa_a.pk]
    assert [e["id"] for e in por_cnpj] == [empresa_b.pk]
    assert [e["id"] for e in inativas] == [empresa_b.pk]


# --- Usuários ---------------------------------------------------------------------------


def test_master_cria_usuario_com_email_verificado_e_senha_que_nao_volta(cliente_de, master):
    resposta = cliente_de(master).post(
        USUARIOS,
        {"email": "Pessoa.Nova@Exemplo.TEST", "nome": "Pessoa Nova", "senha": SENHA_DE_TESTE},
        format="json",
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["email"] == "pessoa.nova@exemplo.test"
    assert "senha" not in corpo and "password" not in corpo
    usuario = Usuario.objects.get(pk=corpo["id"])
    assert usuario.check_password(SENHA_DE_TESTE)
    assert EmailAddress.objects.get(user=usuario).verified is True
    assert not usuario.is_master


def test_usuario_sem_senha_nasce_sem_senha_utilizavel(cliente_de, master):
    resposta = cliente_de(master).post(USUARIOS, {"email": "so.google@exemplo.test"}, format="json")

    assert resposta.status_code == 201
    assert not Usuario.objects.get(pk=resposta.json()["id"]).has_usable_password()


def test_email_duplicado_sem_diferenciar_maiusculas_e_recusado(cliente_de, master, usuario):
    resposta = cliente_de(master).post(USUARIOS, {"email": "USUARIO@exemplo.test"}, format="json")

    assert resposta.status_code == 400 and "email" in resposta.json()


def test_senha_fraca_e_recusada(cliente_de, master):
    resposta = cliente_de(master).post(
        USUARIOS, {"email": "fraca@exemplo.test", "senha": "12345678"}, format="json"
    )

    assert resposta.status_code == 400 and "senha" in resposta.json()


def test_auditoria_de_usuario_nunca_guarda_a_senha(cliente_de, master):
    cliente_de(master).post(
        USUARIOS, {"email": "auditada@exemplo.test", "senha": SENHA_DE_TESTE}, format="json"
    )

    registro = LogAuditoria.objects.get(acao=LogAuditoria.Acao.USUARIO_CRIADO)
    assert SENHA_DE_TESTE not in str(registro.detalhes)


def test_alterar_email_sincroniza_o_endereco_do_allauth(cliente_de, master, usuario):
    cliente_de(master).patch(
        f"{USUARIOS}{usuario.pk}/", {"email": "novo@exemplo.test"}, format="json"
    )

    enderecos = list(
        EmailAddress.objects.filter(user=usuario).values_list("email", "primary", "verified")
    )
    assert enderecos == [("novo@exemplo.test", True, True)]


def test_master_nao_pode_desativar_nem_rebaixar_a_si_mesmo(cliente_de, master):
    cliente = cliente_de(master)
    rota = f"{USUARIOS}{master.pk}/"

    assert cliente.patch(rota, {"is_active": False}, format="json").status_code == 400
    assert cliente.patch(rota, {"is_master": False}, format="json").status_code == 400
    master.refresh_from_db()
    assert master.is_active and master.is_master


def test_master_pode_rebaixar_outro_master(cliente_de, master):
    outro = criar_usuario_de_teste("outro.master@exemplo.test", master=True)

    resposta = cliente_de(master).patch(
        f"{USUARIOS}{outro.pk}/", {"is_master": False}, format="json"
    )

    assert resposta.status_code == 200
    outro.refresh_from_db()
    assert not outro.is_master


# --- Vínculos ---------------------------------------------------------------------------


def test_master_cria_vinculo_e_o_criador_fica_registrado(cliente_de, master, usuario, empresa_a):
    resposta = cliente_de(master).post(
        VINCULOS,
        {"usuario": usuario.pk, "empresa": empresa_a.pk, "perfil": "emissor"},
        format="json",
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["criado_por_email"] == master.email
    assert "nfse.emitir" in corpo["permissoes_efetivas"]
    assert VinculoUsuarioEmpresa.objects.get(pk=corpo["id"]).criado_por == master
    assert LogAuditoria.objects.filter(
        acao=LogAuditoria.Acao.VINCULO_CRIADO, empresa=empresa_a
    ).exists()


def test_vinculo_duplicado_e_permissao_invalida_sao_recusados(
    cliente_de, master, usuario, empresa_a, vincular
):
    vincular(usuario, empresa_a)
    cliente = cliente_de(master)

    duplicado = cliente.post(
        VINCULOS,
        {"usuario": usuario.pk, "empresa": empresa_a.pk, "perfil": "emissor"},
        format="json",
    )
    outro = criar_usuario_de_teste("outro@exemplo.test")
    invalida = cliente.post(
        VINCULOS,
        {
            "usuario": outro.pk,
            "empresa": empresa_a.pk,
            "perfil": "emissor",
            "permissoes_extras": ["x.y"],
        },
        format="json",
    )

    assert duplicado.status_code == 400
    assert invalida.status_code == 400 and "permissoes_extras" in invalida.json()


def test_vinculo_altera_perfil_e_permissoes_mas_nao_usuario_nem_empresa(
    cliente_de, master, usuario, empresa_a, empresa_b, vincular
):
    vinculo = vincular(usuario, empresa_a, Perfil.CONSULTA)
    cliente = cliente_de(master)
    rota = f"{VINCULOS}{vinculo.pk}/"

    ok = cliente.patch(
        rota, {"perfil": "emissor", "permissoes_removidas": ["nfse.cancelar"]}, format="json"
    )
    troca = cliente.patch(rota, {"empresa": empresa_b.pk}, format="json")

    assert ok.status_code == 200
    vinculo.refresh_from_db()
    assert vinculo.perfil == "emissor" and vinculo.permissoes_removidas == ["nfse.cancelar"]
    assert troca.status_code == 400
    assert LogAuditoria.objects.filter(acao=LogAuditoria.Acao.VINCULO_ALTERADO).count() == 1


def test_vinculos_filtram_por_empresa_e_usuario(
    cliente_de, master, usuario, empresa_a, empresa_b, vincular
):
    outro = criar_usuario_de_teste("outro@exemplo.test")
    vincular(usuario, empresa_a)
    vincular(usuario, empresa_b)
    vincular(outro, empresa_a)
    cliente = cliente_de(master)

    da_a = cliente.get(VINCULOS, {"empresa": empresa_a.pk}).json()
    do_usuario = cliente.get(VINCULOS, {"usuario": usuario.pk}).json()

    assert len(da_a) == 2 and len(do_usuario) == 2


def test_catalogo_de_permissoes_e_perfis(cliente_de, master):
    corpo = cliente_de(master).get("/api/admin-global/permissoes/").json()

    assert "nfse.cancelar" in {p["nome"] for p in corpo["permissoes"]}
    perfis = {p["valor"]: p for p in corpo["perfis"]}
    assert set(perfis) == {"administrador", "emissor", "financeiro", "consulta"}
    assert "nfse.cancelar" in perfis["emissor"]["permissoes"]
    assert "nfse.cancelar" not in perfis["consulta"]["permissoes"]


# --- /api/eu/ -----------------------------------------------------------------------------


def test_eu_do_usuario_comum_lista_so_empresas_vinculadas_ativas(
    cliente_de, usuario, empresa_a, empresa_b, vincular
):
    vincular(usuario, empresa_a, Perfil.EMISSOR)
    vincular(usuario, empresa_b, Perfil.CONSULTA, ativo=False)

    corpo = cliente_de(usuario).get("/api/eu/").json()

    assert corpo["email"] == usuario.email and corpo["is_master"] is False
    assert [e["id"] for e in corpo["empresas"]] == [empresa_a.pk]
    assert corpo["empresas"][0]["perfil"] == "emissor"
    assert corpo["mfa"] == {"ativo": False, "obrigatorio": False}


def test_eu_do_master_lista_todas_as_empresas_ativas(cliente_de, master, empresa_a, empresa_b):
    empresa_b.ativo = False
    empresa_b.save()

    corpo = cliente_de(master).get("/api/eu/").json()

    assert corpo["is_master"] is True
    assert [e["id"] for e in corpo["empresas"]] == [empresa_a.pk]
    assert corpo["empresas"][0]["perfil"] == "master"


def test_eu_exige_login(cliente_de):
    assert cliente_de().get("/api/eu/").status_code == 403


# --- Fluxo de aceite -----------------------------------------------------------------------


def test_master_cria_duas_empresas_e_um_usuario_com_perfis_diferentes_em_cada(cliente_de, master):
    painel = cliente_de(master)

    empresa_1 = painel.post(
        EMPRESAS, {"razao_social": "Primeira Teste Ltda", "cnpj": CNPJ_A}, format="json"
    ).json()
    empresa_2 = painel.post(
        EMPRESAS, {"razao_social": "Segunda Teste Ltda", "cnpj": CNPJ_B}, format="json"
    ).json()
    pessoa = painel.post(
        USUARIOS,
        {"email": "pessoa@exemplo.test", "nome": "Pessoa", "senha": SENHA_DE_TESTE},
        format="json",
    ).json()
    for empresa, perfil in ((empresa_1, "administrador"), (empresa_2, "consulta")):
        resposta = painel.post(
            VINCULOS,
            {"usuario": pessoa["id"], "empresa": empresa["id"], "perfil": perfil},
            format="json",
        )
        assert resposta.status_code == 201

    # A pessoa entra e opera cada empresa conforme o perfil dela naquela empresa.
    aba = cliente_de(Usuario.objects.get(pk=pessoa["id"]))
    h1, h2 = {"X-Empresa": str(empresa_1["id"])}, {"X-Empresa": str(empresa_2["id"])}
    rota = "/api/teste/anotacoes/"

    assert aba.post(rota, {"texto": "na primeira"}, format="json", headers=h1).status_code == 201
    assert aba.post(rota, {"texto": "na segunda"}, format="json", headers=h2).status_code == 403
    assert [n["texto"] for n in aba.get(rota, headers=h1).json()] == ["na primeira"]
    assert aba.get(rota, headers=h2).json() == []
    assert {e["id"] for e in aba.get("/api/eu/").json()["empresas"]} == {
        empresa_1["id"],
        empresa_2["id"],
    }
    assert Empresa.objects.count() == 2
