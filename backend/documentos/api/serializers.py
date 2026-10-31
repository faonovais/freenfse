"""Entrada e saída da API de documentos.

**Nenhuma saída contém credencial**: só se diz se ela existe.
"""

from django.core.exceptions import ValidationError as ErroDjango
from django.core.validators import validate_email
from rest_framework import serializers

from documentos.models import (
    ArquivoDrive,
    ConfiguracaoEmail,
    EnvioEmail,
    Exportacao,
)
from documentos.services import envio_email
from documentos.services.credenciais import CredencialInvalida, ler_conta_de_servico

CAMPOS_SECRETOS_EMAIL = ("smtp_senha", "graph_client_secret", "gmail_conta_servico")
P = ConfiguracaoEmail.Provedor


def _lista_de_emails(valor, campo):
    limpos = []
    for item in valor or []:
        email = str(item).strip().lower()
        try:
            validate_email(email)
        except ErroDjango:
            raise serializers.ValidationError({campo: f"E-mail inválido: {item}."}) from None
        if email not in limpos:
            limpos.append(email)
    return limpos


class ConfigEmailEntrada(serializers.Serializer):
    """Corpo de `PUT /config/email/`. Credencial ausente/vazia = manter; `null` = apagar."""

    provedor = serializers.ChoiceField(choices=P.choices)
    remetente_email = serializers.EmailField(required=False, allow_blank=True)
    remetente_nome = serializers.CharField(required=False, allow_blank=True, max_length=100)
    smtp_host = serializers.CharField(required=False, allow_blank=True, max_length=255)
    smtp_porta = serializers.IntegerField(required=False, min_value=1, max_value=65535)
    smtp_seguranca = serializers.ChoiceField(
        choices=ConfiguracaoEmail.Seguranca.choices, required=False
    )
    smtp_usuario = serializers.CharField(required=False, allow_blank=True, max_length=255)
    smtp_senha = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, trim_whitespace=False
    )
    graph_tenant_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    graph_client_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    graph_client_secret = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    gmail_conta_servico = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    envio_automatico = serializers.BooleanField(required=False)
    avisar_cancelamento = serializers.BooleanField(required=False)
    anexar_pdf = serializers.BooleanField(required=False)
    anexar_xml = serializers.BooleanField(required=False)
    copias_fixas = serializers.ListField(child=serializers.CharField(), required=False)
    emails_alerta = serializers.ListField(child=serializers.CharField(), required=False)
    assunto_modelo = serializers.CharField(required=False, max_length=200)
    corpo_modelo = serializers.CharField(required=False, allow_blank=True)

    def validate(self, dados):
        """Confere modelos, listas de e-mail e o que cada provedor exige."""
        atual = ConfiguracaoEmail.obter()
        erros = envio_email.validar_modelos(
            dados.get("assunto_modelo", atual.assunto_modelo),
            dados.get("corpo_modelo", atual.corpo_modelo),
        )
        for campo in ("copias_fixas", "emails_alerta"):
            if campo in dados:
                try:
                    dados[campo] = _lista_de_emails(dados[campo], campo)
                except serializers.ValidationError as erro:
                    erros.update({k: str(v[0]) for k, v in erro.detail.items()})
        provedor = dados["provedor"]
        remetente = dados.get("remetente_email", atual.remetente_email)
        if provedor != P.NENHUM and not remetente:
            erros["remetente_email"] = "Informe o e-mail do remetente."

        def tem(campo):
            return (campo in dados and dados[campo]) or (
                campo not in dados and getattr(atual, campo)
            )

        if provedor == P.SMTP and not tem("smtp_host"):
            erros["smtp_host"] = "Informe o servidor SMTP."
        if provedor == P.GRAPH:
            for campo, texto in (
                ("graph_tenant_id", "Informe o ID do tenant da Microsoft."),
                ("graph_client_id", "Informe o ID do aplicativo."),
                ("graph_client_secret", "Informe o segredo do aplicativo."),
            ):
                if not tem(campo):
                    erros[campo] = texto
        if provedor == P.GMAIL:
            if not tem("gmail_conta_servico"):
                erros["gmail_conta_servico"] = "Envie a chave JSON da conta de serviço do Google."
            elif dados.get("gmail_conta_servico"):
                try:
                    ler_conta_de_servico(dados["gmail_conta_servico"])
                except CredencialInvalida as erro:
                    erros["gmail_conta_servico"] = str(erro)
        if erros:
            raise serializers.ValidationError(erros)
        return dados


