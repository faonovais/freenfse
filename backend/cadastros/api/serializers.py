"""Serializers de cadastros. A validação de negócio fica nos modelos (`clean`)."""

from django.core.exceptions import ValidationError as ErroDjango
from rest_framework import serializers

from cadastros.models import PerfilPessoa, Pessoa, Servico
from core.models import Municipio
from core.validators import formatar_cnpj, formatar_cpf


def _validar_candidato(modelo, instancia, atributos, campos):
    """Monta o registro como ficaria após a gravação e roda `clean()`; devolve o candidato."""
    base = {campo: getattr(instancia, campo) for campo in campos} if instancia else {}
    base.update(atributos)
    candidato = modelo(**base)
    if instancia is not None:
        candidato.pk = instancia.pk
    try:
        candidato.clean()
    except ErroDjango as erro:
        raise serializers.ValidationError(erro.message_dict) from None
    return candidato


class PerfilPessoaSerializer(serializers.ModelSerializer):
    """Perfil de pessoa (cliente, fornecedor…)."""

    class Meta:
        model = PerfilPessoa
        fields = ["id", "codigo", "nome", "sistema", "ativo"]
        read_only_fields = ["sistema"]


class PessoaSerializer(serializers.ModelSerializer):
    """Pessoa; os perfis são informados pelo código (`cliente`, `fornecedor`…)."""

    # Aceita com pontuação (até 18 caracteres); o modelo normaliza para só dígitos/letras.
    documento = serializers.CharField(max_length=18, required=False, allow_blank=True)
    perfis = serializers.SlugRelatedField(
        many=True,
        slug_field="codigo",
        queryset=PerfilPessoa.objects.filter(ativo=True),
        required=False,
    )
    documento_formatado = serializers.SerializerMethodField()
    municipio_nome = serializers.SerializerMethodField()
    # Aceitam máscara; o modelo normaliza para só dígitos.
    cep = serializers.CharField(max_length=10, required=False, allow_blank=True)
    telefone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    CAMPOS_DO_MODELO = (
        "tipo", "documento", "nif", "motivo_sem_nif", "nome", "inscricao_municipal",
        "telefone", "emails_envio", "logradouro", "numero", "complemento", "bairro",
        "codigo_municipio", "cep", "pais", "codigo_postal", "cidade", "estado", "ativo",
    )  # fmt: skip

    class Meta:
        model = Pessoa
        fields = [
            "id", "tipo", "documento", "documento_formatado", "nif", "motivo_sem_nif", "nome",
            "inscricao_municipal", "telefone", "emails_envio", "logradouro", "numero",
            "complemento", "bairro", "codigo_municipio", "municipio_nome", "cep", "pais",
            "codigo_postal", "cidade", "estado", "perfis", "ativo", "criado_em", "atualizado_em",
        ]  # fmt: skip
        read_only_fields = ["criado_em", "atualizado_em"]
        extra_kwargs = {"motivo_sem_nif": {"required": False, "allow_null": True}}

    def get_documento_formatado(self, pessoa):
        """CPF ou CNPJ com pontuação."""
        if pessoa.tipo == Pessoa.Tipo.PESSOA_FISICA:
            return formatar_cpf(pessoa.documento)
        if pessoa.tipo == Pessoa.Tipo.PESSOA_JURIDICA:
            return formatar_cnpj(pessoa.documento)
        return ""

    def get_municipio_nome(self, pessoa):
        """Nome e UF do município do endereço."""
        municipio = Municipio.objects.filter(codigo=pessoa.codigo_municipio).first()
        return f"{municipio.nome}/{municipio.uf}" if municipio else ""

    def validate(self, atributos):
        """Valida as regras da pessoa e a unicidade do documento."""
        propostos = {k: v for k, v in atributos.items() if k in self.CAMPOS_DO_MODELO}
        candidato = _validar_candidato(Pessoa, self.instance, propostos, self.CAMPOS_DO_MODELO)
        if candidato.documento:
            repetidas = Pessoa.objects.filter(documento=candidato.documento)
            if self.instance is not None:
                repetidas = repetidas.exclude(pk=self.instance.pk)
            if repetidas.exists():
                raise serializers.ValidationError(
                    {"documento": "Já existe uma pessoa cadastrada com este documento."}
                )
        return atributos

    def create(self, dados):
        """Cria a pessoa já normalizada."""
        perfis = dados.pop("perfis", [])
        pessoa = Pessoa(**dados)
        pessoa.clean()
        pessoa.save()
        pessoa.perfis.set(perfis)
        return pessoa

    def update(self, pessoa, dados):
        """Altera a pessoa já normalizada."""
        perfis = dados.pop("perfis", None)
        for campo, valor in dados.items():
            setattr(pessoa, campo, valor)
        pessoa.clean()
        pessoa.save()
        if perfis is not None:
            pessoa.perfis.set(perfis)
        return pessoa


CAMPOS_DO_SERVICO = (
    "nome", "descricao", "codigo_tributacao_nacional", "codigo_tributacao_municipal", "nbs",
    "cst_ibs_cbs", "c_class_trib", "aliquota_iss", "iss_retido", "retencao_irrf",
    "retencao_csll", "retencao_pis", "retencao_cofins", "retencao_inss", "vigencia_inicio",
    "vigencia_fim", "ativo",
)  # fmt: skip


class ServicoSerializer(serializers.ModelSerializer):
    """Serviço com vigência."""

    class Meta:
        model = Servico
        fields = ["id", *CAMPOS_DO_SERVICO, "criado_em", "atualizado_em"]
        read_only_fields = ["criado_em", "atualizado_em"]
        # Os códigos aceitam máscara (por exemplo, 17.01.01); o modelo normaliza para dígitos.
        extra_kwargs = {
            "codigo_tributacao_nacional": {"max_length": 12},
            "codigo_tributacao_municipal": {
                "max_length": 6,
                "required": False,
                "allow_blank": True,
            },
            "nbs": {"max_length": 15, "required": False, "allow_blank": True},
            "cst_ibs_cbs": {"max_length": 5, "required": False, "allow_blank": True},
            "c_class_trib": {"max_length": 8, "required": False, "allow_blank": True},
        }

    def validate(self, atributos):
        """Valida as regras do serviço e antecipa a checagem de sobreposição de vigência."""
        candidato = _validar_candidato(Servico, self.instance, atributos, CAMPOS_DO_SERVICO)
        try:
            candidato.validar_vigencia()
        except ErroDjango as erro:
            raise serializers.ValidationError(erro.message_dict) from None
        return atributos
