"""API de documentos (`/api/documentos/`).

Configuração de e-mail e Drive, envios por nota e download em lote.

Todas as rotas são de empresa (exigem `X-Empresa`) e usam `PermissaoPorOperacao`, que falha fechada.
Credenciais entram, mas nunca saem: as respostas só dizem se existem.
"""

from django.db import transaction
from django.http import FileResponse
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.permissions import PermissaoPorOperacao
from core.models import LogAuditoria
from core.services import auditoria
from documentos import tasks
from documentos.api import serializers as s
from documentos.models import ConfiguracaoDrive, ConfiguracaoEmail, EnvioEmail, Exportacao
from documentos.services import contexto, envio_email, exportacao
from documentos.services.drive import caminhos
from documentos.services.drive import envio as envio_drive
from fiscal.models import Nfse

T = EnvioEmail.Tipo
NOTA_EMITIDA = (Nfse.Situacao.AUTORIZADA, Nfse.Situacao.CANCELADA, Nfse.Situacao.SUBSTITUIDA)


def _erro(codigo, detalhe, http=status.HTTP_409_CONFLICT):
    return Response({"codigo": codigo, "detalhe": detalhe}, status=http)


def _nota_emitida(pk):
    """Devolva a nota emitida (com XML) ou `None`."""
    return Nfse.objects.filter(pk=pk, situacao__in=NOTA_EMITIDA).first()


# --- Configuração de e-mail ----------------------------------------------------------------


class ConfigEmailView(APIView):
    """Configuração de e-mail da empresa (consulta e alteração)."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"get": "config.consultar", "put": "config.editar"}

    def get(self, request):
        """Devolve a configuração, sem credenciais."""
        return Response(s.config_email_saida(ConfiguracaoEmail.obter()))

    def put(self, request):
        """Valida e grava. Credencial ausente ou vazia é mantida; `null` apaga."""
        entrada = s.ConfigEmailEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        configuracao = ConfiguracaoEmail.obter()
        alterados = []
        for campo, valor in entrada.validated_data.items():
            if campo in s.CAMPOS_SECRETOS_EMAIL:
                if valor == "" or valor == getattr(configuracao, campo, None):
                    continue
            elif getattr(configuracao, campo) == valor:
                continue
            setattr(configuracao, campo, valor)
            alterados.append(campo)
        configuracao.save()
        auditoria.registrar(
            LogAuditoria.Acao.EMAIL_CONFIG_ALTERADA,
            request=request,
            alvo="email",
            detalhes={"campos": sorted(alterados)},  # só os nomes: nunca os valores
        )
        return Response(s.config_email_saida(configuracao))


class TesteEmailView(APIView):
    """Envia um e-mail de teste com a configuração salva."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "config.editar"}

    def post(self, request):
        """Envia na hora e devolve o resultado em linguagem simples."""
        entrada = s.EntradaDeTeste(data=request.data)
        entrada.is_valid(raise_exception=True)
        envio = envio_email.enviar_teste(entrada.validated_data["destino"], usuario=request.user)
        return Response(s.EnvioEmailSerializer(envio).data)


# --- Configuração do Drive -----------------------------------------------------------------


class EntradaDrive(serializers.Serializer):
    """Corpo de `PUT /config/drive/`. Credencial vazia/ausente = manter."""

    ativo = serializers.BooleanField(required=False)
    conta_servico = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    pasta_raiz_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    modelo_subpastas = serializers.CharField(required=False, allow_blank=True, max_length=300)
    modelo_arquivo = serializers.CharField(required=False, allow_blank=True, max_length=200)
    enviar_automaticamente = serializers.BooleanField(required=False)


