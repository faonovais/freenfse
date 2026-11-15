"""Serializers de cadastros. A validação de negócio fica nos modelos (`clean`)."""

from django.core.exceptions import ValidationError as ErroDjango
from rest_framework import serializers

from cadastros.models import PerfilPessoa, Pessoa, Servico, _apenas_digitos
from core.api.serializers import ServicoOficialResumoSerializer
from core.models import Municipio, ServicoOficial
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


CAMPOS_FISCAIS_TRAVADOS = (
    "codigo_tributacao_nacional",
    "nbs",
    "cst_ibs_cbs",
    "c_class_trib",
    "codigo_indicador_operacao",
)

CAMPOS_DO_SERVICO = (
    "nome", "descricao", "servico_oficial_id", "codigo_tributacao_nacional",
    "codigo_tributacao_municipal", "nbs", "cst_ibs_cbs", "c_class_trib",
    "codigo_indicador_operacao", "aliquota_iss", "iss_retido", "retencao_irrf",
    "retencao_csll", "retencao_pis", "retencao_cofins", "retencao_inss", "vigencia_inicio",
    "vigencia_fim", "ativo",
)  # fmt: skip


class ServicoSerializer(serializers.ModelSerializer):
    """Serviço com vigência e vínculo obrigatório a um serviço oficial da empresa."""

    servico_oficial_detalhes = serializers.SerializerMethodField()

    class Meta:
        model = Servico
        fields = [
            "id",
            *CAMPOS_DO_SERVICO,
            "servico_oficial_detalhes",
            "criado_em",
            "atualizado_em",
        ]
        read_only_fields = ["criado_em", "atualizado_em"]
        # Os códigos aceitam máscara (por exemplo, 17.01.01); o modelo normaliza para dígitos.
        extra_kwargs = {
            "servico_oficial_id": {"required": False, "allow_null": True},
            "codigo_tributacao_nacional": {
                "max_length": 12,
                "required": False,
                "allow_blank": True,
            },
            "codigo_tributacao_municipal": {
                "max_length": 6,
                "required": False,
                "allow_blank": True,
            },
            "nbs": {"max_length": 15, "required": False, "allow_blank": True},
            "cst_ibs_cbs": {"max_length": 5, "required": False, "allow_blank": True},
            "c_class_trib": {"max_length": 8, "required": False, "allow_blank": True},
            "codigo_indicador_operacao": {"max_length": 12, "required": False, "allow_blank": True},
        }

    def get_servico_oficial_detalhes(self, servico):
        """Resumo do serviço oficial vinculado, quando houver."""
        if not servico.servico_oficial_id:
            return None
        oficial = ServicoOficial.objects.filter(pk=servico.servico_oficial_id).first()
        return ServicoOficialResumoSerializer(oficial).data if oficial else None

    def validate(self, atributos):
        """Exige serviço oficial vinculado e trava os 5 campos fiscais oficiais."""
        servico_oficial_id = atributos.get(
            "servico_oficial_id",
            getattr(self.instance, "servico_oficial_id", None),
        )
        if not servico_oficial_id:
            raise serializers.ValidationError(
                {"servico_oficial_id": "Selecione um serviço oficial vinculado à empresa."}
            )

        request = self.context.get("request")
        empresa = getattr(request, "empresa", None)
        trocando_vinculo = (
            self.instance is None or servico_oficial_id != self.instance.servico_oficial_id
        )
        consulta = (
            empresa.servicos_oficiais.filter(pk=servico_oficial_id)
            if empresa is not None
            else ServicoOficial.objects.filter(pk=servico_oficial_id)
        )
        if trocando_vinculo:
            consulta = consulta.filter(ativo=True)
        oficial = consulta.first()
        if oficial is None:
            raise serializers.ValidationError(
                {
                    "servico_oficial_id": (
                        "O serviço oficial selecionado não está vinculado ou ativo para esta "
                        "empresa."
                    )
                }
            )

        entrada = self.initial_data if isinstance(self.initial_data, dict) else {}
        erros_trava = {}
        for campo in CAMPOS_FISCAIS_TRAVADOS:
            if campo not in entrada:
                continue
            valor_enviado = _apenas_digitos(entrada[campo])
            valor_oficial = getattr(oficial, campo)
            if self.instance is not None or valor_enviado:
                if valor_enviado != valor_oficial:
                    erros_trava[campo] = (
                        "Este campo é definido pelo serviço oficial vinculado e não pode ser "
                        "alterado diretamente."
                    )
        if erros_trava:
            raise serializers.ValidationError(erros_trava)

        atributos["servico_oficial_id"] = oficial.pk
        for campo in CAMPOS_FISCAIS_TRAVADOS:
            atributos[campo] = getattr(oficial, campo)

        candidato = _validar_candidato(Servico, self.instance, atributos, CAMPOS_DO_SERVICO)
        try:
            candidato.validar_vigencia()
        except ErroDjango as erro:
            raise serializers.ValidationError(erro.message_dict) from None
        return atributos
