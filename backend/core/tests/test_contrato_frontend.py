"""Contrato SPA × API: toda rota que o frontend chama precisa existir no backend.

Os testes do frontend usam uma API falsa, então um endereço errado em `frontend/src/api/`
passaria despercebido por lá. Aqui as rotas são extraídas dos módulos da SPA e resolvidas
no URLconf real.
"""

import re
from pathlib import Path

import pytest
from django.urls import Resolver404, resolve

PASTA_API_SPA = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api"

pytestmark = pytest.mark.skipif(
    not PASTA_API_SPA.is_dir(), reason="o código do frontend não está disponível neste ambiente"
)

PREFIXOS_DO_BACKEND = ("/api/", "/_allauth/", "/accounts/")


def _rotas_do_modulo(nome_arquivo):
    """Endereços chamados por um módulo da SPA, com os parâmetros substituídos por valores."""
    texto = (PASTA_API_SPA / nome_arquivo).read_text(encoding="utf-8")
    base = re.search(r"const BASE = '([^']+)'", texto)
    base = base.group(1) if base else ""
    recursos = re.findall(r"recurso\('([a-z-]+)'\)", texto)
    literais = re.findall(r"[`'](/[^`']*|\$\{BASE\}[^`']*)[`']", texto)
    rotas = set()
    for literal in literais:
        caminho = literal.replace("${BASE}", base)
        if "${nome}" in caminho:
            candidatos = [caminho.replace("${nome}", nome) for nome in recursos]
        elif "${tema}" in caminho:
            candidatos = [caminho.replace("${tema}", tema) for tema in ("claro", "escuro")]
        else:
            candidatos = [caminho]
        for candidato in candidatos:
            candidato = re.sub(r"\$\{id\}", "1", candidato)
            candidato = candidato.split("${consulta")[0]  # a query string não faz parte da rota
            candidato = re.sub(r"\$\{[^}]*\}", "", candidato).split("?")[0]
            # Ignora a própria constante BASE e rotas da SPA (ex.: callback_url '/').
            if candidato != base and candidato.startswith(PREFIXOS_DO_BACKEND):
                rotas.add(candidato)
    return rotas


@pytest.mark.parametrize(
    "modulo",
    [
        "auth.js",
        "admin.js",
        "versao.js",
        "cadastros.js",
        "fiscal.js",
        "documentos.js",
        "agendamentos.js",
    ],  # fmt: skip
)
def test_toda_rota_chamada_pela_spa_existe_no_backend(modulo):
    rotas = _rotas_do_modulo(modulo)
    assert rotas, f"nenhuma rota encontrada em {modulo}: o extrator precisa ser ajustado"

    inexistentes = []
    for rota in sorted(rotas):
        try:
            resolve(rota)
        except Resolver404:
            inexistentes.append(rota)

    assert inexistentes == []


def test_o_extrator_enxerga_as_rotas_criticas():
    rotas = _rotas_do_modulo("auth.js") | _rotas_do_modulo("admin.js")

    assert "/_allauth/browser/v1/account/authenticators/recovery-codes" in rotas
    assert "/_allauth/browser/v1/auth/2fa/authenticate" in rotas
    assert "/api/admin-global/vinculos/1/" in rotas
    assert "/api/eu/" in rotas
    cadastros = _rotas_do_modulo("cadastros.js") | _rotas_do_modulo("fiscal.js")
    assert "/api/cadastros/pessoas/1/" in cadastros
    assert "/api/cadastros/copia/pessoas/" in cadastros
    assert "/api/cadastros/municipios/" in cadastros
    assert "/api/fiscal/logo/escuro/" in cadastros
    assert "/api/fiscal/parametros/verificar-convenio/" in cadastros
