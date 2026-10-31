"""Fixtures do instalador: um repositório falso (só com o que o instalador lê) e utilitários."""

import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "instalador"))

from freenfse_instalador.executor import ExecutorSimulado  # noqa: E402
from freenfse_instalador.parametros import Parametros  # noqa: E402


@pytest.fixture
def repo(tmp_path):
    """Cópia mínima do repositório: `.env.example`, modelos do Nginx e as páginas de erro."""
    destino = tmp_path / "repo"
    (destino / "docker" / "nginx").mkdir(parents=True)
    shutil.copy(RAIZ / ".env.example", destino / ".env.example")
    for nome in ("tls.conf.modelo", "locais.conf", "proxy.conf", "http.conf"):
        shutil.copy(RAIZ / "docker" / "nginx" / nome, destino / "docker" / "nginx" / nome)
    shutil.copytree(RAIZ / "docker" / "erros", destino / "docker" / "erros")
    (destino / "docker-compose.yml").write_text("services: {}\n")
    (destino / "backend").mkdir()
    (destino / "backend" / "requirements.txt").write_text("")
    return destino


@pytest.fixture
def parametros(repo, tmp_path):
    """Fábrica de `Parametros` apontando tudo para pastas temporárias."""

    def _criar(modo="compose", **ajustes):
        base = {
            "modo": modo,
            "dominio": "nfse.exemplo.com.br",
            "dados": tmp_path / "dados",
            "repositorio": repo,
            "arquivo_env": tmp_path / "config" / "freenfse.env",
            "pasta_systemd": tmp_path / "systemd",
            "pasta_nginx": tmp_path / "nginx",
            "nao_interativo": True,
            "extras": {
                "pasta_bin": tmp_path / "bin",
                "pasta_letsencrypt": tmp_path / "letsencrypt",
                "dados_explicito": True,
            },
        }
        base.update(ajustes)
        return Parametros(**base)

    return _criar


@pytest.fixture
def saida():
    """Lista que recebe tudo o que o instalador 'imprime'."""
    return []


@pytest.fixture
def executor():
    return ExecutorSimulado()


def todos_os_segredos(env):
    """Valores secretos de um `.env` (para conferir que nunca aparecem em saída nem comando)."""
    from freenfse_instalador.segredos import SEGREDOS

    valores = set()
    for nome in SEGREDOS:
        valor = env.get(nome, "")
        valores.add(valor)
        valores.update(parte.partition(":")[2] for parte in valor.split(",") if ":" in parte)
    return {v for v in valores if len(v) >= 8}
