"""Configuração fiscal da empresa (no schema de cada empresa)."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.fields import CampoBinarioCriptografado, CampoTextoCriptografado
from core.services import municipios


class _UnicoPorEmpresa(models.Model):
    """Base de modelos com uma única linha por empresa (o schema já isola as empresas)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """Fixa a chave primária em 1: só existe uma linha por schema."""
        self.pk = 1
        super().save(*args, **kwargs)


class ParametrosFiscais(_UnicoPorEmpresa):
    """Parâmetros fiscais da empresa (uma linha por empresa)."""

    class RegimeTributario(models.TextChoices):
        """Regime tributário; define a opção pelo Simples Nacional da DPS (`opSimpNac`)."""

        MEI = "mei", "Microempreendedor individual (MEI)"
        SIMPLES_NACIONAL = "simples_nacional", "Simples Nacional (ME ou EPP)"
        LUCRO_PRESUMIDO = "lucro_presumido", "Lucro presumido"
        LUCRO_REAL = "lucro_real", "Lucro real"
        OUTRO = "outro", "Outro (não optante pelo Simples)"

    class RegimeApuracaoSimples(models.IntegerChoices):
        """`regApTribSN`: como os tributos do Simples são apurados (exigido para ME/EPP)."""

        FEDERAIS_E_MUNICIPAL_PELO_SIMPLES = 1, "Tributos federais e municipal pelo Simples"
        FEDERAIS_PELO_SIMPLES_ISSQN_FORA = 2, "Federais pelo Simples e ISSQN fora do Simples"
        FEDERAIS_E_MUNICIPAL_FORA_DO_SIMPLES = 3, "Federais e municipal fora do Simples"

    class RegimeEspecial(models.IntegerChoices):
        """`regEspTrib`: regime especial de tributação do ISSQN."""

        NENHUM = 0, "Nenhum"
        ATO_COOPERADO = 1, "Ato cooperado (sociedade cooperativa)"
        ESTIMATIVA = 2, "Estimativa"
        MICROEMPRESA_MUNICIPAL = 3, "Microempresa municipal"
        NOTARIO_OU_REGISTRADOR = 4, "Notário ou registrador"
        PROFISSIONAL_AUTONOMO = 5, "Profissional autônomo"
        SOCIEDADE_DE_PROFISSIONAIS = 6, "Sociedade de profissionais"
        OUTROS = 9, "Outros"

    class Ambiente(models.TextChoices):
        """Ambiente de emissão. O padrão é a produção restrita (testes, sem valor fiscal)."""

        PRODUCAO_RESTRITA = "producao_restrita", "Produção restrita (testes)"
        PRODUCAO = "producao", "Produção (notas com valor fiscal)"

    regime_tributario = models.CharField(
        max_length=20, choices=RegimeTributario, default=RegimeTributario.OUTRO
    )
    regime_apuracao_simples = models.PositiveSmallIntegerField(
        choices=RegimeApuracaoSimples, null=True, blank=True
    )
    regime_especial = models.PositiveSmallIntegerField(
        choices=RegimeEspecial, default=RegimeEspecial.NENHUM
    )
    serie_dps = models.PositiveIntegerField(
        "série da DPS", default=1, help_text="De 1 a 99999. Não troque depois de emitir."
    )
    ambiente = models.CharField(max_length=20, choices=Ambiente, default=Ambiente.PRODUCAO_RESTRITA)
    codigo_municipio_emissor = models.CharField(
        "município emissor (código IBGE)", max_length=7, blank=True
    )

    # Último resultado da verificação do convênio do município (ver fiscal/services).
    convenio_verificado_em = models.DateTimeField(null=True, blank=True)
    convenio_codigo_municipio = models.CharField(max_length=7, blank=True)
    convenio_ambiente = models.CharField(max_length=20, blank=True)
    convenio_resultado = models.JSONField(default=dict, blank=True)

    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "parâmetros fiscais"
        verbose_name_plural = "parâmetros fiscais"
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="parametros_fiscais_unico_por_empresa")
        ]

    def __str__(self):
        return f"Parâmetros fiscais ({self.get_ambiente_display()})"

    @classmethod
    def obter(cls):
        """Devolve os parâmetros da empresa, criando-os com os padrões na primeira vez."""
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def opcao_simples(self):
        """Código `opSimpNac` da DPS, derivado do regime (1 não optante, 2 MEI, 3 ME/EPP)."""
        return {
            self.RegimeTributario.MEI: 2,
            self.RegimeTributario.SIMPLES_NACIONAL: 3,
        }.get(self.regime_tributario, 1)

    @property
    def convenio_atual(self):
        """O resultado do convênio só vale para o município e o ambiente em que foi verificado."""
        return bool(self.convenio_verificado_em) and (
            self.convenio_codigo_municipio == self.codigo_municipio_emissor
            and self.convenio_ambiente == self.ambiente
        )

    def clean(self):
        """Valida as combinações de regime, série e município."""
        erros = {}
        precisa_apuracao = self.regime_tributario == self.RegimeTributario.SIMPLES_NACIONAL
        if precisa_apuracao and self.regime_apuracao_simples is None:
            erros["regime_apuracao_simples"] = (
                "ME/EPP optante pelo Simples precisa informar como os tributos são apurados."
            )
        if not precisa_apuracao and self.regime_apuracao_simples is not None:
            erros["regime_apuracao_simples"] = (
                "Só se aplica a ME/EPP optante pelo Simples Nacional."
            )
        if not 1 <= int(self.serie_dps or 0) <= 99999:
            erros["serie_dps"] = "A série da DPS vai de 1 a 99999."
        self.codigo_municipio_emissor = "".join(
            c for c in (self.codigo_municipio_emissor or "") if c.isdigit()
        )
        if self.codigo_municipio_emissor:
            try:
                municipios.validar_codigo_ibge(self.codigo_municipio_emissor)
            except ValidationError as erro:
                erros["codigo_municipio_emissor"] = erro.messages[0]
        if erros:
            raise ValidationError(erros)


