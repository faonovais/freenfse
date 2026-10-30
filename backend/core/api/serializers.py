"""Serializers da API de administração (Master)."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ErroDjango
from rest_framework import serializers

from core.models import Empresa, Usuario, VinculoUsuarioEmpresa
from core.permissoes import catalogo
from core.services import acesso
from core.validators import normalizar_cnpj, validar_cnpj


class EmpresaSerializer(serializers.ModelSerializer):
    """Empresa (tenant). O CNPJ só é definido na criação."""

    cnpj_formatado = serializers.CharField(read_only=True)

    class Meta:
        model = Empresa
        fields = [
            "id",
            "razao_social",
            "cnpj",
            "cnpj_formatado",
            "schema_name",
            "ativo",
            "criado_em",
            "atualizado_em",
        ]
        read_only_fields = ["schema_name", "criado_em", "atualizado_em"]
        # Aceita o CNPJ com pontuação (18 caracteres); a normalização é feita em validate_cnpj.
        extra_kwargs = {"cnpj": {"validators": [], "max_length": 18}}

    def validate_cnpj(self, valor):
        """Normaliza, valida os dígitos e impede duplicidade e troca de CNPJ."""
        cnpj = normalizar_cnpj(valor)
        try:
            validar_cnpj(cnpj)
        except ErroDjango as erro:
            raise serializers.ValidationError(erro.messages) from None
        if self.instance is not None:
            if cnpj != self.instance.cnpj:
                raise serializers.ValidationError("O CNPJ de uma empresa não pode ser alterado.")
            return cnpj
        if Empresa.objects.filter(cnpj=cnpj).exists():
            raise serializers.ValidationError("Já existe uma empresa com este CNPJ.")
        return cnpj


class UsuarioSerializer(serializers.ModelSerializer):
    """Usuário. A senha é opcional (quem entra só por Google não precisa) e nunca é devolvida."""

    senha = serializers.CharField(
        write_only=True, required=False, allow_blank=False, trim_whitespace=False
    )
    mfa_ativo = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "email",
            "nome",
            "is_active",
            "is_master",
            "senha",
            "mfa_ativo",
            "criado_em",
            "atualizado_em",
        ]
        read_only_fields = ["criado_em", "atualizado_em"]
        extra_kwargs = {"email": {"validators": []}}

    def get_mfa_ativo(self, usuario):
        """Indica se o usuário já configurou o 2FA."""
        return acesso.usuario_tem_2fa(usuario)

    def validate_email(self, valor):
        """E-mail em minúsculas e único sem diferenciar maiúsculas."""
        email = valor.strip().lower()
        existentes = Usuario.objects.filter(email__iexact=email)
        if self.instance is not None:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise serializers.ValidationError("Já existe um usuário com este e-mail.")
        return email

    def validate_senha(self, valor):
        """Aplica as regras de senha do Django."""
        try:
            validate_password(valor, user=self.instance)
        except ErroDjango as erro:
            raise serializers.ValidationError(list(erro.messages)) from None
        return valor

    def validate(self, atributos):
        """Impede o Master de remover o próprio acesso (evita trancar o sistema)."""
        solicitante = self.context["request"].user
        if self.instance is not None and self.instance.pk == solicitante.pk:
            if atributos.get("is_active") is False:
                raise serializers.ValidationError(
                    {"is_active": "Você não pode desativar o próprio usuário."}
                )
            if atributos.get("is_master") is False:
                raise serializers.ValidationError(
                    {"is_master": "Você não pode remover o próprio papel Master."}
                )
        return atributos


class VinculoSerializer(serializers.ModelSerializer):
    """Vínculo usuário × empresa. Usuário e empresa só são definidos na criação."""

    usuario_email = serializers.CharField(source="usuario.email", read_only=True)
    empresa_razao_social = serializers.CharField(source="empresa.razao_social", read_only=True)
    empresa_cnpj = serializers.CharField(source="empresa.cnpj", read_only=True)
    criado_por_email = serializers.CharField(
        source="criado_por.email", read_only=True, default=None
    )
    permissoes_efetivas = serializers.SerializerMethodField()

    class Meta:
        model = VinculoUsuarioEmpresa
        fields = [
            "id",
            "usuario",
            "usuario_email",
            "empresa",
            "empresa_razao_social",
            "empresa_cnpj",
            "perfil",
            "permissoes_extras",
            "permissoes_removidas",
            "permissoes_efetivas",
            "ativo",
            "criado_por_email",
            "criado_em",
            "atualizado_em",
        ]
        read_only_fields = ["criado_em", "atualizado_em"]
        # A unicidade do par é verificada em `validate` (com mensagem em português).
        validators = []

    def get_permissoes_efetivas(self, vinculo):
        """Permissões que o usuário tem de fato nesta empresa."""
        return sorted(vinculo.permissoes_efetivas())

    def validate(self, atributos):
        """Impede trocar usuário/empresa, duplicar o par e usar permissões fora do catálogo."""
        if self.instance is not None:
            for campo in ("usuario", "empresa"):
                if campo in atributos and atributos[campo] != getattr(self.instance, campo):
                    raise serializers.ValidationError(
                        {campo: "Não pode ser alterado; crie outro vínculo."}
                    )
        else:
            if VinculoUsuarioEmpresa.objects.filter(
                usuario=atributos["usuario"], empresa=atributos["empresa"]
            ).exists():
                raise serializers.ValidationError("Este usuário já tem vínculo com esta empresa.")

        candidato = self.instance or VinculoUsuarioEmpresa()
        for campo in ("perfil", "permissoes_extras", "permissoes_removidas"):
            if campo in atributos:
                setattr(candidato, campo, atributos[campo])
        try:
            candidato.clean()
        except ErroDjango as erro:
            raise serializers.ValidationError(erro.message_dict) from None
        return atributos


def descrever_catalogo():
    """Catálogo de permissões como lista `{nome, descricao}` ordenada."""
    return [{"nome": nome, "descricao": desc} for nome, desc in sorted(catalogo().items())]
