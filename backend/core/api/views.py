"""Views da API do app core."""

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def versao(request):
    """Retorna a versão da aplicação (conteúdo do arquivo VERSION)."""
    return Response({"versao": settings.VERSAO})
