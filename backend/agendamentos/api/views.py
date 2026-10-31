"""API dos agendamentos (`/api/agendamentos/`): rotas de empresa, exigem `X-Empresa`.

Todas usam `PermissaoPorOperacao`, que falha fechada. Aprovar e descartar rascunhos exige
`nfse.emitir`; o resto, `agendamento.consultar` (ler) ou `agendamento.editar` (alterar).
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from agendamentos import recorrencia
from agendamentos.api import serializers as s
from agendamentos.models import Agendamento, ExecucaoAgendamento, ModeloNfse
from agendamentos.services import agenda, modelos, rascunhos
from core.api.permissions import PermissaoPorOperacao
from core.models import LogAuditoria, VinculoUsuarioEmpresa
from core.services import auditoria
from fiscal import tasks as tarefas_fiscais
from fiscal.models import Nfse
from fiscal.services import nfse as servico_nfse
from fiscal.services.nfse import ErroDeNota

CAMPOS_QUE_AFETAM_A_GERACAO = {
    "ativo", "tomador", "servico", "valores", "competencia_padrao",
    "informacoes_complementares", "percentual_total_tributos_simples", "ibs_cbs",
}  # fmt: skip
LIMITE_DAS_LISTAS = 200
PREVIA_PADRAO = 5


def _erro(codigo, detalhe, http=status.HTTP_409_CONFLICT, **extra):
    return Response({"codigo": codigo, "detalhe": detalhe, **extra}, status=http)


# --- Modelos de NFS-e ------------------------------------------------------------------------


class ModeloViewSet(viewsets.GenericViewSet):
    """Modelos de NFS-e da empresa."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "agendamento.consultar",
        "retrieve": "agendamento.consultar",
        "previa": "agendamento.consultar",
        "create": "agendamento.editar",
        "partial_update": "agendamento.editar",
        "gerar_rascunho": "nfse.emitir",
    }
    pagination_class = None

    def get_queryset(self):
        """Modelos da empresa ativa (o schema já isola as empresas)."""
        return ModeloNfse.objects.select_related("tomador", "servico")

    def _saida(self, modelo):
        problemas = (
            modelos.erros_de_preparo(modelo, hoje=timezone.localdate()) if modelo.ativo else {}
        )
        em_uso = agenda.agendamentos_do_modelo(modelo).count()
        return s.modelo_saida(modelo, problemas=problemas, em_uso=em_uso)

    def list(self, request):
        """Todos os modelos, com o que impede cada um de gerar rascunho hoje."""
        return Response([self._saida(m) for m in self.get_queryset()[:LIMITE_DAS_LISTAS]])

    def retrieve(self, request, pk=None):
        """Um modelo."""
        return Response(self._saida(self.get_object()))

    def _salvar(self, request, modelo, dados, *, criando):
        erros = s.aplicar_modelo(modelo, dados)
        nome = (modelo.nome or "").strip()
        if nome and ModeloNfse.objects.filter(nome__iexact=nome).exclude(pk=modelo.pk).exists():
            erros["nome"] = "Já existe um modelo com este nome."
        com_geracao = criando or bool(CAMPOS_QUE_AFETAM_A_GERACAO & set(dados))
        erros = {
            **modelos.validar_modelo(modelo, hoje=timezone.localdate(), com_geracao=com_geracao),
            **erros,
        }
        if erros:
            return Response(erros, status=status.HTTP_400_BAD_REQUEST)
        modelo.save()
        auditoria.registrar(
            LogAuditoria.Acao.MODELO_NFSE_SALVO,
            request=request,
            alvo=f"modelo:{modelo.pk}",
            detalhes={"criado": criando},
        )
        return Response(self._saida(modelo), status=status.HTTP_201_CREATED if criando else 200)

    def create(self, request):
        """Cria um modelo (ativo precisa estar completo e gerar um rascunho válido hoje)."""
        entrada = s.ModeloEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        modelo = ModeloNfse(criado_por_id=request.user.pk, criado_por_email=request.user.email)
        return self._salvar(request, modelo, entrada.validated_data, criando=True)

    def partial_update(self, request, pk=None):
        """Altera o modelo. Vale para os próximos rascunhos; os já criados não mudam."""
        entrada = s.ModeloEntrada(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        return self._salvar(request, self.get_object(), entrada.validated_data, criando=False)

    @action(detail=True, methods=["post"])
    def previa(self, request, pk=None):
        """Mostra como ficaria um rascunho gerado hoje com este modelo (sem gravar)."""
        modelo, hoje = self.get_object(), timezone.localdate()
        try:
            preparo = servico_nfse.preparar(
                modelos.dados_do_rascunho(modelo, data_execucao=hoje), hoje=hoje
            )
        except ErroDeNota as erro:
            return Response({"ok": False, "erros": erro.erros})
        return Response(
            {
                "ok": True,
                "competencia": preparo.competencia,
                "tomador": preparo.pessoa.nome,
                "totais": preparo.totais,
                "avisos": preparo.avisos,
                "informacoes_complementares": preparo.complementos["informacoes_complementares"],
            }
        )

    @action(detail=True, methods=["post"], url_path="gerar-rascunho")
    def gerar_rascunho(self, request, pk=None):
        """Cria agora um rascunho a partir do modelo (cópia dos dados). Não emite nada."""
        modelo = self.get_object()
        try:
            nfse = modelos.gerar_rascunho(
                modelo, usuario=request.user, data_execucao=timezone.localdate()
            )
        except ErroDeNota as erro:
            return _erro(
                "modelo_invalido",
                "O modelo não pôde gerar o rascunho. Corrija o que está apontado.",
                status.HTTP_400_BAD_REQUEST,
                erros=erro.erros,
            )
        auditoria.registrar(
            LogAuditoria.Acao.NFSE_RASCUNHO_CRIADO,
            request=request,
            alvo=f"nfse:{nfse.pk}",
            detalhes={"modelo": modelo.pk},
        )
        return Response({"id": nfse.pk}, status=status.HTTP_201_CREATED)


# --- Agendamentos ----------------------------------------------------------------------------


def _regra_da_entrada(dados):
    return recorrencia.Regra(
        frequencia=dados["frequencia"],
        hora=dados["hora"],
        data_inicio=dados["data_inicio"],
        intervalo=dados.get("intervalo", 1),
        dias_semana=tuple(dados.get("dias_semana", ())),
        dia_do_mes=dados.get("dia_do_mes"),
        mes=dados.get("mes"),
        data_fim=dados.get("data_fim"),
        max_execucoes=dados.get("max_execucoes"),
    )


class AgendamentoViewSet(viewsets.GenericViewSet):
    """Agendamentos da empresa (cada um gera rascunhos a partir de um modelo)."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "agendamento.consultar",
        "retrieve": "agendamento.consultar",
        "previa_datas": "agendamento.consultar",
        "create": "agendamento.editar",
        "partial_update": "agendamento.editar",
        "suspender": "agendamento.editar",
        "reativar": "agendamento.editar",
    }
    pagination_class = None

    def get_queryset(self):
        """Agendamentos da empresa ativa."""
        return Agendamento.objects.select_related("modelo")

    def _saida(self, agendamento):
        proximas = []
        if agendamento.situacao == Agendamento.Situacao.ATIVO and agendamento.proxima_execucao:
            proximas = agenda.previa_de_datas(
                agenda.regra_do(agendamento),
                executadas=agendamento.execucoes_realizadas,
                agora=agendamento.proxima_execucao - dt.timedelta(seconds=1),
                quantidade=PREVIA_PADRAO,
            )
        return s.agendamento_saida(agendamento, proximas=proximas)

    def list(self, request):
        """Todos os agendamentos, com as próximas datas dos ativos."""
        return Response([self._saida(a) for a in self.get_queryset()[:LIMITE_DAS_LISTAS]])

    def retrieve(self, request, pk=None):
        """Um agendamento."""
        return Response(self._saida(self.get_object()))

    def _salvar(self, request, agendamento, dados):
        modelo = responsavel = None
        erros = {}
        if "modelo" in dados:
            modelo = ModeloNfse.objects.filter(pk=dados.pop("modelo")).first()
            if modelo is None:
                erros["modelo"] = "Modelo não encontrado."
        if "responsavel" in dados:
            responsavel = get_user_model().objects.filter(pk=dados.pop("responsavel")).first()
            if responsavel is None:
                erros["responsavel"] = "Responsável não encontrado."
        if agendamento is None:
            faltando = {
                campo: "Campo obrigatório."
                for campo in ("nome", "frequencia", "hora", "data_inicio")
                if campo not in dados
            }
            if modelo is None and "modelo" not in erros:
                faltando["modelo"] = "Escolha o modelo."
            if responsavel is None and "responsavel" not in erros:
                faltando["responsavel"] = "Escolha o responsável."
            erros.update(faltando)
        if erros:
            return Response(erros, status=status.HTTP_400_BAD_REQUEST)
        try:
            salvo = agenda.salvar(
                dados,
                agendamento=agendamento,
                modelo=modelo,
                responsavel=responsavel,
                usuario=request.user,
                empresa=request.empresa,
                agora=timezone.now(),
                request=request,
            )
        except agenda.ErroDeAgendamento as erro:
            return Response(erro.erros, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._saida(salvo), status=201 if agendamento is None else 200)

    def create(self, request):
        """Cria o agendamento e calcula a próxima execução."""
        entrada = s.AgendamentoEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        return self._salvar(request, None, dict(entrada.validated_data))

    def partial_update(self, request, pk=None):
        """Altera o agendamento; mudar a regra recalcula a próxima data a partir de agora."""
        entrada = s.AgendamentoEntrada(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        return self._salvar(request, self.get_object(), dict(entrada.validated_data))

    @action(detail=True, methods=["post"])
    def suspender(self, request, pk=None):
        """Suspende: nenhuma data é gerada até reativar."""
        try:
            agendamento = agenda.suspender(
                self.get_object(),
                motivo=str(request.data.get("motivo", "")).strip(),
                usuario=request.user,
                empresa=request.empresa,
                request=request,
            )
        except agenda.ErroDeAgendamento as erro:
            return Response(erro.erros, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._saida(agendamento))

    @action(detail=True, methods=["post"])
    def reativar(self, request, pk=None):
        """Reativa um agendamento suspenso. Só vale a próxima data futura (nada retroativo)."""
        try:
            agendamento = agenda.reativar(
                self.get_object(),
                usuario=request.user,
                empresa=request.empresa,
                agora=timezone.now(),
                request=request,
            )
        except agenda.ErroDeAgendamento as erro:
            return Response(erro.erros, status=status.HTTP_400_BAD_REQUEST)
        return Response(self._saida(agendamento))

    @action(detail=False, methods=["post"], url_path="previa-datas")
    def previa_datas(self, request):
        """Próximas datas de uma regra, antes de salvar (e os erros da regra, se houver)."""
        entrada = s.PreviaDeDatasEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = dict(entrada.validated_data)
        faltando = {
            c: "Campo obrigatório." for c in ("frequencia", "hora", "data_inicio") if c not in dados
        }
        if faltando:
            return Response(faltando, status=status.HTTP_400_BAD_REQUEST)
        regra = _regra_da_entrada(dados)
        erros = recorrencia.validar(regra)
        if erros:
            return Response(erros, status=status.HTTP_400_BAD_REQUEST)
        existente = Agendamento.objects.filter(pk=dados.get("agendamento")).first()
        executadas = existente.execucoes_realizadas if existente else 0
        instantes = agenda.previa_de_datas(
            regra, executadas=executadas, agora=timezone.now(), quantidade=dados["quantidade"]
        )
        return Response(
            {
                "datas": [s.instante_saida(i) for i in instantes],
                "termina": len(instantes) < dados["quantidade"],
            }
        )


class ExecucaoViewSet(viewsets.GenericViewSet):
    """Histórico de execuções dos agendamentos."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"list": "agendamento.consultar"}
    serializer_class = s.ExecucaoSerializer
    pagination_class = None

    def list(self, request):
        """Execuções mais recentes, com filtros por agendamento e situação."""
        consulta = ExecucaoAgendamento.objects.select_related("agendamento", "nfse")
        if agendamento := request.query_params.get("agendamento"):
            consulta = consulta.filter(agendamento_id=agendamento if agendamento.isdigit() else 0)
        if situacao := request.query_params.get("situacao"):
            consulta = consulta.filter(situacao=situacao)
        return Response(s.ExecucaoSerializer(consulta[:LIMITE_DAS_LISTAS], many=True).data)


class OpcoesView(APIView):
    """Listas que os formulários precisam: frequências, modelos ativos, responsáveis possíveis."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"get": "agendamento.consultar"}

    def get(self, request):
        """Opções; os responsáveis só vão para quem pode editar agendamentos."""
        responsaveis = []
        if "agendamento.editar" in request.permissoes:
            vinculos = VinculoUsuarioEmpresa.objects.filter(
                empresa=request.empresa, ativo=True, usuario__is_active=True
            ).select_related("usuario")
            responsaveis = [
                {"id": v.usuario_id, "email": v.usuario.email, "nome": v.usuario.nome}
                for v in vinculos
                if "nfse.emitir" in v.permissoes_efetivas()
            ]
        return Response(
            {
                "frequencias": [
                    {"valor": v, "rotulo": r} for v, r in Agendamento.Frequencia.choices
                ],
                "competencias": [
                    {"valor": v, "rotulo": r} for v, r in ModeloNfse.Competencia.choices
                ],
                "variaveis_do_texto": s.variaveis_do_texto(),
                "modelos": [
                    {"id": m.pk, "nome": m.nome} for m in ModeloNfse.objects.filter(ativo=True)
                ],
                "responsaveis": responsaveis,
                "tolerancia_horas": agenda.tolerancia().total_seconds() // 3600,
            }
        )


# --- Rascunhos -------------------------------------------------------------------------------


class EntradaDeAprovacao(serializers.Serializer):
    """Corpo da aprovação em lote."""

    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)


class EntradaDeDescarte(serializers.Serializer):
    """Corpo do descarte."""

    motivo = serializers.CharField(allow_blank=True)


def _origem_do_rascunho(nfse):
    origem = getattr(nfse, "origem", None)
    if origem is None:
        return {"tipo": "manual", "nome": "", "data_execucao": None}
    if origem.execucao_id:
        execucao = origem.execucao
        return {
            "tipo": "agendamento",
            "nome": execucao.agendamento.nome,
            "agendamento": execucao.agendamento_id,
            "data_execucao": execucao.data_execucao,
        }
    return {"tipo": "modelo", "nome": origem.modelo_nome, "data_execucao": None}


class RascunhoViewSet(viewsets.GenericViewSet):
    """Rascunhos de NFS-e esperando decisão: aprovar (individual ou em lote) ou descartar."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "nfse.consultar",
        "situacao": "nfse.consultar",
        "aprovar": "nfse.emitir",
        "descartar": "nfse.emitir",
    }
    pagination_class = None

    def get_queryset(self):
        """Rascunhos da empresa ativa."""
        return Nfse.objects.filter(situacao=Nfse.Situacao.RASCUNHO).select_related(
            "origem__execucao__agendamento"
        )

    def list(self, request):
        """Rascunhos pendentes (mais antigos primeiro), de onde vieram e o total."""
        consulta = self.get_queryset().order_by("criado_em", "id")
        if agendamento := request.query_params.get("agendamento"):
            consulta = consulta.filter(
                origem__execucao__agendamento_id=agendamento if agendamento.isdigit() else 0
            )
        total = consulta.count()
        linhas = [
            {
                "id": n.pk,
                "tomador_nome": n.tomador_nome,
                "valor_servico": n.valor_servico,
                "competencia": n.competencia,
                "criado_em": n.criado_em,
                "criado_por_email": n.criado_por_email,
                "origem": _origem_do_rascunho(n),
            }
            for n in consulta[:LIMITE_DAS_LISTAS]
        ]
        return Response({"total": total, "itens": linhas})

    @action(detail=False, methods=["post"])
    def aprovar(self, request):
        """Pede a emissão de cada rascunho, pelo fluxo da Fase 3; devolve o resultado por item."""
        entrada = EntradaDeAprovacao(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultados = rascunhos.aprovar_em_lote(
                entrada.validated_data["ids"],
                usuario=request.user,
                empresa=request.empresa,
                permissoes=request.permissoes,
                request=request,
            )
        except rascunhos.ErroDeRascunho as erro:
            return Response(erro.erros, status=status.HTTP_400_BAD_REQUEST)
        schema = request.empresa.schema_name
        for resultado in resultados:
            if resultado["ok"]:
                nfse_id = resultado["id"]
                transaction.on_commit(
                    lambda i=nfse_id: tarefas_fiscais.emitir_nfse.delay(schema, i)
                )
        aceitas = sum(r["ok"] for r in resultados)
        return Response(
            {"resultados": resultados, "aceitas": aceitas, "recusadas": len(resultados) - aceitas}
        )

    @action(detail=True, methods=["post"])
    def descartar(self, request, pk=None):
        """Descarta um rascunho, com motivo (situação final; nada é enviado à Sefin)."""
        entrada = EntradaDeDescarte(data=request.data)
        entrada.is_valid(raise_exception=True)
        nfse = self.get_object()
        try:
            rascunhos.descartar(
                nfse,
                motivo=entrada.validated_data["motivo"],
                usuario=request.user,
                empresa=request.empresa,
                request=request,
            )
        except rascunhos.ErroDeRascunho as erro:
            return Response(erro.erros, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": nfse.pk, "situacao": nfse.situacao})

    @action(detail=False, methods=["get"])
    def situacao(self, request):
        """Situação atual das notas informadas (`?ids=1,2`), para acompanhar o lote aprovado."""
        ids = [
            int(i) for i in request.query_params.get("ids", "").split(",") if i.strip().isdigit()
        ]
        notas = Nfse.objects.filter(pk__in=ids[: rascunhos.LIMITE_DO_LOTE])
        return Response(
            [
                {
                    "id": n.pk,
                    "situacao": n.situacao,
                    "situacao_rotulo": n.get_situacao_display(),
                    "numero_nfse": n.numero_nfse,
                    "mensagem": n.mensagem,
                }
                for n in notas
            ]
        )
