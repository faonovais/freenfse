"""Views de cadastros (pessoas, perfis, serviços e cópia entre empresas)."""

import datetime as dt

from django.core.exceptions import ValidationError as ErroDjango
from django.db import IntegrityError
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from cadastros.models import PerfilPessoa, Pessoa, Servico
from cadastros.services import copia, servicos
from core.api.permissions import PermissaoPorOperacao
from core.models import Empresa

from .serializers import (
    PerfilPessoaSerializer,
    PessoaSerializer,
    ServicoSerializer,
)


class PaginacaoPadrao(PageNumberPagination):
    """25 por página; `tamanho` ajusta até 200."""

    page_size = 25
    page_size_query_param = "tamanho"
    max_page_size = 200


def _como_booleano(valor):
    return {"true": True, "false": False}.get(str(valor).lower())


class PerfilPessoaViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Perfis de pessoa da empresa (os padrão vêm da migração)."""

    queryset = PerfilPessoa.objects.all()
    serializer_class = PerfilPessoaSerializer
    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"list": "cadastro.consultar", "create": "cadastro.editar"}
    pagination_class = None


class PessoaViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Pessoas da empresa ativa. Sem exclusão: desative (`ativo=false`)."""

    queryset = Pessoa.objects.prefetch_related("perfis")
    serializer_class = PessoaSerializer
    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "cadastro.consultar",
        "retrieve": "cadastro.consultar",
        "create": "cadastro.editar",
        "update": "cadastro.editar",
        "partial_update": "cadastro.editar",
    }
    pagination_class = PaginacaoPadrao

    def get_queryset(self):
        """Filtros: `busca` (nome ou documento), `tipo`, `perfil` (código) e `ativo`."""
        consulta = super().get_queryset()
        params = self.request.query_params
        busca = params.get("busca", "").strip()
        if busca:
            consulta = consulta.filter(nome__icontains=busca) | consulta.filter(
                documento__icontains="".join(c for c in busca if c.isalnum()).upper()
            )
        if params.get("tipo"):
            consulta = consulta.filter(tipo=params["tipo"])
        if params.get("perfil"):
            consulta = consulta.filter(perfis__codigo=params["perfil"])
        ativo = _como_booleano(params.get("ativo"))
        if ativo is not None:
            consulta = consulta.filter(ativo=ativo)
        return consulta.distinct().order_by("nome", "id")

    def perform_create(self, serializer):
        """Grava e converte a corrida de unicidade em erro de validação."""
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {"documento": "Já existe uma pessoa cadastrada com este documento."}
            ) from None


class ServicoViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Serviços (versões com vigência) da empresa ativa."""

    queryset = Servico.objects.all()
    serializer_class = ServicoSerializer
    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "cadastro.consultar",
        "retrieve": "cadastro.consultar",
        "vigente": "cadastro.consultar",
        "create": "cadastro.editar",
        "update": "cadastro.editar",
        "partial_update": "cadastro.editar",
    }
    pagination_class = None

    def get_queryset(self):
        """Filtros: `busca`, `ativo` e `vigente_em` (data ISO)."""
        consulta = super().get_queryset()
        params = self.request.query_params
        busca = params.get("busca", "").strip()
        if busca:
            consulta = consulta.filter(nome__icontains=busca) | consulta.filter(
                codigo_tributacao_nacional__icontains=busca
            )
        ativo = _como_booleano(params.get("ativo"))
        if ativo is not None:
            consulta = consulta.filter(ativo=ativo)
        if params.get("vigente_em"):
            try:
                data = dt.date.fromisoformat(params["vigente_em"])
            except ValueError:
                raise serializers.ValidationError(
                    {"vigente_em": "Use a data no formato AAAA-MM-DD."}
                ) from None
            consulta = consulta.vigentes_em(data)
        return consulta.order_by("nome", "codigo_tributacao_nacional", "-vigencia_inicio")

    def _gravar(self, serializer):
        """Aplica os dados validados ao serviço e grava sob o lock de vigência."""
        servico = serializer.instance or Servico()
        for campo, valor in serializer.validated_data.items():
            setattr(servico, campo, valor)
        try:
            return servicos.salvar_servico(servico)
        except ErroDjango as erro:
            raise serializers.ValidationError(erro.message_dict) from None

    def perform_create(self, serializer):
        """Cria a versão sob o lock de vigência."""
        serializer.instance = self._gravar(serializer)

    def perform_update(self, serializer):
        """Altera a versão sob o lock de vigência."""
        serializer.instance = self._gravar(serializer)

    @action(detail=False, methods=["get"])
    def vigente(self, request):
        """Versão vigente de um serviço numa data: `?codigo_nacional=&codigo_municipal=&data=`."""
        params = request.query_params
        try:
            data = dt.date.fromisoformat(params.get("data") or dt.date.today().isoformat())
        except ValueError:
            raise serializers.ValidationError(
                {"data": "Use a data no formato AAAA-MM-DD."}
            ) from None
        nacional = "".join(c for c in params.get("codigo_nacional", "") if c.isdigit())
        if len(nacional) != 6:
            raise serializers.ValidationError(
                {"codigo_nacional": "Informe o código de tributação nacional (6 dígitos)."}
            )
        municipal = "".join(c for c in params.get("codigo_municipal", "") if c.isdigit())
        servico = Servico.objects.vigente(data, nacional, municipal)
        if servico is None:
            return Response(
                {"detalhe": f"Nenhuma versão deste serviço vigente em {data:%d/%m/%Y}."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(servico).data)


def _sem_acesso_a_origem():
    """Mesma resposta do middleware para empresa sem acesso: não revela se ela existe."""
    return Response(
        {"codigo": "sem_acesso_a_empresa", "detalhe": "Você não tem acesso a esta empresa."},
        status=status.HTTP_403_FORBIDDEN,
    )


class CopiaPessoasView(APIView):
    """Copia pessoas de outra empresa para a empresa ativa (cópia, não vínculo)."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"get": "cadastro.editar", "post": "cadastro.editar"}

    @staticmethod
    def _origem(valor):
        try:
            return Empresa.objects.filter(pk=int(valor), ativo=True).first()
        except TypeError, ValueError:
            return None

    def get(self, request):
        """Lista as pessoas da empresa de origem (`?empresa=ID`) para o usuário escolher."""
        origem = self._origem(request.query_params.get("empresa"))
        if origem is None:
            return _sem_acesso_a_origem()
        try:
            pessoas = copia.listar_da_origem(
                usuario=request.user,
                empresa_origem=origem,
                empresa_destino=request.empresa,
                busca=request.query_params.get("busca", "").strip(),
            )
        except copia.SemAcessoAOrigem:
            return _sem_acesso_a_origem()
        except copia.CopiaInvalida as erro:
            raise serializers.ValidationError({"empresa": str(erro)}) from None
        return Response(pessoas)

    def post(self, request):
        """Copia as pessoas indicadas em `ids`, ou todas com `todas: true`."""
        origem = self._origem(request.data.get("empresa_origem"))
        if origem is None:
            return _sem_acesso_a_origem()
        ids, todas = request.data.get("ids"), request.data.get("todas") is True
        if todas == (ids is not None):
            raise serializers.ValidationError(
                {"ids": "Informe `ids` (lista) ou `todas: true`, só um dos dois."}
            )
        if ids is not None:
            if (
                not isinstance(ids, list)
                or not 0 < len(ids) <= 1000
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
            ):
                raise serializers.ValidationError(
                    {"ids": "Informe de 1 a 1000 identificadores numéricos."}
                )
        try:
            resultado = copia.copiar_pessoas(
                request=request,
                empresa_origem=origem,
                empresa_destino=request.empresa,
                ids=None if todas else ids,
            )
        except copia.SemAcessoAOrigem:
            return _sem_acesso_a_origem()
        except copia.CopiaInvalida as erro:
            raise serializers.ValidationError({"empresa_origem": str(erro)}) from None
        return Response(resultado, status=status.HTTP_201_CREATED)
