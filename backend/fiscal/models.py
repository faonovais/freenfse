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
