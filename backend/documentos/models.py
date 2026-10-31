"""Documentos da empresa (no schema de cada empresa): e-mail, Google Drive e download em lote.

As credenciais (senha SMTP, segredo do Microsoft Graph, JSON da conta de serviço do Google) ficam
em campos criptografados (`core.fields`): um *dump* do banco não as expõe, e nenhuma API as devolve.
"""

from django.db import models

from core.fields import CampoTextoCriptografado


class _UnicoPorEmpresa(models.Model):
    """Base de modelos com uma única linha por empresa (o schema já isola as empresas)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Fixa a chave primária em 1: só existe uma linha por schema."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def obter(cls):
        """Devolve a configuração da empresa, criando-a com os padrões na primeira vez."""
        return cls.objects.get_or_create(pk=1)[0]


# --- E-mail -------------------------------------------------------------------------------


class ConfiguracaoEmail(_UnicoPorEmpresa):
    """Como a empresa envia e-mail: provedor, credenciais, quando enviar e modelo da mensagem."""

    class Provedor(models.TextChoices):
        """Provedor de envio (interface comum em `documentos.services.email`)."""

        NENHUM = "nenhum", "Nenhum (e-mail desligado)"
        SMTP = "smtp", "SMTP"
        GMAIL = "gmail", "Gmail (API, conta de serviço)"
        GRAPH = "graph", "Microsoft 365 (Graph, aplicativo)"

    class Seguranca(models.TextChoices):
        """Proteção da conexão SMTP."""

        STARTTLS = "starttls", "STARTTLS (porta 587)"
        SSL = "ssl", "SSL/TLS direto (porta 465)"
        NENHUMA = "nenhuma", "Sem criptografia (não recomendado)"

    provedor = models.CharField(max_length=10, choices=Provedor, default=Provedor.NENHUM)
    remetente_email = models.EmailField("e-mail do remetente", blank=True)
    remetente_nome = models.CharField("nome do remetente", max_length=100, blank=True)

    # SMTP
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_porta = models.PositiveIntegerField(default=587)
    smtp_seguranca = models.CharField(max_length=10, choices=Seguranca, default=Seguranca.STARTTLS)
    smtp_usuario = models.CharField(max_length=255, blank=True)
    smtp_senha = CampoTextoCriptografado(null=True, blank=True)  # noqa: DJ001

    # Microsoft Graph (aplicativo, sem usuário: fluxo client credentials)
    graph_tenant_id = models.CharField(max_length=64, blank=True)
    graph_client_id = models.CharField(max_length=64, blank=True)
    graph_client_secret = CampoTextoCriptografado(null=True, blank=True)  # noqa: DJ001

    # Gmail (conta de serviço com delegação em todo o domínio; o remetente é o usuário delegado)
    gmail_conta_servico = CampoTextoCriptografado(null=True, blank=True)  # noqa: DJ001

    # Quando enviar e o que anexar
    envio_automatico = models.BooleanField(
        "enviar ao autorizar", default=False, help_text="Desligado: o envio é manual."
    )
    avisar_cancelamento = models.BooleanField("avisar o cliente ao cancelar", default=False)
    anexar_pdf = models.BooleanField(default=True)
    anexar_xml = models.BooleanField(default=True)
    copias_fixas = models.JSONField("cópias fixas", default=list, blank=True)
    emails_alerta = models.JSONField(
        "e-mails dos alertas", default=list, blank=True,
        help_text="Quem recebe o alerta de vencimento do certificado (padrão: administradores).",
    )  # fmt: skip

    assunto_modelo = models.CharField(
        max_length=200, default="NFS-e nº {numero_nfse} de {nome_emitente}"
    )
    corpo_modelo = models.TextField(
        default=(
            "Olá, {nome_tomador}.\n\n"
            "Segue a NFS-e nº {numero_nfse}, de {nome_emitente}, referente a {competencia}, "
            "no valor de R$ {valor}.\n\n"
            "Chave de acesso: {chave}\n"
        )
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração de e-mail"
        verbose_name_plural = "configurações de e-mail"

    def __str__(self):
        return f"E-mail ({self.get_provedor_display()})"


class EnvioEmail(models.Model):
    """Registro de cada e-mail: para quem, quando, resultado e erro em linguagem simples."""

    class Tipo(models.TextChoices):
        """Motivo do envio."""

        AUTORIZACAO = "autorizacao", "Ao autorizar"
        CANCELAMENTO = "cancelamento", "Aviso de cancelamento"
        MANUAL = "manual", "Envio manual"
        REENVIO = "reenvio", "Reenvio"
        TESTE = "teste", "E-mail de teste"
        ALERTA_CERTIFICADO = "alerta_certificado", "Alerta de certificado"
        AVISO_AGENDAMENTO = "aviso_agendamento", "Aviso de agendamento"
        RASCUNHOS_PENDENTES = "rascunhos_pendentes", "Rascunhos pendentes"

    class Situacao(models.TextChoices):
        """Andamento do envio."""

        PENDENTE = "pendente", "Na fila"
        ENVIADO = "enviado", "Enviado"
        FALHOU = "falhou", "Falhou"

    nfse = models.ForeignKey(
        "fiscal.Nfse", null=True, blank=True, on_delete=models.PROTECT, related_name="envios_email"
    )
    tipo = models.CharField(max_length=20, choices=Tipo)
    situacao = models.CharField(max_length=10, choices=Situacao, default=Situacao.PENDENTE)
    provedor = models.CharField(max_length=10, blank=True)
    destinatarios = models.JSONField(default=list)
    copias = models.JSONField(default=list, blank=True)
    assunto = models.CharField(max_length=300, blank=True)
    anexos = models.JSONField(default=list, blank=True)
    tentativas = models.PositiveIntegerField(default=0)
    max_tentativas = models.PositiveIntegerField(default=5)
    proxima_tentativa = models.DateTimeField(null=True, blank=True, db_index=True)
    corpo_avulso = models.TextField(
        blank=True, help_text="Texto dos envios sem nota (alerta de certificado)."
    )
    erro = models.TextField(blank=True, help_text="Explicação em linguagem simples.")
    erro_tecnico = models.CharField(max_length=500, blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    chave_idempotencia = models.CharField(max_length=80, null=True, blank=True, unique=True)  # noqa: DJ001
    # O usuário vive no schema público: sem chave estrangeira entre schemas (GUIDELINES §1).
    criado_por_id = models.PositiveBigIntegerField(null=True, blank=True)
    criado_por_email = models.CharField(max_length=254, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "envio de e-mail"
        verbose_name_plural = "envios de e-mail"
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} ({self.situacao})"


# --- Google Drive -------------------------------------------------------------------------


class ConfiguracaoDrive(_UnicoPorEmpresa):
    """Cópia dos documentos no Google Drive: conta de serviço, pasta raiz e modelos de caminho."""

    ativo = models.BooleanField(default=False)
    conta_servico = CampoTextoCriptografado(null=True, blank=True)  # noqa: DJ001
    conta_servico_email = models.CharField(
        max_length=254, blank=True, help_text="E-mail da conta de serviço (não é segredo)."
    )
    pasta_raiz_id = models.CharField("ID da pasta raiz", max_length=100, blank=True)
    pasta_raiz_nome = models.CharField(max_length=255, blank=True)
    modelo_subpastas = models.CharField(max_length=300, default="{ano}/{mes}", blank=True)
    modelo_arquivo = models.CharField(
        max_length=200, default="NFSe {numero_nfse} - {chave}", blank=True
    )
    enviar_automaticamente = models.BooleanField(default=True)
    validado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do Google Drive"
        verbose_name_plural = "configurações do Google Drive"

    def __str__(self):
        return f"Drive ({'ativo' if self.ativo else 'desligado'})"


class PastaDrive(models.Model):
    """Cache `caminho → ID da pasta` por empresa: o Drive aceita pastas com o mesmo nome."""

    pasta_raiz_id = models.CharField(max_length=100)
    caminho = models.CharField(max_length=1000)
    pasta_id = models.CharField(max_length=100)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pasta do Drive"
        verbose_name_plural = "pastas do Drive"
        constraints = [
            models.UniqueConstraint(fields=["pasta_raiz_id", "caminho"], name="pasta_drive_unica")
        ]

    def __str__(self):
        return self.caminho


class ArquivoDrive(models.Model):
    """Cada arquivo copiado ao Drive (XML, PDF, XML de evento), com o `fileId` para sobrescrever."""

    class Situacao(models.TextChoices):
        """Andamento da cópia."""

        PENDENTE = "pendente", "Na fila"
        ENVIADO = "enviado", "Enviado"
        FALHOU = "falhou", "Falhou"

    nfse = models.ForeignKey("fiscal.Nfse", on_delete=models.PROTECT, related_name="arquivos_drive")
    papel = models.CharField(max_length=40, help_text="xml, pdf ou evento:<tipo>:<identificador>.")
    situacao = models.CharField(max_length=10, choices=Situacao, default=Situacao.PENDENTE)
    pasta_id = models.CharField(max_length=100, blank=True)
    caminho = models.CharField(max_length=1000, blank=True)
    nome = models.CharField(max_length=300, blank=True)
    file_id = models.CharField(max_length=100, blank=True)
    tentativas = models.PositiveIntegerField(default=0)
    proxima_tentativa = models.DateTimeField(null=True, blank=True, db_index=True)
    erro = models.TextField(blank=True)
    aviso = models.TextField(blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "arquivo no Drive"
        verbose_name_plural = "arquivos no Drive"
        ordering = ["nfse_id", "papel"]
        constraints = [
            models.UniqueConstraint(fields=["nfse", "papel"], name="arquivo_drive_unico")
        ]

    def __str__(self):
        return f"{self.papel} ({self.situacao})"


# --- Download em lote ---------------------------------------------------------------------


class Exportacao(models.Model):
    """Pedido de download em lote: o ZIP é gerado em segundo plano e expurgado depois."""

    class Situacao(models.TextChoices):
        """Andamento da exportação."""

        PENDENTE = "pendente", "Na fila"
        GERANDO = "gerando", "Gerando"
        PRONTA = "pronta", "Pronta para baixar"
        FALHOU = "falhou", "Falhou"
        EXPIRADA = "expirada", "Expirada"

    solicitante_id = models.PositiveBigIntegerField()
    solicitante_email = models.CharField(max_length=254, blank=True)
    filtros = models.JSONField(default=dict)
    situacao = models.CharField(max_length=10, choices=Situacao, default=Situacao.PENDENTE)
    total = models.PositiveIntegerField(default=0)
    processadas = models.PositiveIntegerField(default=0)
    tamanho_bytes = models.PositiveBigIntegerField(default=0)
    arquivo = models.CharField(
        max_length=300, blank=True, help_text="Nome do ZIP na pasta temporária."
    )
    nome_download = models.CharField(max_length=150, blank=True)
    erro = models.TextField(blank=True)
    avisos = models.JSONField(default=list, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    concluido_em = models.DateTimeField(null=True, blank=True)
    expira_em = models.DateTimeField(null=True, blank=True)
    baixado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "exportação"
        verbose_name_plural = "exportações"
        ordering = ["-criado_em", "-id"]

    def __str__(self):
        return f"Exportação {self.pk} ({self.situacao})"
