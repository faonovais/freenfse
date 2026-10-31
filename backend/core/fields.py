"""Campos de modelo criptografados (AES-256-GCM com chave versionada).

O banco guarda sempre o token (`v<n>:` + nonce + cifra); o modelo enxerga o
valor em claro. Como cada gravação usa um nonce novo, **não é possível filtrar
por esses campos** (só `isnull`). Guarde ao lado um campo derivado e não
sensível (ex.: CNPJ do titular) quando precisar buscar.
"""

from django.apps import apps
from django.db import NotSupportedError, models

from . import crypto


class _SemBusca:
    """Mixin: só permite o lookup `isnull`."""

    def get_lookup(self, lookup_name):
        """Recusa filtros por valor, que nunca casariam com o texto cifrado."""
        if lookup_name != "isnull":
            raise NotSupportedError(
                f"Campo criptografado não permite o filtro '{lookup_name}' (apenas isnull)."
            )
        return super().get_lookup(lookup_name)


class CampoTextoCriptografado(_SemBusca, models.TextField):
    """Texto criptografado (senhas, tokens, credenciais)."""

    description = "Texto criptografado com AES-256-GCM"

    def get_prep_value(self, value):
        """Cifra o valor antes de gravar."""
        value = super().get_prep_value(value)
        return None if value is None else crypto.cifrar_texto(value)

    def from_db_value(self, value, expression, connection):
        """Decifra o valor lido do banco."""
        return None if value is None else crypto.decifrar_texto(value)


class CampoBinarioCriptografado(_SemBusca, models.BinaryField):
    """Bytes criptografados (ex.: arquivo .pfx do certificado A1)."""

    description = "Bytes criptografados com AES-256-GCM"

    def get_db_prep_value(self, value, connection, prepared=False):
        """Cifra os bytes antes de gravar."""
        if value is None:
            return None
        return super().get_db_prep_value(crypto.cifrar_bytes(value), connection, prepared)

    def from_db_value(self, value, expression, connection):
        """Decifra os bytes lidos do banco."""
        return None if value is None else crypto.decifrar_bytes(value)


TIPOS_CRIPTOGRAFADOS = (CampoTextoCriptografado, CampoBinarioCriptografado)


def campos_criptografados():
    """Lista `(modelo, campo)` de todos os campos criptografados dos apps instalados."""
    return [
        (modelo, campo)
        for modelo in apps.get_models()
        for campo in modelo._meta.concrete_fields
        if isinstance(campo, TIPOS_CRIPTOGRAFADOS)
    ]
