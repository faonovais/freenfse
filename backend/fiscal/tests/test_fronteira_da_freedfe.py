"""A freedfe só entra por três portas: o gateway, a persistência e a leitura do certificado."""

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PERMITIDOS = ("fiscal/gateway.py", "fiscal/persistencia/", "fiscal/services/certificado.py")


def _importa_freedfe(arquivo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import) and any(a.name.split(".")[0] == "freedfe" for a in no.names):
            return True
        if isinstance(no, ast.ImportFrom) and (no.module or "").split(".")[0] == "freedfe":
            return True
    return False


def test_nenhum_codigo_de_producao_fora_das_portas_importa_a_freedfe():
    intrusos = []
    for arquivo in RAIZ.rglob("*.py"):
        relativo = arquivo.relative_to(RAIZ).as_posix()
        if "/tests/" in relativo or relativo.startswith(PERMITIDOS) or "/migrations/" in relativo:
            continue
        if _importa_freedfe(arquivo):
            intrusos.append(relativo)

    assert intrusos == []
