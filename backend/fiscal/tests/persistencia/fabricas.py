"""Fábricas de dados fictícios para os testes fiscais."""

import datetime as dt
from decimal import Decimal

from fiscal.models import Nfse, ParametrosFiscais


def criar_nfse(**extra):
    """Rascunho mínimo de nota, no schema ativo."""
    dados = {
        "ambiente": ParametrosFiscais.Ambiente.PRODUCAO_RESTRITA,
        "serie": 900,
        "competencia": dt.date(2026, 11, 1),
        "valor_servico": Decimal("100.00"),
    }
    dados.update(extra)
    return Nfse.objects.create(**dados)
