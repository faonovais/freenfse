"""Município da prestação do serviço: de onde vem e o que ele valida (issue #29, ADR 0010).

O município da prestação é o `cLocPrestacao` da DPS e, nos serviços cuja incidência do ISSQN é o
**local da prestação** (aba MUN.INCID_INFO.SERV. do Anexo VI), o município de incidência que a
regra da alíquota consulta. Cada campo é resolvido sozinho, como no IBS/CBS:

1. **nota** — o que o usuário informou naquela nota;
2. **modelo** — o que o modelo de NFS-e define (vazio = herda);
3. **emissor** — o município do emissor, o padrão.

Antes da correção a DPS levava sempre o município do emissor; o resultado continua o mesmo quando
ninguém informa nada.
"""

import re

from django.core.exceptions import ValidationError

from core.services import municipios

ORIGEM_NOTA, ORIGEM_MODELO, ORIGEM_EMISSOR = "nota", "modelo", "emissor"
ROTULO_DA_ORIGEM = {
    ORIGEM_NOTA: "informado nesta nota",
    ORIGEM_MODELO: "do modelo",
    ORIGEM_EMISSOR: "padrão: município do emissor",
}


def normalizar(valor):
    """Só os dígitos do código IBGE, ou `None` quando vazio (= não definiu, herda)."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos or None


def erro_do_codigo(valor):
    """Mensagem em linguagem simples se o código não for de um município da tabela; senão `None`."""
    try:
        municipios.validar_codigo_ibge(valor)
    except ValidationError as erro:
        return erro.messages[0]
    return None


def resolver(nota, modelo, parametros):
    """`(código, origem)` do município da prestação: nota > modelo > emissor.

    `nota` e `modelo` são o que cada nível definiu (texto; vazio ou `None` = herda). Se nem o
    emissor está definido, devolve `(None, None)`: quem usa decide o bloqueio.
    """
    for origem, bruto in ((ORIGEM_NOTA, nota), (ORIGEM_MODELO, modelo)):
        codigo = normalizar(bruto)
        if codigo:
            return codigo, origem
    emissor = normalizar(parametros.codigo_municipio_emissor)
    return (emissor, ORIGEM_EMISSOR) if emissor else (None, None)


def da_nota(nfse, parametros):
    """O município da prestação de uma nota já gravada, a partir do que ela guarda.

    Rascunhos anteriores a esta correção não guardam nada e caem no município do emissor, o que
    a DPS sempre informou.
    """
    complementos = nfse.complementos or {}
    return resolver(
        complementos.get("municipio_prestacao_nota"),
        complementos.get("municipio_prestacao_modelo"),
        parametros,
    )
