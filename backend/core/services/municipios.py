"""Consulta e validação de códigos de município (tabela do schema público)."""

import re

from django.core.exceptions import ValidationError

from core.models import Municipio


def validar_codigo_ibge(valor):
    """Valida o código IBGE: 7 dígitos e existente na tabela de municípios.

    Pensado para validar campos de modelos de empresa, que guardam o código como texto (sem
    chave estrangeira entre schemas). Se a tabela estiver vazia, o erro orienta a carregá-la.
    """
    codigo = re.sub(r"\D", "", str(valor or ""))
    if len(codigo) != 7:
        raise ValidationError("O código do município (IBGE) deve ter 7 dígitos.", code="ibge")
    if not Municipio.objects.filter(codigo=codigo).exists():
        if not Municipio.objects.exists():
            raise ValidationError(
                "A tabela de municípios está vazia. Peça ao administrador do sistema para "
                "executar `python manage.py carregar_municipios`.",
                code="municipios_nao_carregados",
            )
        raise ValidationError(f"Município com o código IBGE {codigo} não encontrado.", code="ibge")
    return codigo


def obter(codigo):
    """Devolve o `Municipio` pelo código IBGE, ou `None`."""
    return Municipio.objects.filter(codigo=re.sub(r"\D", "", str(codigo or ""))).first()
