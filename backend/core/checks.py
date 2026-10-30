"""Verificações do sistema (`manage.py check`)."""

from django.conf import settings
from django.core.checks import Error, Warning, register

from core import crypto


@register()
def verificar_chaves_de_criptografia(app_configs, **kwargs):
    """Avisa se `FREENFSE_CHAVES` falta e recusa chaves malformadas."""
    brutas = getattr(settings, "FREENFSE_CHAVES", None) or []
    if not brutas:
        return [
            Warning(
                "FREENFSE_CHAVES não está configurada.",
                hint="Gere uma chave com `python manage.py gerar_chave` e defina "
                "FREENFSE_CHAVES=1:<chave>. Sem ela, campos criptografados não funcionam.",
                id="core.W001",
            )
        ]
    try:
        crypto.versao_atual()
    except crypto.ErroDeConfiguracaoDeChaves as erro:
        return [Error(str(erro), id="core.E001")]
    return []
