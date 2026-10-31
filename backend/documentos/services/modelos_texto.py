"""Modelos de texto com variáveis `{nome}` (e-mail e caminhos do Drive).

Um único analisador serve aos dois usos, para que as regras de validação (variável desconhecida,
chave sem fechamento) não divirjam. Chaves literais não existem nos modelos: `{` e `}` só
delimitam variáveis.
"""

import re

PADRAO = re.compile(r"\{([^{}]*)\}")


def analisar(modelo, variaveis_validas):
    """Confere o modelo e devolve `(erros, usadas)`.

    `erros` são frases para o usuário: chave sem fechamento ou sem abertura e variável
    desconhecida (com a lista das válidas).
    """
    erros = []
    resto = PADRAO.sub("", modelo or "")
    if "{" in resto:
        erros.append("Há uma chave '{' sem o '}' correspondente.")
    if "}" in resto:
        erros.append("Há uma chave '}' sem o '{' correspondente.")
    usadas = PADRAO.findall(modelo or "")
    desconhecidas = sorted({nome for nome in usadas if nome not in variaveis_validas})
    for nome in desconhecidas:
        validas = ", ".join("{" + v + "}" for v in sorted(variaveis_validas))
        erros.append(f"A variável {{{nome}}} não existe. Use: {validas}.")
    return erros, usadas


def renderizar(modelo, valores, tratar=None):
    """Troca cada `{variável}` pelo valor; `tratar` (opcional) ajusta cada valor antes."""

    def trocar(encontrado):
        valor = str(valores.get(encontrado.group(1), ""))
        return tratar(valor) if tratar else valor

    return PADRAO.sub(trocar, modelo or "")
