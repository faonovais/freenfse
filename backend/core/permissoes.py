"""Catálogo de permissões nomeadas e perfis padrão (D22).

Permissão = ação × recurso (`nfse.emitir`), avaliada sempre no vínculo do
usuário com a empresa da requisição. O perfil Administrador recebe todas as
permissões do catálogo; os demais recebem as listadas em `registrar_permissao`.

As fases seguintes ampliam o catálogo chamando `registrar_permissao` no módulo
`permissoes.py` do próprio app (ex.: `nfse_recebida.consultar`).
"""

import re

from django.db import models


class Perfil(models.TextChoices):
    """Perfis padrão atribuídos por empresa no vínculo do usuário."""

    ADMINISTRADOR = "administrador", "Administrador"
    EMISSOR = "emissor", "Emissor"
    FINANCEIRO = "financeiro", "Financeiro"
    CONSULTA = "consulta", "Consulta"


# Rótulo informado ao frontend para o papel global (fora dos perfis de empresa).
PERFIL_MASTER = "master"

_PADRAO_NOME = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")
_CATALOGO: dict[str, str] = {}
_PERFIS: dict[str, set[str]] = {valor: set() for valor in Perfil.values}


def registrar_permissao(nome, descricao, perfis=()):
    """Inclui uma permissão no catálogo e a concede aos perfis informados.

    O Administrador sempre recebe a permissão. Registrar de novo o mesmo nome
    atualiza a descrição e acrescenta perfis.
    """
    if not _PADRAO_NOME.fullmatch(nome):
        raise ValueError(f"Nome de permissão inválido: {nome!r} (use recurso.acao).")
    desconhecidos = set(perfis) - set(Perfil.values)
    if desconhecidos:
        raise ValueError(f"Perfis desconhecidos: {sorted(desconhecidos)}")
    _CATALOGO[nome] = descricao
    for perfil in {*perfis, Perfil.ADMINISTRADOR}:
        _PERFIS[perfil].add(nome)


def catalogo():
    """Retorna uma cópia do catálogo `{nome: descrição}`."""
    return dict(_CATALOGO)


def todas_as_permissoes():
    """Retorna todas as permissões do catálogo (o que o Master possui)."""
    return frozenset(_CATALOGO)


def permissoes_do_perfil(perfil):
    """Retorna as permissões padrão de um perfil."""
    return frozenset(_PERFIS[str(perfil)])


def permissoes_desconhecidas(nomes):
    """Retorna, em ordem, os nomes que não existem no catálogo."""
    return sorted(set(nomes) - set(_CATALOGO))


registrar_permissao(
    "nfse.consultar",
    "Consultar NFS-e",
    perfis=[Perfil.EMISSOR, Perfil.FINANCEIRO, Perfil.CONSULTA],
)
registrar_permissao("nfse.emitir", "Emitir NFS-e", perfis=[Perfil.EMISSOR])
registrar_permissao("nfse.cancelar", "Cancelar NFS-e", perfis=[Perfil.EMISSOR])
registrar_permissao("nfse.substituir", "Substituir NFS-e", perfis=[Perfil.EMISSOR])
registrar_permissao(
    "cadastro.consultar",
    "Consultar cadastros (pessoas e serviços)",
    perfis=[Perfil.EMISSOR, Perfil.FINANCEIRO, Perfil.CONSULTA],
)
registrar_permissao("cadastro.editar", "Editar cadastros", perfis=[Perfil.EMISSOR])
registrar_permissao(
    "config.consultar",
    "Consultar a configuração da empresa",
    perfis=[Perfil.FINANCEIRO, Perfil.CONSULTA],
)
registrar_permissao("config.editar", "Editar a configuração da empresa")
registrar_permissao("usuario.gerenciar", "Gerenciar usuários e vínculos da empresa")
