"""API das NFS-e emitidas (`/api/fiscal/notas/`).

Rascunho, emissão, consulta, cancelamento, substituição e arquivos.

Toda rota é de empresa (exige `X-Empresa`) e usa `PermissaoPorOperacao`, que **falha fechada**:
uma ação sem permissão declarada abaixo é negada. A emissão é assíncrona (Celery): a rota só
coloca a nota "em envio" e a interface acompanha a situação.
"""

import datetime as dt

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.api.permissions import PermissaoPorOperacao
from core.models import LogAuditoria
from core.services import auditoria
from fiscal import gateway, tasks
from fiscal.models import Nfse, ParametrosFiscais, TransicaoInvalida
from fiscal.services import bloqueios as servico_bloqueios
from fiscal.services import emissao
from fiscal.services import nfse as servico_nfse


class PaginacaoDeNotas(PageNumberPagination):
    """25 por página; `tamanho` ajusta até 100."""

    page_size = 25
    page_size_query_param = "tamanho"
    max_page_size = 100


class EventoSerializer(serializers.Serializer):
    """Evento confirmado pela Sefin."""

    tipo_evento = serializers.CharField()
    rotulo = serializers.CharField()
    descricao = serializers.CharField()
    registrado_em = serializers.DateTimeField()


class NfseListaSerializer(serializers.ModelSerializer):
    """Linha da lista de notas."""

    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)

    class Meta:
        model = Nfse
        fields = [
            "id",
            "situacao",
            "situacao_rotulo",
            "numero_nfse",
            "numero_dps",
            "serie",
            "competencia",
            "tomador_nome",
            "tomador_documento",
            "valor_servico",
            "emitida_em",
            "criado_em",
            "ambiente",
            "mensagem",
            "substitui",
        ]


class NfseDetalheSerializer(NfseListaSerializer):
    """Nota completa: snapshots, erros, eventos, histórico e o que o usuário pode fazer."""

    eventos = serializers.SerializerMethodField()
    historico = serializers.SerializerMethodField()
    acoes = serializers.SerializerMethodField()
    leiaute_descricao = serializers.SerializerMethodField()
    substituta = serializers.SerializerMethodField()
    substitui_numero = serializers.SerializerMethodField()
    tomador_id = serializers.IntegerField(source="tomador_ref_id", read_only=True)
    servico_id = serializers.IntegerField(source="servico_ref_id", read_only=True)

    class Meta(NfseListaSerializer.Meta):
        fields = [
            *NfseListaSerializer.Meta.fields,
            "chave",
            "id_dps",
            "leiaute",
            "leiaute_descricao",
            "tomador",
            "servico",
            "valores",
            "totais",
            "complementos",
            "erros",
            "hash_xml_nfse",
            "substituicao_motivo",
            "substituicao_texto",
            "substituta",
            "substitui_numero",
            "tomador_id",
            "servico_id",
            "criado_por_email",
            "eventos",
            "historico",
            "acoes",
        ]

    def get_eventos(self, nfse):
        """Eventos confirmados pela Sefin, em ordem."""
        return [
            {
                "tipo_evento": e.tipo_evento,
                "rotulo": e.rotulo,
                "descricao": e.descricao,
                "registrado_em": e.registrado_em,
            }
            for e in nfse.eventos.all()
        ]

    def get_historico(self, nfse):
        """Mudanças de situação da nota."""
        return [
            {"de": t.de, "para": t.para, "motivo": t.motivo, "momento": t.momento}
            for t in nfse.transicoes.all()
        ]

    def get_leiaute_descricao(self, nfse):
        """Nome do leiaute usado no envio."""
        return gateway.descricao_do_leiaute(nfse.leiaute)

    def get_substituta(self, nfse):
        """Nota que a substitui (a não rejeitada), se houver."""
        substituta = nfse.substitutas.exclude(situacao=Nfse.Situacao.REJEITADA).first()
        return substituta.pk if substituta else None

    def get_substitui_numero(self, nfse):
        """Número da nota substituída, quando esta é uma substituta."""
        return nfse.substitui.numero_nfse if nfse.substitui_id else ""

    def get_acoes(self, nfse):
        """O que o usuário pode fazer com a nota agora (situação e permissões)."""
        permissoes = self.context["permissoes"]
        situacao = nfse.situacao
        autorizada = situacao == Nfse.Situacao.AUTORIZADA
        emitir = "nfse.substituir" if nfse.substitui_id else "nfse.emitir"
        return {
            "editar": nfse.editavel and "nfse.emitir" in permissoes,
            "emitir": situacao
            in (Nfse.Situacao.RASCUNHO, Nfse.Situacao.REJEITADA, Nfse.Situacao.INCERTA)
            and emitir in permissoes,
            "consultar": bool(nfse.chave) and "nfse.consultar" in permissoes,
            "conferir": situacao == Nfse.Situacao.INCERTA and "nfse.consultar" in permissoes,
            "cancelar": autorizada and "nfse.cancelar" in permissoes,
            "substituir": autorizada and "nfse.substituir" in permissoes,
            "baixar_xml": bool(nfse.xml_nfse),
            "danfse": situacao
            in (Nfse.Situacao.AUTORIZADA, Nfse.Situacao.CANCELADA, Nfse.Situacao.SUBSTITUIDA),
        }


