"""Tabelas da persistência da freedfe (no schema de cada empresa).

Elas guardam o que a biblioteca precisa lembrar entre chamadas: o estado de cada DPS, a
evidência do que foi enviado e recebido, os XMLs das notas e dos eventos, o cache de parâmetros
municipais, o estado da sequência de NSU e a trilha técnica das chamadas. A parte de negócio
(situação da nota para o usuário, snapshots, permissões) fica em `Nfse`/`EventoNfse`.
"""

from django.db import models


class SerieDps(models.Model):
    """Uma linha por série de DPS: é o cadeado de `reservar_proximo`.

    `SELECT ... FOR UPDATE` nesta linha serializa a escolha do próximo número, inclusive
    quando a série ainda não tem nenhuma DPS (nada para travar na tabela de emissões).
    """

    serie = models.PositiveIntegerField(primary_key=True)

    class Meta:
        verbose_name = "série de DPS"
        verbose_name_plural = "séries de DPS"

    def __str__(self):
        return f"Série {self.serie}"


class EmissaoDps(models.Model):
    """Estado de uma DPS (identificada pelo Id de 45 posições), no formato da biblioteca."""

    class Situacao(models.TextChoices):
        """Mesmos valores de `freedfe.nfse.estado_emissao.SituacaoEmissao`."""

        PENDENTE = "pendente", "Reservada, nunca enviada"
        ENVIADA = "enviada", "Enviada, sem resultado"
        AUTORIZADA = "autorizada", "Autorizada"
        REJEITADA = "rejeitada", "Rejeitada"
        INCERTA = "incerta", "Resultado incerto"

    id_dps = models.CharField(max_length=45, unique=True)
    emitente = models.CharField(
        max_length=14, help_text="CNPJ/CPF do emitente, tirado do Id da DPS."
    )
    serie = models.PositiveIntegerField()
    numero = models.BigIntegerField()
    situacao = models.CharField(
        max_length=10, choices=Situacao, default=Situacao.PENDENTE, db_index=True
    )
    # `None` (e não texto vazio) é o valor "ainda não houve" do contrato da biblioteca.
    chave = models.CharField(max_length=50, null=True, blank=True)  # noqa: DJ001
    erros = models.JSONField(default=list, blank=True)
    motivo = models.TextField(null=True, blank=True)  # noqa: DJ001
    tentativas = models.PositiveIntegerField(default=0)
    caminho_dps = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    caminho_resposta = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    # Carimbos em ISO 8601, como a biblioteca os produz (comparados literalmente nos testes).
    ts_reserva = models.CharField(max_length=40, null=True, blank=True)  # noqa: DJ001
    ts_envio = models.CharField(max_length=40, null=True, blank=True)  # noqa: DJ001
    ts_resposta = models.CharField(max_length=40, null=True, blank=True)  # noqa: DJ001
    nfse = models.ForeignKey(
        "fiscal.Nfse",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="emissoes",
        help_text="Nota do freenfse a que esta DPS pertence (gravada junto com a reserva).",
    )

    class Meta:
        verbose_name = "emissão de DPS"
        verbose_name_plural = "emissões de DPS"
        ordering = ["serie", "numero", "id_dps"]
        constraints = [
            # Defesa em profundidade: mesmo sem o cadeado, o banco recusa número repetido.
            models.UniqueConstraint(
                fields=["emitente", "serie", "numero"], name="emissao_dps_numero_unico"
            )
        ]

    def __str__(self):
        return f"{self.id_dps} ({self.situacao})"


class EvidenciaFiscal(models.Model):
    """DPS enviada, respostas brutas e pedidos de evento, exatamente como trafegaram."""

    class Tipo(models.TextChoices):
        """Origem da evidência."""

        DPS = "dps", "DPS"
        EVENTO = "evento", "Evento"

    referencia = models.CharField(max_length=200, unique=True)
    tipo = models.CharField(max_length=6, choices=Tipo)
    id_dps = models.CharField(max_length=45, blank=True, db_index=True)
    chave = models.CharField(max_length=50, blank=True, db_index=True)
    tipo_evento = models.CharField(max_length=6, blank=True)
    mes = models.CharField(max_length=10)
    tentativa = models.PositiveIntegerField(default=0)
    sufixo = models.CharField(max_length=60)
    versao = models.PositiveIntegerField(
        default=1, help_text="Conteúdo diferente para a mesma tentativa vira nova versão."
    )
    conteudo = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evidência fiscal"
        verbose_name_plural = "evidências fiscais"
        ordering = ["id"]

    def __str__(self):
        return self.referencia


