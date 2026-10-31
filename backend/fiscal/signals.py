"""Sinais do núcleo fiscal: o que outros apps (documentos) ouvem sem que o fiscal os conheça.

Os sinais são enviados com `send_robust`: uma falha de quem ouve (por exemplo, o Redis fora do ar
ao enfileirar uma cópia ao Drive) nunca desfaz nem atrasa o resultado fiscal da nota.
"""

import logging

from django.dispatch import Signal

logger = logging.getLogger(__name__)

# Enviado quando a Sefin autoriza a nota. Argumentos: `nfse`.
nfse_autorizada = Signal()

# Enviado quando um evento novo da nota (cancelamento, substituição…) é confirmado pela Sefin.
# Argumentos: `nfse`, `evento` (`EventoNfse`).
nfse_evento_confirmado = Signal()


def avisar(sinal, **argumentos):
    """Envia o sinal sem deixar uma falha de quem ouve interferir na operação fiscal."""
    for receptor, resultado in sinal.send_robust(sender=avisar, **argumentos):
        if isinstance(resultado, Exception):
            logger.error(
                "Falha em %s ao tratar %s: %r",
                getattr(receptor, "__name__", receptor),
                sinal,
                resultado,
            )
