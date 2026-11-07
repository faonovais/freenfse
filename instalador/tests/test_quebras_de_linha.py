"""Quebras de linha dos arquivos que rodam em Linux (issue #30).

Um clone no Windows com `core.autocrlf=true` troca LF por CRLF; num shell script ou entrypoint isso
vira `bash\\r: comando não encontrado` e o contêiner nem sobe. O `.gitattributes` fixa LF nesses
tipos. Aqui estão a prova disso e o teste que falha se um deles aparecer versionado com CRLF.
"""

import os
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import PurePosixPath

import pytest
from conftest import RAIZ

# Os tipos que precisam de LF na árvore de trabalho (os mesmos do `.gitattributes`).
PADROES_COM_LF = (
    "*.sh",
    "entrypoint*",
    "Dockerfile*",
    "*.dockerfile",
    "*.conf",
    "*.modelo",
    "*.service",
    "*.timer",
    "*.socket",
    "*.py",
    ".env*",
)

# Um exemplo de caminho (nem precisa existir) para cada tipo.
EXEMPLOS = (
    "scripts/qualquer.sh",
    "docker/entrypoint-backend.sh",
    "docker/entrypoint",
    "docker/Dockerfile.backend",
    "Dockerfile",
    "docker/app.dockerfile",
    "docker/nginx/http.conf",
    "docker/nginx/tls.conf.modelo",
    "deploy/freenfse-web.service",
    "deploy/freenfse-backup.timer",
    "deploy/freenfse.socket",
    "instalador/instalar.py",
    ".env.example",
)


def precisa_de_lf(caminho):
    """Diz se o arquivo é de um tipo que roda em Linux e portanto exige LF."""
    nome = PurePosixPath(caminho).name
    return any(fnmatch(nome, padrao) for padrao in PADROES_COM_LF)


def com_crlf(conteudos):
    """Dos `{caminho: bytes}`, os caminhos de tipo sensível que têm `\\r` (CRLF ou CR solto)."""
    return sorted(c for c, dados in conteudos.items() if precisa_de_lf(c) and b"\r" in dados)


def git(*argumentos, cwd=RAIZ, **extra):
    return subprocess.run(
        ["git", *argumentos], cwd=cwd, capture_output=True, timeout=60, check=False, **extra
    )


def exigir_git():
    """Pula sem o `git`; no CI (variável `CI`) a ausência é uma falha, para o teste nunca sumir."""
    if shutil.which("git") is None:
        if os.environ.get("CI"):
            pytest.fail("O git é necessário nestes testes e não está instalado no CI.")
        pytest.skip("git não instalado")
    if not (RAIZ / ".git").exists():
        if os.environ.get("CI"):
            pytest.fail("O CI deveria rodar dentro de um clone do repositório.")
        pytest.skip("não é um clone do repositório")


# -- a lógica de detecção (vale em qualquer ambiente) ---------------------------------------


@pytest.mark.parametrize("caminho", EXEMPLOS)
def test_cada_tipo_sensivel_e_reconhecido(caminho):
    assert precisa_de_lf(caminho)


@pytest.mark.parametrize("caminho", ["README.md", "frontend/src/App.jsx", "docker-compose.yml"])
def test_outros_tipos_nao_entram_na_lista(caminho):
    assert not precisa_de_lf(caminho)


def test_deteccao_acha_crlf_e_cr_solto_so_nos_tipos_sensiveis():
    conteudos = {
        "docker/entrypoint-backend.sh": b'#!/bin/bash\r\nexec "$@"\r\n',
        "docker/nginx/http.conf": b"server {}\n",
        "instalador/instalar.py": b"#!/usr/bin/env python3\rprint(1)\n",
        "docs/manual.md": b"linha\r\nlinha\r\n",  # markdown pode ter CRLF: não é script
    }

    assert com_crlf(conteudos) == [
        "docker/entrypoint-backend.sh",
        "instalador/instalar.py",
    ]


# -- o repositório de verdade ---------------------------------------------------------------


def test_nenhum_arquivo_versionado_de_tipo_sensivel_tem_crlf():
    exigir_git()
    listagem = git("ls-files", "-z")
    assert listagem.returncode == 0, listagem.stderr
    caminhos = [c for c in listagem.stdout.decode().split("\0") if c and precisa_de_lf(c)]
    assert caminhos, "nenhum arquivo sensível encontrado: a lista de tipos está errada?"

    conteudos = {c: (RAIZ / c).read_bytes() for c in caminhos if (RAIZ / c).is_file()}

    assert com_crlf(conteudos) == [], (
        "Estes arquivos têm CRLF e quebram em Linux. Corrija com `git add --renormalize .` "
        "(ou `dos2unix`) e confira o .gitattributes."
    )


@pytest.mark.parametrize("caminho", EXEMPLOS)
def test_gitattributes_fixa_lf_em_cada_tipo_sensivel(caminho):
    exigir_git()
    atributos = git("check-attr", "text", "eol", "--", caminho).stdout.decode()

    assert f"{caminho}: eol: lf" in atributos
    assert f"{caminho}: text: set" in atributos


def test_gitattributes_normaliza_o_resto_e_nao_mexe_em_binarios():
    exigir_git()
    texto = git("check-attr", "text", "--", "frontend/src/App.jsx").stdout.decode()
    binario = git("check-attr", "text", "--", "frontend/public/fonte.woff2").stdout.decode()

    assert "text: auto" in texto
    assert "text: unset" in binario  # `binary` = sem conversão nenhuma


def test_arquivo_com_crlf_e_normalizado_ao_entrar_no_repositorio(tmp_path):
    exigir_git()
    repo = tmp_path / "repo"
    repo.mkdir()
    assert git("init", "-q", cwd=repo).returncode == 0
    shutil.copy(RAIZ / ".gitattributes", repo / ".gitattributes")
    crlf = {
        "entrypoint.sh": b'#!/bin/bash\r\nexec "$@"\r\n',
        "Dockerfile.x": b'FROM scratch\r\nCMD ["x"]\r\n',
        "nginx.conf": b"events {}\r\n",
        "freenfse.service": b"[Unit]\r\nDescription=x\r\n",
        "instalar.py": b"#!/usr/bin/env python3\r\nprint(1)\r\n",
    }
    for nome, dados in crlf.items():
        (repo / nome).write_bytes(dados)

    assert git("add", "-A", cwd=repo).returncode == 0

    for nome in crlf:
        guardado = git("show", f":{nome}", cwd=repo).stdout
        assert b"\r" not in guardado, f"{nome} entrou no repositório com CRLF"
        assert guardado.count(b"\n") == crlf[nome].count(b"\n")