class DocumentoFiscal(models.Model):
    """NFS-e guardada como a Sefin devolveu (XML original, com o hash para conferência)."""

    modelo = models.CharField(max_length=10)
    chave = models.CharField(max_length=50)
    tipo_xml = models.CharField(max_length=30)
    xml_completo = models.BooleanField(default=True)
    resumo = models.JSONField(help_text="`ResumoDocumento.para_dict()` da biblioteca.")
    xml = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    nsu = models.CharField(max_length=15, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "documento fiscal"
        verbose_name_plural = "documentos fiscais"
        constraints = [
            models.UniqueConstraint(fields=["modelo", "chave"], name="documento_fiscal_unico")
        ]

    def __str__(self):
        return f"{self.modelo} {self.chave}"


class EventoFiscal(models.Model):
    """Evento de uma nota (cancelamento, substituição…), com o XML original."""

    modelo = models.CharField(max_length=10)
    chave = models.CharField(max_length=50, db_index=True)
    tipo_evento = models.CharField(max_length=6)
    identificador = models.CharField(max_length=80)
    resumo = models.JSONField(help_text="`EventoDocumento.para_dict()` da biblioteca.")
    xml = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    nsu = models.CharField(max_length=15, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evento fiscal"
        verbose_name_plural = "eventos fiscais"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["modelo", "chave", "tipo_evento", "identificador"],
                name="evento_fiscal_unico",
            )
        ]

    def __str__(self):
        return f"{self.tipo_evento} {self.chave}"


class NsuRecebido(models.Model):
    """NSU já recebidos por modelo de documento (detecção de lacunas)."""

    modelo = models.CharField(max_length=10)
    nsu = models.CharField(max_length=15)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["modelo", "nsu"], name="nsu_recebido_unico")]

    def __str__(self):
        return f"{self.modelo} NSU {self.nsu}"


class XmlNaoReconhecido(models.Model):
    """XML de tipo desconhecido: nada recebido pode ser perdido."""

    nsu = models.CharField(max_length=15, blank=True)
    esquema = models.CharField(max_length=120, blank=True)
    xml = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"XML não reconhecido {self.pk}"


class EstadoNsuFiscal(models.Model):
    """Estado da sequência de NSU por recurso (`nsu_nfse`, `nsu_nfse_<cnpj>`)."""

    recurso = models.CharField(max_length=80, unique=True)
    dados = models.JSONField(default=dict)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.recurso


class CacheParametroFiscal(models.Model):
    """Cache dos parâmetros municipais consultados ao ambiente nacional."""

    municipio = models.CharField(max_length=7)
    nome = models.CharField(max_length=120)
    consultado_em = models.DateTimeField()
    dados = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["municipio", "nome"], name="cache_parametro_unico")
        ]

    def __str__(self):
        return f"{self.municipio}/{self.nome}"


class AuditoriaFiscal(models.Model):
    """Trilha técnica das chamadas da biblioteca à Sefin. Nunca contém XML."""

    momento = models.DateTimeField(auto_now_add=True, db_index=True)
    servico = models.CharField(max_length=40, blank=True)
    operacao = models.CharField(max_length=60, blank=True)
    id_dps = models.CharField(max_length=45, blank=True, db_index=True)
    chave = models.CharField(max_length=50, blank=True, db_index=True)
    situacao = models.CharField(max_length=30, blank=True)
    dados = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "auditoria fiscal"
        verbose_name_plural = "auditoria fiscal"
        ordering = ["id"]

    def __str__(self):
        return f"{self.servico}/{self.operacao} ({self.situacao})"
