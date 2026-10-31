"""Modelos de NFS-e e agendamentos (Fase 5). Tudo vive no schema de cada empresa (D4).

- `ModeloNfse`: a nota "de referência" (tomador, serviço, valores, texto e e-mail). Gerar uma nota a
  partir dele **copia** os dados (snapshot): alterar o modelo depois nunca muda uma nota já criada.
- `Agendamento`: repete um modelo numa frequência e gera **rascunhos** (D12), nunca notas emitidas.
- `ExecucaoAgendamento`: o histórico, uma linha por data (`UNIQUE` com o agendamento: é a garantia
  de que uma data gera no máximo um rascunho).
- `OrigemNfse`: de que modelo e de que execução veio uma nota, com a cópia do e-mail.

O usuário vive no schema público: aqui só se guardam o id e o e-mail dele (GUIDELINES §1).
"""

from django.db import models
from django.db.models.functions import Lower

EMAIL_CAMPOS_BOOLEANOS = {
    "email_envio_automatico": "envio_automatico",
    "email_avisar_cancelamento": "avisar_cancelamento",
    "email_anexar_pdf": "anexar_pdf",
    "email_anexar_xml": "anexar_xml",
}


class ModeloNfse(models.Model):
    """Nota de referência da empresa: de onde saem os rascunhos manuais e agendados."""

    class Competencia(models.TextChoices):
        """Qual competência o rascunho recebe, em relação à data da execução."""

        MES_DA_EXECUCAO = "mes_da_execucao", "Mês da execução"
        MES_ANTERIOR = "mes_anterior", "Mês anterior ao da execução"

    nome = models.CharField(max_length=120)
    ativo = models.BooleanField(default=True)
    tomador = models.ForeignKey(
        "cadastros.Pessoa", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # O modelo aponta para uma versão do serviço; ao gerar, vale a versão **vigente na
    # competência** com os mesmos códigos de tributação (a vigência muda sem mexer no modelo).
    servico = models.ForeignKey(
        "cadastros.Servico", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    valores = models.JSONField(
        default=dict,
        blank=True,
        help_text="servico, desconto_incondicionado, desconto_condicionado, deducao_*.",
    )
    complementos = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "informacoes_complementares (aceita {competencia} {mes} {ano} {data_execucao}), "
            "percentual_total_tributos_simples."
        ),
    )
    competencia_padrao = models.CharField(
        max_length=20, choices=Competencia, default=Competencia.MES_DA_EXECUCAO
    )

    # Sobreposição da configuração de e-mail da empresa (D21). Vazio/nulo = herdar da empresa.
    email_envio_automatico = models.BooleanField(null=True, blank=True)
    email_avisar_cancelamento = models.BooleanField(null=True, blank=True)
    email_anexar_pdf = models.BooleanField(null=True, blank=True)
    email_anexar_xml = models.BooleanField(null=True, blank=True)
    email_assunto_modelo = models.CharField(max_length=200, blank=True)
    email_corpo_modelo = models.TextField(blank=True)
    email_copias_fixas = models.JSONField(null=True, blank=True)

    criado_por_id = models.PositiveBigIntegerField(null=True, blank=True)
    criado_por_email = models.CharField(max_length=254, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "modelo de NFS-e"
        verbose_name_plural = "modelos de NFS-e"
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(Lower("nome"), name="modelo_nfse_nome_unico")]

    def __str__(self):
        return self.nome

    def sobreposicao_de_email(self):
        """Só o que este modelo muda na configuração de e-mail (o resto é herdado da empresa)."""
        valores = {}
        for campo, chave in EMAIL_CAMPOS_BOOLEANOS.items():
            if getattr(self, campo) is not None:
                valores[chave] = getattr(self, campo)
        if self.email_assunto_modelo:
            valores["assunto_modelo"] = self.email_assunto_modelo
        if self.email_corpo_modelo:
            valores["corpo_modelo"] = self.email_corpo_modelo
        if self.email_copias_fixas is not None:
            valores["copias_fixas"] = list(self.email_copias_fixas)
        return valores