class EntradaDeNota(serializers.Serializer):
    """Corpo para criar ou corrigir um rascunho (a validação de negócio fica no serviço)."""

    tomador = serializers.IntegerField()
    servico = serializers.IntegerField()
    competencia = serializers.DateField()
    valores = serializers.DictField()
    informacoes_complementares = serializers.CharField(
        required=False, allow_blank=True, max_length=2000
    )
    percentual_total_tributos_simples = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    ibs_cbs = serializers.DictField(required=False, allow_null=True)


class EntradaDeCancelamento(serializers.Serializer):
    """Corpo do cancelamento."""

    codigo_motivo = serializers.IntegerField()
    justificativa = serializers.CharField(allow_blank=True, max_length=1000)


class EntradaDeSubstituicao(serializers.Serializer):
    """Corpo do pedido de nota substituta."""

    codigo_motivo = serializers.CharField(max_length=2)
    motivo = serializers.CharField(required=False, allow_blank=True, max_length=300)


def _erro(codigo, detalhe, http=status.HTTP_409_CONFLICT, **extra):
    return Response({"codigo": codigo, "detalhe": detalhe, **extra}, status=http)


def _digitos(texto):
    return "".join(c for c in texto if c.isdigit())


class NotaViewSet(viewsets.GenericViewSet):
    """NFS-e emitidas pela empresa ativa."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "nfse.consultar",
        "retrieve": "nfse.consultar",
        "prontidao": "nfse.consultar",
        "consultar": "nfse.consultar",
        "conferir": "nfse.consultar",
        "xml": "nfse.consultar",
        "danfse": "nfse.consultar",
        "create": "nfse.emitir",
        "partial_update": "nfse.emitir",
        "previa": "nfse.emitir",
        "emitir": "nfse.emitir",
        "cancelar": "nfse.cancelar",
        "substituir": "nfse.substituir",
    }
    pagination_class = PaginacaoDeNotas
    serializer_class = NfseListaSerializer

    # -- consulta ----------------------------------------------------------------------

    def get_queryset(self):
        """Notas da empresa ativa (o schema já isola as empresas)."""
        consulta = Nfse.objects.all()
        if self.action in ("retrieve", "partial_update"):
            consulta = consulta.prefetch_related("eventos", "transicoes")
        return consulta

    def _filtrar(self, consulta):
        filtros = self.request.query_params
        if inicio := filtros.get("periodo_inicio"):
            consulta = consulta.filter(competencia__gte=_data_ou_erro(inicio, "periodo_inicio"))
        if fim := filtros.get("periodo_fim"):
            consulta = consulta.filter(competencia__lte=_data_ou_erro(fim, "periodo_fim"))
        if situacao := filtros.get("situacao"):
            consulta = consulta.filter(situacao=situacao)
        if tomador := filtros.get("tomador", "").strip():
            condicao = Q(tomador_nome__icontains=tomador)
            if digitos := _digitos(tomador):
                condicao |= Q(tomador_documento__startswith=digitos)
            consulta = consulta.filter(condicao)
        if numero := filtros.get("numero", "").strip():
            consulta = consulta.filter(
                Q(numero_nfse=numero) | Q(numero_dps=int(numero) if numero.isdigit() else -1)
            )
        return consulta

    def list(self, request):
        """Lista paginada, com filtros por período (competência), situação, tomador e número."""
        pagina = self.paginate_queryset(self._filtrar(self.get_queryset()))
        return self.get_paginated_response(NfseListaSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        """Nota completa, com eventos, histórico e as ações permitidas ao usuário."""
        return Response(self._detalhe(self.get_object()))

    def _detalhe(self, nfse):
        nfse.refresh_from_db()
        contexto = {"permissoes": self.request.permissoes}
        return NfseDetalheSerializer(nfse, context=contexto).data

    @action(detail=False, methods=["get"])
    def prontidao(self, request):
        """Diz se a empresa pode emitir e, se não, o que falta (com a tela para resolver)."""
        parametros = ParametrosFiscais.obter()
        pendencias = servico_bloqueios.verificar_prontidao()
        ambiente_producao = parametros.ambiente == ParametrosFiscais.Ambiente.PRODUCAO
        return Response(
            {
                "pronta": not pendencias,
                "bloqueios": [b.para_dict() for b in pendencias],
                "ambiente": parametros.ambiente,
                "leiaute": gateway.leiaute_em_vigor(ambiente_producao),
                "leiaute_descricao": gateway.descricao_do_leiaute(
                    gateway.leiaute_em_vigor(ambiente_producao)
                ),
                "motivos_de_cancelamento": [
                    {"codigo": k, "rotulo": v} for k, v in gateway.MOTIVOS_DE_CANCELAMENTO.items()
                ],
                "motivos_de_substituicao": [
                    {"codigo": k, "rotulo": v}
                    for k, v in servico_nfse.MOTIVOS_DE_SUBSTITUICAO.items()
                ],
            }
        )

    # -- rascunho ----------------------------------------------------------------------

    def _entrada(self, request):
        entrada = EntradaDeNota(data=request.data)
        entrada.is_valid(raise_exception=True)
        return dict(entrada.validated_data)

    @action(detail=False, methods=["post"])
    def previa(self, request):
        """Calcula e valida a nota **sem gravar nada**: é a conferência antes de enviar."""
        try:
            preparo = servico_nfse.preparar(self._entrada(request))
        except servico_nfse.ErroDeNota as erro:
            raise serializers.ValidationError(erro.erros) from None
        return Response(
            {
                "tomador": preparo.tomador,
                "servico": preparo.servico,
                "competencia": preparo.competencia,
                "valores": preparo.valores,
                "totais": preparo.totais,
                "complementos": preparo.complementos,
                "avisos": preparo.avisos,
                "bloqueios": [b.para_dict() for b in servico_bloqueios.verificar_prontidao()],
            }
        )

    def create(self, request):
        """Cria o rascunho (com cópia dos dados do tomador e do serviço)."""
        try:
            nfse = servico_nfse.criar_rascunho(self._entrada(request), usuario=request.user)
        except servico_nfse.ErroDeNota as erro:
            raise serializers.ValidationError(erro.erros) from None
        auditoria.registrar(
            LogAuditoria.Acao.NFSE_RASCUNHO_CRIADO, request=request, alvo=f"nfse:{nfse.pk}"
        )
        return Response(self._detalhe(nfse), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        """Corrige um rascunho ou uma nota rejeitada (refaz a cópia dos dados)."""
        nfse = self.get_object()
        try:
            servico_nfse.atualizar_rascunho(nfse, self._entrada(request))
        except servico_nfse.ErroDeNota as erro:
            raise serializers.ValidationError(erro.erros) from None
        return Response(self._detalhe(nfse))

    # -- emissão e consulta ------------------------------------------------------------

    @action(detail=True, methods=["post"])
    def emitir(self, request, pk=None):
        """Coloca a nota "em envio" e agenda a emissão (assíncrona). Responde 202."""
        nfse = self.get_object()
        if nfse.substitui_id and "nfse.substituir" not in request.permissoes:
            return _erro(
                "permissao_negada",
                "Emitir uma nota substituta exige a permissão de substituir notas.",
                http=status.HTTP_403_FORBIDDEN,
            )
        try:
            emissao.solicitar_emissao(
                nfse, usuario=request.user, request=request, empresa=request.empresa
            )
        except emissao.BloqueioDeEmissao as erro:
            return _erro(
                "empresa_nao_pronta",
                str(erro),
                bloqueios=[b.para_dict() for b in erro.bloqueios],
            )
        except (emissao.ErroDeEmissao, TransicaoInvalida) as erro:
            return _erro("operacao_recusada", str(erro))
        schema, nfse_id = request.empresa.schema_name, nfse.pk
        transaction.on_commit(lambda: tasks.emitir_nfse.delay(schema, nfse_id))
        return Response(self._detalhe(nfse), status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def consultar(self, request, pk=None):
        """Consulta a Sefin e atualiza a nota (XML e eventos)."""
        nfse = self.get_object()
        try:
            emissao.consultar(request.empresa, nfse)
        except gateway.TravaOcupadaErro:
            return _erro("trava_ocupada", "Há outra operação fiscal em andamento. Tente de novo.")
        except emissao.ErroDeEmissao as erro:
            return _erro("consulta_recusada", str(erro), http=status.HTTP_502_BAD_GATEWAY)
        return Response(self._detalhe(nfse))

    @action(detail=True, methods=["post"])
    def conferir(self, request, pk=None):
        """Pergunta à Sefin o que houve com uma nota de resultado incerto. Nunca reenvia."""
        nfse = self.get_object()
        if nfse.situacao != Nfse.Situacao.INCERTA:
            return _erro(
                "operacao_recusada", "Só uma nota com resultado incerto precisa ser conferida."
            )
        try:
            emissao.reconciliar_nota(request.empresa, nfse)
        except gateway.TravaOcupadaErro:
            return _erro("trava_ocupada", "Há outra operação fiscal em andamento. Tente de novo.")
        except emissao.ErroDeEmissao as erro:
            return _erro("consulta_recusada", str(erro), http=status.HTTP_502_BAD_GATEWAY)
        return Response(self._detalhe(nfse))

    # -- cancelamento e substituição ---------------------------------------------------

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        """Cancela a nota. Só muda depois de a Sefin confirmar o evento."""
        nfse = self.get_object()
        entrada = EntradaDeCancelamento(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            emissao.cancelar(
                request.empresa,
                nfse,
                codigo_motivo=entrada.validated_data["codigo_motivo"],
                justificativa=entrada.validated_data["justificativa"],
                usuario=request.user,
                request=request,
            )
        except servico_nfse.ErroDeNota as erro:
            raise serializers.ValidationError(erro.erros) from None
        except emissao.CancelamentoRecusado as erro:
            return _erro(
                "cancelamento_recusado",
                str(erro),
                http=status.HTTP_422_UNPROCESSABLE_ENTITY,
                erros=erro.erros,
            )
        except emissao.CancelamentoIncerto as erro:
            return _erro("cancelamento_incerto", str(erro), http=status.HTTP_502_BAD_GATEWAY)
        except (emissao.ErroDeEmissao, TransicaoInvalida) as erro:
            return _erro("operacao_recusada", str(erro))
        return Response(self._detalhe(nfse))

    @action(detail=True, methods=["post"])
    def substituir(self, request, pk=None):
        """Cria o rascunho da nota substituta ("emitir nota substituta a partir desta")."""
        original = self.get_object()
        entrada = EntradaDeSubstituicao(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            substituta = servico_nfse.criar_substituta(
                original,
                codigo_motivo=entrada.validated_data["codigo_motivo"],
                motivo=entrada.validated_data.get("motivo", ""),
                usuario=request.user,
            )
        except servico_nfse.ErroDeNota as erro:
            raise serializers.ValidationError(erro.erros) from None
        auditoria.registrar(
            LogAuditoria.Acao.NFSE_SUBSTITUICAO_CRIADA,
            request=request,
            alvo=f"nfse:{original.pk}",
            detalhes={"substituta": substituta.pk, "motivo": substituta.substituicao_motivo},
        )
        return Response(self._detalhe(substituta), status=status.HTTP_201_CREATED)

    # -- arquivos ----------------------------------------------------------------------

    @action(detail=True, methods=["get"])
    def xml(self, request, pk=None):
        """XML original da NFS-e, como a Sefin devolveu."""
        nfse = self.get_object()
        if not nfse.xml_nfse:
            return _erro("sem_xml", "Esta nota ainda não tem XML (não foi autorizada).")
        resposta = HttpResponse(bytes(nfse.xml_nfse), content_type="application/xml")
        resposta["Content-Disposition"] = f'attachment; filename="nfse-{nfse.chave}.xml"'
        return resposta

    @action(detail=True, methods=["get"])
    def danfse(self, request, pk=None):
        """DANFSe em PDF, gerado na hora (marca d'água se cancelada ou substituída)."""
        nfse = self.get_object()
        try:
            pdf = emissao.gerar_danfse(request.empresa, nfse)
        except gateway.TravaOcupadaErro:
            return _erro("trava_ocupada", "Há outra operação fiscal em andamento. Tente de novo.")
        except emissao.ErroDeEmissao as erro:
            return _erro("danfse_indisponivel", str(erro))
        resposta = HttpResponse(pdf, content_type="application/pdf")
        resposta["Content-Disposition"] = f'inline; filename="danfse-{nfse.chave}.pdf"'
        return resposta


def _data_ou_erro(texto, campo):
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        raise serializers.ValidationError({campo: "Use o formato AAAA-MM-DD."}) from None