class ConfigDriveView(APIView):
    """Configuração do Google Drive da empresa."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"get": "config.consultar", "put": "config.editar"}

    def get(self, request):
        """Devolve a configuração, sem a credencial."""
        return Response(s.config_drive_saida(ConfiguracaoDrive.obter()))

    def put(self, request):
        """Valida modelos, credencial e acesso à pasta raiz; grava se tudo estiver certo."""
        entrada = EntradaDrive(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            configuracao = envio_drive.salvar_configuracao(
                dados=entrada.validated_data, usuario=request.user, request=request
            )
        except envio_drive.ErroDeConfiguracaoDrive as erro:
            return Response(erro.erros, status=status.HTTP_400_BAD_REQUEST)
        return Response(s.config_drive_saida(configuracao))


class PreviaDriveView(APIView):
    """Valida os modelos de caminho e mostra como uma nota real ficaria no Drive."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "config.consultar"}

    def post(self, request):
        """Todos os erros dos modelos, ou a pré-visualização com uma nota real."""
        atual = ConfiguracaoDrive.obter()
        subpastas = request.data.get("modelo_subpastas", atual.modelo_subpastas)
        arquivo = request.data.get("modelo_arquivo", atual.modelo_arquivo)
        erros = caminhos.validar(subpastas, arquivo)
        if erros:
            return Response(erros, status=status.HTTP_400_BAD_REQUEST)
        nota = Nfse.objects.filter(
            situacao__in=NOTA_EMITIDA, pk=request.data.get("nota") or None
        ).first() or (
            Nfse.objects.filter(situacao__in=NOTA_EMITIDA, emitida_em__isnull=False)
            .order_by("-emitida_em")
            .first()
        )
        if nota is None:
            return Response(
                {"previa": None, "detalhe": "Ainda não há nota emitida para servir de exemplo."}
            )
        modelo = ConfiguracaoDrive(modelo_subpastas=subpastas, modelo_arquivo=arquivo)
        return Response(
            {
                "previa": caminhos.pre_visualizar(modelo, nota, contexto.empresa_atual()),
                "nota": nota.pk,
                "numero_nfse": nota.numero_nfse,
            }
        )


# --- Envios por nota -----------------------------------------------------------------------


