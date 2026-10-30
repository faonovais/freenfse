import pytest
from django.core.exceptions import ValidationError

from core.models import VinculoUsuarioEmpresa
from core.permissoes import (
    Perfil,
    catalogo,
    permissoes_desconhecidas,
    permissoes_do_perfil,
    registrar_permissao,
    todas_as_permissoes,
)

OBRIGATORIAS = {
    "nfse.emitir",
    "nfse.cancelar",
    "nfse.substituir",
    "cadastro.editar",
    "config.editar",
    "usuario.gerenciar",
}


def test_catalogo_traz_as_permissoes_pedidas():
    assert OBRIGATORIAS <= set(catalogo())


def test_administrador_tem_todas_as_permissoes():
    assert permissoes_do_perfil(Perfil.ADMINISTRADOR) == todas_as_permissoes()


def test_emissor_emite_cancela_e_substitui_mas_nao_administra():
    permissoes = permissoes_do_perfil(Perfil.EMISSOR)

    assert {"nfse.emitir", "nfse.cancelar", "nfse.substituir", "cadastro.editar"} <= permissoes
    assert not {"config.editar", "usuario.gerenciar"} & permissoes


def test_consulta_so_le():
    permissoes = permissoes_do_perfil(Perfil.CONSULTA)

    assert permissoes
    assert all(nome.endswith(".consultar") for nome in permissoes)


def test_financeiro_nao_emite_nem_cancela():
    permissoes = permissoes_do_perfil(Perfil.FINANCEIRO)

    assert "nfse.consultar" in permissoes
    assert not {"nfse.emitir", "nfse.cancelar", "nfse.substituir"} & permissoes


def test_catalogo_e_extensivel_para_fases_futuras():
    registrar_permissao("teste_fase.consultar", "Permissão de exemplo", perfis=[Perfil.CONSULTA])
    try:
        assert "teste_fase.consultar" in permissoes_do_perfil(Perfil.CONSULTA)
        assert "teste_fase.consultar" in permissoes_do_perfil(Perfil.ADMINISTRADOR)
        assert "teste_fase.consultar" not in permissoes_do_perfil(Perfil.EMISSOR)
    finally:
        from core import permissoes as modulo

        modulo._CATALOGO.pop("teste_fase.consultar", None)
        for conjunto in modulo._PERFIS.values():
            conjunto.discard("teste_fase.consultar")


@pytest.mark.parametrize("nome", ["emitir", "Nfse.emitir", "nfse.emitir.x", "nfse-emitir.x", ""])
def test_nome_de_permissao_invalido_e_recusado(nome):
    with pytest.raises(ValueError):
        registrar_permissao(nome, "x")


def test_perfil_desconhecido_e_recusado():
    with pytest.raises(ValueError):
        registrar_permissao("teste.consultar", "x", perfis=["inexistente"])


def test_permissoes_efetivas_somam_extras_e_subtraem_removidas(usuario, empresa_a, vincular):
    vinculo = vincular(
        usuario,
        empresa_a,
        Perfil.CONSULTA,
        permissoes_extras=["nfse.emitir"],
        permissoes_removidas=["cadastro.consultar"],
    )

    efetivas = vinculo.permissoes_efetivas()

    assert "nfse.emitir" in efetivas
    assert "cadastro.consultar" not in efetivas
    assert "nfse.consultar" in efetivas


def test_vinculo_recusa_permissao_fora_do_catalogo(usuario, empresa_a):
    vinculo = VinculoUsuarioEmpresa(usuario=usuario, empresa=empresa_a, permissoes_extras=["x.y"])

    with pytest.raises(ValidationError) as erro:
        vinculo.full_clean(exclude=["criado_por"])

    assert "permissoes_extras" in erro.value.message_dict
    assert permissoes_desconhecidas(["x.y", "nfse.emitir"]) == ["x.y"]


def test_vinculo_recusa_permissao_extra_e_removida_ao_mesmo_tempo(usuario, empresa_a):
    vinculo = VinculoUsuarioEmpresa(
        usuario=usuario,
        empresa=empresa_a,
        permissoes_extras=["nfse.emitir"],
        permissoes_removidas=["nfse.emitir"],
    )

    with pytest.raises(ValidationError):
        vinculo.full_clean(exclude=["criado_por"])


def test_vinculo_e_unico_por_par(usuario, empresa_a, vincular):
    vincular(usuario, empresa_a)

    with pytest.raises(ValidationError):
        VinculoUsuarioEmpresa(usuario=usuario, empresa=empresa_a).validate_constraints()
