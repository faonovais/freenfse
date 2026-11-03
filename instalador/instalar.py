#!/usr/bin/env python3
"""Instalador do freenfse. Uso: python3 instalador/instalar.py {compose|nativo} [opções].

Só usa a biblioteca padrão do Python. Veja `--help` e docs/instalacao.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freenfse_instalador import parametros  # noqa: E402
from freenfse_instalador.compose import InstalacaoCompose  # noqa: E402
from freenfse_instalador.executor import ErroDeComando, Executor, ExecutorSimulado  # noqa: E402
from freenfse_instalador.nativo import InstalacaoNativa  # noqa: E402
from freenfse_instalador.saude import FalhaNaVerificacao  # noqa: E402


def principal(argv=None):
    """Executa a instalação; devolve o código de saída (0 = tudo certo)."""
    try:
        p = parametros.ler_argumentos(sys.argv[1:] if argv is None else argv)
    except parametros.ErroDeParametro as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2
    executor = ExecutorSimulado() if p.simular else Executor()
    classe = InstalacaoCompose if p.modo == "compose" else InstalacaoNativa
    instalacao = classe(p, executor)
    if p.simular:
        print("SIMULAÇÃO: nada será executado nem gravado.")
    try:
        instalacao.instalar()
    except (RuntimeError, ErroDeComando, FalhaNaVerificacao, OSError) as erro:
        print(f"\nA instalação parou: {erro}", file=sys.stderr)
        print("Corrija e rode o instalador de novo: ele é seguro de repetir.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
