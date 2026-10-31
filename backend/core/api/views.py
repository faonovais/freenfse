"""Views da API do app core."""

from django.conf import settings
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Empresa, Usuario, VinculoUsuarioEmpresa
from core.permissoes import PERFIL_MASTER, Perfil, permissoes_do_perfil
from core.services import acesso, empresas, usuarios, vinculos

from .permissions import PermissaoMaster
from .serializers import (
    EmpresaSerializer,
    UsuarioSerializer,
    VinculoSerializer,
    descrever_catalogo,
)


@api_view(["GET", "HEAD"])
@permission_classes([AllowAny])
def versao(request):
    """Retorna a versão da aplicação (conteúdo do arquivo VERSION)."""
    return Response({"versao": settings.VERSAO})


def _empresa_para_o_frontend(empresa, perfil, permissoes):
    return {
        "id": empresa.pk,
        "razao_social": empresa.razao_social,
        "cnpj": empresa.cnpj,
        "cnpj_formatado": empresa.cnpj_formatado,
        "perfil": perfil,
        "permissoes": sorted(permissoes),
    }


class EuView(APIView):
    """Quem sou eu: dados do usuário logado, política de 2FA e empresas que ele pode operar."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Devolve usuário, estado do 2FA e as empresas acessíveis com perfil e permissões."""
        usuario = request.user
        itens = []
        if usuario.is_master:
            todas = acesso.empresas_acessiveis(usuario)
            for empresa in todas:
                _, perfil, permissoes = acesso.acesso_a_empresa(usuario, empresa)
                itens.append(_empresa_para_o_frontend(empresa, perfil, permissoes))
        else:
            for vinculo in VinculoUsuarioEmpresa.objects.filter(
                usuario=usuario, ativo=True, empresa__ativo=True
            ).select_related("empresa"):
                itens.append(
                    _empresa_para_o_frontend(
                        vinculo.empresa, vinculo.perfil, vinculo.permissoes_efetivas()
                    )
                )
        return Response(
            {
                "id": usuario.pk,
                "email": usuario.email,
                "nome": usuario.nome,
                "is_master": usuario.is_master,
                "mfa": {
                    "ativo": acesso.usuario_tem_2fa(usuario),
                    "obrigatorio": acesso.exige_2fa(usuario),
                },
                "empresas": itens,
            }
        )


class EmpresaAtivaView(APIView):
    """Empresa ativa da requisição (cabeçalho X-Empresa) com o perfil e as permissões do usuário."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Confirma a empresa que o middleware ativou."""
        return Response(
            _empresa_para_o_frontend(request.empresa, request.perfil, request.permissoes)
        )


class _AdminGlobalViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Base da administração global: só o Master, sem exclusão (desative em vez de apagar)."""

    permission_classes = [PermissaoMaster]
    pagination_class = None


class EmpresaViewSet(_AdminGlobalViewSet):
    """Empresas (tenants)."""

    queryset = Empresa.objects.all()
    serializer_class = EmpresaSerializer

    def get_queryset(self):
        """Filtros opcionais: `busca` (razão social ou CNPJ) e `ativo`."""
        consulta = super().get_queryset()
        busca = self.request.query_params.get("busca", "").strip()
        if busca:
            consulta = consulta.filter(razao_social__icontains=busca) | consulta.filter(
                cnpj__icontains=busca.replace(".", "").replace("/", "").replace("-", "")
            )
        ativo = self.request.query_params.get("ativo")
        if ativo in ("true", "false"):
            consulta = consulta.filter(ativo=(ativo == "true"))
        return consulta.order_by("razao_social")

    def perform_create(self, serializer):
        """Cria a empresa e o schema dela."""
        serializer.instance = empresas.criar_empresa(
            request=self.request, **serializer.validated_data
        )

    def perform_update(self, serializer):
        """Altera a empresa."""
        serializer.instance = empresas.atualizar_empresa(
            serializer.instance, request=self.request, **serializer.validated_data
        )


class UsuarioViewSet(_AdminGlobalViewSet):
    """Usuários."""

    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer

    def get_queryset(self):
        """Filtro opcional `busca` (e-mail ou nome)."""
        consulta = super().get_queryset()
        busca = self.request.query_params.get("busca", "").strip()
        if busca:
            consulta = consulta.filter(email__icontains=busca) | consulta.filter(
                nome__icontains=busca
            )
        return consulta.order_by("email")

    def perform_create(self, serializer):
        """Cria o usuário."""
        serializer.instance = usuarios.criar_usuario(
            request=self.request, **serializer.validated_data
        )

    def perform_update(self, serializer):
        """Altera o usuário."""
        serializer.instance = usuarios.atualizar_usuario(
            serializer.instance, request=self.request, **serializer.validated_data
        )


class VinculoViewSet(_AdminGlobalViewSet):
    """Vínculos usuário × empresa."""

    queryset = VinculoUsuarioEmpresa.objects.select_related("usuario", "empresa", "criado_por")
    serializer_class = VinculoSerializer

    def get_queryset(self):
        """Filtros opcionais: `empresa`, `usuario` e `ativo`."""
        consulta = super().get_queryset()
        for parametro in ("empresa", "usuario"):
            valor = self.request.query_params.get(parametro, "")
            if valor.isdigit():
                consulta = consulta.filter(**{f"{parametro}_id": int(valor)})
        ativo = self.request.query_params.get("ativo")
        if ativo in ("true", "false"):
            consulta = consulta.filter(ativo=(ativo == "true"))
        return consulta

    def perform_create(self, serializer):
        """Concede o acesso."""
        serializer.instance = vinculos.criar_vinculo(
            request=self.request, **serializer.validated_data
        )

    def perform_update(self, serializer):
        """Altera perfil, permissões ou situação."""
        serializer.instance = vinculos.atualizar_vinculo(
            serializer.instance, request=self.request, **serializer.validated_data
        )


class PermissoesView(APIView):
    """Catálogo de permissões e permissões padrão de cada perfil (para a tela de vínculos)."""

    permission_classes = [PermissaoMaster]

    def get(self, request):
        """Lista o catálogo e os perfis."""
        return Response(
            {
                "permissoes": descrever_catalogo(),
                "perfis": [
                    {
                        "valor": perfil.value,
                        "rotulo": perfil.label,
                        "permissoes": sorted(permissoes_do_perfil(perfil.value)),
                    }
                    for perfil in Perfil
                ],
                "perfil_master": PERFIL_MASTER,
            }
        )