class Certificado(_UnicoPorEmpresa):
    """Certificado digital A1 da empresa. O `.pfx` e a senha ficam **cifrados** (AES-256-GCM).

    Os campos cifrados nunca saem pela API; só a leitura em memória pelo gateway fiscal os
    decifra. Os demais campos são metadados públicos do certificado.
    """

    arquivo_pfx = CampoBinarioCriptografado()
    senha = CampoTextoCriptografado()

    titular = models.CharField(max_length=500)
    cnpj_titular = models.CharField(max_length=14)
    valido_de = models.DateTimeField()
    valido_ate = models.DateTimeField()
    impressao_digital = models.CharField("SHA-256 do certificado", max_length=64)
    mesma_raiz_autorizada = models.BooleanField(
        default=False,
        help_text="O certificado é de outro estabelecimento (mesma raiz de CNPJ) e foi autorizado.",
    )
    enviado_por = models.EmailField(blank=True)
    enviado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "certificado A1"
        verbose_name_plural = "certificados A1"
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="certificado_unico_por_empresa")
        ]

    def __str__(self):
        return f"Certificado de {self.titular}"

    def __repr__(self):
        return f"<Certificado {self.impressao_digital[:12]}>"  # nunca o conteúdo nem a senha

    def dias_para_vencer(self, agora=None):
        """Dias inteiros até o vencimento (negativo se já venceu)."""
        return (self.valido_ate - (agora or timezone.now())).days

    def vencido(self, agora=None):
        """Indica se a validade já terminou."""
        return self.valido_ate < (agora or timezone.now())


class AlertaCertificado(models.Model):
    """Registro de um alerta de vencimento já gerado (garante um alerta por faixa)."""

    class Faixa(models.IntegerChoices):
        """Quantos dias faltavam; 0 = já venceu."""

        VENCIDO = 0, "Vencido"
        SETE_DIAS = 7, "7 dias ou menos"
        QUINZE_DIAS = 15, "15 dias ou menos"
        TRINTA_DIAS = 30, "30 dias ou menos"

    impressao_digital = models.CharField(max_length=64)
    faixa = models.PositiveSmallIntegerField(choices=Faixa)
    dias_restantes = models.IntegerField()
    valido_ate = models.DateTimeField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "alerta de vencimento do certificado"
        verbose_name_plural = "alertas de vencimento do certificado"
        ordering = ["-criado_em", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["impressao_digital", "faixa"], name="alerta_certificado_por_faixa"
            )
        ]

    def __str__(self):
        return f"Alerta {self.get_faixa_display()} ({self.impressao_digital[:12]})"