class Agendamento(models.Model):
    """Repete um modelo numa frequência e gera rascunhos para aprovação (D12, D13, D17)."""

    class Frequencia(models.TextChoices):
        """Como se repete."""

        UNICA = "unica", "Uma única vez"
        DIARIA = "diaria", "Diária"
        SEMANAL = "semanal", "Semanal"
        MENSAL = "mensal", "Mensal"
        ANUAL = "anual", "Anual"

    class Situacao(models.TextChoices):
        """Andamento do agendamento."""

        ATIVO = "ativo", "Ativo"
        SUSPENSO = "suspenso", "Suspenso"
        ENCERRADO = "encerrado", "Encerrado"

    nome = models.CharField(max_length=120)
    modelo = models.ForeignKey(ModeloNfse, on_delete=models.PROTECT, related_name="agendamentos")
    responsavel_id = models.PositiveBigIntegerField()
    responsavel_email = models.CharField(max_length=254)

    frequencia = models.CharField(max_length=10, choices=Frequencia)
    intervalo = models.PositiveIntegerField(default=1)
    dias_semana = models.JSONField(default=list, blank=True)
    dia_do_mes = models.PositiveSmallIntegerField(null=True, blank=True)
    mes = models.PositiveSmallIntegerField(null=True, blank=True)
    hora = models.TimeField(help_text="Hora de Brasília (America/Sao_Paulo).")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    max_execucoes = models.PositiveIntegerField(null=True, blank=True)

    situacao = models.CharField(max_length=10, choices=Situacao, default=Situacao.ATIVO)
    motivo_situacao = models.CharField(
        max_length=300, blank=True, help_text="Por que está suspenso ou encerrado."
    )
    execucoes_realizadas = models.PositiveIntegerField(default=0)
    proxima_execucao = models.DateTimeField(null=True, blank=True)

    criado_por_id = models.PositiveBigIntegerField(null=True, blank=True)
    criado_por_email = models.CharField(max_length=254, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "agendamento"
        verbose_name_plural = "agendamentos"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(Lower("nome"), name="agendamento_nome_unico"),
            models.CheckConstraint(
                condition=models.Q(data_fim__isnull=True) | models.Q(max_execucoes__isnull=True),
                name="agendamento_fim_ou_limite",
            ),
        ]
        indexes = [models.Index(fields=["situacao", "proxima_execucao"])]

    def __str__(self):
        return self.nome


class ExecucaoAgendamento(models.Model):
    """O que aconteceu em cada data de execução de um agendamento (o histórico)."""

    class Situacao(models.TextChoices):
        """Resultado da data."""

        PROCESSANDO = "processando", "Em andamento"
        GERADA = "gerada", "Rascunho gerado"
        FALHOU = "falhou", "Falhou"
        PERDIDA = "perdida", "Não executada (atraso)"
        SUSPENSA = "suspensa", "Não executada (agendamento suspenso)"

    agendamento = models.ForeignKey(Agendamento, on_delete=models.PROTECT, related_name="execucoes")
    data_execucao = models.DateField(help_text="Data (de Brasília) da ocorrência.")
    previsto_para = models.DateTimeField()
    situacao = models.CharField(
        max_length=12, choices=Situacao, default=Situacao.PROCESSANDO, db_index=True
    )
    erro = models.TextField(blank=True, help_text="Explicação em linguagem simples.")
    nfse = models.ForeignKey(
        "fiscal.Nfse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    concluido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "execução de agendamento"
        verbose_name_plural = "execuções de agendamento"
        ordering = ["-data_execucao", "-id"]
        constraints = [
            # Uma data, uma execução: é o que impede dois rascunhos da mesma ocorrência.
            models.UniqueConstraint(
                fields=["agendamento", "data_execucao"], name="execucao_unica_por_data"
            ),
        ]

    def __str__(self):
        return f"{self.agendamento_id} em {self.data_execucao} ({self.situacao})"


class OrigemNfse(models.Model):
    """De onde veio uma nota: o modelo, a execução e a cópia da sobreposição de e-mail.

    A cópia (`email`) é tirada quando o rascunho nasce: mudar o modelo depois não muda o e-mail de
    uma nota já criada, nem de uma emitida.
    """

    nfse = models.OneToOneField("fiscal.Nfse", on_delete=models.CASCADE, related_name="origem")
    modelo = models.ForeignKey(
        ModeloNfse, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    modelo_nome = models.CharField(max_length=120)
    execucao = models.OneToOneField(
        ExecucaoAgendamento, null=True, blank=True, on_delete=models.SET_NULL, related_name="origem"
    )
    email = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "origem da NFS-e"
        verbose_name_plural = "origens das NFS-e"

    def __str__(self):
        return f"{self.nfse_id} ← {self.modelo_nome}"
