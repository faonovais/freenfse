"""Views de cadastros (pessoas, perfis, serviços e cópia entre empresas)."""

import datetime as dt

from django.core.exceptions import ValidationError as ErroDjango
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from cadastros.models import PerfilPessoa, Pessoa, Servico
from cadastros.services import copia, servicos
from core.api.permissions import PermissaoPorOperacao, QualquerVinculado
from core.models import Empresa, Municipio
from core.municipios import normalizar_nome
from fiscal.referencias import classificacao, indop

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
        "referencias_ibs_cbs": "cadastro.consultar",
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
            data = dt.date.fromisoformat(params.get("data") or timezone.localdate().isoformat())
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

    @action(detail=False, methods=["get"], url_path="referencias-ibs-cbs")
    def referencias_ibs_cbs(self, request):
        """Apoio ao cadastro: sugestão de cIndOp (Anexo VIII) e situação da classificação.

        `?codigo_nacional=&nbs=&c_class_trib=&data=` — todos opcionais. Só leitura de tabelas
        oficiais versionadas; nada é gravado nem consultado na rede.
        """
        params = request.query_params
        try:
            data = dt.date.fromisoformat(params.get("data") or timezone.localdate().isoformat())
        except ValueError:
            raise serializers.ValidationError(
                {"data": "Use a data no formato AAAA-MM-DD."}
            ) from None
        nacional = "".join(c for c in params.get("codigo_nacional", "") if c.isdigit())
        sugestao = indop.sugerir(nacional, params.get("nbs", "")) if len(nacional) == 6 else None
        return Response(
            {
                "indop": sugestao
                and {
                    **sugestao,
                    "locais": {o: indop.local_de_incidencia_do_ibs(o) for o in sugestao["opcoes"]},
                    "classes_possiveis": indop.classes_possiveis(nacional, params.get("nbs", "")),
                },
                "classificacao": _classificacao_para_a_tela(params.get("c_class_trib", ""), data),
            }
        )


def _classificacao_para_a_tela(c_class_trib, data):
    """Situação oficial da classificação numa data, em linguagem para a tela (ou `None`)."""
    codigo = "".join(c for c in c_class_trib if c.isdigit())
    if not codigo:
        return None
    todas = classificacao.todas()
    oficial = classificacao.consultar(codigo, data)
    if oficial is None:
        return {
            "codigo": codigo,
            "consta": codigo in todas,
            "vigente": False,
            "mensagem": (
                f"A classificação {codigo} não vigora em {data:%d/%m/%Y} na tabela oficial."
                if codigo in todas
                else f"A classificação {codigo} não consta da tabela oficial da calculadora."
            ),
        }
    if not oficial.aceita_nfse:
        mensagem = f"A classificação {codigo} não vale para NFS-e (regra E0958 da Sefin)."
    elif oficial.exige_grupo_ibs_cbs:
        mensagem = (
            f"A classificação {codigo} exige o grupo de IBS/CBS: a nota precisa do indicador da "
            "operação (cIndOp)."
        )
    else:
        mensagem = (
            f"A classificação {codigo} não tem tributação de IBS/CBS: a nota sai sem o grupo e "
            "sem o indicador da operação."
        )
    return {
        "codigo": codigo,
        "consta": True,
        "vigente": True,
        "descricao": oficial.descricao,
        "aceita_nfse": oficial.aceita_nfse,
        "exige_grupo_ibs_cbs": oficial.exige_grupo_ibs_cbs,
        "mensagem": mensagem,
    }


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


class MunicipioView(APIView):
    """Busca de municípios (dado público do IBGE) para os campos de endereço."""

    permission_classes = [QualquerVinculado]

    def get(self, request):
        """Até 20 municípios por `busca` (nome, sem acento nem caixa) e `uf`, ou um por `codigo`."""
        params = request.query_params
        consulta = Municipio.objects.all()
        codigo = "".join(c for c in params.get("codigo", "") if c.isdigit())
        if codigo:
            consulta = consulta.filter(codigo=codigo)
        busca = params.get("busca", "").strip()
        if busca:
            consulta = consulta.filter(nome_busca__contains=normalizar_nome(busca))
        uf = params.get("uf", "").strip().upper()
        if uf:
            consulta = consulta.filter(uf=uf)
        if not (codigo or busca):
            return Response([])
        return Response(
            [
                {"codigo": m.codigo, "nome": m.nome, "uf": m.uf}
                for m in consulta.order_by("nome", "uf")[:20]
            ]
        )
