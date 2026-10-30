"""Rotas de empresa usadas nos testes de middleware e de PermissaoPorOperacao."""

from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from core.api.permissions import PermissaoPorOperacao

from .models import Anotacao


class AnotacaoSerializer(serializers.ModelSerializer):
    """Serializer da anotação (o segredo nunca é devolvido)."""

    class Meta:
        model = Anotacao
        fields = ["id", "texto", "segredo"]
        extra_kwargs = {"segredo": {"write_only": True}}


class AnotacaoViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Anotações da empresa ativa, com uma permissão nomeada por operação."""

    queryset = Anotacao.objects.all()
    serializer_class = AnotacaoSerializer
    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "nfse.consultar",
        "retrieve": "nfse.consultar",
        "create": "nfse.emitir",
        "cancelar": "nfse.cancelar",
        # "sem_declaracao" fica de fora de propósito: PermissaoPorOperacao falha fechada.
    }

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Operação que exige `nfse.cancelar`."""
        return Response({"cancelada": self.get_object().pk})

    @action(detail=False, methods=["get"])
    def sem_declaracao(self, request):
        """Operação sem permissão declarada: deve ser negada para todos."""
        return Response({"ok": True})


roteador = SimpleRouter()
roteador.register("anotacoes", AnotacaoViewSet, basename="anotacao")
urlpatterns = roteador.urls
