"""Endpoint de saúde da instalação (público, sem dados sensíveis)."""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from operacao import saude


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
@throttle_classes([])
def saude_da_instalacao(request):
    """Estado de cada peça (banco, Redis, worker, agendador, backup) em uma palavra.

    HTTP 200 quando está `ok` ou `degradado` (worker, agendador ou backup com problema: a
    aplicação atende, mas algo precisa de atenção) e 503 quando `falha` (banco ou Redis fora).
    Não devolve versão, endereço nem mensagem de erro.
    """
    estado_geral, componentes = saude.estado(com_memo=True)
    codigo = status.HTTP_503_SERVICE_UNAVAILABLE if estado_geral == "falha" else status.HTTP_200_OK
    return Response({"status": estado_geral, **componentes}, status=codigo)
