"""Versão mínima do Python do instalador e a mensagem para quem tem uma mais antiga.

O instalador roda com o Python do SERVIDOR, que numa VPS comum é o da distribuição (3.10 no
Ubuntu 22.04, 3.11 no Debian 12, 3.12 no Ubuntu 24.04), e não com o 3.14 do backend. Por isso ele
só usa a biblioteca padrão e o código é escrito para este mínimo; o CI roda os testes do instalador
em 3.10, 3.12 e 3.14 (issue #30).

Com um Python mais antigo, `SyntaxError` no meio de um módulo é a pior forma de avisar.
`instalar.py` confere a versão ANTES de importar o resto, e este módulo precisa continuar valendo
em Pythons antigos (sem sintaxe nova nem anotações avaliadas em tempo de execução).
"""

import sys

PYTHON_MINIMO = (3, 10)


def como_texto(versao, partes=2):
    """`(3, 10, 4, ...)` vira `'3.10'` (ou `'3.10.4'` com `partes=3`)."""
    return ".".join(str(parte) for parte in tuple(versao)[:partes])


def python_suficiente(versao=None):
    """Diz se `versao` (a do Python em uso, por padrão) atende ao mínimo do instalador."""
    versao = sys.version_info if versao is None else versao
    return tuple(versao)[:2] >= PYTHON_MINIMO


def mensagem_de_python_antigo(versao=None):
    """Texto de erro para quem rodou o instalador com um Python mais antigo que o mínimo."""
    versao = sys.version_info if versao is None else versao
    return (
        f"Erro: o instalador do freenfse precisa do Python {como_texto(PYTHON_MINIMO)} ou mais "
        f"novo; este é o Python {como_texto(versao, 3)}.\n"
        "Rode-o com um Python mais novo do servidor (ex.: python3.12 instalador/instalar.py ...) "
        "ou instale um: Ubuntu 22.04 (3.10), Debian 12 (3.11) e Ubuntu 24.04 (3.12) já atendem."
    )
