"""Serializers fiscais. O certificado é só de saída e nunca expõe o `.pfx` nem a senha."""

from django.utils import timezone
from rest_framework import serializers

from core.models import Municipio
from core.validators import formatar_cnpj
from fiscal.models import Certificado, ParametrosFiscais
from fiscal.services.vencimento import faixa_de


def _opcoes(escolhas):
    return [{"valor": valor, "rotulo": rotulo} for valor, rotulo in escolhas.choices]


class ParametrosFiscaisSerializer(serializers.Serializer):
    """Parâmetros fiscais (saída); a entrada é validada por `EntradaDeParametros`."""

    regime_tributario = serializers.CharField()
    regime_apuracao_simples = serializers.IntegerField(allow_null=True)
    regime_especial = serializers.IntegerField()
    serie_dps = serializers.IntegerField()
    ambiente = serializers.CharField()
    codigo_municipio_emissor = serializers.CharField()
    opcao_simples = serializers.IntegerField()
    municipio_emissor = serializers.SerializerMethodField()
    convenio = serializers.SerializerMethodField()
    atualizado_em = serializers.DateTimeField()

    def get_municipio_emissor(self, parametros):
        """Nome e UF do município emissor."""
        municipio = Municipio.objects.filter(codigo=parametros.codigo_municipio_emissor).first()
        return f"{municipio.nome}/{municipio.uf}" if municipio else ""

    def get_convenio(self, parametros):
        """Último resultado da verificação do convênio, com a data e se ainda vale."""
        if not parametros.convenio_verificado_em:
            return None
        return {
            # Em horário de Brasília (America/Sao_Paulo), como os demais campos de data e hora da
            # API: o instante é o mesmo, mas a data que o usuário lê não pula de dia às 21h.
            "verificado_em": timezone.localtime(parametros.convenio_verificado_em),
            "codigo_municipio": parametros.convenio_codigo_municipio,
            "ambiente": parametros.convenio_ambiente,
            "atual": parametros.convenio_atual,
            **parametros.convenio_resultado,
        }


class EntradaDeParametros(serializers.Serializer):
    """Campos editáveis dos parâmetros fiscais (todos opcionais: atualização parcial)."""

    regime_tributario = serializers.ChoiceField(
        choices=ParametrosFiscais.RegimeTributario.choices, required=False
    )
    regime_apuracao_simples = serializers.ChoiceField(
        choices=ParametrosFiscais.RegimeApuracaoSimples.choices, required=False, allow_null=True
    )
    regime_especial = serializers.ChoiceField(
        choices=ParametrosFiscais.RegimeEspecial.choices, required=False
    )
    serie_dps = serializers.IntegerField(min_value=1, max_value=99999, required=False)
    ambiente = serializers.ChoiceField(choices=ParametrosFiscais.Ambiente.choices, required=False)
    codigo_municipio_emissor = serializers.CharField(max_length=9, allow_blank=True, required=False)
    confirmar_producao = serializers.BooleanField(required=False, default=False)


def opcoes_de_parametros():
    """Listas de opções (valor e rótulo) para montar os campos de seleção da tela."""
    return {
        "regime_tributario": _opcoes(ParametrosFiscais.RegimeTributario),
        "regime_apuracao_simples": _opcoes(ParametrosFiscais.RegimeApuracaoSimples),
        "regime_especial": _opcoes(ParametrosFiscais.RegimeEspecial),
        "ambiente": _opcoes(ParametrosFiscais.Ambiente),
    }


class CertificadoSerializer(serializers.ModelSerializer):
    """Metadados do certificado. **Nunca** inclui `arquivo_pfx` nem `senha`."""

    cnpj_formatado = serializers.SerializerMethodField()
    dias_para_vencer = serializers.SerializerMethodField()
    vencido = serializers.SerializerMethodField()
    faixa_alerta = serializers.SerializerMethodField()

    class Meta:
        model = Certificado
        fields = [
            "titular",
            "cnpj_titular",
            "cnpj_formatado",
            "valido_de",
            "valido_ate",
            "dias_para_vencer",
            "vencido",
            "faixa_alerta",
            "impressao_digital",
            "mesma_raiz_autorizada",
            "enviado_por",
            "enviado_em",
        ]
        read_only_fields = fields

    def get_cnpj_formatado(self, certificado):
        """CNPJ do titular com pontuação."""
        return formatar_cnpj(certificado.cnpj_titular)

    def get_dias_para_vencer(self, certificado):
        """Dias até o vencimento (negativo se já venceu)."""
        return certificado.dias_para_vencer()

    def get_vencido(self, certificado):
        """Indica se o certificado já venceu."""
        return certificado.vencido()

    def get_faixa_alerta(self, certificado):
        """Faixa de alerta atual (30, 15, 7, 0 = vencido) ou `None`."""
        faixa = faixa_de(certificado.dias_para_vencer(), certificado.vencido())
        return None if faixa is None else int(faixa)