def config_email_saida(configuracao):
    """Configuração de e-mail **sem credenciais** (só diz se cada uma está configurada)."""
    return {
        "provedor": configuracao.provedor,
        "remetente_email": configuracao.remetente_email,
        "remetente_nome": configuracao.remetente_nome,
        "smtp_host": configuracao.smtp_host,
        "smtp_porta": configuracao.smtp_porta,
        "smtp_seguranca": configuracao.smtp_seguranca,
        "smtp_usuario": configuracao.smtp_usuario,
        "graph_tenant_id": configuracao.graph_tenant_id,
        "graph_client_id": configuracao.graph_client_id,
        "credenciais_configuradas": {
            campo: bool(getattr(configuracao, campo)) for campo in CAMPOS_SECRETOS_EMAIL
        },
        "envio_automatico": configuracao.envio_automatico,
        "avisar_cancelamento": configuracao.avisar_cancelamento,
        "anexar_pdf": configuracao.anexar_pdf,
        "anexar_xml": configuracao.anexar_xml,
        "copias_fixas": configuracao.copias_fixas,
        "emails_alerta": configuracao.emails_alerta,
        "assunto_modelo": configuracao.assunto_modelo,
        "corpo_modelo": configuracao.corpo_modelo,
        "variaveis": envio_email.variaveis_disponiveis(),
        "opcoes": {
            "provedores": [{"valor": v, "rotulo": r} for v, r in P.choices],
            "seguranca": [
                {"valor": v, "rotulo": r} for v, r in ConfiguracaoEmail.Seguranca.choices
            ],
        },
    }


def config_drive_saida(configuracao):
    """Configuração do Drive **sem a credencial** (só o e-mail da conta de serviço)."""
    from documentos.services.drive import caminhos

    return {
        "ativo": configuracao.ativo,
        "conta_servico_configurada": bool(configuracao.conta_servico),
        "conta_servico_email": configuracao.conta_servico_email,
        "pasta_raiz_id": configuracao.pasta_raiz_id,
        "pasta_raiz_nome": configuracao.pasta_raiz_nome,
        "modelo_subpastas": configuracao.modelo_subpastas,
        "modelo_arquivo": configuracao.modelo_arquivo,
        "enviar_automaticamente": configuracao.enviar_automaticamente,
        "validado_em": configuracao.validado_em,
        "variaveis": caminhos.VARIAVEIS,
    }


class EnvioEmailSerializer(serializers.ModelSerializer):
    """Linha do histórico de e-mails da nota."""

    tipo_rotulo = serializers.CharField(source="get_tipo_display", read_only=True)
    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)

    class Meta:
        model = EnvioEmail
        fields = [
            "id", "tipo", "tipo_rotulo", "situacao", "situacao_rotulo", "destinatarios", "copias",
            "assunto", "anexos", "tentativas", "proxima_tentativa", "erro", "enviado_em",
            "criado_em", "criado_por_email",
        ]  # fmt: skip


class ArquivoDriveSerializer(serializers.ModelSerializer):
    """Linha da situação da cópia ao Drive."""

    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)

    class Meta:
        model = ArquivoDrive
        fields = [
            "id", "papel", "situacao", "situacao_rotulo", "caminho", "nome", "tentativas",
            "proxima_tentativa", "erro", "aviso", "enviado_em",
        ]  # fmt: skip


class ExportacaoSerializer(serializers.ModelSerializer):
    """Pedido de download em lote, com progresso."""

    situacao_rotulo = serializers.CharField(source="get_situacao_display", read_only=True)

    class Meta:
        model = Exportacao
        fields = [
            "id", "situacao", "situacao_rotulo", "filtros", "total", "processadas", "tamanho_bytes",
            "nome_download", "erro", "avisos", "criado_em", "concluido_em", "expira_em",
        ]  # fmt: skip


class EntradaDeExportacao(serializers.Serializer):
    """Filtros do download em lote."""

    periodo_inicio = serializers.DateField(required=False)
    periodo_fim = serializers.DateField(required=False)
    competencia = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", required=False)
    situacao = serializers.ListField(child=serializers.CharField(), required=False)
    tomador = serializers.CharField(required=False, allow_blank=True, max_length=300)

    def validate(self, dados):
        """Datas viram texto ISO (o filtro vai para o JSON do pedido)."""
        return {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in dados.items()}


class EntradaDeDestinatarios(serializers.Serializer):
    """Envio manual: destinatários opcionais (sem eles, valem os e-mails do tomador)."""

    destinatarios = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_destinatarios(self, valor):
        """Valida os e-mails informados."""
        return _lista_de_emails(valor, "destinatarios") if valor else []


class EntradaDeTeste(serializers.Serializer):
    """Destino do e-mail de teste."""

    destino = serializers.EmailField()