class LogoEmpresa(models.Model):
    """Logo da empresa, nas versões para o tema claro e escuro (a escura é opcional)."""

    class Tema(models.TextChoices):
        """Tema em que a versão é exibida."""

        CLARO = "claro", "Tema claro"
        ESCURO = "escuro", "Tema escuro"

    tema = models.CharField(max_length=6, choices=Tema, unique=True)
    tipo_conteudo = models.CharField(max_length=20)
    conteudo = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "logo da empresa"
        verbose_name_plural = "logos da empresa"
        ordering = ["tema"]

    def __str__(self):
        return f"Logo ({self.get_tema_display()})"


class TransicaoInvalida(Exception):
    """Mudança de situação da nota que a máquina de estados não permite."""


class Nfse(models.Model):
    """NFS-e do freenfse: do rascunho até a nota autorizada, cancelada ou substituída.

    A **situação** só muda por `fiscal.services.nfse_estados.transicionar`, que confere a
    tabela de transições e registra o histórico. Tomador, serviço e valores ficam como
    **snapshot** no momento da emissão: editar o cadastro depois nunca altera uma nota emitida.
    O XML da NFS-e é o original da Sefin, com o hash SHA-256 gravado ao autorizar.
    """

    class Direcao(models.TextChoices):
        """Só há notas emitidas por enquanto; as tomadas chegam com a sincronização pelo ADN."""

        EMITIDA = "emitida", "Emitida"

    class Situacao(models.TextChoices):
        """Situação da nota para o usuário."""

        RASCUNHO = "rascunho", "Rascunho"
        ENVIANDO = "enviando", "Enviando à Sefin"
        AUTORIZADA = "autorizada", "Autorizada"
        REJEITADA = "rejeitada", "Rejeitada"
        INCERTA = "incerta", "Resultado incerto (a conferir na Sefin)"
        CANCELADA = "cancelada", "Cancelada"
        SUBSTITUIDA = "substituida", "Substituída"

    direcao = models.CharField(max_length=10, choices=Direcao, default=Direcao.EMITIDA)
    situacao = models.CharField(
        max_length=12, choices=Situacao, default=Situacao.RASCUNHO, db_index=True
    )
    ambiente = models.CharField(
        max_length=20,
        choices=ParametrosFiscais.Ambiente,
        help_text="Ambiente em que a nota foi (ou será) emitida, fixado ao criar o rascunho.",
    )
    leiaute = models.CharField(
        max_length=20, blank=True, help_text="Leiaute usado no envio (NT 004 ou NT 009)."
    )

    # Identificação da DPS e da NFS-e.
    serie = models.PositiveIntegerField()
    numero_dps = models.BigIntegerField(null=True, blank=True)
    id_dps = models.CharField(max_length=45, null=True, blank=True, unique=True)
    chave = models.CharField(max_length=50, null=True, blank=True, unique=True)
    numero_nfse = models.CharField(max_length=15, blank=True)
    competencia = models.DateField()
    emitida_em = models.DateTimeField(null=True, blank=True)

    # Snapshots do momento da criação do rascunho (a fonte de verdade do que foi emitido).
    tomador = models.JSONField(default=dict)
    servico = models.JSONField(default=dict)
    valores = models.JSONField(default=dict)
    totais = models.JSONField(default=dict)
    tomador_nome = models.CharField(max_length=300, blank=True, db_index=True)
    tomador_documento = models.CharField(max_length=14, blank=True, db_index=True)
    valor_servico = models.DecimalField(max_digits=17, decimal_places=2)
    tomador_ref = models.ForeignKey(
        "cadastros.Pessoa", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    servico_ref = models.ForeignKey(
        "cadastros.Servico", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    xml_dps = models.BinaryField(null=True, blank=True)
    xml_nfse = models.BinaryField(null=True, blank=True)
    hash_xml_nfse = models.CharField(max_length=64, blank=True)

    erros = models.JSONField(default=list, blank=True)
    mensagem = models.TextField(blank=True)

    substitui = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="substitutas",
        help_text="Nota que esta substitui (só preenchida na nota substituta).",
    )
    substituicao_motivo = models.CharField(max_length=2, blank=True)
    substituicao_texto = models.CharField(max_length=255, blank=True)

    criado_por = models.ForeignKey(
        "core.Usuario", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    criado_por_email = models.CharField(max_length=254, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "NFS-e"
        verbose_name_plural = "NFS-e"
        ordering = ["-criado_em", "-id"]
        indexes = [models.Index(fields=["competencia"])]

    def __str__(self):
        return f"NFS-e {self.numero_nfse or self.numero_dps or 'rascunho'} ({self.situacao})"

    def __init__(self, *args, **kwargs):
        """Guarda a situação lida do banco para detectar mudança fora de `transicionar`."""
        super().__init__(*args, **kwargs)
        self._situacao_gravada = self.situacao

    def save(self, *args, **kwargs):
        """Recusa mudar a situação fora de `transicionar` (a única porta autorizada)."""
        existente = not self._state.adding
        if existente and self.situacao != self._situacao_gravada:
            if not self.__dict__.pop("_transicao_autorizada", False):
                raise TransicaoInvalida(
                    f"A situação da nota não pode ser alterada diretamente "
                    f"({self._situacao_gravada} → {self.situacao}). Use as ações da nota."
                )
        super().save(*args, **kwargs)
        self._situacao_gravada = self.situacao

    @property
    def editavel(self):
        """Só rascunho e nota rejeitada podem ser corrigidas e enviadas de novo."""
        return self.situacao in (self.Situacao.RASCUNHO, self.Situacao.REJEITADA)


class EventoNfse(models.Model):
    """Evento de uma nota confirmado pela Sefin (cancelamento, substituição…)."""

    class Tipo(models.TextChoices):
        """Eventos que o freenfse reconhece pelo nome."""

        CANCELAMENTO = "101101", "Cancelamento"
        CANCELAMENTO_POR_ANALISE = "105104", "Cancelamento deferido por análise fiscal"
        CANCELAMENTO_DE_OFICIO = "305101", "Cancelamento de ofício"
        SUBSTITUICAO = "105102", "Cancelamento por substituição"

    nfse = models.ForeignKey(Nfse, on_delete=models.CASCADE, related_name="eventos")
    tipo_evento = models.CharField(max_length=6)
    identificador = models.CharField(max_length=80, blank=True)
    descricao = models.CharField(max_length=255, blank=True)
    registrado_em = models.DateTimeField(null=True, blank=True)
    xml = models.BinaryField(null=True, blank=True)
    hash_xml = models.CharField(max_length=64, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evento da NFS-e"
        verbose_name_plural = "eventos da NFS-e"
        ordering = ["registrado_em", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["nfse", "tipo_evento", "identificador"], name="evento_nfse_unico"
            )
        ]

    def __str__(self):
        return f"{self.tipo_evento} da nota {self.nfse_id}"

    @property
    def rotulo(self):
        """Nome do evento em português, quando conhecido."""
        try:
            return self.Tipo(self.tipo_evento).label
        except ValueError:
            return f"Evento {self.tipo_evento}"


class TransicaoNfse(models.Model):
    """Histórico das mudanças de situação da nota (quem, quando, por quê)."""

    nfse = models.ForeignKey(Nfse, on_delete=models.CASCADE, related_name="transicoes")
    de = models.CharField(max_length=12)
    para = models.CharField(max_length=12)
    motivo = models.CharField(max_length=255, blank=True)
    usuario_email = models.CharField(max_length=254, blank=True)
    momento = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "transição da NFS-e"
        verbose_name_plural = "transições da NFS-e"
        ordering = ["id"]

    def __str__(self):
        return f"{self.de} → {self.para}"


# As tabelas da persistência da freedfe pertencem ao app fiscal e precisam ser importadas aqui
# para o Django conhecê-las.
from fiscal.persistencia import modelos as _modelos_da_persistencia  # noqa: E402,F401