class EnviosDaNotaView(APIView):
    """Histórico de e-mails e situação da cópia ao Drive de uma nota."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"get": "documentos.consultar"}

    def get(self, request, pk):
        """E-mails (com resultado e erro didático), arquivos no Drive e destinatários padrão."""
        nota = Nfse.objects.filter(pk=pk).first()
        if nota is None:
            return _erro("nao_encontrada", "Nota não encontrada.", status.HTTP_404_NOT_FOUND)
        configuracao = ConfiguracaoEmail.obter()
        return Response(
            {
                "emails": s.EnvioEmailSerializer(nota.envios_email.all(), many=True).data,
                "drive": s.ArquivoDriveSerializer(nota.arquivos_drive.all(), many=True).data,
                "destinatarios_padrao": envio_email.destinatarios_da_nota(nota),
                "email_configurado": configuracao.provedor != ConfiguracaoEmail.Provedor.NENHUM,
                "drive_ativo": ConfiguracaoDrive.obter().ativo,
            }
        )


class EmailDaNotaView(APIView):
    """Envio manual da nota por e-mail."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "documentos.enviar"}

    def post(self, request, pk):
        """Coloca o envio na fila (destinatários padrão ou os informados)."""
        nota = _nota_emitida(pk)
        if nota is None:
            return _erro("nota_nao_emitida", "Só uma nota emitida pode ser enviada por e-mail.")
        entrada = s.EntradaDeDestinatarios(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            envio = envio_email.solicitar(
                nota,
                T.MANUAL,
                usuario=request.user,
                destinatarios=entrada.validated_data.get("destinatarios") or None,
            )
        except envio_email.ErroDeEmail as erro:
            return _erro("email_recusado", str(erro))
        schema = request.empresa.schema_name
        transaction.on_commit(lambda: tasks.processar_envio_email.delay(schema, envio.pk))
        return Response(s.EnvioEmailSerializer(envio).data, status=status.HTTP_202_ACCEPTED)


class ReenviarEmailView(APIView):
    """Reenvio manual de um e-mail já registrado."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "documentos.enviar"}

    def post(self, request, pk):
        """Cria um novo envio com os mesmos destinatários."""
        antigo = EnvioEmail.objects.filter(pk=pk, nfse__isnull=False).first()
        if antigo is None:
            return _erro("nao_encontrado", "Envio não encontrado.", status.HTTP_404_NOT_FOUND)
        try:
            novo = envio_email.reenviar(antigo, usuario=request.user)
        except envio_email.ErroDeEmail as erro:
            return _erro("email_recusado", str(erro))
        schema = request.empresa.schema_name
        transaction.on_commit(lambda: tasks.processar_envio_email.delay(schema, novo.pk))
        return Response(s.EnvioEmailSerializer(novo).data, status=status.HTTP_202_ACCEPTED)


class ReenviarDriveNotaView(APIView):
    """Reenvio da cópia de uma nota ao Drive."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "documentos.enviar"}

    def post(self, request, pk):
        """Enfileira a cópia da nota com o modelo vigente."""
        nota = _nota_emitida(pk)
        if nota is None:
            return _erro("nota_nao_emitida", "Só uma nota emitida pode ser copiada ao Drive.")
        if not ConfiguracaoDrive.obter().ativo:
            return _erro(
                "drive_desligado", "A cópia ao Google Drive não está ativa (Configuração › Drive)."
            )
        auditoria.registrar(
            LogAuditoria.Acao.DRIVE_REENVIADO, request=request, alvo=f"nfse:{nota.pk}"
        )
        schema = request.empresa.schema_name
        transaction.on_commit(lambda: tasks.enviar_nota_ao_drive.delay(schema, nota.pk, True))
        return Response({"enfileirada": True}, status=status.HTTP_202_ACCEPTED)


class ReenviarDrivePeriodoView(APIView):
    """Reenvio da cópia ao Drive de todas as notas de um período."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {"post": "documentos.enviar"}

    def post(self, request):
        """Enfileira a cópia de todas as notas emitidas no período (data de emissão)."""
        entrada = s.EntradaDeExportacao(data=request.data)
        entrada.is_valid(raise_exception=True)
        if not ConfiguracaoDrive.obter().ativo:
            return _erro(
                "drive_desligado", "A cópia ao Google Drive não está ativa (Configuração › Drive)."
            )
        filtros = entrada.validated_data
        notas = list(
            envio_drive.notas_do_periodo(
                filtros.get("periodo_inicio"), filtros.get("periodo_fim")
            ).values_list("pk", flat=True)[: exportacao.limite_de_notas() + 1]
        )
        if len(notas) > exportacao.limite_de_notas():
            return _erro(
                "periodo_grande",
                f"O período tem mais de {exportacao.limite_de_notas()} notas. Reduza o período.",
            )
        schema = request.empresa.schema_name
        for nota_id in notas:
            transaction.on_commit(
                lambda i=nota_id: tasks.enviar_nota_ao_drive.delay(schema, i, True)
            )
        auditoria.registrar(
            LogAuditoria.Acao.DRIVE_REENVIADO,
            request=request,
            alvo="periodo",
            detalhes={"notas": len(notas)},
        )
        return Response({"enfileiradas": len(notas)}, status=status.HTTP_202_ACCEPTED)


# --- Download em lote ----------------------------------------------------------------------


class ExportacaoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Downloads em lote do usuário na empresa ativa. Cada pessoa só enxerga os seus."""

    permission_classes = [PermissaoPorOperacao]
    permissao_requerida = {
        "list": "documentos.exportar",
        "retrieve": "documentos.exportar",
        "create": "documentos.exportar",
        "download": "documentos.exportar",
    }
    serializer_class = s.ExportacaoSerializer
    pagination_class = None

    def get_queryset(self):
        """Só os pedidos do próprio usuário (mesmo o Administrador não vê os dos outros)."""
        return Exportacao.objects.filter(solicitante_id=self.request.user.pk)

    def create(self, request):
        """Valida os filtros e limites, grava o pedido e enfileira a geração (202)."""
        entrada = s.EntradaDeExportacao(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            pedido = exportacao.solicitar(
                entrada.validated_data, usuario=request.user, request=request
            )
        except exportacao.ErroDeExportacao as erro:
            return _erro("lote_recusado", str(erro), status.HTTP_400_BAD_REQUEST)
        schema = request.empresa.schema_name
        transaction.on_commit(lambda: tasks.gerar_exportacao.delay(schema, pedido.pk))
        return Response(s.ExportacaoSerializer(pedido).data, status=status.HTTP_202_ACCEPTED)

    def download(self, request, pk=None):
        """Entrega o ZIP, só a quem pediu e enquanto não expira."""
        pedido = self.get_object()
        try:
            caminho = exportacao.abrir_para_download(pedido, request.user, request=request)
        except exportacao.ErroDeExportacao as erro:
            return _erro("download_indisponivel", str(erro))
        return FileResponse(
            caminho.open("rb"),
            as_attachment=True,
            filename=pedido.nome_download or caminho.name,
            content_type="application/zip",
        )
