"""Retenção dos registros de envio de e-mail (decisão do usuário na issue #18, ADR 0008).

Os registros de envio (`EnvioEmail`) guardam e-mails de pessoas e o histórico de falhas: ficam
**5 anos**, igual à guarda fiscal, e depois são apagados automaticamente. Este módulo **não toca
em nenhum documento fiscal**: XML, evidências e eventos têm guarda mínima de 5 anos e não existe
expurgo automático deles (o teste `test_retencao.py` prova isso com o relógio avançado).
"""

from django.conf import settings

from documentos.models import EnvioEmail
from documentos.services import contexto


def anos_de_retencao():
    """Anos de guarda dos registros de envio (`FREENFSE_RETENCAO_ENVIOS_ANOS`, padrão 5)."""
    return max(1, int(settings.FREENFSE_RETENCAO_ENVIOS_ANOS))


def limite_de_retencao(agora, anos):
    """Instante `anos` antes de `agora` (29/02 vira 28/02 em ano comum)."""
    try:
        return agora.replace(year=agora.year - anos)
    except ValueError:
        return agora.replace(year=agora.year - anos, day=28)


def expurgar_envios_de_email(*, agora=None):
    """Apaga os registros de envio da empresa ativa criados há mais que a retenção.

    Só `EnvioEmail` é apagado, e só o que for **estritamente mais antigo** que o limite. Devolve
    quantos registros foram removidos.
    """
    agora = agora or contexto.agora()
    antigos = EnvioEmail.objects.filter(criado_em__lt=limite_de_retencao(agora, anos_de_retencao()))
    return antigos.delete()[1].get(EnvioEmail._meta.label, 0)
